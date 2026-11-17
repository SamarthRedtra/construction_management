"""Company-scoped stock movement reports for the Procurement workspace."""

import csv
from io import StringIO
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from construction_management.api.controlled_procurement import (
	ACCOUNT_ROLES, ADMIN_ROLES, CATALOG_ROLES, _active_company, _allowed_companies, _controlled_doc, _require,
)


INSIGHT_ROLES = CATALOG_ROLES
LEDGER_ROLES = ACCOUNT_ROLES | ADMIN_ROLES

INSIGHT_METRICS = (
	"ordered",
	"received",
	"consumed",
	"transferred_in",
	"transferred_out",
	"other",
	"on_hand",
)

INSIGHT_METRIC_META = {
	"ordered": {"label": "Ordered", "kind": "qty", "qty_kind": "qty", "value_kind": "amount"},
	"received": {"label": "Received", "kind": "qty", "qty_kind": "qty", "value_kind": "amount"},
	"consumed": {"label": "Consumed", "kind": "qty", "qty_kind": "qty", "value_kind": "amount"},
	"transferred_in": {"label": "Transfer in", "kind": "qty", "qty_kind": "qty", "value_kind": "amount"},
	"transferred_out": {"label": "Transfer out", "kind": "qty", "qty_kind": "qty", "value_kind": "amount"},
	"other": {"label": "Other", "kind": "qty", "qty_kind": "qty", "value_kind": "amount"},
	"on_hand": {"label": "On hand", "kind": "qty", "qty_kind": "qty", "value_kind": "amount"},
}

BREAKDOWN_LIMIT = 500

SLE_PROJECT_SCOPE_SQL = "coalesce(nullif(sle.project, ''), nullif(wh.custom_project, '')) = %(project)s"

# Stock Reconciliation rows store actual_qty = 0; their movement is the jump in qty_after_transaction.
QTY_CHANGE_SQL = """(case when sle.voucher_type = 'Stock Reconciliation'
	then sle.qty_after_transaction - coalesce((
		select prev.qty_after_transaction from `tabStock Ledger Entry` prev
		where prev.item_code = sle.item_code and prev.warehouse = sle.warehouse and prev.is_cancelled = 0
		and (prev.posting_datetime < sle.posting_datetime
			or (prev.posting_datetime = sle.posting_datetime and prev.creation < sle.creation))
		order by prev.posting_datetime desc, prev.creation desc limit 1), 0)
	else sle.actual_qty end)"""

# Procurement stock screens cover only controlled catalog items (disabled ones keep their history).
CATALOG_ITEM_SQL = """exists (select 1 from `tabItem` catalog_item
	where catalog_item.name = sle.item_code and catalog_item.controlled_procurement_catalog = 1)"""


def _company() -> str:
	company = _active_company()
	if not company or company not in _allowed_companies():
		frappe.throw(_("Select an accessible company."), frappe.PermissionError)
	return company


def _insight_project(project: str) -> tuple[str, str]:
	"""Shared company/project guard for insights screens."""
	_require(INSIGHT_ROLES)
	company = _company()
	if not project or frappe.db.get_value("Project", project, "company") != company:
		frappe.throw(_("Choose a project in the active company."), frappe.PermissionError)
	return company, project


def _empty_insight_row(item_code: str) -> dict:
	row = {"item_code": item_code}
	for metric in INSIGHT_METRICS:
		row[metric] = 0
		row[f"{metric}_value"] = 0
	return row


def _insight_summary(rows: list[dict]) -> dict:
	summary = {metric: {"qty": 0, "value": 0} for metric in INSIGHT_METRICS}
	for row in rows:
		for metric in INSIGHT_METRICS:
			summary[metric]["qty"] += flt(row.get(metric))
			summary[metric]["value"] += flt(row.get(f"{metric}_value"))
	for metric in INSIGHT_METRICS:
		summary[metric]["qty"] = flt(summary[metric]["qty"])
		summary[metric]["value"] = flt(summary[metric]["value"])
	return summary


