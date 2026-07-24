# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt

DEDUCTION_ITEM_CODES = {"RETENTION-DEDUCTION", "ADVANCE-DEDUCTION"}


@frappe.whitelist()
def get_warehouse_project(warehouse, company=None):
	"""
	Get the linked project for a warehouse.
	
	Args:
		warehouse: Warehouse name
		company: Optional company to validate the project against
		
	Returns:
		Project name if linked, else None
	"""
	if not warehouse:
		return None

	fields = ["custom_project"]

	# Some sites may not have a standard `project` field on Warehouse; check before querying
	if frappe.db.has_column("Warehouse", "project"):
		fields.append("project")

	project_data = frappe.db.get_value(
		"Warehouse",
		warehouse,
		fields,
		as_dict=True,
	)

	if not project_data:
		return None

	# Prefer the custom link, fallback to the standard project field
	project = project_data.get("custom_project") or project_data.get("project")

	if project and company:
		project_company = frappe.db.get_value("Project", project, "company")
		if project_company and project_company != company:
			# Ignore projects belonging to another company
			return None

	return project


@frappe.whitelist()
def get_project_warehouse(project):
	"""
	Get a warehouse linked to the given project (prefers custom_project link, falls back to standard project field).
	Returns the first matching warehouse name.
	"""
	if not project:
		return None

	warehouse = frappe.db.get_value("Warehouse", {"custom_project": project}, "name")

	if not warehouse and frappe.db.has_column("Warehouse", "project"):
		warehouse = frappe.db.get_value("Warehouse", {"project": project}, "name")

	return warehouse


def get_linked_purchase_order(doc):
	purchase_order = doc.get("custom_purchase_order")
	if purchase_order:
		return purchase_order

	for item in doc.get("items") or []:
		if item.get("purchase_order"):
			return item.purchase_order

	return None


def is_subcontractor_purchase(doc, purchase_order=None):
	if doc.get("custom_suppliersubcontractor") == "Subcontractor":
		return True

	purchase_order = purchase_order or get_linked_purchase_order(doc)
	if not purchase_order:
		return False

	return (
		frappe.db.get_value("Purchase Order", purchase_order, "custom_suppliersubcontractor")
		== "Subcontractor"
	)


def get_purchase_party_type(voucher_type: str | None = None, voucher_no: str | None = None, doc=None) -> str:
	"""
	Resolve Supplier vs Subcontractor for a purchase voucher.

	Returns ``\"Subcontractor\"`` or ``\"Supplier\"`` (blank / missing defaults to Supplier).
	"""
	flag = None

	if doc is not None:
		flag = doc.get("custom_suppliersubcontractor")
		if flag not in ("Supplier", "Subcontractor"):
			po = get_linked_purchase_order(doc)
			if po:
				flag = frappe.db.get_value("Purchase Order", po, "custom_suppliersubcontractor")
		return "Subcontractor" if flag == "Subcontractor" else "Supplier"

	if not voucher_type or not voucher_no:
		return "Supplier"

	if voucher_type == "Purchase Invoice":
		flag = frappe.db.get_value("Purchase Invoice", voucher_no, "custom_suppliersubcontractor")
		if flag not in ("Supplier", "Subcontractor"):
			po = frappe.db.sql(
				"""
				SELECT purchase_order FROM `tabPurchase Invoice Item`
				WHERE parent = %s AND IFNULL(purchase_order, '') != ''
				LIMIT 1
				""",
				voucher_no,
			)
			po = po[0][0] if po else None
			if not po and frappe.db.has_column("Purchase Invoice", "custom_purchase_order"):
				po = frappe.db.get_value("Purchase Invoice", voucher_no, "custom_purchase_order")
			if po:
				flag = frappe.db.get_value("Purchase Order", po, "custom_suppliersubcontractor")
	elif voucher_type == "Purchase Receipt":
		flag = frappe.db.get_value("Purchase Receipt", voucher_no, "custom_suppliersubcontractor")
		if flag not in ("Supplier", "Subcontractor"):
			po = frappe.db.sql(
				"""
				SELECT purchase_order FROM `tabPurchase Receipt Item`
				WHERE parent = %s AND IFNULL(purchase_order, '') != ''
				LIMIT 1
				""",
				voucher_no,
			)
			po = po[0][0] if po else None
			if not po and frappe.db.has_column("Purchase Receipt", "custom_purchase_order"):
				po = frappe.db.get_value("Purchase Receipt", voucher_no, "custom_purchase_order")
			if po:
				flag = frappe.db.get_value("Purchase Order", po, "custom_suppliersubcontractor")
	elif voucher_type == "Purchase Order":
		flag = frappe.db.get_value("Purchase Order", voucher_no, "custom_suppliersubcontractor")

	return "Subcontractor" if flag == "Subcontractor" else "Supplier"


def get_purchase_cost_category(voucher_type: str | None, voucher_no: str | None, doc=None) -> str:
	"""Map purchase party type to project/BOQ cost bucket: material | subcontractor."""
	party = get_purchase_party_type(voucher_type=voucher_type, voucher_no=voucher_no, doc=doc)
	return "subcontractor" if party == "Subcontractor" else "material"


def get_purchase_cost_category_sql(pi_alias: str = "pi", pii_alias: str = "pii") -> str:
	"""
	SQL expression returning 'Subcontractor' or 'Supplier' for a PI join.

	Uses PI.custom_suppliersubcontractor, else linked PO via item, else 'Supplier'.
	"""
	return f"""COALESCE(
		NULLIF({pi_alias}.custom_suppliersubcontractor, ''),
		(
			SELECT po.custom_suppliersubcontractor
			FROM `tabPurchase Order` po
			WHERE po.name = {pii_alias}.purchase_order
			LIMIT 1
		),
		'Supplier'
	)"""


def get_purchase_deduction_percentages(doc, po_doc):
	"""Use PO retention/advance % only. Project defaults must not override explicit PO values."""
	return (
		flt(po_doc.get("custom_retention_")),
		flt(po_doc.get("custom_advance_")),
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_purchase_receipts_for_invoice(
	doctype, txt, searchfield, start, page_len, filters, as_dict=False
):
	"""Purchase Receipt search for PI 'Get Items From' popup — date ascending, with delivery note."""
	filters = filters or {}

	filter_list = [
		["docstatus", "=", 1],
		["is_return", "=", 0],
	]

	for fieldname in ("company", "supplier", "posting_date"):
		value = filters.get(fieldname)
		if value not in (None, ""):
			filter_list.append([fieldname, "=", value])

	delivery_note = filters.get("supplier_delivery_note")
	if delivery_note not in (None, ""):
		filter_list.append(["supplier_delivery_note", "like", f"%{delivery_note}%"])

	status = filters.get("status")
	if status:
		if isinstance(status, list) and len(status) == 2:
			filter_list.append(["status", status[0], status[1]])
		else:
			filter_list.append(["status", "=", status])

	or_filters = []
	if txt:
		or_filters = [
			["name", "like", f"%{txt}%"],
			["supplier_delivery_note", "like", f"%{txt}%"],
		]

	return frappe.get_list(
		"Purchase Receipt",
		filters=filter_list,
		or_filters=or_filters,
		fields=["name", "supplier", "posting_date", "supplier_delivery_note"],
		order_by="posting_date asc, name asc",
		limit_start=start,
		limit_page_length=page_len,
		ignore_permissions=True,
	)
