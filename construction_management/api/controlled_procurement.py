# Copyright (c) 2026, Construction Management
# License: MIT

"""Controlled catalog import and standard ERPNext procurement document creation."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime


ADMIN_ROLES = {"System Manager", "CEO"}
PURCHASE_ROLES = ADMIN_ROLES | {"Purchase User", "Purchase Manager"}
STOCK_ROLES = ADMIN_ROLES | {"Stock User", "Stock Manager"}
STOCKABLE = "Stockable"
ASSET = "Asset"
SERVICE = "Service"


def _roles() -> set[str]:
	return set(frappe.get_roles())


def _require(roles: set[str]) -> None:
	if not _roles().intersection(roles):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _as_dict(value: str | dict | None) -> dict:
	if isinstance(value, str):
		return frappe.parse_json(value)
	return value or {}


def _catalog_item(item_code: str) -> dict:
	item = frappe.db.get_value(
		"Item", item_code,
		["name", "stock_uom", "is_stock_item", "is_fixed_asset", "controlled_procurement_catalog", "controlled_item_type"],
		as_dict=True,
	)
	if not item or not cint(item.controlled_procurement_catalog) or item.stock_uom != "Nos":
		frappe.throw(_("Item {0} is not in the controlled Nos catalog.").format(item_code))
	return item


def _set_row_type(row, item: dict) -> None:
	row.controlled_item_type = item.controlled_item_type


def _append_item(doc, row_data: dict, defaults: dict, warehouses: bool = False) -> None:
	item = _catalog_item(row_data.get("item_code"))
	row = doc.append("items", {
		"item_code": item.name,
		"qty": flt(row_data.get("qty")),
		"uom": "Nos",
		"stock_uom": "Nos",
		"conversion_factor": 1,
		"rate": flt(row_data.get("rate")),
		"description": row_data.get("notes") or "",
	})
	if warehouses:
		row.s_warehouse = row_data.get("source_warehouse")
		row.t_warehouse = row_data.get("target_warehouse")
	elif doc.doctype == "Purchase Order":
		row.warehouse = row_data.get("warehouse") or doc.set_warehouse
	_apply_allocation(row, row_data, defaults)
	_set_row_type(row, item)


def _validate_company_links(company: str, project: str | None = None, warehouse: str | None = None) -> None:
	"""Projects and warehouses picked in the workspace must belong to the document's company."""
	for doctype, name in (("Project", project), ("Warehouse", warehouse)):
		if name and frappe.db.get_value(doctype, name, "company") not in (company, None, ""):
			frappe.throw(_("{0} {1} does not belong to company {2}.").format(_(doctype), name, company))


def _validate_line_data(items: list[dict]) -> None:
	if not items:
		frappe.throw(_("Add at least one item."))
	for row in items:
		if not row.get("item_code") or flt(row.get("qty")) <= 0:
			frappe.throw(_("Every item must have a controlled item and a quantity greater than zero."))


def _allocation_defaults(data: dict) -> dict:
	defaults = {field: data.get(field) for field in ("project", "bill_no", "boq_item")}
	_validate_allocation(defaults)
	return defaults


def _apply_allocation(row, row_data: dict, defaults: dict) -> None:
	allocation = {field: row_data.get(field) or defaults[field] for field in defaults}
	_validate_allocation(allocation)
	for field, value in allocation.items():
		setattr(row, field, value)


def _validate_allocation(allocation: dict) -> None:
	project = allocation.get("project")
	bill_no = allocation.get("bill_no")
	boq_item = allocation.get("boq_item")
	if not project or not bill_no or not boq_item:
		frappe.throw(_("Project, Bill No, and BOQ Item are required for controlled procurement."))
	frappe.has_permission("Project", "read", doc=frappe.get_doc("Project", project), throw=True)
	bill = frappe.db.get_value("BOQ Bill", bill_no, ["project"], as_dict=True)
	item = frappe.db.get_value("BOQ Item", boq_item, ["project", "parent_bill"], as_dict=True)
	if not bill or not item or bill.project != project or item.project != project or item.parent_bill != bill_no:
		frappe.throw(_("Bill No and BOQ Item must belong to the selected Project."))


@frappe.whitelist(methods=["GET"])
def get_catalog(company: str = "", search: str = "", start: int = 0, page_length: int = 50) -> dict:
	"""Return only visible controlled catalog items for the workspace."""
	if not _roles().intersection(PURCHASE_ROLES | STOCK_ROLES):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	filters = {"disabled": 0, "is_purchase_item": 1, "controlled_procurement_catalog": 1, "stock_uom": "Nos"}
	if search:
		filters["item_name"] = ["like", f"%{search.strip()}%"]
	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or 50, 1), 100)
	return {
		"rows": frappe.get_all(
		"Item", filters=filters,
		fields=["name", "item_name", "item_group", "stock_uom", "controlled_item_type", "controlled_catalog_source"],
		order_by="item_name asc", limit_start=start, limit_page_length=page_length,
		),
		"total_count": frappe.db.count("Item", filters),
	}


def _allowed_companies() -> list[str]:
	"""Companies the user can access (respects User Permissions)."""
	return frappe.get_list("Company", pluck="name", order_by="name asc", limit_page_length=0)


def _active_company() -> str:
	"""The user's default company, if they can still access it; scopes every workspace list."""
	company = frappe.defaults.get_user_default("Company")
	allowed = _allowed_companies()
	if company in allowed:
		return company
	return allowed[0] if len(allowed) == 1 else ""


def _scoped(filters: dict) -> dict:
	company = _active_company()
	return {**filters, "company": company} if company else filters


@frappe.whitelist(methods=["POST"])
def set_active_company(company: str) -> dict:
	"""Switch the workspace company; stored as the user's default like Desk does."""
	_require(PURCHASE_ROLES | STOCK_ROLES)
	if company not in _allowed_companies():
		frappe.throw(_("You do not have access to company {0}.").format(company), frappe.PermissionError)
	# Desk stores the session default under the scrubbed key; get_user_default reads it from there
	frappe.defaults.set_user_default("company", company)
	return get_workspace_context()


@frappe.whitelist(methods=["GET"])
def get_workspace_context() -> dict:
	"""Return permissions, defaults, and safe dashboard totals for the Vue workspace."""
	roles = _roles()
	if not roles.intersection(PURCHASE_ROLES | STOCK_ROLES):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	company = _active_company()
	return {
		"user": frappe.session.user,
		"full_name": frappe.utils.get_fullname(frappe.session.user),
		"user_image": frappe.db.get_value("User", frappe.session.user, "user_image"),
		"currency": (frappe.get_cached_value("Company", company, "default_currency") if company else None)
		or frappe.defaults.get_global_default("currency"),
		"default_company": company,
		"companies": _allowed_companies(),
		"can_purchase": bool(roles.intersection(PURCHASE_ROLES)),
		"can_transfer": bool(roles.intersection(STOCK_ROLES)),
		"can_manage_catalog": bool(roles.intersection(ADMIN_ROLES)),
		"can_email_purchase_order": frappe.has_permission("Purchase Order", "email"),
		"dashboard": {
			"purchase_orders": frappe.db.count("Purchase Order", _scoped({"is_subcontracted": 0, "docstatus": ["<", 2]})),
			"purchase_receipts": frappe.db.count("Purchase Receipt", _scoped({"is_subcontracted": 0, "docstatus": ["<", 2]})),
			"material_transfers": frappe.db.count("Stock Entry", _scoped({"purpose": "Material Transfer", "docstatus": ["<", 2]})),
			"catalog_items": frappe.db.count("Item", {"controlled_procurement_catalog": 1, "stock_uom": "Nos", "disabled": 0}),
			"draft_purchase_orders": frappe.db.count("Purchase Order", _scoped({"is_subcontracted": 0, "docstatus": 0})),
			"purchase_invoices": frappe.db.count("Purchase Invoice", _scoped(_workspace_filters("Purchase Invoice", {"docstatus": ["<", 2]}))),
			"unpaid_invoices": frappe.db.count("Purchase Invoice", _scoped(_workspace_filters("Purchase Invoice", {"docstatus": 1, "outstanding_amount": [">", 0]}))),
			"payable_outstanding": sum(frappe.get_all(
				"Purchase Invoice", filters=_scoped(_workspace_filters("Purchase Invoice", {"docstatus": 1, "outstanding_amount": [">", 0]})),
				pluck="outstanding_amount", limit_page_length=0,
			)),
			"open_lpos": 0 if not _has_open_po_field() else frappe.db.count("Purchase Order", _scoped({
				"is_subcontracted": 0, "docstatus": 1, "custom_is_provisional_po": 1, "per_received": ["<", 100],
				"status": ["not in", CLOSED_PO_STATUSES],
			})),
		},
	}