def _insight_dates(from_date: str = "", to_date: str = "") -> tuple[str, str, bool]:
	"""Normalize insight date filters; empty both means all-time report semantics."""
	start = str(getdate(from_date)) if from_date else ""
	end = str(getdate(to_date)) if to_date else ""
	if start and end and getdate(start) > getdate(end):
		frappe.throw(_("From date must be on or before To date."))
	filtered = bool(start or end)
	if filtered and not end:
		end = str(today())
	return start, end, filtered


def _transaction_date_clause(alias: str, from_date: str, to_date: str) -> tuple[str, dict]:
	clauses = []
	params = {}
	if from_date:
		clauses.append(f"{alias}.transaction_date >= %(from_date)s")
		params["from_date"] = from_date
	if to_date:
		clauses.append(f"{alias}.transaction_date <= %(to_date)s")
		params["to_date"] = to_date
	return (" and ".join(clauses), params) if clauses else ("", {})


def _posting_date_clause(alias: str, from_date: str, to_date: str) -> tuple[str, dict]:
	clauses = []
	params = {}
	if from_date:
		clauses.append(f"{alias}.posting_date >= %(from_date)s")
		params["from_date"] = from_date
	if to_date:
		clauses.append(f"{alias}.posting_date <= %(to_date)s")
		params["to_date"] = to_date
	return (" and ".join(clauses), params) if clauses else ("", {})


def _apply_movement_metrics(
	item: dict,
	voucher_type: str,
	purpose: str | None,
	inbound: float,
	outbound: float,
	inbound_value: float,
	outbound_value: float,
	*,
	update_on_hand: bool = True,
) -> None:
	if update_on_hand:
		item["on_hand"] += inbound + outbound
		item["on_hand_value"] += inbound_value + outbound_value
	if voucher_type == "Purchase Receipt":
		item["received"] += inbound + outbound
		item["received_value"] += inbound_value + outbound_value
	elif voucher_type == "Stock Entry" and purpose == "Material Issue":
		item["consumed"] -= outbound + inbound
		item["consumed_value"] -= outbound_value + inbound_value
	elif voucher_type == "Stock Entry" and purpose == "Material Transfer":
		item["transferred_in"] += inbound
		item["transferred_out"] -= outbound
		item["transferred_in_value"] += inbound_value
		item["transferred_out_value"] -= outbound_value
	else:
		item["other"] += inbound + outbound
		item["other_value"] += inbound_value + outbound_value


def _attach_item_names(rows: list[dict]) -> None:
	if not rows:
		return
	item_codes = list({row["item_code"] for row in rows})
	name_by_code = {
		row.name: row.item_name for row in frappe.get_all(
			"Item", filters={"name": ["in", item_codes]}, fields=["name", "item_name"], limit_page_length=0,
		)
	}
	for row in rows:
		row["item_name"] = name_by_code.get(row["item_code"]) or row["item_code"]


def _desk_url(doctype: str, name: str) -> str:
	if not doctype or not name:
		return ""
	return f"/app/{doctype.lower().replace(' ', '-')}/{quote(name)}"


def _breakdown_kind(doctype: str, name: str) -> str | None:
	"""Return CP router kind when the voucher is visible in the Procurement workspace."""
	if not doctype or not name:
		return None
	if doctype == "Purchase Order" and not cint(frappe.db.get_value("Purchase Order", name, "is_subcontracted")):
		return "orders"
	if doctype == "Purchase Receipt" and not cint(frappe.db.get_value("Purchase Receipt", name, "is_subcontracted")):
		return "receipts"
	if doctype == "Stock Entry" and frappe.db.get_value("Stock Entry", name, "purpose") == "Material Transfer":
		return "transfers"
	return None


def _breakdown_row(
	doctype: str,
	name: str,
	posting_date,
	qty,
	amount=None,
	warehouse: str = "",
) -> dict:
	row = {
		"doctype": doctype,
		"name": name,
		"posting_date": posting_date,
		"qty": flt(qty),
		"warehouse": warehouse or "",
		"kind": _breakdown_kind(doctype, name),
		"desk_url": _desk_url(doctype, name),
	}
	if amount is not None:
		row["amount"] = flt(amount)
	return row


