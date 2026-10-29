"""Company-scoped stock movement reports for the Procurement workspace."""

import csv
from io import StringIO

import frappe
from frappe import _
from frappe.utils import cint, flt

from construction_management.api.controlled_procurement import (
	ACCOUNT_ROLES, ADMIN_ROLES, CATALOG_ROLES, _active_company, _allowed_companies, _controlled_doc, _require,
)


INSIGHT_ROLES = CATALOG_ROLES
LEDGER_ROLES = ACCOUNT_ROLES | ADMIN_ROLES

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
def get_procurement_insights(project: str) -> dict:
	"""BuildSuite-style material status from current PO commitments and stock movements."""
	_require(INSIGHT_ROLES)
	company = _company()
	if not project or frappe.db.get_value("Project", project, "company") != company:
		frappe.throw(_("Choose a project in the active company."), frappe.PermissionError)
	ordered = frappe.db.sql("""select poi.item_code, sum(poi.qty) as qty
		from `tabPurchase Order Item` poi join `tabPurchase Order` po on po.name = poi.parent
		join `tabItem` item on item.name = poi.item_code and item.is_stock_item = 1
		where po.company = %(company)s and po.docstatus = 1
		and coalesce(nullif(poi.project, ''), po.project) = %(project)s
		group by poi.item_code""", {"company": company, "project": project}, as_dict=True)
	movements = frappe.db.sql(f"""select sle.item_code, sle.voucher_type, se.purpose,
		sum(greatest({QTY_CHANGE_SQL}, 0)) as inbound,
		sum(least({QTY_CHANGE_SQL}, 0)) as outbound
		from `tabStock Ledger Entry` sle
		join `tabWarehouse` wh on wh.name = sle.warehouse
		left join `tabStock Entry` se on se.name = sle.voucher_no and sle.voucher_type = 'Stock Entry'
		where sle.company = %(company)s and sle.is_cancelled = 0
		and coalesce(nullif(sle.project, ''), nullif(wh.custom_project, '')) = %(project)s
		group by sle.item_code, sle.voucher_type, se.purpose""", {"company": company, "project": project}, as_dict=True)
	items = {row.item_code: {"item_code": row.item_code, "ordered": flt(row.qty), "received": 0, "consumed": 0, "transferred_in": 0, "transferred_out": 0, "other": 0, "on_hand": 0} for row in ordered}
	for row in movements:
		item = items.setdefault(row.item_code, {"item_code": row.item_code, "ordered": 0, "received": 0, "consumed": 0, "transferred_in": 0, "transferred_out": 0, "other": 0, "on_hand": 0})
		inbound, outbound = flt(row.inbound), flt(row.outbound)
		item["on_hand"] += inbound + outbound
		if row.voucher_type == "Purchase Receipt":
			item["received"] += inbound + outbound
		elif row.voucher_type == "Stock Entry" and row.purpose == "Material Issue":
			item["consumed"] -= outbound + inbound
		elif row.voucher_type == "Stock Entry" and row.purpose == "Material Transfer":
			item["transferred_in"] += inbound
			item["transferred_out"] -= outbound
		else:
			item["other"] += inbound + outbound
	return {"company": company, "project": project, "rows": sorted(items.values(), key=lambda row: row["item_code"])}