@frappe.whitelist(methods=["GET"])
def get_controlled_documents(doctype: str, search: str = "", start: int = 0, page_length: int = 25, submitted_only: int = 0, docstatus: str = "") -> dict:
	"""List documents that belong to the controlled workspace.

	`docstatus` also accepts "unpaid" and "overdue" for purchase invoices.
	"""
	if doctype not in DOCUMENT_ROLES:
		frappe.throw(_("Unsupported controlled document type."))
	_require(DOCUMENT_ROLES[doctype])
	filters = _scoped(_workspace_filters(doctype, {"docstatus": ["<", 2]}))
	if doctype == "Stock Entry":
		filters["purpose"] = "Material Transfer"
	if cint(submitted_only):
		filters["docstatus"] = 1
	elif docstatus in {"0", "1"}:
		filters["docstatus"] = cint(docstatus)
	elif doctype == "Purchase Invoice" and docstatus in {"unpaid", "overdue"}:
		filters.update({"docstatus": 1, "outstanding_amount": [">", 0]})
		if docstatus == "overdue":
			filters["due_date"] = ["<", frappe.utils.today()]
	fields = _document_list_fields(doctype)
	or_filters = None
	if search:
		like = f"%{search.strip()}%"
		or_filters = [["name", "like", like], ["project", "like", like]]
		if doctype != "Stock Entry":
			or_filters.append(["supplier_name", "like", like])
		if doctype == "Purchase Invoice":
			or_filters.append(["custom_supplier_invoice_no", "like", like])
	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or 25, 1), 100)
	return {
		"rows": frappe.get_list(doctype, filters=filters, or_filters=or_filters, fields=fields, order_by="modified desc", limit_start=start, limit_page_length=page_length),
		"total_count": len(frappe.get_list(doctype, filters=filters, or_filters=or_filters, pluck="name", limit_page_length=0)),
	}


@frappe.whitelist(methods=["GET"])
def get_controlled_document(doctype: str, name: str) -> dict:
	"""Return a controlled document and its standard email trail."""
	doc = _controlled_doc(doctype, name)
	result = doc.as_dict()
	for row in result.get("items") or []:
		row["vat"] = _vat_choice(row.get("item_tax_template"), doc.company)
	result["email_history"] = frappe.get_all(
		"Communication",
		filters={"reference_doctype": doctype, "reference_name": name, "communication_medium": "Email"},
		fields=["name", "subject", "sender", "recipients", "sent_or_received", "creation"],
		order_by="creation desc",
	)
	if doctype == "Purchase Order":
		result["supplier_email"] = frappe.db.get_value("Supplier", doc.supplier, "email_id") or ""
	result["attachments"] = frappe.get_all(
		"File", filters={"attached_to_doctype": doctype, "attached_to_name": name},
		fields=["name", "file_name", "file_url", "creation"], order_by="creation desc",
	)
	result["owner_name"] = frappe.utils.get_fullname(doc.owner)
	return result


TAX_MASTER = "Purchase Taxes and Charges Template"
LINE_VAT = ("standard", "zero", "exempt")


def _line_vat_templates(company: str) -> dict:
	"""Item Tax Templates behind the per-line VAT choices, resolved by the company's naming."""
	templates = frappe.get_all("Item Tax Template", filters={"company": company, "disabled": 0}, pluck="name")

	def find(word):
		return next((name for name in templates if "vat" in name.lower() and word in name.lower()), None)

	return {"standard": None, "zero": find("zero"), "exempt": find("exempt")}


def _vat_choice(item_tax_template: str | None, company: str) -> str:
	"""Map a stored Item Tax Template back to the line choice shown in the UI."""
	if not item_tax_template:
		return "standard"
	for choice, template in _line_vat_templates(company).items():
		if template and template == item_tax_template:
			return choice
	return "standard"


@frappe.whitelist(methods=["GET"])
def get_tax_options(company: str = "") -> dict:
	"""Purchase tax templates and per-line VAT choices for the active company."""
	_require(PURCHASE_ROLES | STOCK_ROLES)
	company = company or _active_company()
	return {
		"templates": frappe.get_all(TAX_MASTER, filters={"company": company, "disabled": 0}, pluck="name", order_by="is_default desc, name asc"),
		"default_template": frappe.db.get_value(TAX_MASTER, {"company": company, "is_default": 1, "disabled": 0}, "name"),
		"line_templates": _line_vat_templates(company),
	}


def _apply_taxes(doc, taxes_and_charges: str | None, vat_by_row: list[str] | None = None) -> None:
	"""Load the header tax template and tag Zero-rated / Exempt lines with their Item Tax Template.

	ERPNext rebuilds each line's tax map from these on save, so the template is all a line needs.
	"""
	from erpnext.accounts.services.taxes import get_taxes_and_charges

	doc.set("taxes", [])
	doc.taxes_and_charges = taxes_and_charges or None
	if taxes_and_charges:
		if frappe.db.get_value(TAX_MASTER, taxes_and_charges, "company") != doc.company:
			frappe.throw(_("Tax template {0} does not belong to company {1}.").format(taxes_and_charges, doc.company))
		for tax in get_taxes_and_charges(TAX_MASTER, taxes_and_charges) or []:
			doc.append("taxes", tax)
	line_templates = _line_vat_templates(doc.company)
	for row, choice in zip(doc.items, vat_by_row or []):
		choice = choice if choice in LINE_VAT else "standard"
		if choice != "standard" and not line_templates.get(choice):
			frappe.throw(_("No {0} VAT Item Tax Template is set up for company {1}.").format(choice, doc.company))
		row.item_tax_template = line_templates.get(choice)


def _totals_payload(doc) -> dict:
	"""Per-line VAT and tax rows as ERPNext calculated them."""
	# calculate_taxes_and_totals keeps an unsaved per-item breakdown on the document
	position = {id(row): i for i, row in enumerate(doc.items)}
	line_tax = [0.0] * len(doc.items)
	for detail in doc.get("_item_wise_tax_details") or []:
		i = position.get(id(detail.item))
		if i is not None:
			line_tax[i] += flt(detail.amount)
	return {
		"net_total": flt(doc.net_total),
		"total_taxes_and_charges": flt(doc.total_taxes_and_charges),
		"grand_total": flt(doc.grand_total),
		"rounded_total": flt(doc.get("rounded_total")),
		"taxes": [{"description": tax.description or tax.account_head, "rate": flt(tax.rate), "amount": flt(tax.tax_amount)} for tax in doc.taxes],
		"line_tax": line_tax,
	}


@frappe.whitelist(methods=["POST"])
def preview_totals(doctype: str, data: str | dict) -> dict:
	"""Calculate taxes and totals for an unsaved form exactly as ERPNext will on save."""
	_require(PURCHASE_ROLES)
	if doctype not in ("Purchase Order", "Purchase Receipt", "Purchase Invoice"):
		frappe.throw(_("Unsupported document type."))
	data = _as_dict(data)
	doc = frappe.new_doc(doctype)
	doc.company = data.get("company") or _active_company()
	doc.supplier = data.get("supplier") or None
	doc.currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	doc.conversion_rate = 1
	lines = [row for row in data.get("items") or [] if row.get("item_code")]
	for i, row in enumerate(lines, start=1):
		qty, rate = flt(row.get("qty")), flt(row.get("rate"))
		doc.append("items", {"idx": i, "name": f"row-{i}", "item_code": row.get("item_code"), "qty": qty, "rate": rate,
			"price_list_rate": rate, "conversion_factor": 1, "uom": row.get("uom") or "Nos"})
	_apply_taxes(doc, data.get("taxes_and_charges"), [row.get("vat") for row in lines])
	from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals

	calculate_taxes_and_totals(doc)
	payload = _totals_payload(doc)
	# map line tax back onto the submitted rows, including blank ones
	it = iter(payload["line_tax"])
	payload["line_tax"] = [next(it) if row.get("item_code") else 0 for row in data.get("items") or []]
	return payload


CONNECTION_DATE_FIELDS = ("posting_date", "transaction_date", "reference_date", "schedule_date")
CONNECTION_AMOUNT_FIELDS = ("grand_total", "paid_amount", "total_debit", "amount", "total")


def _connection_names(doctype: str, name: str, target: str, found: dict, links: dict) -> list[str]:
	"""Names of `target` documents linked to this one, following Desk's Connections rules."""
	from frappe.desk.notifications import get_child_doctypes_with_field, get_external_link_fieldname

	if found.get("names"):
		return list(found["names"])
	fieldname = get_external_link_fieldname(target, links)
	if not fieldname:
		return []
	child_doctypes = get_child_doctypes_with_field(target, fieldname)
	if child_doctypes:
		or_filters = [[child, fieldname, "=", name] for child in child_doctypes]
		return frappe.get_list(target, or_filters=or_filters, pluck="name", distinct=True, limit_page_length=50, order_by="creation desc")
	return frappe.get_list(target, filters={fieldname: name}, pluck="name", limit_page_length=50, order_by="creation desc")