def _warehouse_scope_filters(company: str, project: str) -> tuple[str, dict]:
	"""SQL fragment and values limiting warehouses to a project (and optional site location)."""
	site_location = frappe.db.get_value("Project", project, "site_location") or ""
	clauses = ["wh.company = %(company)s", "wh.is_group = 0", "wh.disabled = 0"]
	if site_location:
		clauses.append("(wh.custom_project = %(project)s or wh.name = %(site_location)s)")
	else:
		clauses.append("wh.custom_project = %(project)s")
	return " and ".join(clauses), {"company": company, "project": project, "site_location": site_location}


@frappe.whitelist(methods=["GET"])
def get_insight_projects() -> dict:
	_require(INSIGHT_ROLES)
	company = _company()
	return {"rows": frappe.get_all("Project", filters={"company": company}, fields=["name", "project_name"], order_by="name desc", limit_page_length=0)}


def _ledger_scope(receipt: str, project: str, item_code: str, warehouse: str, from_date: str, to_date: str) -> tuple[str, str, dict]:
	"""Apply the same document, role, and company checks to screen and export."""
	company = _company()
	if receipt:
		grn = _controlled_doc("Purchase Receipt", receipt)
		if grn.company != company:
			frappe.throw(_("Receive Note belongs to another company."), frappe.PermissionError)
	else:
		_require(LEDGER_ROLES)
	if project and frappe.db.get_value("Project", project, "company") != company:
		frappe.throw(_("Project does not belong to the active company."), frappe.PermissionError)
	if warehouse and frappe.db.get_value("Warehouse", warehouse, "company") != company:
		frappe.throw(_("Warehouse does not belong to the active company."), frappe.PermissionError)
	conditions = ["sle.company = %(company)s", "sle.is_cancelled = 0", CATALOG_ITEM_SQL]
	params = {"company": company, "selected_project": project or ""}
	if project:
		project_warehouses = [row["value"] for row in _project_warehouses(company, project)]
		if not project_warehouses:
			conditions.append("1 = 0")
		else:
			conditions.append("sle.warehouse in %(project_warehouses)s")
			params["project_warehouses"] = project_warehouses
	filter_values = {"project": project, "item_code": item_code, "warehouse": warehouse, "from_date": from_date, "to_date": to_date}
	for key, column in (("project", "coalesce(nullif(sle.project, ''), nullif(wh.custom_project, ''))"), ("item_code", "sle.item_code"), ("warehouse", "sle.warehouse"), ("from_date", "sle.posting_date"), ("to_date", "sle.posting_date")):
		value = filter_values[key]
		if value:
			if key == "project":
				continue  # linked warehouse scope above is authoritative, including Project.site_location
			operator = ">=" if key == "from_date" else "<=" if key == "to_date" else "="
			conditions.append(f"{column} {operator} %({key})s")
			params[key] = value
	if receipt:
		conditions.append("sle.voucher_type = 'Purchase Receipt' and sle.voucher_no = %(receipt)s")
		params["receipt"] = receipt
	return company, " and ".join(conditions), params


def _ledger_rows(where: str, params: dict, limit: int, start: int = 0) -> list[dict]:
	rows = frappe.db.sql(f"""select sle.name, sle.posting_date, sle.posting_time, sle.item_code,
		sle.warehouse, coalesce(nullif(%(selected_project)s, ''), nullif(sle.project, ''), nullif(wh.custom_project, '')) as project,
		{QTY_CHANGE_SQL} as actual_qty, sle.qty_after_transaction,
		sle.stock_value_difference as movement_value, sle.stock_value as valuation_balance,
		sle.voucher_type, sle.voucher_no
		from `tabStock Ledger Entry` sle join `tabWarehouse` wh on wh.name = sle.warehouse where {where}
		order by sle.posting_date desc, sle.posting_time desc, sle.creation desc
		limit %(limit)s offset %(start)s""", {**params, "limit": limit, "start": start}, as_dict=True)
	for row in rows:
		qty = flt(row.actual_qty)
		row.in_qty = qty if qty > 0 else 0
		row.out_qty = -qty if qty < 0 else 0
	return rows


