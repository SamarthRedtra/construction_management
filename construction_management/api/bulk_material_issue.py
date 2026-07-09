# Copyright (c) 2026, Construction Management
# License: MIT

import json

import frappe
from frappe import _
from frappe.utils import flt, get_last_day, getdate

SOURCE_PURCHASE_RECEIPT = "Purchase Receipt"
SOURCE_STOCK_ENTRY = "Stock Entry"
MATERIAL_TRANSFER_TYPE = "Material Transfer"
MATERIAL_ISSUE_TYPE = "Material Issue"

POSTING_DATE_SAME = "Same as Source Document"
POSTING_DATE_END_OF_MONTH = "End of Month"


def _get_source_posting_date(source_doctype, source_name):
	if not source_doctype or not source_name:
		frappe.throw(_("Source document is required to determine posting date"))

	if not frappe.db.exists(source_doctype, source_name):
		frappe.throw(_("{0} {1} not found").format(source_doctype, source_name))

	posting_date = frappe.db.get_value(source_doctype, source_name, "posting_date")
	if not posting_date:
		frappe.throw(_("Posting date not found for {0} {1}").format(source_doctype, source_name))

	return getdate(posting_date)


def get_boq_bulk_issue_settings(company):
	return frappe.db.get_value(
		"BOQ Settings",
		company,
		[
			"bulk_material_issue_posting_date_rule",
			"bulk_material_issue_default_stock_entry_type",
			"default_warehouse",
		],
		as_dict=True,
	) or {}


def get_bulk_material_issue_posting_date(
	company,
	source_posting_date,
	posting_date_override=None,
):
	if posting_date_override:
		return getdate(posting_date_override)

	if not source_posting_date:
		frappe.throw(_("Source posting date is required to compute Material Issue posting date"))

	source_posting_date = getdate(source_posting_date)
	settings = get_boq_bulk_issue_settings(company)
	rule = settings.get("bulk_material_issue_posting_date_rule") or POSTING_DATE_SAME

	if rule == POSTING_DATE_END_OF_MONTH:
		return get_last_day(source_posting_date)

	return source_posting_date


def _issued_qty_field_available(parent_doctype):
	return frappe.db.has_column(parent_doctype, "custom_material_issued_qty")


def get_issued_qty(parent_doctype, row_name):
	if not row_name or not _issued_qty_field_available(parent_doctype):
		return 0
	return flt(frappe.db.get_value(parent_doctype, row_name, "custom_material_issued_qty"))


def append_issue_stock_entry_link(parent_doctype, row_name, stock_entry_name):
	if not row_name or not stock_entry_name:
		return

	if parent_doctype == "Purchase Receipt Item" and frappe.db.has_column(
		"Purchase Receipt Item", "custom_material_issue_stock_entries"
	):
		current = frappe.db.get_value(
			"Purchase Receipt Item", row_name, "custom_material_issue_stock_entries"
		) or ""
		entries = [entry.strip() for entry in current.split(",") if entry.strip()]
		if stock_entry_name not in entries:
			entries.append(stock_entry_name)
			frappe.db.set_value(
				"Purchase Receipt Item",
				row_name,
				"custom_material_issue_stock_entries",
				", ".join(entries),
				update_modified=False,
			)


def increment_issued_qty(parent_doctype, row_name, qty):
	if not row_name or qty <= 0 or not _issued_qty_field_available(parent_doctype):
		return

	current = get_issued_qty(parent_doctype, row_name)
	frappe.db.set_value(
		parent_doctype,
		row_name,
		"custom_material_issued_qty",
		flt(current + qty),
		update_modified=False,
	)


def decrement_issued_qty(parent_doctype, row_name, qty):
	if not row_name or qty <= 0 or not _issued_qty_field_available(parent_doctype):
		return

	current = get_issued_qty(parent_doctype, row_name)
	frappe.db.set_value(
		parent_doctype,
		row_name,
		"custom_material_issued_qty",
		max(0, flt(current - qty)),
		update_modified=False,
	)


def get_available_stock(warehouse, item_code):
	if not warehouse or not item_code:
		return 0

	return flt(
		frappe.db.get_value(
			"Bin",
			{"warehouse": warehouse, "item_code": item_code},
			"actual_qty",
		)
	)