def _connection_rows(doctype: str, names: list[str]) -> list[dict]:
	"""Status, date and amount for each linked document (whatever fields that doctype has)."""
	meta = frappe.get_meta(doctype)
	fields = ["name", "docstatus"] + [field for field in ("status", "title") if meta.has_field(field)]
	date_field = next((field for field in CONNECTION_DATE_FIELDS if meta.has_field(field)), None)
	amount_field = next((field for field in CONNECTION_AMOUNT_FIELDS if meta.has_field(field)), None)
	fields += [f"{date_field} as date"] if date_field else []
	fields += [f"{amount_field} as amount"] if amount_field else []
	if not meta.is_submittable:
		fields.remove("docstatus")
	return frappe.get_list(doctype, filters={"name": ["in", names]}, fields=fields, order_by="creation desc", limit_page_length=50)


@frappe.whitelist(methods=["GET"])
def get_document_connections(doctype: str, name: str) -> list[dict]:
	"""Desk's Connections tab for a workspace document: groups of linked doctypes with their documents."""
	from frappe.desk.notifications import get_open_count

	doc = _controlled_doc(doctype, name)
	links = doc.meta.get_dashboard_data()
	counts = get_open_count(doctype, name).get("count") or {}
	found_by_doctype = {
		row["doctype"]: row
		for row in (counts.get("internal_links_found") or []) + (counts.get("external_links_found") or [])
		if row.get("count")
	}
	groups = []
	for group in links.transactions:
		items = []
		for target in group.get("items") or []:
			found = found_by_doctype.get(target)
			if not found or not frappe.has_permission(target, "read"):
				continue
			names = _connection_names(doctype, name, target, found, links)
			if names:
				items.append({"doctype": target, "count": len(names), "documents": _connection_rows(target, names)})
		if items:
			groups.append({"label": group.get("label") or _("Related"), "items": items})

	# post-dated cheques reserve invoice amounts but are not in ERPNext's dashboard config
	if doctype == "Purchase Invoice" and frappe.db.table_exists("PDC Invoice Reference") and frappe.has_permission("Post Dated Cheques", "read"):
		pdcs = frappe.get_all("PDC Invoice Reference", filters={"reference_doctype": doctype, "reference_name": name}, pluck="parent", distinct=True)
		if pdcs:
			item = {"doctype": "Post Dated Cheques", "count": len(pdcs), "documents": _connection_rows("Post Dated Cheques", pdcs)}
			payment = next((group for group in groups if group["label"] == _("Payment")), None)
			if payment:
				payment["items"].append(item)
			else:
				groups.insert(0, {"label": _("Payment"), "items": [item]})
	return groups


@frappe.whitelist(methods=["GET"])
def get_boq_options(project: str, bill_no: str = "") -> dict:
	"""Return only BOQ bills and items belonging to one selected project."""
	_require(PURCHASE_ROLES | STOCK_ROLES)
	if not project:
		return {"bills": [], "items": []}
	frappe.has_permission("Project", "read", doc=frappe.get_doc("Project", project), throw=True)
	bills = frappe.get_all("BOQ Bill", filters={"project": project}, fields=["name", "bill_no"], order_by="sequence asc")
	item_filters = {"project": project}
	if bill_no:
		item_filters["parent_bill"] = bill_no
	items = frappe.get_all("BOQ Item", filters=item_filters, fields=["name", "description", "parent_bill", "unit"], order_by="idx asc")
	return {"bills": bills, "items": items}


@frappe.whitelist(methods=["GET"])
def get_purchase_order_items(purchase_order: str) -> list[dict]:
	"""Return the still-receivable lines of a submitted PO (app-created or raised in Desk)."""
	_require(PURCHASE_ROLES)
	po = _controlled_doc("Purchase Order", purchase_order)
	if po.docstatus != 1:
		frappe.throw(_("Select a submitted Purchase Order."))
	return [
		{
			"purchase_order_item": row.name,
			"item_code": row.item_code,
			"item_name": row.item_name,
			"remaining_qty": max(flt(row.qty) - flt(row.received_qty), 0),
			"rate": row.rate,
			"project": row.project,
			"bill_no": row.bill_no,
			"boq_item": row.boq_item,
			"controlled_item_type": row.controlled_item_type,
			"vat": _vat_choice(row.item_tax_template, po.company),
			"po_taxes_and_charges": po.taxes_and_charges or "",
			"uom": row.uom,
			"warehouse": row.warehouse,
			# app-created POs need catalog items + BOQ allocation; Desk POs are received as they are
			"controlled": cint(po.controlled_procurement),
		}
		for row in po.items
		if flt(row.qty) > flt(row.received_qty)
	]


@frappe.whitelist(methods=["POST"])
def create_controlled_item(data: str | dict) -> dict:
	"""Create a manually maintained controlled Stockable, Asset, or Service item."""
	_require(ADMIN_ROLES)
	data = _as_dict(data)
	company = data.get("company")
	item_type = data.get("item_type")
	if item_type not in {STOCKABLE, ASSET, SERVICE}:
		frappe.throw(_("Select Stockable, Asset, or Service."))
	if not company or not data.get("item_name") or not data.get("item_group"):
		frappe.throw(_("Company, Item Name, and Item Group are required."))
	if not frappe.db.exists("Item Group", data["item_group"]):
		frappe.throw(_("Item Group {0} does not exist.").format(data["item_group"]))
	company_rules = frappe.db.get_value(
		"Company", company, ["controlled_service_expense_account", "controlled_asset_category"], as_dict=True
	)
	item_data = {
		"doctype": "Item", "item_code": data.get("item_code") or _item_code(data["item_name"]),
		"item_name": data["item_name"], "item_group": data["item_group"], "stock_uom": "Nos",
		"is_purchase_item": 1, "controlled_procurement_catalog": 1,
		"controlled_item_type": item_type,
		"controlled_catalog_source": "CEO Manual",
		"controlled_catalog_version": "manual",
	}
	if item_type == STOCKABLE:
		item_data.update({"is_stock_item": 1, "is_fixed_asset": 0})
	elif item_type == ASSET:
		asset_category = data.get("asset_category") or company_rules.controlled_asset_category
		if not asset_category:
			frappe.throw(_("Configure an Asset Category for the company before creating an Asset item."))
		item_data.update({"is_stock_item": 0, "is_fixed_asset": 1, "asset_category": asset_category})
	else:
		expense_account = data.get("expense_account") or company_rules.controlled_service_expense_account
		if not expense_account:
			frappe.throw(_("Configure a Service Expense Account for the company before creating a Service item."))
		from redtra_customisation.redtra_customisation.service_item_validator import ServiceItemValidator
		ServiceItemValidator.validate_expense_account(expense_account, company)
		item_data.update({"is_stock_item": 0, "is_fixed_asset": 0, "expense_account": expense_account, "company": company})
	item = frappe.get_doc(item_data)
	item.flags.controlled_procurement_api = True
	item.insert()
	return {"doctype": "Item", "name": item.name}


@frappe.whitelist(methods=["POST"])
def create_purchase_order(data: str | dict) -> dict:
	_require(PURCHASE_ROLES)
	data = _as_dict(data)
	items = data.get("items") or []
	_validate_line_data(items)
	defaults = _allocation_defaults(data)
	company = data.get("company")
	_validate_company_links(company, project=data.get("project"), warehouse=data.get("warehouse"))
	for row in items:
		_validate_company_links(company, project=row.get("project"), warehouse=row.get("warehouse"))
	doc = frappe.new_doc("Purchase Order")
	doc.update({
		"company": company, "supplier": data.get("supplier"), "project": data.get("project"),
		"bill_no": defaults["bill_no"], "boq_item": defaults["boq_item"],
		"schedule_date": data.get("required_by"), "set_warehouse": data.get("warehouse"),
		"contact_person": data.get("contact_person") or None,
		"tc_name": data.get("tc_name") or None, "terms": data.get("terms") or None,
		"controlled_procurement": 1,
	})
	for row in items:
		_append_item(doc, row, defaults)
	_apply_taxes(doc, data.get("taxes_and_charges"), [row.get("vat") for row in items])
	doc.flags.controlled_procurement_api = True
	doc.insert()
	return {"doctype": doc.doctype, "name": doc.name}