LEDGER_OPTION_FIELDS = {
	"project": ("coalesce(nullif(sle.project, ''), nullif(wh.custom_project, ''))", "coalesce(project.project_name, project.name)"),
	"item_code": ("sle.item_code", "coalesce(item.item_name, sle.item_code)"),
	"warehouse": ("sle.warehouse", "sle.warehouse"),
}


@frappe.whitelist(methods=["GET"])
def get_stock_ledger_options(field: str, search: str = "", receipt: str = "") -> list[dict]:
	"""Search company projects/warehouses and ledger items visible to this user."""
	if field not in LEDGER_OPTION_FIELDS:
		frappe.throw(_("Invalid stock-ledger filter."))
	company, where, params = _ledger_scope(receipt, "", "", "", "", "")
	search = (search or "").strip()[:100]
	if not receipt and field in {"project", "warehouse"}:
		doctype, label_field, filters = (
			("Project", "project_name", {"company": company}) if field == "project"
			else ("Warehouse", "warehouse_name", {"company": company, "is_group": 0, "disabled": 0})
		)
		search_fields = ["name", label_field]
		if field == "project" and frappe.get_meta("Project").has_field("custom_project_no"):
			search_fields.append("custom_project_no")
		rows = frappe.get_all(doctype, filters=filters,
			or_filters=[[name, "like", f"%{search}%"] for name in search_fields] if search else None,
			fields=["name", label_field], order_by="name asc", limit_page_length=20)
		return [{"value": row.name, "label": row.get(label_field) or row.name} for row in rows]
	value, label = LEDGER_OPTION_FIELDS[field]
	params["search"] = f"%{search}%"
	return frappe.db.sql(f"""select distinct {value} as value, {label} as label
		from `tabStock Ledger Entry` sle
		join `tabWarehouse` wh on wh.name = sle.warehouse
		left join `tabItem` item on item.name = sle.item_code
		left join `tabProject` project on project.name = coalesce(nullif(sle.project, ''), nullif(wh.custom_project, ''))
		where {where} and {value} is not null and {value} != ''
		and ({value} like %(search)s or {label} like %(search)s)
		order by value asc limit 20""", params, as_dict=True)


@frappe.whitelist(methods=["GET"])
def get_stock_ledger(receipt: str = "", project: str = "", item_code: str = "", warehouse: str = "", from_date: str = "", to_date: str = "", start: int = 0) -> dict:
	"""GRN viewers see only that voucher; unrestricted ledger search requires ledger access."""
	company, where, params = _ledger_scope(receipt, project, item_code, warehouse, from_date, to_date)
	page_length = 100
	start = max(cint(start), 0)
	total_count = cint(frappe.db.sql(
		f"""select count(*) from `tabStock Ledger Entry` sle
		join `tabWarehouse` wh on wh.name = sle.warehouse where {where}""",
		params,
	)[0][0])
	rows = _ledger_rows(where, params, page_length, start)
	return {
		"rows": rows,
		"has_more": start + len(rows) < total_count,
		"total_count": total_count,
		"page_length": page_length,
		"company": company,
		"receipt": receipt,
		"resolved_warehouses": _project_warehouses(company, project),
	}


def _project_warehouses(company: str, project: str) -> list[dict]:
	if not project:
		return []
	site_location = frappe.db.get_value("Project", project, "site_location") or ""
	filters = {"company": company, "is_group": 0, "disabled": 0}
	rows = frappe.get_all("Warehouse", filters=filters,
		or_filters=[["custom_project", "=", project], ["name", "=", site_location]] if site_location else [["custom_project", "=", project]],
		fields=["name", "warehouse_name"], order_by="name asc", limit_page_length=0)
	return [{"value": row.name, "label": row.warehouse_name or row.name} for row in rows]