def _get_project_warehouses(project, company=None):
	if not project:
		return []

	warehouses = []
	site_location = frappe.db.get_value("Project", project, "site_location")
	if site_location:
		warehouses.append(site_location)

	filters = {}
	if frappe.db.has_column("Warehouse", "custom_project"):
		filters["custom_project"] = project
	elif frappe.db.has_column("Warehouse", "project"):
		filters["project"] = project
	else:
		return warehouses

	if filters:
		for row in frappe.get_all(
			"Warehouse",
			filters=filters,
			fields=["name", "company"],
		):
			if company and row.company and row.company != company:
				continue
			if row.name not in warehouses:
				warehouses.append(row.name)

	return warehouses


def _resolve_pr_item_warehouse(pr_item, pr_doc, boq_settings, item_code=None):
	item_code = item_code or pr_item.get("item_code")
	candidates = []

	if pr_item.get("warehouse"):
		candidates.append(pr_item.get("warehouse"))

	project = pr_item.get("project") or pr_doc.get("project")
	if project:
		candidates.extend(_get_project_warehouses(project, pr_doc.company))

	default_wh = boq_settings.get("default_warehouse")
	if default_wh and default_wh not in candidates:
		candidates.append(default_wh)

	# Prefer the first candidate that already has stock, otherwise keep PR warehouse.
	best_wh = None
	best_available = 0
	for warehouse in candidates:
		available = get_available_stock(warehouse, item_code)
		if available > best_available:
			best_available = available
			best_wh = warehouse

	if best_wh:
		return best_wh

	return candidates[0] if candidates else None


def _apply_stock_cap(row, available_pool=None):
	remaining_qty = flt(row.get("remaining_qty") or row.get("qty_to_issue"))
	warehouse = row.get("warehouse")
	item_code = row.get("item_code")

	if available_pool is not None:
		pool_key = (warehouse, item_code)
		available_qty = flt(available_pool.get(pool_key, get_available_stock(warehouse, item_code)))
	else:
		available_qty = get_available_stock(warehouse, item_code)
		pool_key = (warehouse, item_code)

	qty_to_issue = min(remaining_qty, available_qty) if available_qty > 0 else 0

	row["remaining_qty"] = remaining_qty
	row["available_qty"] = available_qty
	row["qty_to_issue"] = qty_to_issue
	row["stock_limited"] = 1 if qty_to_issue < remaining_qty else 0

	if available_pool is not None:
		available_pool[pool_key] = max(0, available_qty - qty_to_issue)

	return row


def _allocate_stock_across_rows(rows):
	available_pool = {}
	allocated_rows = []

	for row in rows:
		warehouse = row.get("warehouse")
		item_code = row.get("item_code")
		pool_key = (warehouse, item_code)
		if pool_key not in available_pool:
			available_pool[pool_key] = get_available_stock(warehouse, item_code)

		allocated_rows.append(_apply_stock_cap(row, available_pool))

	return allocated_rows


def _finalize_eligible_rows(rows, hide_zero_stock=True):
	rows = _allocate_stock_across_rows(rows)
	if hide_zero_stock:
		rows = [row for row in rows if flt(row.get("available_qty")) > 0]
	return rows