@frappe.whitelist(methods=["POST"])
def create_purchase_receipt(data: str | dict) -> dict:
	_require(PURCHASE_ROLES)
	data = _as_dict(data)
	po_name = data.get("purchase_order")
	po = _controlled_doc("Purchase Order", po_name)
	if po.docstatus != 1:
		frappe.throw(_("Select a submitted Purchase Order."))
	if not cint(po.controlled_procurement):
		return _receive_desk_purchase_order(po, data)
	items = data.get("items") or []
	_validate_line_data(items)
	po_rows = {row.name: row for row in po.items}
	# receipt-level allocation defaults to the PO's but can be changed on the receipt
	defaults = {field: data.get(field) or po.get(field) for field in ("project", "bill_no", "boq_item")}
	_validate_allocation(defaults)
	_validate_company_links(po.company, project=defaults["project"])
	doc = frappe.new_doc("Purchase Receipt")
	doc.update({
		"company": po.company, "supplier": po.supplier, "project": defaults["project"],
		"bill_no": defaults["bill_no"], "boq_item": defaults["boq_item"],
		"posting_date": data.get("received_on"), "custom_purchase_order": po.name,
		"controlled_procurement": 1,
	})
	for data_row in items:
		po_row = po_rows.get(data_row.get("purchase_order_item"))
		if not po_row or po_row.item_code != data_row.get("item_code"):
			frappe.throw(_("Receipt items must come from the selected Purchase Order."))
		item = _catalog_item(po_row.item_code)
		_validate_company_links(po.company, warehouse=data_row.get("warehouse"))
		line_project = (data_row if data_row.get("use_override") else defaults).get("project")
		warehouse_project = get_warehouse_project(data_row.get("warehouse")) if data_row.get("warehouse") else ""
		if warehouse_project and warehouse_project != line_project:
			frappe.throw(_("Warehouse {0} belongs to project {1}, so goods received there are booked to {1}. Select project {1} (and its Bill / BOQ Item) or a different warehouse.").format(
				data_row.get("warehouse"), warehouse_project))
		row = doc.append("items", {
			"item_code": po_row.item_code, "qty": flt(data_row.get("qty")), "uom": "Nos", "stock_uom": "Nos",
			"conversion_factor": 1, "rate": po_row.rate, "purchase_order": po.name,
			"purchase_order_item": po_row.name, "warehouse": data_row.get("warehouse"),
		})
		_apply_allocation(row, data_row if data_row.get("use_override") else {}, defaults)
		_set_row_type(row, item)
	# VAT follows the order unless the receiver changes it
	taxes_and_charges = data.get("taxes_and_charges") if "taxes_and_charges" in data else po.taxes_and_charges
	_apply_taxes(doc, taxes_and_charges, [
		data_row.get("vat") or _vat_choice(po_rows[data_row.get("purchase_order_item")].item_tax_template, po.company)
		for data_row in items
	])
	doc.flags.controlled_procurement_api = True
	doc.insert()
	return {"doctype": doc.doctype, "name": doc.name}


def _receive_desk_purchase_order(po, data: dict) -> dict:
	"""Receive note for a PO raised in Desk, built with ERPNext's own PO → receipt mapping.

	Items and UOMs come from the PO as they are; Project / Bill / BOQ are optional here.
	"""
	from erpnext.buying.doctype.purchase_order.mapper import make_purchase_receipt

	lines = {row.get("purchase_order_item"): row for row in data.get("items") or [] if flt(row.get("qty")) > 0}
	if not lines:
		frappe.throw(_("Enter a receive qty on at least one line."))
	doc = make_purchase_receipt(po.name)
	header = {field: data.get(field) or po.get(field) for field in ("project", "bill_no", "boq_item")}
	if all(header.values()):
		_validate_allocation(header)
	_validate_company_links(po.company, project=header["project"])
	kept = []
	for row in doc.items:
		line = lines.pop(row.purchase_order_item, None)
		if not line:
			continue
		pending = flt(row.qty)
		if flt(line.get("qty")) > pending + 0.0001:
			frappe.throw(_("{0}: only {1} {2} is left to receive.").format(row.item_name or row.item_code, pending, row.uom))
		row.qty = flt(line.get("qty"))
		row.received_qty = row.qty
		row.warehouse = line.get("warehouse") or row.warehouse
		_validate_company_links(po.company, warehouse=row.warehouse)
		allocation = {field: (line if line.get("use_override") else header).get(field) for field in ("project", "bill_no", "boq_item")}
		if line.get("use_override") and all(allocation.values()):
			_validate_allocation(allocation)
		for field, value in allocation.items():
			if value and row.meta.has_field(field):
				row.set(field, value)
		# receipts post to a project (site rule, enforced again on submit); a site warehouse decides it
		row.project = get_warehouse_project(row.warehouse) or row.project
		if not row.project:
			frappe.throw(_("{0}: select a Project for this receive note (warehouse {1} is not linked to one).").format(
				row.item_name or row.item_code, row.warehouse))
		row.idx = len(kept) + 1
		kept.append(row)
	if lines:
		frappe.throw(_("Receive note lines must come from Purchase Order {0}.").format(po.name))
	doc.set("items", kept)
	doc.update({
		"project": header["project"], "bill_no": header["bill_no"], "boq_item": header["boq_item"],
		"posting_date": data.get("received_on") or doc.posting_date, "set_posting_time": 1 if data.get("received_on") else 0,
		"custom_purchase_order": po.name if doc.meta.has_field("custom_purchase_order") else None,
		"controlled_procurement": 0,
	})
	taxes_and_charges = data.get("taxes_and_charges") if "taxes_and_charges" in data else po.taxes_and_charges
	vat_by_line = {line.get("purchase_order_item"): line.get("vat") for line in data.get("items") or []}
	_apply_taxes(doc, taxes_and_charges, [
		vat_by_line.get(row.purchase_order_item) or _vat_choice(row.item_tax_template, po.company) for row in kept
	])
	doc.flags.controlled_procurement_api = True
	doc.insert()
	return {"doctype": doc.doctype, "name": doc.name}


@frappe.whitelist(methods=["POST"])
def create_material_transfer(data: str | dict) -> dict:
	_require(STOCK_ROLES)
	data = _as_dict(data)
	items = data.get("items") or []
	_validate_line_data(items)
	defaults = _allocation_defaults(data)
	doc = frappe.new_doc("Stock Entry")
	doc.update({
		"company": data.get("company"), "purpose": "Material Transfer", "project": data.get("project"),
		# mandatory in this ERPNext version; the standard type for the Material Transfer purpose
		"stock_entry_type": frappe.db.get_value("Stock Entry Type", {"purpose": "Material Transfer"}, "name", order_by="is_standard desc") or "Material Transfer",
		"bill_no": defaults["bill_no"], "boq_item": defaults["boq_item"],
		"posting_date": data.get("posting_date"), "controlled_procurement": 1,
	})
	for row_data in items:
		item = _catalog_item(row_data.get("item_code"))
		if item.controlled_item_type != STOCKABLE or not cint(item.is_stock_item):
			frappe.throw(_("Only controlled Stockable items can be transferred."))
		_append_item(doc, row_data, defaults, warehouses=True)
	doc.flags.controlled_procurement_api = True
	doc.insert()
	return {"doctype": doc.doctype, "name": doc.name}


@frappe.whitelist(methods=["POST"])
def update_purchase_order_items(name: str, items: str | list) -> dict:
	"""Change qty/rate or add/remove lines on a submitted PO (ERPNext "Update Items").

	Lines already received cannot go below their received qty or be removed; ERPNext enforces that.
	"""
	from erpnext.accounts.services.child_item_update import update_child_qty_rate

	po = _controlled_doc("Purchase Order", name, "write")
	if po.docstatus != 1:
		frappe.throw(_("Only submitted purchase orders can be updated this way; edit the draft instead."))
	if po.status in ("Closed", "Completed", "Delivered"):
		frappe.throw(_("Purchase Order {0} is {1} and can no longer be changed.").format(name, po.status))
	items = frappe.parse_json(items) if isinstance(items, str) else items
	if not items:
		frappe.throw(_("A purchase order needs at least one item."))
	existing = {row.name: row for row in po.items}
	trans_items = []
	for row in items:
		if flt(row.get("qty")) <= 0:
			frappe.throw(_("Quantity must be greater than zero for {0}.").format(row.get("item_code")))
		current = existing.get(row.get("docname"))
		if not current and cint(po.controlled_procurement):
			_catalog_item(row.get("item_code"))  # new lines on controlled POs must be catalog items
		trans_items.append({
			"docname": current.name if current else None,
			"item_code": current.item_code if current else row.get("item_code"),
			"qty": flt(row.get("qty")),
			"rate": flt(row.get("rate")),
			"uom": current.uom if current else (row.get("uom") or frappe.db.get_value("Item", row.get("item_code"), "stock_uom")),
			"conversion_factor": current.conversion_factor if current else 1,
			"schedule_date": str(current.schedule_date if current else po.schedule_date),
			**({} if current else {"item_tax_template": _line_vat_templates(po.company).get(row.get("vat") or "standard")}),
		})
	update_child_qty_rate("Purchase Order", json.dumps(trans_items), name)
	return {"name": name}


INVOICE_SOURCES = {"Purchase Order": "po_detail", "Purchase Receipt": "pr_detail"}


def _map_invoice(source_doctype: str, source_name: str):
	"""Unsaved Purchase Invoice for the still-unbilled part of a PO or receipt (ERPNext's own mapper)."""
	if source_doctype not in INVOICE_SOURCES:
		frappe.throw(_("Invoices can be created from a Purchase Order or Purchase Receipt."))
	source = _controlled_doc(source_doctype, source_name)
	if source.docstatus != 1:
		frappe.throw(_("{0} {1} must be submitted before it can be invoiced.").format(_(source_doctype), source_name))
	if flt(source.get("per_billed")) >= 100:
		frappe.throw(_("{0} {1} is already fully invoiced.").format(_(source_doctype), source_name))
	if source_doctype == "Purchase Order":
		from erpnext.buying.doctype.purchase_order.mapper import make_purchase_invoice
	else:
		from erpnext.stock.doctype.purchase_receipt.mapper import make_purchase_invoice
	return source, make_purchase_invoice(source_name)