@frappe.whitelist(methods=["GET"])
def get_project_warehouses(project: str) -> dict:
	"""Return the active warehouse scope automatically resolved for a project."""
	_require(LEDGER_ROLES)
	company = _company()
	if not project or frappe.db.get_value("Project", project, "company") != company:
		frappe.throw(_("Choose a project in the active company."), frappe.PermissionError)
	return {"company": company, "project": project, "warehouses": _project_warehouses(company, project)}


@frappe.whitelist(methods=["GET"])
def get_stock_balance(project: str = "", item_code: str = "", warehouse: str = "", from_date: str = "", to_date: str = "") -> dict:
	"""Aggregate ERPNext valuation movements for the same project/warehouse scope as the ledger."""
	company, where, params = _ledger_scope("", project, item_code, warehouse, "", to_date)
	period_where = "sle.posting_date <= %(to_date)s" if to_date else "1 = 1"
	opening_where = "sle.posting_date < %(from_date)s" if from_date else "0 = 1"
	movement_where = "sle.posting_date >= %(from_date)s" if from_date else "1 = 1"
	if to_date:
		movement_where += " and sle.posting_date <= %(to_date)s"
	rows = frappe.db.sql(f"""select m.item_code, max(item.item_name) as item_name, max(item.stock_uom) as stock_uom,
		sum(case when m.is_opening then m.qty else 0 end) as opening_qty,
		sum(case when m.is_opening then m.value else 0 end) as opening_value,
		sum(case when m.is_movement and m.qty > 0 then m.qty else 0 end) as in_qty,
		sum(case when m.is_movement and m.qty < 0 then -m.qty else 0 end) as out_qty,
		sum(case when m.is_movement and m.qty > 0 then m.value else 0 end) as in_value,
		sum(case when m.is_movement and m.qty < 0 then m.value else 0 end) as out_value,
		sum(case when m.in_period then m.qty else 0 end) as balance_qty,
		sum(case when m.in_period then m.value else 0 end) as balance_value
		from (
			select sle.item_code, {QTY_CHANGE_SQL} as qty, sle.stock_value_difference as value,
				({opening_where}) as is_opening, ({movement_where}) as is_movement, ({period_where}) as in_period
			from `tabStock Ledger Entry` sle
			join `tabWarehouse` wh on wh.name = sle.warehouse
			where {where}
		) m
		left join `tabItem` item on item.name = m.item_code
		group by m.item_code order by m.item_code asc""", {**params, "from_date": from_date, "to_date": to_date}, as_dict=True)
	return {"company": company, "project": project, "rows": rows,
		"resolved_warehouses": _project_warehouses(company, project)}


@frappe.whitelist(methods=["GET"])
def export_stock_balance(project: str = "", item_code: str = "", warehouse: str = "", from_date: str = "", to_date: str = "") -> None:
	"""Export exactly the aggregate rows shown by the Procurement Stock Balance screen."""
	report = get_stock_balance(project, item_code, warehouse, from_date, to_date)
	output = StringIO()
	writer = csv.writer(output)
	writer.writerow(["Company", "Project", "Item Code", "Item Name", "UOM", "Opening Qty", "Opening Value", "In Qty", "In Value", "Out Qty", "Out Value", "Balance Qty", "Balance Value"])
	for row in report["rows"]:
		writer.writerow([_csv_text(report["company"]), _csv_text(report["project"]), _csv_text(row.item_code), _csv_text(row.item_name), _csv_text(row.stock_uom),
			flt(row.opening_qty), flt(row.opening_value), flt(row.in_qty), flt(row.in_value), flt(row.out_qty), flt(row.out_value), flt(row.balance_qty), flt(row.balance_value)])
	frappe.response["filename"] = f"stock-balance-{frappe.utils.today()}.csv"
	frappe.response["filecontent"] = "\ufeff" + output.getvalue()
	frappe.response["type"] = "download"


def _csv_text(value) -> str:
	text = str(value or "")
	return "'" + text if text.startswith(("=", "+", "-", "@")) else text


