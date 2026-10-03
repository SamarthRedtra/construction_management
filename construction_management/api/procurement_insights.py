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
	conditions = ["sle.company = %(company)s", "sle.is_cancelled = 0"]
	params = {"company": company}
	filter_values = {"project": project, "item_code": item_code, "warehouse": warehouse, "from_date": from_date, "to_date": to_date}
	for key, column in (("project", "coalesce(nullif(sle.project, ''), nullif(wh.custom_project, ''))"), ("item_code", "sle.item_code"), ("warehouse", "sle.warehouse"), ("from_date", "sle.posting_date"), ("to_date", "sle.posting_date")):
		value = filter_values[key]
		if value:
			operator = ">=" if key == "from_date" else "<=" if key == "to_date" else "="
			conditions.append(f"{column} {operator} %({key})s")
			params[key] = value
	if receipt:
		conditions.append("sle.voucher_type = 'Purchase Receipt' and sle.voucher_no = %(receipt)s")
		params["receipt"] = receipt
	return company, " and ".join(conditions), params


def _ledger_rows(where: str, params: dict, limit: int, start: int = 0) -> list[dict]:
	return frappe.db.sql(f"""select sle.name, sle.posting_date, sle.posting_time, sle.item_code,
		sle.warehouse, coalesce(nullif(sle.project, ''), nullif(wh.custom_project, '')) as project,
		sle.actual_qty, sle.qty_after_transaction,
		sle.voucher_type, sle.voucher_no
		from `tabStock Ledger Entry` sle join `tabWarehouse` wh on wh.name = sle.warehouse where {where}
		order by sle.posting_date desc, sle.posting_time desc, sle.creation desc
		limit %(limit)s offset %(start)s""", {**params, "limit": limit, "start": start}, as_dict=True)


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
	rows = _ledger_rows(where, params, 101, max(cint(start), 0))
	return {"rows": rows[:100], "has_more": len(rows) > 100, "company": company, "receipt": receipt}


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
	writer.writerow(["Company", "Posting Date", "Posting Time", "Item Code", "Warehouse", "Project", "Voucher Type", "Voucher No", "Movement Qty", "Balance Qty"])
	for row in rows:
		writer.writerow([_csv_text(company), row.posting_date, row.posting_time, _csv_text(row.item_code),
			_csv_text(row.warehouse), _csv_text(row.project), _csv_text(row.voucher_type), _csv_text(row.voucher_no),
			flt(row.actual_qty), flt(row.qty_after_transaction)])
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
	movements = frappe.db.sql("""select sle.item_code, sle.voucher_type, se.purpose,
		sum(case when sle.actual_qty > 0 then sle.actual_qty else 0 end) as inbound,
		sum(case when sle.actual_qty < 0 then sle.actual_qty else 0 end) as outbound
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