@frappe.whitelist(methods=["GET"])
def get_invoice_sources(search: str = "") -> list[dict]:
	"""Submitted POs and receipts of the active company that still have something to invoice."""
	_require(PURCHASE_ROLES)
	like = f"%{(search or '').strip()}%"
	rows = []
	for doctype, date_field, extra in (
		("Purchase Order", "transaction_date", {"status": ["not in", ["Closed", "On Hold"]]}),
		("Purchase Receipt", "posting_date", {"is_return": 0}),
	):
		filters = _scoped(_workspace_filters(doctype, {"docstatus": 1, "per_billed": ["<", 100], **extra}))
		for row in frappe.get_list(
			doctype, filters=filters, or_filters=[["name", "like", like], ["supplier_name", "like", like]] if search else None,
			fields=["name", "supplier", "supplier_name", "grand_total", "per_billed", f"{date_field} as date", "project"],
			order_by="modified desc", limit_page_length=40,
		):
			rows.append({"doctype": doctype, **row})
	return sorted(rows, key=lambda row: str(row["date"]), reverse=True)


@frappe.whitelist(methods=["GET"])
def get_invoice_lines(source_doctype: str, source_name: str) -> dict:
	"""The lines, tax and supplier an invoice from this PO / receipt would start with."""
	_require(PURCHASE_ROLES)
	source, mapped = _map_invoice(source_doctype, source_name)
	key_field = INVOICE_SOURCES[source_doctype]
	return {
		"supplier": mapped.supplier,
		"supplier_name": mapped.supplier_name,
		"company": mapped.company,
		"currency": mapped.currency,
		"project": source.get("project"),
		# follow the PO / receipt; if it carried no tax, start from the company default (usually VAT 5%)
		"taxes_and_charges": mapped.taxes_and_charges or source.get("taxes_and_charges")
		or frappe.db.get_value(TAX_MASTER, {"company": mapped.company, "is_default": 1, "disabled": 0}, "name") or "",
		"due_date": mapped.get("due_date"),
		"lines": [
			{
				"key": row.get(key_field),
				"item_code": row.item_code,
				"item_name": row.item_name,
				"description": row.description,
				"unbilled_qty": flt(row.qty),
				"qty": flt(row.qty),
				"rate": flt(row.rate),
				"uom": row.uom,
				"project": row.get("project"),
				"bill_no": row.get("bill_no"),
				"boq_item": row.get("boq_item"),
				"purchase_order": row.get("purchase_order"),
				"purchase_receipt": row.get("purchase_receipt"),
				"vat": _vat_choice(row.get("item_tax_template"), mapped.company),
			}
			for row in mapped.items
			if flt(row.qty) > 0
		],
	}


@frappe.whitelist(methods=["POST"])
def create_purchase_invoice(data: str | dict) -> dict:
	"""Draft Purchase Invoice for chosen lines of a PO or receipt, never above the unbilled qty."""
	_require(PURCHASE_ROLES)
	frappe.has_permission("Purchase Invoice", "create", throw=True)
	data = _as_dict(data)
	if not (data.get("supplier_invoice_no") or "").strip():
		frappe.throw(_("Supplier invoice no is required."))
	source_doctype, source_name = data.get("source_doctype"), data.get("source_name")
	_source, doc = _map_invoice(source_doctype, source_name)
	key_field = INVOICE_SOURCES[source_doctype]
	mapped_rows = {row.get(key_field): row for row in doc.items}
	lines = [line for line in data.get("items") or [] if flt(line.get("qty")) > 0]
	if not lines:
		frappe.throw(_("Add at least one line to invoice."))
	kept = []
	for line in lines:
		row = mapped_rows.get(line.get("key"))
		if not row:
			frappe.throw(_("Invoice lines must come from {0} {1}.").format(_(source_doctype), source_name))
		if flt(line.get("qty")) > flt(row.qty) + 0.0001:
			frappe.throw(_("{0}: only {1} is left to invoice.").format(row.item_name or row.item_code, flt(row.qty)))
		row.qty = flt(line.get("qty"))
		if line.get("rate") is not None:
			row.rate = flt(line.get("rate"))
		row.idx = len(kept) + 1
		# mandatory Warehouse Type dimension; every existing invoice books lines to "Transit"
		for field in ("site", "rejected_site"):
			if row.meta.has_field(field) and not row.get(field):
				row.set(field, "Transit")
		kept.append(row)
	doc.set("items", kept)
	doc.custom_supplier_invoice_no = data["supplier_invoice_no"].strip()
	doc.bill_date = data.get("supplier_invoice_date") or None
	if data.get("posting_date"):
		doc.set_posting_time = 1
		doc.posting_date = data["posting_date"]
	if data.get("due_date"):
		doc.due_date = data["due_date"]
		doc.payment_terms_template = None
		doc.set("payment_schedule", [])
	if data.get("remarks"):
		doc.remarks = data["remarks"]
	_apply_taxes(doc, data.get("taxes_and_charges"), [line.get("vat") for line in lines])
	doc.insert()
	return {"doctype": doc.doctype, "name": doc.name}


def _payable_invoice(invoice: str):
	doc = _controlled_doc("Purchase Invoice", invoice)
	if doc.docstatus != 1:
		frappe.throw(_("Submit the invoice before recording a payment."))
	if flt(doc.outstanding_amount) <= 0:
		frappe.throw(_("Purchase Invoice {0} is already fully paid.").format(invoice))
	return doc


def _remaining_payable(doc) -> float:
	"""Outstanding amount not already reserved by pending post-dated cheques."""
	try:
		from redtra_customisation.redtra_customisation.doctype.post_dated_cheques.post_dated_cheques import (
			get_remaining_pdc_allocatable,
		)
	except ImportError:
		return flt(doc.outstanding_amount)
	return flt(get_remaining_pdc_allocatable(doc.doctype, doc.name))


@frappe.whitelist(methods=["GET"])
def get_payment_defaults(invoice: str) -> dict:
	"""Amounts, payment modes and the company's bank / cash accounts for the Record payment form."""
	_require(PURCHASE_ROLES)
	doc = _payable_invoice(invoice)
	company = frappe.db.get_value("Company", doc.company, ["default_bank_account", "default_cash_account"], as_dict=True)
	modes = frappe.get_all("Mode of Payment", filters={"enabled": 1}, fields=["name", "type"], order_by="name asc")
	for mode in modes:
		mode["account"] = frappe.db.get_value("Mode of Payment Account", {"parent": mode.name, "company": doc.company}, "default_account") or (
			company.default_cash_account if mode.type == "Cash" else company.default_bank_account
		)
	return {
		"invoice": doc.name,
		"supplier": doc.supplier,
		"supplier_name": doc.supplier_name,
		"company": doc.company,
		"currency": doc.currency,
		"outstanding_amount": flt(doc.outstanding_amount),
		"payable_amount": _remaining_payable(doc),
		"supplier_invoice_no": doc.get("custom_supplier_invoice_no") or "",
		"modes": modes,
	}


@frappe.whitelist(methods=["POST"])
def record_invoice_payment(invoice: str, data: str | dict) -> dict:
	"""Pay a submitted invoice: a Payment Entry now, or a Post Dated Cheque for a future-dated cheque."""
	_require(PURCHASE_ROLES)
	data = _as_dict(data)
	doc = _payable_invoice(invoice)
	amount = flt(data.get("amount"))
	remaining = _remaining_payable(doc)
	if amount <= 0:
		frappe.throw(_("Enter an amount greater than zero."))
	if amount > remaining + 0.01:
		frappe.throw(_("Only {0} is left to pay on {1} after pending post-dated cheques.").format(
			frappe.format_value(remaining, {"fieldtype": "Currency", "options": doc.currency}), invoice))
	mode = data.get("mode_of_payment")
	mode_type = frappe.db.get_value("Mode of Payment", mode, "type") if mode else None
	if not mode_type:
		frappe.throw(_("Select a mode of payment."))
	account = data.get("account")
	account_row = frappe.db.get_value("Account", account, ["company", "account_type", "is_group"], as_dict=True) if account else None
	if not account_row or account_row.company != doc.company or account_row.is_group or account_row.account_type not in ("Bank", "Cash"):
		frappe.throw(_("Select a bank or cash account of {0}.").format(doc.company))
	today = getdate(frappe.utils.today())
	reference_date = getdate(data.get("reference_date") or today)
	reference_no = (data.get("reference_no") or "").strip()

	if "cheque" in mode.lower() and reference_date > today:
		if not reference_no:
			frappe.throw(_("Enter the cheque number."))
		frappe.has_permission("Post Dated Cheques", "create", throw=True)
		pdc = frappe.get_doc({
			"doctype": "Post Dated Cheques",
			"company": doc.company,
			"project": doc.get("project"),
			"cost_center": doc.get("cost_center"),
			"posting_date": reference_date,
			"payment_type": "Pay",
			"party_type": "Supplier",
			"party": doc.supplier,
			"party_name": doc.supplier_name,
			"mode_of_payment": mode,
			"reference_no": reference_no,
			"reference_date": reference_date,
			"amount": amount,
			"bank_account": account,
			"invoice_references": [{
				"reference_doctype": doc.doctype,
				"reference_name": doc.name,
				"total_amount": flt(doc.grand_total),
				"outstanding_amount": flt(doc.outstanding_amount),
				"allocated_amount": amount,
			}],
		})
		pdc.insert()
		pdc.submit()
		return {"doctype": pdc.doctype, "name": pdc.name, "post_dated": 1}

	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	pe = get_payment_entry(doc.doctype, doc.name, party_amount=amount, bank_account=account)
	pe.mode_of_payment = mode
	pe.posting_date = getdate(data.get("posting_date") or today)
	pe.reference_no = reference_no or doc.get("custom_supplier_invoice_no") or doc.name
	pe.reference_date = reference_date
	if data.get("remarks"):
		pe.remarks = data["remarks"]
	pe.insert()
	pe.submit()
	return {"doctype": pe.doctype, "name": pe.name, "post_dated": 0}