@frappe.whitelist(methods=["GET"])
def export_stock_ledger(receipt: str = "", project: str = "", item_code: str = "", warehouse: str = "", from_date: str = "", to_date: str = "") -> None:
	"""Download all matching ledger rows (up to 50,000) with screen-equivalent access checks."""
	company, where, params = _ledger_scope(receipt, project, item_code, warehouse, from_date, to_date)
	rows = _ledger_rows(where, params, 50001)
	if len(rows) > 50000:
		frappe.throw(_("More than 50,000 ledger entries match. Narrow the filters before exporting."))
	output = StringIO()
	writer = csv.writer(output)
	writer.writerow(["Company", "Posting Date", "Posting Time", "Item Code", "Warehouse", "Project", "Voucher Type", "Voucher No", "In Qty", "Out Qty", "Movement Value", "Balance Qty", "Valuation Balance"])
	for row in rows:
		writer.writerow([_csv_text(company), row.posting_date, row.posting_time, _csv_text(row.item_code),
			_csv_text(row.warehouse), _csv_text(row.project), _csv_text(row.voucher_type), _csv_text(row.voucher_no),
			flt(row.in_qty), flt(row.out_qty), flt(row.movement_value), flt(row.qty_after_transaction), flt(row.valuation_balance)])
	frappe.response["filename"] = f"stock-ledger-{frappe.utils.today()}.csv"
	frappe.response["filecontent"] = "\ufeff" + output.getvalue()
	frappe.response["type"] = "download"


@frappe.whitelist(methods=["GET"])
def get_procurement_insights(project: str, from_date: str = "", to_date: str = "") -> dict:
	"""BuildSuite-style material status from current PO commitments and stock movements."""
	company, project = _insight_project(project)
	start, end, filtered = _insight_dates(from_date, to_date)
	po_date_clause, po_date_params = _transaction_date_clause("po", start, end if filtered else "")
	sle_period_clause, sle_period_params = _posting_date_clause("sle", start, end if filtered else "")

	ordered = frappe.db.sql(f"""select poi.item_code, sum(poi.qty) as qty, sum(poi.amount) as amount
		from `tabPurchase Order Item` poi join `tabPurchase Order` po on po.name = poi.parent
		join `tabItem` item on item.name = poi.item_code and item.is_stock_item = 1
		where po.company = %(company)s and po.docstatus = 1
		and coalesce(nullif(poi.project, ''), po.project) = %(project)s
		{"and " + po_date_clause if po_date_clause else ""}
		group by poi.item_code""", {"company": company, "project": project, **po_date_params}, as_dict=True)
	sle_where = f"sle.company = %(company)s and sle.is_cancelled = 0 and {SLE_PROJECT_SCOPE_SQL}"
	if sle_period_clause:
		sle_where += f" and {sle_period_clause}"
	movements = frappe.db.sql(f"""select sle.item_code, sle.voucher_type, se.purpose,
		sum(greatest({QTY_CHANGE_SQL}, 0)) as inbound,
		sum(least({QTY_CHANGE_SQL}, 0)) as outbound,
		sum(case when ({QTY_CHANGE_SQL}) > 0 then sle.stock_value_difference else 0 end) as inbound_value,
		sum(case when ({QTY_CHANGE_SQL}) < 0 then sle.stock_value_difference else 0 end) as outbound_value
		from `tabStock Ledger Entry` sle
		join `tabWarehouse` wh on wh.name = sle.warehouse
		left join `tabStock Entry` se on se.name = sle.voucher_no and sle.voucher_type = 'Stock Entry'
		where {sle_where}
		group by sle.item_code, sle.voucher_type, se.purpose""", {"company": company, "project": project, **sle_period_params}, as_dict=True)

	items: dict[str, dict] = {}
	for row in ordered:
		item = _empty_insight_row(row.item_code)
		item["ordered"] = flt(row.qty)
		item["ordered_value"] = flt(row.amount)
		items[row.item_code] = item

	for row in movements:
		item = items.setdefault(row.item_code, _empty_insight_row(row.item_code))
		movement_qty = flt(row.inbound), flt(row.outbound)
		movement_value = flt(row.inbound_value), flt(row.outbound_value)
		_apply_movement_metrics(
			item, row.voucher_type, row.purpose, *movement_qty, *movement_value,
			update_on_hand=not filtered,
		)

	if filtered:
		as_at = end or str(today())
		sle_as_at_clause, sle_as_at_params = _posting_date_clause("sle", "", as_at)
		for row in frappe.db.sql(
			f"""select sle.item_code,
				sum({QTY_CHANGE_SQL}) as qty,
				sum(sle.stock_value_difference) as value
			from `tabStock Ledger Entry` sle
			join `tabWarehouse` wh on wh.name = sle.warehouse
			where sle.company = %(company)s and sle.is_cancelled = 0
			and {SLE_PROJECT_SCOPE_SQL}
			and {sle_as_at_clause}
			group by sle.item_code""",
			{"company": company, "project": project, **sle_as_at_params},
			as_dict=True,
		):
			item = items.setdefault(row.item_code, _empty_insight_row(row.item_code))
			item["on_hand"] = flt(row.qty)
			item["on_hand_value"] = flt(row.value)
	else:
		wh_where, wh_params = _warehouse_scope_filters(company, project)
		for row in frappe.db.sql(
			f"""select bin.item_code, sum(bin.stock_value) as stock_value
			from `tabBin` bin
			join `tabWarehouse` wh on wh.name = bin.warehouse
			where {wh_where}
			group by bin.item_code""",
			wh_params,
			as_dict=True,
		):
			item = items.setdefault(row.item_code, _empty_insight_row(row.item_code))
			item["on_hand_value"] = flt(row.stock_value)

	rows = sorted(items.values(), key=lambda row: row["item_code"])
	_attach_item_names(rows)
	currency = frappe.get_cached_value("Company", company, "default_currency") or ""
	return {
		"company": company,
		"project": project,
		"from_date": start or None,
		"to_date": end if filtered else None,
		"filtered": filtered,
		"currency": currency,
		"metrics": INSIGHT_METRIC_META,
		"summary": _insight_summary(rows),
		"rows": rows,
	}