def _get_material_transfer_rows(filters, selected_sources=None):
	conditions = [
		"se.docstatus = 1",
		"se.stock_entry_type = %(stock_entry_type)s",
	]
	values = {"stock_entry_type": MATERIAL_TRANSFER_TYPE}

	if filters.get("company"):
		conditions.append("se.company = %(company)s")
		values["company"] = filters["company"]

	if filters.get("from_date"):
		conditions.append("se.posting_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("se.posting_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	if filters.get("project"):
		conditions.append("(se.project = %(project)s OR sed.project = %(project)s)")
		values["project"] = filters["project"]

	if selected_sources:
		conditions.append("se.name in %(selected_sources)s")
		values["selected_sources"] = tuple(selected_sources)

	rows = frappe.db.sql(
		f"""
		SELECT
			se.name AS source_name,
			'{SOURCE_STOCK_ENTRY}' AS source_doctype,
			se.posting_date AS source_posting_date,
			se.company,
			sed.name AS source_line_name,
			sed.item_code,
			sed.t_warehouse AS warehouse,
			sed.qty AS source_qty,
			IFNULL(sed.custom_material_issued_qty, 0) AS issued_qty,
			sed.project,
			sed.boq_item,
			sed.bill_no
		FROM `tabStock Entry` se
		INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
		WHERE {" AND ".join(conditions)}
			AND sed.t_warehouse IS NOT NULL
			AND sed.qty > IFNULL(sed.custom_material_issued_qty, 0)
		ORDER BY se.posting_date ASC, se.name ASC, sed.idx ASC
		""",
		values,
		as_dict=True,
	)

	result = []
	for row in rows:
		qty_to_issue = flt(row.source_qty) - flt(row.issued_qty)
		if qty_to_issue <= 0:
			continue

		result.append(
			{
				"source_doctype": SOURCE_STOCK_ENTRY,
				"source_name": row.source_name,
				"source_posting_date": row.source_posting_date,
				"source_line_name": row.source_line_name,
				"company": row.company,
				"item_code": row.item_code,
				"warehouse": row.warehouse,
				"remaining_qty": qty_to_issue,
				"project": row.project,
				"boq_item": row.get("boq_item"),
				"bill_no": row.get("bill_no"),
				"posting_date": get_bulk_material_issue_posting_date(
					row.company, row.source_posting_date, filters.get("posting_date_override")
				),
			}
		)

	return result


def _get_purchase_receipt_rows(filters, selected_sources=None):
	conditions = [
		"pr.docstatus = 1",
	]
	values = {}

	if filters.get("company"):
		conditions.append("pr.company = %(company)s")
		values["company"] = filters["company"]

	if filters.get("from_date"):
		conditions.append("pr.posting_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("pr.posting_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	if filters.get("project"):
		conditions.append("(pr.project = %(project)s OR pri.project = %(project)s)")
		values["project"] = filters["project"]

	if selected_sources:
		conditions.append("pr.name in %(selected_sources)s")
		values["selected_sources"] = tuple(selected_sources)

	issued_qty_select = (
		"IFNULL(pri.custom_material_issued_qty, 0)"
		if frappe.db.has_column("Purchase Receipt Item", "custom_material_issued_qty")
		else "0"
	)

	rows = frappe.db.sql(
		f"""
		SELECT
			pr.name AS source_name,
			'{SOURCE_PURCHASE_RECEIPT}' AS source_doctype,
			pr.posting_date AS source_posting_date,
			pr.company,
			pri.name AS source_line_name,
			pri.item_code,
			pri.warehouse,
			pri.received_qty AS source_qty,
			{issued_qty_select} AS issued_qty,
			IFNULL(pri.project, pr.project) AS project,
			pri.boq_item,
			IFNULL(pri.bill_no, pr.bill_no) AS bill_no
		FROM `tabPurchase Receipt` pr
		INNER JOIN `tabPurchase Receipt Item` pri ON pri.parent = pr.name
		INNER JOIN `tabItem` item ON item.name = pri.item_code
		WHERE {" AND ".join(conditions)}
			AND item.is_stock_item = 1
			AND pri.received_qty > {issued_qty_select}
		ORDER BY pr.posting_date ASC, pr.name ASC, pri.idx ASC
		""",
		values,
		as_dict=True,
	)

	boq_settings_cache = {}
	result = []
	for row in rows:
		qty_to_issue = flt(row.source_qty) - flt(row.issued_qty)
		if qty_to_issue <= 0:
			continue

		if row.company not in boq_settings_cache:
			boq_settings_cache[row.company] = get_boq_bulk_issue_settings(row.company)

		pr_doc = frappe.get_cached_doc(SOURCE_PURCHASE_RECEIPT, row.source_name)
		pr_item = next(
			(item for item in pr_doc.items if item.name == row.source_line_name),
			None,
		)
		warehouse = _resolve_pr_item_warehouse(
			pr_item or row,
			pr_doc,
			boq_settings_cache[row.company],
			item_code=row.item_code,
		)
		if not warehouse:
			continue

		result.append(
			{
				"source_doctype": SOURCE_PURCHASE_RECEIPT,
				"source_name": row.source_name,
				"source_posting_date": row.source_posting_date,
				"source_line_name": row.source_line_name,
				"company": row.company,
				"item_code": row.item_code,
				"warehouse": warehouse,
				"remaining_qty": qty_to_issue,
				"project": row.project,
				"boq_item": row.get("boq_item"),
				"bill_no": row.get("bill_no"),
				"posting_date": get_bulk_material_issue_posting_date(
					row.company, row.source_posting_date, filters.get("posting_date_override")
				),
			}
		)

	return result


def _normalize_selected_sources(selected_sources, source_type):
	if not selected_sources:
		return None, None

	if isinstance(selected_sources, str):
		selected_sources = json.loads(selected_sources)

	selected_mt = []
	selected_pr = []
	for row in selected_sources:
		if isinstance(row, dict):
			doctype = row.get("doctype")
			name = row.get("name")
		else:
			name = row
			if source_type == "Purchase Receipt":
				doctype = SOURCE_PURCHASE_RECEIPT
			elif source_type == "Material Transfer":
				doctype = SOURCE_STOCK_ENTRY
			elif frappe.db.exists(SOURCE_PURCHASE_RECEIPT, name):
				doctype = SOURCE_PURCHASE_RECEIPT
			elif frappe.db.exists(SOURCE_STOCK_ENTRY, name):
				doctype = SOURCE_STOCK_ENTRY
			else:
				continue

		if doctype == SOURCE_STOCK_ENTRY:
			selected_mt.append(name)
		elif doctype == SOURCE_PURCHASE_RECEIPT:
			selected_pr.append(name)

	return (selected_mt or None), (selected_pr or None)


@frappe.whitelist()
def get_eligible_sources(
	company,
	source_type="Both",
	project=None,
	from_date=None,
	to_date=None,
	posting_date_override=None,
	selected_sources=None,
	hide_zero_stock=1,
):
	if not company:
		frappe.throw(_("Company is mandatory"))

	filters = {
		"company": company,
		"project": project,
		"from_date": from_date,
		"to_date": to_date,
		"posting_date_override": posting_date_override,
		"hide_zero_stock": int(hide_zero_stock),
	}

	selected_mt, selected_pr = _normalize_selected_sources(selected_sources, source_type)

	rows = []
	if source_type in ("Material Transfer", "Both"):
		rows.extend(_get_material_transfer_rows(filters, selected_mt))

	if source_type in ("Purchase Receipt", "Both"):
		rows.extend(_get_purchase_receipt_rows(filters, selected_pr))

	return _finalize_eligible_rows(rows, hide_zero_stock=bool(int(hide_zero_stock or 0)))


def _get_source_line_context(source_doctype, source_line_name):
	if source_doctype == SOURCE_PURCHASE_RECEIPT:
		row = frappe.db.get_value(
			"Purchase Receipt Item",
			source_line_name,
			["received_qty", "parent"],
			as_dict=True,
		)
		if not row:
			frappe.throw(_("Purchase Receipt Item {0} not found").format(source_line_name))
		return "Purchase Receipt Item", flt(row.received_qty), row.parent

	if source_doctype == SOURCE_STOCK_ENTRY:
		row = frappe.db.get_value(
			"Stock Entry Detail",
			source_line_name,
			["qty", "parent"],
			as_dict=True,
		)
		if not row:
			frappe.throw(_("Stock Entry Detail {0} not found").format(source_line_name))
		return "Stock Entry Detail", flt(row.qty), row.parent

	frappe.throw(_("Unsupported source doctype {0}").format(source_doctype))


def _validate_issue_qty(source_doctype, source_line_name, qty):
	parent_doctype, source_qty, _source_name = _get_source_line_context(
		source_doctype, source_line_name
	)
	remaining = source_qty - get_issued_qty(parent_doctype, source_line_name)
	if qty > remaining:
		frappe.throw(
			_("Cannot issue {0} for source line {1}. Remaining issuable quantity is {2}").format(
				qty, source_line_name, remaining
			)
		)


def _validate_stock_availability(warehouse, item_code, qty):
	available = get_available_stock(warehouse, item_code)
	if available < qty:
		frappe.throw(
			_("Insufficient stock for item {0} in warehouse {1}. Available: {2}, Required: {3}").format(
				item_code, warehouse, available, qty
			)
		)


def _group_rows_by_source(rows):
	grouped = {}
	for row in rows:
		key = (row["source_doctype"], row["source_name"])
		grouped.setdefault(key, []).append(row)
	return grouped


def _create_material_issue_for_source(source_rows, submit=True, posting_date_override=None):
	if not source_rows:
		return None

	first = source_rows[0]
	company = first["company"]
	settings = get_boq_bulk_issue_settings(company)
	stock_entry_type = settings.get("bulk_material_issue_default_stock_entry_type") or MATERIAL_ISSUE_TYPE
	source_posting_date = _get_source_posting_date(first["source_doctype"], first["source_name"])
	posting_date = get_bulk_material_issue_posting_date(
		company,
		source_posting_date,
		posting_date_override,
	)

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = stock_entry_type
	se.company = company
	se.posting_date = posting_date
	se.set_posting_time = 1
	se.project = first.get("project")

	if se.meta.has_field("custom_bulk_issue_source_doctype"):
		se.custom_bulk_issue_source_doctype = first["source_doctype"]
	if se.meta.has_field("custom_bulk_issue_source_name"):
		se.custom_bulk_issue_source_name = first["source_name"]

	for row in source_rows:
		qty = flt(row.get("qty_to_issue") or row.get("qty"))
		if qty <= 0:
			continue

		source_line = row.get("source_line_name")
		if source_line:
			_validate_issue_qty(first["source_doctype"], source_line, qty)

		_validate_stock_availability(row["warehouse"], row["item_code"], qty)

		item_row = {
			"item_code": row["item_code"],
			"qty": qty,
			"s_warehouse": row["warehouse"],
			"project": row.get("project"),
		}

		if frappe.get_meta("Stock Entry Detail").has_field("boq_item") and row.get("boq_item"):
			item_row["boq_item"] = row["boq_item"]
		if frappe.get_meta("Stock Entry Detail").has_field("bill_no") and row.get("bill_no"):
			item_row["bill_no"] = row["bill_no"]
		if frappe.get_meta("Stock Entry Detail").has_field("custom_bulk_issue_source_line"):
			item_row["custom_bulk_issue_source_line"] = row.get("source_line_name")

		se.append("items", item_row)

	if not se.items:
		return None

	se.insert()
	if submit:
		se.submit()

	for row in source_rows:
		qty = flt(row.get("qty_to_issue") or row.get("qty"))
		source_line = row.get("source_line_name")
		if row["source_doctype"] == SOURCE_PURCHASE_RECEIPT:
			increment_issued_qty("Purchase Receipt Item", source_line, qty)
			append_issue_stock_entry_link("Purchase Receipt Item", source_line, se.name)
		elif row["source_doctype"] == SOURCE_STOCK_ENTRY:
			increment_issued_qty("Stock Entry Detail", source_line, qty)

	return se


@frappe.whitelist()
def create_material_issues(rows, submit=1, posting_date_override=None):
	if isinstance(rows, str):
		rows = json.loads(rows)

	if not rows:
		frappe.throw(_("No rows selected for material issue"))

	submit = int(submit)
	results = []
	grouped = _group_rows_by_source(rows)

	for (source_doctype, source_name), source_rows in grouped.items():
		savepoint = f"bulk_issue_{frappe.generate_hash(length=8)}"
		frappe.db.savepoint(savepoint)
		try:
			stock_entry = _create_material_issue_for_source(
				source_rows,
				submit=submit,
				posting_date_override=posting_date_override,
			)
			results.append(
				{
					"source_doctype": source_doctype,
					"source_name": source_name,
					"status": "Success",
					"stock_entry": stock_entry.name if stock_entry else "",
					"posting_date": str(stock_entry.posting_date) if stock_entry else "",
					"error_message": "",
				}
			)
		except Exception as exc:
			frappe.db.rollback(save_point=savepoint)
			results.append(
				{
					"source_doctype": source_doctype,
					"source_name": source_name,
					"status": "Failed",
					"stock_entry": "",
					"error_message": str(exc).split("\n")[0],
				}
			)

	return results


def reverse_bulk_material_issue(stock_entry_doc):
	if stock_entry_doc.docstatus != 2:
		return

	if not stock_entry_doc.meta.has_field("custom_bulk_issue_source_doctype"):
		return

	source_doctype = stock_entry_doc.get("custom_bulk_issue_source_doctype")
	if not source_doctype:
		return

	for item in stock_entry_doc.items:
		qty = flt(item.qty)
		source_line = item.get("custom_bulk_issue_source_line")
		if not source_line:
			continue

		if source_doctype == SOURCE_PURCHASE_RECEIPT:
			decrement_issued_qty("Purchase Receipt Item", source_line, qty)
		elif source_doctype == SOURCE_STOCK_ENTRY:
			decrement_issued_qty("Stock Entry Detail", source_line, qty)