@frappe.whitelist(methods=["POST"])
def submit_document(doctype: str, name: str) -> dict:
	"""Submit any workspace draft (controlled or raised in Desk) after normal permission checks."""
	doc = _controlled_doc(doctype, name, "submit")
	if doc.docstatus != 0:
		frappe.throw(_("{0} is not a draft.").format(name))
	doc.flags.controlled_procurement_api = True
	doc.submit()
	return {"doctype": doctype, "name": doc.name, "docstatus": doc.docstatus}


def _workbook_rows(path: Path) -> tuple[list[dict], list[dict]]:
	from openpyxl import load_workbook

	book = load_workbook(path, read_only=True, data_only=True)
	rows = []
	header_index = None
	for sheet in book.worksheets:
		candidate_rows = list(sheet.iter_rows(values_only=True))
		candidate_header = next((i for i, row in enumerate(candidate_rows) if "Item Group" in row and "Description" in row), None)
		if candidate_header is not None:
			rows, header_index = candidate_rows, candidate_header
			break
	if header_index is None:
		frappe.throw(_("The workbook must contain Item Group and Description columns."))
	headers = {str(value).strip(): position for position, value in enumerate(rows[header_index]) if value}
	valid, exceptions = [], []
	for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
		group = str(row[headers["Item Group"]] or "").strip()
		description = str(row[headers["Description"]] or "").strip()
		if not group and not description:
			continue
		if group == "Item Group" or not group or not description:
			exceptions.append({"row": row_number, "reason": "Missing item group or description"})
			continue
		valid.append({
			"row": row_number, "item_group": group, "item_name": description,
			"supplier": str(row[headers.get("Supplier", -1)] or "").strip() if "Supplier" in headers else "",
			"rate": flt(row[headers.get("Rates", -1)] or 0) if "Rates" in headers else 0,
		})
	return valid, exceptions


def _item_code(item_name: str) -> str:
	base = "CP-" + frappe.scrub(item_name).upper()[:100]
	code = base
	index = 2
	while frappe.db.exists("Item", code):
		code = f"{base[:95]}-{index}"
		index += 1
	return code


def _ensure_group(group: str) -> None:
	if frappe.db.exists("Item Group", group):
		return
	frappe.get_doc({"doctype": "Item Group", "item_group_name": group, "parent_item_group": "All Item Groups", "is_group": 0}).insert()


def _normalise_name(value: str) -> str:
	return " ".join((value or "").split()).casefold()


def _supplier_name(supplier: str) -> str:
	"""Resolve harmless whitespace/case variations without creating suppliers."""
	if frappe.db.exists("Supplier", supplier):
		return supplier
	wanted = _normalise_name(supplier)
	for row in frappe.get_all("Supplier", fields=["name", "supplier_name"]):
		if wanted in {_normalise_name(row.name), _normalise_name(row.supplier_name)}:
			return row.name
	return ""


def _add_supplier_and_price(item, supplier: str, rate: float) -> str:
	if not supplier:
		return "missing supplier"
	requested_supplier = supplier
	supplier = _supplier_name(requested_supplier)
	if not supplier:
		return f"supplier not found: {requested_supplier}"
	if supplier not in {row.supplier for row in item.get("supplier_items") or []}:
		item.append("supplier_items", {"supplier": supplier})
	if rate > 0:
		price = frappe.db.get_value("Item Price", {"item_code": item.name, "supplier": supplier, "buying": 1, "uom": "Nos"}, "name")
		if price:
			frappe.db.set_value("Item Price", price, "price_list_rate", rate)
		else:
			frappe.get_doc({"doctype": "Item Price", "item_code": item.name, "price_list": "Standard Buying", "price_list_rate": rate, "buying": 1, "supplier": supplier, "uom": "Nos"}).insert()
	return ""


def import_catalog_from_path(path: str) -> dict:
	"""Administrator-only development helper; production uses catalog file or Desk upload."""
	_require(ADMIN_ROLES)
	rows, exceptions = _workbook_rows(Path(path))
	return _import_catalog_rows(rows, exceptions, Path(path).name, "Workbook Import", "uploaded", _rows_checksum(rows))


@frappe.whitelist(methods=["POST"])
def preview_catalog_workbook(file_url: str) -> dict:
	_require(ADMIN_ROLES)
	rows, exceptions = _workbook_rows(_uploaded_file_path(file_url))
	return _catalog_preview(rows, exceptions, Path(file_url).name, _rows_checksum(rows))


@frappe.whitelist(methods=["POST"])
def import_catalog_workbook(file_url: str) -> dict:
	_require(ADMIN_ROLES)
	rows, exceptions = _workbook_rows(_uploaded_file_path(file_url))
	return _import_catalog_rows(rows, exceptions, Path(file_url).name, "Workbook Import", "uploaded", _rows_checksum(rows))


def import_packaged_catalog() -> dict:
	"""Import the versioned application asset during a production migration."""
	path = Path(frappe.get_app_path("construction_management", "data", "controlled_procurement_catalog_v1.json"))
	payload = json.loads(path.read_text())
	return _import_catalog_rows(
		payload["items"], [], payload["source_filename"], "Workbook Import",
		payload["version"], payload["checksum"],
	)


def _import_catalog_rows(rows, exceptions, source_name, source_type, version, checksum) -> dict:
	by_name = defaultdict(list)
	for row in rows:
		by_name[row["item_name"]].append(row)
	created = reused = 0
	for item_name, source_rows in by_name.items():
		first = source_rows[0]
		_ensure_group(first["item_group"])
		existing = frappe.db.get_value("Item", {"item_name": item_name, "stock_uom": "Nos", "disabled": 0}, "name")
		if existing:
			item = frappe.get_doc("Item", existing)
			reused += 1
		else:
			item = frappe.get_doc({
				"doctype": "Item", "item_code": _item_code(item_name), "item_name": item_name,
				"item_group": first["item_group"], "stock_uom": "Nos", "is_stock_item": 1,
				"is_purchase_item": 1, "is_fixed_asset": 0,
			})
			item.flags.controlled_procurement_api = True
			item.insert()
			created += 1
		item.controlled_procurement_catalog = 1
		item.controlled_item_type = STOCKABLE
		item.controlled_import_source = source_name
		item.controlled_imported_on = now_datetime()
		item.controlled_catalog_source = source_type
		item.controlled_catalog_version = version
		item.controlled_catalog_checksum = checksum
		for source in source_rows:
			error = _add_supplier_and_price(item, source["supplier"], source["rate"])
			if error:
				exceptions.append({"row": source["row"], "item": item_name, "reason": error})
		item.flags.controlled_procurement_api = True
		item.save()
	return {"created": created, "reused": reused, "exceptions": exceptions, "valid_rows": len(rows)}


def _catalog_preview(rows, exceptions, source_name, checksum) -> dict:
	preview = {"create": 0, "reuse": 0, "supplier_exceptions": list(exceptions)}
	by_name = defaultdict(list)
	for row in rows:
		by_name[row["item_name"]].append(row)
	for item_name, source_rows in by_name.items():
		if frappe.db.exists("Item", {"item_name": item_name, "stock_uom": "Nos", "disabled": 0}):
			preview["reuse"] += 1
		else:
			preview["create"] += 1
		for row in source_rows:
			if row.get("supplier") and not _supplier_name(row["supplier"]):
				preview["supplier_exceptions"].append({"row": row["row"], "item": item_name, "reason": f"supplier not found: {row['supplier']}"})
	return {"source": source_name, "checksum": checksum, "valid_rows": len(rows), **preview}


def _rows_checksum(rows) -> str:
	encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
	return hashlib.sha256(encoded).hexdigest()


def _uploaded_file_path(file_url: str) -> Path:
	file_doc = frappe.get_doc("File", {"file_url": file_url})
	if not file_doc.file_name.lower().endswith(".xlsx"):
		frappe.throw(_("Upload an Excel .xlsx workbook."))
	return Path(file_doc.get_full_path())