@frappe.whitelist(methods=["GET"])
def get_procurement_insight_breakdown(
	project: str, item_code: str, metric: str, from_date: str = "", to_date: str = "",
) -> dict:
	"""Line-level vouchers behind a single insights cell."""
	company, project = _insight_project(project)
	if metric not in INSIGHT_METRICS:
		frappe.throw(_("Invalid insight metric."))
	if not item_code or not frappe.db.exists("Item", item_code):
		frappe.throw(_("Choose a valid item."))

	start, end, filtered = _insight_dates(from_date, to_date)
	po_date_clause, po_date_params = _transaction_date_clause("po", start, end if filtered else "")
	sle_period_clause, sle_period_params = _posting_date_clause("sle", start, end if filtered else "")

	meta = INSIGHT_METRIC_META[metric]
	params = {"company": company, "project": project, "item_code": item_code}
	rows: list[dict] = []

	if metric == "ordered":
		for row in frappe.db.sql(
			f"""select po.name, po.transaction_date as posting_date, poi.qty, poi.amount, poi.warehouse
			from `tabPurchase Order Item` poi
			join `tabPurchase Order` po on po.name = poi.parent
			join `tabItem` item on item.name = poi.item_code and item.is_stock_item = 1
			where po.company = %(company)s and po.docstatus = 1
			and coalesce(nullif(poi.project, ''), po.project) = %(project)s
			and poi.item_code = %(item_code)s
			{"and " + po_date_clause if po_date_clause else ""}
			order by po.transaction_date desc, po.name desc
			limit %(limit)s""",
			{**params, **po_date_params, "limit": BREAKDOWN_LIMIT},
			as_dict=True,
		):
			rows.append(_breakdown_row("Purchase Order", row.name, row.posting_date, row.qty, row.amount, row.warehouse))

	elif metric == "on_hand":
		if filtered:
			as_at = end or str(today())
			sle_as_at_clause, sle_as_at_params = _posting_date_clause("sle", "", as_at)
			for row in frappe.db.sql(
				f"""select sle.warehouse, sum({QTY_CHANGE_SQL}) as qty
				from `tabStock Ledger Entry` sle
				join `tabWarehouse` wh on wh.name = sle.warehouse
				where sle.company = %(company)s and sle.is_cancelled = 0
				and sle.item_code = %(item_code)s and {SLE_PROJECT_SCOPE_SQL}
				and {sle_as_at_clause}
				group by sle.warehouse
				having abs(sum({QTY_CHANGE_SQL})) > 0.000001
				order by sle.warehouse asc
				limit %(limit)s""",
				{**params, **sle_as_at_params, "limit": BREAKDOWN_LIMIT},
				as_dict=True,
			):
				rows.append({
					"doctype": "",
					"name": "",
					"posting_date": as_at,
					"qty": flt(row.qty),
					"warehouse": row.warehouse,
					"kind": None,
					"desk_url": "",
				})
		else:
			wh_where, wh_params = _warehouse_scope_filters(company, project)
			for row in frappe.db.sql(
				f"""select bin.warehouse, bin.actual_qty as qty
				from `tabBin` bin
				join `tabWarehouse` wh on wh.name = bin.warehouse
				where bin.item_code = %(item_code)s and {wh_where}
				order by bin.warehouse asc
				limit %(limit)s""",
				{**params, **wh_params, "limit": BREAKDOWN_LIMIT},
				as_dict=True,
			):
				rows.append({
					"doctype": "",
					"name": "",
					"posting_date": None,
					"qty": flt(row.qty),
					"warehouse": row.warehouse,
					"kind": None,
					"desk_url": "",
				})

	else:
		sle_filters = {
			"received": "sle.voucher_type = 'Purchase Receipt'",
			"consumed": "sle.voucher_type = 'Stock Entry' and se.purpose = 'Material Issue'",
			"transferred_in": "sle.voucher_type = 'Stock Entry' and se.purpose = 'Material Transfer' and ({qty}) > 0".format(qty=QTY_CHANGE_SQL),
			"transferred_out": "sle.voucher_type = 'Stock Entry' and se.purpose = 'Material Transfer' and ({qty}) < 0".format(qty=QTY_CHANGE_SQL),
			"other": """not (
				sle.voucher_type = 'Purchase Receipt'
				or (sle.voucher_type = 'Stock Entry' and coalesce(se.purpose, '') in ('Material Issue', 'Material Transfer'))
			)""",
		}[metric]
		qty_sql = {
			"received": QTY_CHANGE_SQL,
			"consumed": f"-({QTY_CHANGE_SQL})",
			"transferred_in": QTY_CHANGE_SQL,
			"transferred_out": f"-({QTY_CHANGE_SQL})",
			"other": QTY_CHANGE_SQL,
		}[metric]
		for row in frappe.db.sql(
			f"""select sle.voucher_type, sle.voucher_no, sle.posting_date, sle.warehouse,
				{qty_sql} as qty, sle.stock_value_difference as amount
			from `tabStock Ledger Entry` sle
			join `tabWarehouse` wh on wh.name = sle.warehouse
			left join `tabStock Entry` se on se.name = sle.voucher_no and sle.voucher_type = 'Stock Entry'
			where sle.company = %(company)s and sle.is_cancelled = 0
			and sle.item_code = %(item_code)s and {SLE_PROJECT_SCOPE_SQL}
			and {sle_filters}
			{"and " + sle_period_clause if sle_period_clause else ""}
			order by sle.posting_date desc, sle.posting_time desc, sle.creation desc
			limit %(limit)s""",
			{**params, **sle_period_params, "limit": BREAKDOWN_LIMIT},
			as_dict=True,
		):
			doctype = row.voucher_type if row.voucher_type in ("Purchase Order", "Purchase Receipt", "Stock Entry") else row.voucher_type
			rows.append(_breakdown_row(doctype, row.voucher_no, row.posting_date, row.qty, row.amount, row.warehouse))

	return {
		"company": company,
		"project": project,
		"from_date": start or None,
		"to_date": end if filtered else None,
		"item_code": item_code,
		"metric": metric,
		"metric_meta": meta,
		"rows": rows,
	}