def validate_item(doc, method=None) -> None:
	if doc.is_new() and not _roles().intersection(ADMIN_ROLES) and not getattr(doc.flags, "controlled_procurement_api", False):
		frappe.throw(_("Only CEO and System Manager can create items."), frappe.PermissionError)
	if cint(doc.get("controlled_procurement_catalog")) and doc.stock_uom != "Nos":
		frappe.throw(_("Controlled catalog items must use Nos as their stock UOM."))


def _workspace_only() -> bool:
	"""Site config `controlled_procurement_workspace_only: 1` forces new POs, receipts and transfers
	through the Procurement app. Off by default, so Desk creation works as usual."""
	return bool(cint(frappe.conf.get("controlled_procurement_workspace_only")))


def validate_transaction(doc, method=None) -> None:
	from_workspace = getattr(doc.flags, "controlled_procurement_api", False)
	if doc.is_new() and not from_workspace:
		if _workspace_only() and not _roles().intersection(ADMIN_ROLES):
			frappe.throw(_("Create procurement documents from the Controlled Procurement workspace."), frappe.PermissionError)
		# Desk duplicates and mapped documents (e.g. a receipt made from a controlled PO) copy the
		# flag; a document created in Desk is a normal one, not a catalog-controlled one
		doc.controlled_procurement = 0
	if not cint(doc.get("controlled_procurement")):
		return
	if not getattr(doc.flags, "controlled_procurement_api", False) and not _roles().intersection(ADMIN_ROLES):
		frappe.throw(_("Edit or submit this document from the Controlled Procurement workspace."), frappe.PermissionError)
	_validate_allocation({field: doc.get(field) for field in ("project", "bill_no", "boq_item")})
	for row in doc.get("items") or []:
		item = _catalog_item(row.item_code)
		if row.uom != "Nos":
			frappe.throw(_("Controlled procurement items must use Nos."))
		_set_row_type(row, item)
		if doc.doctype == "Stock Entry" and (item.controlled_item_type != STOCKABLE or not cint(item.is_stock_item)):
			frappe.throw(_("Material Transfer accepts Stockable controlled items only."))
		_validate_allocation({field: row.get(field) for field in ("project", "bill_no", "boq_item")})
	if doc.doctype == "Purchase Receipt":
		_validate_receipt_allocations(doc)


def _validate_receipt_allocations(doc) -> None:
	for row in doc.get("items") or []:
		if not row.purchase_order_item:
			frappe.throw(_("Controlled Purchase Receipt items must come from a Purchase Order."))
		po_values = frappe.db.exists("Purchase Order Item", row.purchase_order_item)
		if not po_values:
			frappe.throw(_("Controlled Purchase Receipt items must come from a Purchase Order."))
		# allocation may be re-pointed at receipt time; it only has to be a valid Project/Bill/BOQ
		# set (checked by the caller) inside the receipt's company
		_validate_company_links(doc.company, project=row.get("project"))


def _document_list_fields(doctype: str) -> list[str]:
	fields = ["name", "project", "bill_no", "boq_item", "grand_total", "status", "docstatus", "modified"]
	if doctype == "Purchase Order":
		return fields + ["supplier", "supplier_name", "transaction_date", "schedule_date", "per_received", "per_billed", "controlled_procurement"]
	if doctype == "Purchase Receipt":
		return fields + ["supplier", "supplier_name", "posting_date", "controlled_procurement"]
	if doctype == "Purchase Invoice":
		return fields + ["supplier", "supplier_name", "posting_date", "due_date", "outstanding_amount", "custom_supplier_invoice_no", "is_paid"]
	return fields + ["posting_date", "purpose", "controlled_procurement", "total_outgoing_value"]


def _workspace_filters(doctype: str, filters: dict) -> dict:
	if doctype in ("Purchase Order", "Purchase Receipt"):
		return {**filters, "is_subcontracted": 0}
	if doctype == "Purchase Invoice":
		return {**filters, "is_subcontracted": 0, "is_return": 0}
	return filters


def _has_open_po_field() -> bool:
	return frappe.get_meta("Purchase Order").has_field("custom_is_provisional_po")


DOCUMENT_ROLES = {
	"Purchase Order": PURCHASE_ROLES,
	"Purchase Receipt": PURCHASE_ROLES,
	"Purchase Invoice": PURCHASE_ROLES,
	"Stock Entry": STOCK_ROLES,
}
CLOSED_PO_STATUSES = ("Closed", "Completed", "Delivered", "On Hold")


def _in_workspace(doc) -> bool:
	"""Every non-subcontracted PO is visible; receipts and transfers only when created here."""
	if doc.doctype in ("Purchase Order", "Purchase Receipt"):
		return not cint(doc.get("is_subcontracted"))
	if doc.doctype == "Purchase Invoice":
		return not cint(doc.get("is_subcontracted")) and not cint(doc.get("is_return"))
	return doc.get("purpose") == "Material Transfer"


def _controlled_doc(doctype: str, name: str, ptype: str = "read"):
	if doctype not in DOCUMENT_ROLES:
		frappe.throw(_("Unsupported controlled document type."))
	_require(DOCUMENT_ROLES[doctype])
	doc = frappe.get_doc(doctype, name)
	frappe.has_permission(doctype, ptype, doc=doc, throw=True)
	if not _in_workspace(doc):
		frappe.throw(_("This document is not part of Controlled Procurement."))
	return doc


@frappe.whitelist(methods=["GET"])
def get_open_lpos(search: str = "", supplier: str = "", project: str = "", start: int = 0, page_length: int = 50, controlled_only: int = 0, open_po_only: int = 0) -> dict:
	"""Submitted non-subcontracted LPOs that still have quantities waiting to be received."""
	_require(PURCHASE_ROLES)
	conditions = [
		"po.is_subcontracted = 0", "po.docstatus = 1", "po.per_received < 100",
		"po.status not in %(closed)s",
	]
	if cint(open_po_only):
		# the Open LPOs tab lists only POs ticked "Provisional / Open PO"
		if not _has_open_po_field():
			return {"rows": [], "total_count": 0, "summary": {"open_lpos": 0, "pending_value": 0, "overdue": 0}}
		conditions.append("po.custom_is_provisional_po = 1")
	if cint(controlled_only):
		# the workspace receipt form can only receive catalog-controlled orders
		conditions.append("po.controlled_procurement = 1")
	values = {"closed": CLOSED_PO_STATUSES, "today": frappe.utils.today()}
	company = _active_company()
	if company:
		conditions.append("po.company = %(company)s")
		values["company"] = company
	if supplier:
		conditions.append("po.supplier = %(supplier)s")
		values["supplier"] = supplier
	if project:
		conditions.append("po.project = %(project)s")
		values["project"] = project
	if search:
		conditions.append("(po.name like %(search)s or po.supplier_name like %(search)s or po.project like %(search)s)")
		values["search"] = f"%{search.strip()}%"
	# only list POs the user can read, then aggregate pending lines in SQL
	permitted = frappe.get_list(
		"Purchase Order", filters=_scoped({"is_subcontracted": 0, "docstatus": 1, "per_received": ["<", 100]}),
		pluck="name", limit_page_length=0,
	)
	if not permitted:
		return {"rows": [], "total_count": 0, "summary": {"open_lpos": 0, "pending_value": 0, "overdue": 0}}
	conditions.append("po.name in %(permitted)s")
	values["permitted"] = tuple(permitted)
	where = " and ".join(conditions)
	# "Provisional / Open PO" tick (redtra_customisation); receipts may exceed the ordered qty
	provisional = "po.custom_is_provisional_po" if _has_open_po_field() else "0"
	rows = frappe.db.sql(
		f"""
		select po.name, po.supplier, po.supplier_name, po.project, po.transaction_date, po.schedule_date,
			po.grand_total, po.per_received, po.per_billed, po.status, po.currency, po.controlled_procurement,
			{provisional} as is_open_po,
			sum(greatest(poi.qty - poi.received_qty, 0)) as pending_qty,
			sum(greatest(poi.qty - poi.received_qty, 0) * poi.rate) as pending_value,
			count(poi.name) as line_count,
			(po.schedule_date < %(today)s) as is_overdue,
			datediff(%(today)s, po.transaction_date) as age_days
		from `tabPurchase Order` po
		join `tabPurchase Order Item` poi on poi.parent = po.name
		where {where}
		group by po.name
		order by po.schedule_date asc, po.name asc
		""",
		values,
		as_dict=True,
	)
	summary = {
		"open_lpos": len(rows),
		"pending_value": sum(flt(row.pending_value) for row in rows),
		"overdue": sum(1 for row in rows if cint(row.is_overdue)),
	}
	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or 50, 1), 200)
	return {"rows": rows[start : start + page_length], "total_count": len(rows), "summary": summary}


@frappe.whitelist(methods=["GET"])
def get_document_activity(doctype: str, name: str) -> list[dict]:
	"""Comments and emails for a controlled document, newest first."""
	_controlled_doc(doctype, name)
	comments = frappe.get_all(
		"Comment",
		filters={"reference_doctype": doctype, "reference_name": name, "comment_type": "Comment"},
		fields=["name", "content", "owner", "comment_email", "creation"],
	)
	emails = frappe.get_all(
		"Communication",
		filters={"reference_doctype": doctype, "reference_name": name, "communication_medium": "Email"},
		fields=["name", "subject", "content", "sender", "recipients", "cc", "sent_or_received", "delivery_status", "has_attachment", "creation"],
	)
	users = {row.owner for row in comments} | {row.sender for row in emails}
	names = dict(frappe.get_all("User", filters={"name": ["in", list(users)]}, fields=["name", "full_name"], as_list=True)) if users else {}
	activity = [
		{"type": "comment", "name": row.name, "content": row.content, "by": names.get(row.owner) or row.owner, "creation": row.creation}
		for row in comments
	] + [
		{
			"type": "email", "name": row.name, "subject": row.subject, "content": row.content,
			"by": names.get(row.sender) or row.sender, "recipients": row.recipients, "cc": row.cc,
			"direction": row.sent_or_received, "status": row.delivery_status,
			"has_attachment": row.has_attachment, "creation": row.creation,
		}
		for row in emails
	]
	return sorted(activity, key=lambda row: row["creation"], reverse=True)


@frappe.whitelist(methods=["POST"])
def add_document_comment(doctype: str, name: str, content: str) -> dict:
	_controlled_doc(doctype, name)
	if not (content or "").strip():
		frappe.throw(_("Comment cannot be empty."))
	comment = frappe.get_doc({
		"doctype": "Comment", "comment_type": "Comment", "reference_doctype": doctype, "reference_name": name,
		"comment_email": frappe.session.user, "comment_by": frappe.utils.get_fullname(frappe.session.user),
		"content": frappe.utils.sanitize_html(content),
	})
	comment.insert(ignore_permissions=True)
	return {"name": comment.name}


@frappe.whitelist(methods=["GET"])
def get_email_draft(doctype: str, name: str) -> dict:
	"""Default recipients, subject, and print formats for the email composer."""
	doc = _controlled_doc(doctype, name)
	# the document's contact person first, then the supplier's own email
	recipients = doc.get("contact_email") or ""
	if not recipients and doc.get("supplier"):
		recipients = frappe.db.get_value("Supplier", doc.supplier, "email_id") or ""
	meta = frappe.get_meta(doctype)
	print_formats = ["Standard"] + frappe.get_all(
		"Print Format", filters={"doc_type": doctype, "disabled": 0}, pluck="name", order_by="name asc"
	)
	return {
		"recipients": recipients,
		"subject": f"{doctype}: {doc.name}",
		"message": _("Dear {0},<br><br>Please find attached {1} {2}.<br><br>Regards,<br>{3}").format(
			(doc.get("supplier_name") or doc.get("supplier") or _("Sir/Madam")).strip(), doctype, doc.name,
			frappe.utils.get_fullname(frappe.session.user),
		),
		"print_formats": print_formats,
		"default_print_format": meta.default_print_format or "Standard",
		"email_templates": frappe.get_all(
			"Email Template",
			or_filters=[["reference_doctype", "=", doctype], ["reference_doctype", "is", "not set"], ["reference_doctype", "=", ""]],
			pluck="name", order_by="name asc",
		),
		"can_email": bool(frappe.has_permission(doctype, "email", doc=doc)),
	}


CONTACT_FIELDS = ["name", "first_name", "last_name", "full_name", "designation", "email_id", "phone", "mobile_no", "is_primary_contact"]


@frappe.whitelist(methods=["GET"])
def get_supplier_contacts(supplier: str) -> list[dict]:
	"""Contacts linked to a supplier, primary first."""
	_require(PURCHASE_ROLES)
	frappe.has_permission("Supplier", "read", doc=supplier, throw=True)
	names = frappe.get_all(
		"Dynamic Link", filters={"link_doctype": "Supplier", "link_name": supplier, "parenttype": "Contact"}, pluck="parent"
	)
	if not names:
		return []
	return frappe.get_all(
		"Contact", filters={"name": ["in", names]}, fields=CONTACT_FIELDS,
		order_by="is_primary_contact desc, full_name asc",
	)


def _set_primary_child(contact, table: str, value_field: str, primary_field: str, value: str) -> None:
	"""Make `value` the primary entry of a Contact child table, adding it if missing."""
	value = (value or "").strip()
	if not value:
		return
	found = False
	for row in contact.get(table):
		is_match = row.get(value_field) == value
		row.set(primary_field, 1 if is_match else 0)
		found = found or is_match
	if not found:
		contact.append(table, {value_field: value, primary_field: 1})


@frappe.whitelist(methods=["POST"])
def save_supplier_contact(supplier: str, data: str | dict) -> dict:
	"""Create a supplier contact, or correct an existing one's name, email and numbers."""
	_require(PURCHASE_ROLES)
	data = _as_dict(data)
	if not (data.get("first_name") or "").strip():
		frappe.throw(_("First name is required."))
	if data.get("name"):
		contact = frappe.get_doc("Contact", data["name"])
		contact.check_permission("write")
		if not any(link.link_doctype == "Supplier" and link.link_name == supplier for link in contact.links):
			frappe.throw(_("Contact {0} is not linked to supplier {1}.").format(contact.name, supplier))
	else:
		frappe.has_permission("Supplier", "read", doc=supplier, throw=True)
		contact = frappe.new_doc("Contact")
		contact.append("links", {"link_doctype": "Supplier", "link_name": supplier})
	for field in ("first_name", "last_name", "designation"):
		contact.set(field, (data.get(field) or "").strip())
	_set_primary_child(contact, "email_ids", "email_id", "is_primary", data.get("email_id"))
	_set_primary_child(contact, "phone_nos", "phone", "is_primary_phone", data.get("phone"))
	_set_primary_child(contact, "phone_nos", "phone", "is_primary_mobile_no", data.get("mobile_no"))
	contact.save()
	return frappe.db.get_value("Contact", contact.name, CONTACT_FIELDS, as_dict=True)


@frappe.whitelist(methods=["GET"])
def get_warehouse_project(warehouse: str) -> str:
	"""Project a site warehouse belongs to; receipts into it are always booked to that project."""
	from construction_management.api.purchase_receipt_utils import get_warehouse_project as resolve

	_require(PURCHASE_ROLES | STOCK_ROLES)
	company = frappe.db.get_value("Warehouse", warehouse, "company")
	return resolve(warehouse, company=company) or ""


@frappe.whitelist(methods=["GET"])
def get_terms_template(template: str) -> str:
	"""Terms text from a Terms and Conditions template."""
	_require(PURCHASE_ROLES)
	tnc = frappe.get_doc("Terms and Conditions", template)
	tnc.check_permission("read")
	return tnc.terms or ""


@frappe.whitelist(methods=["GET"])
def get_print_options(doctype: str, name: str) -> dict:
	"""Print formats and letterheads available for a workspace document."""
	doc = _controlled_doc(doctype, name)
	formats = frappe.get_all("Print Format", filters={"doc_type": doctype, "disabled": 0}, pluck="name", order_by="name asc")
	default = frappe.get_meta(doctype).default_print_format
	return {
		"print_formats": ["Standard", *formats],
		"default_print_format": default if default in formats else "Standard",
		"letterheads": frappe.get_all("Letter Head", filters={"disabled": 0}, pluck="name", order_by="is_default desc, name asc"),
		# the document's own letterhead, then its company's, then the site default
		"default_letterhead": doc.get("letter_head")
		or frappe.db.get_value("Company", doc.company, "default_letter_head")
		or frappe.db.get_value("Letter Head", {"is_default": 1, "disabled": 0}, "name"),
	}


@frappe.whitelist(methods=["GET"])
def get_rendered_email_template(doctype: str, name: str, template: str) -> dict:
	"""Render an Email Template's subject and body against a controlled document."""
	doc = _controlled_doc(doctype, name)
	email_template = frappe.get_doc("Email Template", template)
	email_template.check_permission("read")
	return email_template.get_formatted_email(doc.as_dict())


@frappe.whitelist(methods=["POST"])
def send_document_email(
	doctype: str, name: str, recipients: str, subject: str, message: str = "",
	cc: str = "", attach_print: int = 1, print_format: str = "", email_template: str = "",
) -> dict:
	"""Send a controlled document by email; the Communication appears in the activity feed."""
	from frappe.core.doctype.communication.email import make

	_controlled_doc(doctype, name)
	if not (recipients or "").strip():
		frappe.throw(_("Add at least one recipient."))
	result = make(
		doctype=doctype, name=name, content=message, subject=subject, recipients=recipients, cc=cc or None,
		send_email=1, print_format=(print_format or "Standard") if cint(attach_print) else None,
		email_template=email_template or None,
	)
	return {"name": result.get("name"), "emails_not_sent_to": result.get("emails_not_sent_to")}
