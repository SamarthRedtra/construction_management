# Copyright (c) 2026, Construction Management
# License: MIT

"""Controlled catalog import and standard ERPNext procurement document creation."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from io import BytesIO
from pathlib import Path
from uuid import UUID

import frappe
from frappe import _
from frappe.utils.file_manager import save_file
from frappe.utils import cint, flt, getdate, now_datetime, today


ADMIN_ROLES = {"System Manager", "CEO"}
PURCHASE_ROLES = ADMIN_ROLES | {"Purchase User", "Purchase Manager"}
STOCK_ROLES = ADMIN_ROLES | {"Stock User", "Stock Manager"}
ACCOUNT_ROLES = {"Accounts User", "Accounts Manager"}
CATALOG_ROLES = PURCHASE_ROLES | STOCK_ROLES | ACCOUNT_ROLES
OPENING_STOCK_ROLES = ACCOUNT_ROLES | ADMIN_ROLES
STOCKABLE = "Stockable"
ASSET = "Asset"
SERVICE = "Service"
SUPPLIER_TYPES = {"Company", "Individual", "Partnership"}
ALLOCATION_FIELDS = ("project", "bill_no", "boq_item")
EMPTY_ALLOCATION_VALUES = {"", "null", "undefined"}


def _roles() -> set[str]:
	return set(frappe.get_roles())


def _require(roles: set[str]) -> None:
	if not _roles().intersection(roles):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _as_dict(value: str | dict | None) -> dict:
	if isinstance(value, str):
		return frappe.parse_json(value)
	return value or {}


def _normalized_allocation(values: dict) -> dict:
	"""Remove browser placeholder values before applying BOQ allocation rules."""
	allocation = {}
	for field in ALLOCATION_FIELDS:
		value = values.get(field)
		value = value.strip() if isinstance(value, str) else value
		allocation[field] = "" if value is None or str(value).casefold() in EMPTY_ALLOCATION_VALUES else value
	return allocation


def _catalog_item(item_code: str) -> dict:
	item = frappe.db.get_value(
		"Item", item_code,
		["name", "stock_uom", "is_stock_item", "is_fixed_asset", "controlled_procurement_catalog", "controlled_item_type"],
		as_dict=True,
	)
	if not item or not cint(item.controlled_procurement_catalog) or item.stock_uom != "Nos":
		frappe.throw(_("Item {0} is not in the controlled Nos catalog.").format(item_code))
	return item


def _payment_terms_template(value: str | None) -> str | None:
	value = (value or "").strip()
	if value and not frappe.db.exists("Payment Terms Template", value):
		frappe.throw(_("Payment Terms Template {0} does not exist.").format(value))
	return value or None


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
	if doc.doctype != "Stock Entry":
		_apply_allocation(row, row_data, defaults, doc.company)
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


def _item_has_supplier(item_code: str, supplier: str) -> bool:
	return bool(supplier and frappe.db.exists("Item Supplier", {
		"parent": item_code, "parenttype": "Item", "supplier": supplier,
	}))


def _validate_order_supplier_items(data: dict, items: list[dict], existing=None) -> None:
	"""Limit new Standard/Open orders to one supplier-linked catalog item."""
	lpo_type = data.get("lpo_type") or "Standard"
	if lpo_type not in {"Standard", "Open"}:
		return
	if existing:
		if len(items) > len(existing.items):
			frappe.throw(_("New item lines cannot be added to an existing Purchase Order here."))
	else:
		if len(items) != 1:
			frappe.throw(_("Standard and Open LPOs require exactly one item line."))
	supplier = data.get("supplier") or ""
	if not supplier:
		frappe.throw(_("Select a supplier before choosing an item."))
	previous_type = (existing.get("custom_lpo_type") or ("Open" if existing.get("custom_is_provisional_po") else "Standard")) if existing else ""
	legacy_items = Counter(row.item_code for row in existing.items) if existing and existing.supplier == supplier and previous_type in {"Standard", "Open"} else Counter()
	for row in items:
		item_code = row["item_code"]
		if legacy_items[item_code]:
			legacy_items[item_code] -= 1
		elif not _item_has_supplier(item_code, supplier):
			frappe.throw(_("Item {0} is not linked to supplier {1}.").format(item_code, supplier))


def _document_company(company: str | None) -> str:
	"""Resolve an explicit company or the active workspace company for a new document."""
	company = company or _active_company()
	if not company:
		frappe.throw(_("Select a company before creating a controlled procurement document."))
	if company not in _allowed_companies():
		frappe.throw(_("You do not have access to company {0}.").format(company), frappe.PermissionError)
	return company


def _allocation_defaults(data: dict, company: str | None = None) -> dict:
	defaults = _normalized_allocation(data)
	_validate_allocation(defaults, company or _document_company(data.get("company")))
	return defaults


def _apply_allocation(row, row_data: dict, defaults: dict, company: str = "") -> None:
	row_allocation = _normalized_allocation(row_data)
	allocation = {field: row_allocation[field] or defaults[field] for field in defaults}
	_validate_allocation(allocation, company)
	for field, value in allocation.items():
		setattr(row, field, value)


def _is_mrg_company(company: str | None) -> bool:
	if not company:
		return False
	abbr = frappe.db.get_value("Company", company, "abbr") or ""
	return "MRG" in company.upper() or abbr.upper() == "MRG"


def _boq_allocation_mode(company: str | None) -> str:
	"""How much of Project / Bill No / BOQ Item a company's procurement documents must carry.

	"required": all three (SKADA, and any company not configured otherwise).
	"project_only": Project is mandatory, Bill No and BOQ Item are optional (MRG).
	"""
	from construction_management.api.project_numbering import is_skada_company

	if is_skada_company(company):
		return "required"
	if _is_mrg_company(company):
		return "project_only"
	return "required"


def _validate_allocation(allocation: dict, company: str | None = None, mode: str | None = None) -> None:
	"""Check Project / Bill No / BOQ Item against the company's rule (or an explicit `mode`)."""
	allocation = _normalized_allocation(allocation)
	project = allocation.get("project")
	bill_no = allocation.get("bill_no")
	boq_item = allocation.get("boq_item")
	if not project:
		frappe.throw(_("Project is required for controlled procurement."))
	if (mode or _boq_allocation_mode(company)) == "required" and (not bill_no or not boq_item):
		frappe.throw(_("Project, Bill No, and BOQ Item are required for controlled procurement."))
	if boq_item and not bill_no:
		frappe.throw(_("Select the Bill No for BOQ Item {0}.").format(boq_item))

	frappe.has_permission("Project", "read", doc=frappe.get_doc("Project", project), throw=True)
	# whatever is filled in must belong together
	if bill_no:
		bill = frappe.db.get_value("BOQ Bill", bill_no, ["project"], as_dict=True)
		if not bill or bill.project != project:
			frappe.throw(_("Bill No {0} does not belong to Project {1}.").format(bill_no, project))
	if boq_item:
		item = frappe.db.get_value("BOQ Item", boq_item, ["project", "parent_bill"], as_dict=True)
		if not item or item.project != project or item.parent_bill != bill_no:
			frappe.throw(_("Bill No and BOQ Item must belong to the selected Project."))


CATALOG_SORT_FIELDS = {
	"item_name": "item.item_name",
	"name": "item.name",
	"item_group": "item.item_group",
	"controlled_item_type": "item.controlled_item_type",
	"controlled_catalog_source": "item.controlled_catalog_source",
	"actual_qty": "COALESCE(stock.actual_qty, 0)",
}


@frappe.whitelist(methods=["GET"])
def get_catalog(
	company: str = "", search: str = "", start: int = 0, page_length: int = 50,
	item_type: str = "", item_group: str = "", source: str = "", stock_status: str = "",
	sort_by: str = "item_name", sort_order: str = "asc", supplier: str = "",
) -> dict:
	"""Filter and sort the full approved catalog before pagination."""
	_require(CATALOG_ROLES)
	company = _document_company(company)
	if sort_by not in CATALOG_SORT_FIELDS or sort_order.lower() not in {"asc", "desc"}:
		frappe.throw(_("Invalid catalog sort option."))
	if stock_status not in {"", "in_stock", "out_of_stock"}:
		frappe.throw(_("Invalid stock filter."))
	if item_type and item_type not in {STOCKABLE, ASSET, SERVICE}:
		frappe.throw(_("Invalid catalog item type."))

	conditions = ["item.disabled = 0", "item.is_purchase_item = 1", "item.controlled_procurement_catalog = 1", "item.stock_uom = 'Nos'"]
	params = {"company": company, "start": max(cint(start), 0), "page_length": min(max(cint(page_length) or 50, 1), 100)}
	if search.strip():
		conditions.append("(item.item_name LIKE %(search)s OR item.name LIKE %(search)s)")
		params["search"] = f"%{search.strip()}%"
	for value, column, key in ((item_type, "controlled_item_type", "item_type"), (item_group, "item_group", "item_group"), (source, "controlled_catalog_source", "source")):
		if value:
			conditions.append(f"item.{column} = %({key})s")
			params[key] = value
	if stock_status:
		conditions.append("item.controlled_item_type = 'Stockable'")
		conditions.append("COALESCE(stock.actual_qty, 0) > 0" if stock_status == "in_stock" else "COALESCE(stock.actual_qty, 0) <= 0")
	if supplier:
		conditions.append("EXISTS (SELECT 1 FROM `tabItem Supplier` item_supplier WHERE item_supplier.parent = item.name AND item_supplier.parenttype = 'Item' AND item_supplier.supplier = %(supplier)s)")
		params["supplier"] = supplier

	from_clause = """FROM `tabItem` item
	LEFT JOIN (
		SELECT bin.item_code, SUM(bin.actual_qty) AS actual_qty
		FROM `tabBin` bin
		JOIN `tabWarehouse` warehouse ON warehouse.name = bin.warehouse
		WHERE warehouse.company = %(company)s AND warehouse.is_group = 0
		GROUP BY bin.item_code
	) stock ON stock.item_code = item.name"""
	where_clause = " AND ".join(conditions)
	order_clause = f"{CATALOG_SORT_FIELDS[sort_by]} {sort_order.upper()}, item.name ASC"
	rows = frappe.db.sql(
		f"""SELECT item.name, item.item_name, item.item_group, item.stock_uom,
		item.controlled_item_type, item.controlled_catalog_source,
		COALESCE(stock.actual_qty, 0) AS actual_qty
		{from_clause} WHERE {where_clause}
		ORDER BY {order_clause} LIMIT %(page_length)s OFFSET %(start)s""",
		params, as_dict=True,
	)
	total_count = frappe.db.sql(
		f"SELECT COUNT(*) {from_clause} WHERE {where_clause}", params,
	)[0][0]
	return {"rows": rows, "total_count": total_count}


@frappe.whitelist(methods=["GET"])
def get_catalog_supplier_match(item_code: str, supplier: str) -> dict:
	"""Check whether an already selected catalog item belongs to a new PO supplier."""
	_require(PURCHASE_ROLES)
	_catalog_item(item_code)
	return {"eligible": _item_has_supplier(item_code, supplier)}


@frappe.whitelist(methods=["GET"])
def get_catalog_item_suppliers(item_code: str, company: str = "") -> list[dict]:
	"""Return visible, active suppliers linked to an approved buying item."""
	_require(PURCHASE_ROLES)
	_document_company(company)
	_catalog_item(item_code)
	if frappe.db.get_value("Item", item_code, "disabled") or not frappe.db.get_value("Item", item_code, "is_purchase_item"):
		frappe.throw(_("Select an active buying item from the controlled catalog."))
	suppliers = frappe.get_all("Item Supplier", filters={"parent": item_code, "parenttype": "Item"}, pluck="supplier", limit_page_length=0)
	if not suppliers:
		return []
	return frappe.get_list("Supplier", filters={"name": ["in", sorted(set(suppliers))], "disabled": 0},
		fields=["name", "supplier_name"], order_by="supplier_name asc", limit_page_length=0)


@frappe.whitelist(methods=["GET"])
def get_catalog_filter_options() -> dict:
	"""Return selectable groups and sources used by approved catalog items."""
	_require(CATALOG_ROLES)
	filters = {"disabled": 0, "is_purchase_item": 1, "controlled_procurement_catalog": 1, "stock_uom": "Nos"}
	rows = frappe.get_all("Item", filters=filters, fields=["item_group", "controlled_catalog_source"], limit_page_length=0)
	return {
		"item_groups": sorted({row.item_group for row in rows if row.item_group}),
		"sources": sorted({row.controlled_catalog_source for row in rows if row.controlled_catalog_source}),
	}


def _catalog_stock_totals(item_codes: list[str], company: str) -> dict[str, float]:
	if not item_codes or not company:
		return {}
	rows = frappe.db.sql(
		"""select bin.item_code, sum(bin.actual_qty) as actual_qty
		from `tabBin` bin join `tabWarehouse` warehouse on warehouse.name = bin.warehouse
		where bin.item_code in %(items)s and warehouse.company = %(company)s and warehouse.is_group = 0
		group by bin.item_code""",
		{"items": item_codes, "company": company}, as_dict=True,
	)
	return {row.item_code: flt(row.actual_qty) for row in rows}


def _allowed_companies() -> list[str]:
	"""Companies the user can access, preferring explicit Company User Permissions."""
	permitted_companies = frappe.get_all(
		"User Permission",
		filters={"user": frappe.session.user, "allow": "Company"},
		pluck="for_value",
	)
	if permitted_companies:
		return sorted(set(permitted_companies))
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
	_require(CATALOG_ROLES)
	if company not in _allowed_companies():
		frappe.throw(_("You do not have access to company {0}.").format(company), frappe.PermissionError)
	# Desk stores the session default under the scrubbed key; get_user_default reads it from there
	frappe.defaults.set_user_default("company", company)
	return get_workspace_context()


@frappe.whitelist(methods=["GET"])
def get_workspace_context() -> dict:
	"""Return permissions, defaults, and safe dashboard totals for the Vue workspace."""
	roles = _roles()
	if not roles.intersection(CATALOG_ROLES):
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
		"can_manage_catalog": bool(roles.intersection(CATALOG_ROLES)),
		"can_approve_catalog": bool(roles.intersection(ACCOUNT_ROLES | ADMIN_ROLES)),
		"can_request_price_change": bool(roles.intersection(CATALOG_ROLES)),
		"can_approve_price_change": _explicit_ceo(),
		"can_approve_po_price_accounts": any(frappe.db.exists("Has Role", {
			"parent": frappe.session.user, "parenttype": "User", "role": role,
		}) for role in ACCOUNT_ROLES),
		"can_opening_stock": bool(roles.intersection(OPENING_STOCK_ROLES)),
		"can_approve_lpo": bool(roles.intersection(ACCOUNT_ROLES | ADMIN_ROLES)),
		"can_approve_lpo_accounts": bool(roles.intersection(ACCOUNT_ROLES | {"System Manager"})),
		"can_approve_lpo_ceo": bool(roles.intersection(ADMIN_ROLES)),
		"can_override_lpo": "System Manager" in roles,
		"can_view_insights": bool(roles.intersection(CATALOG_ROLES)),
		"can_view_stock_ledger": bool(roles.intersection(ACCOUNT_ROLES | ADMIN_ROLES)),
		"boq_allocation_mode": _boq_allocation_mode(company),
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
				"is_subcontracted": 0, "docstatus": 1, "custom_is_provisional_po": 1,
				"status": ["not in", ("Closed", "On Hold")],
			})),
		},
	}


DOCUMENT_SORT_FIELDS = {
	"Purchase Order": {"modified": "modified", "name": "name", "supplier": "supplier_name", "project": "project", "date": "transaction_date", "status": "status", "value": "grand_total", "received": "per_received"},
	"Purchase Receipt": {"modified": "modified", "name": "name", "supplier": "supplier_name", "project": "project", "date": "posting_date", "status": "status", "value": "grand_total"},
	"Purchase Invoice": {"modified": "modified", "name": "name", "supplier": "supplier_name", "project": "project", "date": "posting_date", "status": "status", "value": "grand_total"},
	"Stock Entry": {"modified": "modified", "name": "name", "project": "project", "date": "posting_date", "status": "status", "value": "total_outgoing_value"},
}


@frappe.whitelist(methods=["GET"])
def get_controlled_documents(doctype: str, search: str = "", start: int = 0, page_length: int = 25, submitted_only: int = 0, docstatus: str = "", supplier: str = "", project: str = "", lpo_type: str = "", purchase_order: str = "", warehouse: str = "", from_warehouse: str = "", to_warehouse: str = "", item_code: str = "", date_from: str = "", date_to: str = "", sort_by: str = "modified", sort_order: str = "desc") -> dict:
	"""List documents that belong to the controlled workspace.

	`docstatus` also accepts "unpaid" and "overdue" for purchase invoices.
	"""
	if doctype not in DOCUMENT_ROLES:
		frappe.throw(_("Unsupported controlled document type."))
	_require(DOCUMENT_ROLES[doctype])
	if sort_by not in DOCUMENT_SORT_FIELDS[doctype] or sort_order.lower() not in {"asc", "desc"}:
		frappe.throw(_("Invalid document sort option."))
	company = _document_company(None)
	filters = _workspace_filters(doctype, {"company": company, "docstatus": ["<", 3 if doctype in {"Purchase Order", "Purchase Receipt", "Stock Entry"} else 2]})
	if doctype == "Stock Entry":
		filters["purpose"] = "Material Transfer"
	if cint(submitted_only):
		filters["docstatus"] = 1
	elif docstatus in ({"0", "1", "2"} if doctype in {"Purchase Order", "Purchase Receipt", "Stock Entry"} else {"0", "1"}):
		filters["docstatus"] = cint(docstatus)
	elif doctype == "Purchase Invoice" and docstatus in {"unpaid", "overdue"}:
		filters.update({"docstatus": 1, "outstanding_amount": [">", 0]})
		if docstatus == "overdue":
			filters["due_date"] = ["<", frappe.utils.today()]
	if supplier and doctype in {"Purchase Order", "Purchase Receipt"}:
		filters["supplier"] = supplier
	matching_names = None

	def narrow_to(names):
		nonlocal matching_names
		names = set(names)
		matching_names = names if matching_names is None else matching_names & names

	if project:
		if doctype in {"Purchase Order", "Purchase Receipt"}:
			header_names = frappe.get_all(doctype, filters={"company": company, "project": project}, pluck="name", limit_page_length=0)
			line_names = frappe.get_all(f"{doctype} Item", filters={"project": project}, pluck="parent", limit_page_length=0)
			narrow_to(header_names + line_names)
		else:
			filters["project"] = project
	if lpo_type and doctype == "Purchase Order":
		if lpo_type not in {"Standard", "Open", "Manual"}:
			frappe.throw(_("Invalid LPO type."))
		if lpo_type in {"Standard", "Open"}:
			narrow_to(row.name for row in frappe.get_all("Purchase Order", filters={"company": company},
				fields=["name", "custom_lpo_type", "custom_is_provisional_po"], limit_page_length=0)
				if row.custom_lpo_type == lpo_type or (not row.custom_lpo_type and ("Open" if cint(row.custom_is_provisional_po) else "Standard") == lpo_type))
		else:
			filters["custom_lpo_type"] = lpo_type
	if date_from or date_to:
		date_field = "transaction_date" if doctype == "Purchase Order" else "posting_date"
		if date_from and date_to and getdate(date_from) > getdate(date_to):
			frappe.throw(_("From date must be before To date."))
		filters[date_field] = ["between", [str(getdate(date_from or "1900-01-01")), str(getdate(date_to or "2999-12-31"))]]
	if doctype == "Purchase Receipt" and purchase_order:
		narrow_to(frappe.get_all("Purchase Receipt Item", filters={"purchase_order": purchase_order}, pluck="parent", limit_page_length=0))
	if doctype == "Purchase Receipt" and warehouse:
		narrow_to(frappe.get_all("Purchase Receipt Item", filters={"warehouse": warehouse}, pluck="parent", limit_page_length=0))
	if doctype == "Stock Entry":
		for field, value in (("from_warehouse", from_warehouse), ("to_warehouse", to_warehouse)):
			if value:
				filters[field] = value
		if item_code:
			narrow_to(frappe.get_all("Stock Entry Detail", filters={"item_code": item_code}, pluck="parent", limit_page_length=0))
	if matching_names is not None:
		filters["name"] = ["in", sorted(matching_names)]
	fields = _document_list_fields(doctype)
	or_filters = None
	if search:
		like = f"%{search.strip()}%"
		or_filters = [["name", "like", like], ["project", "like", like]]
		if doctype != "Stock Entry":
			or_filters.append(["supplier_name", "like", like])
		if doctype == "Purchase Invoice":
			or_filters.append(["custom_supplier_invoice_no", "like", like])
		if doctype == "Purchase Receipt":
			or_filters.append(["supplier_delivery_note", "like", like])
		if doctype == "Purchase Order":
			or_filters.append(["custom_lpo_reference", "like", like])
	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or 25, 1), 100)
	order_by = f"{DOCUMENT_SORT_FIELDS[doctype][sort_by]} {sort_order.lower()}, name asc"
	return {
		"rows": frappe.get_list(doctype, filters=filters, or_filters=or_filters, fields=fields, order_by=order_by, limit_start=start, limit_page_length=page_length),
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
		from construction_management.api.lpo_workflow import lpo_type
		result["custom_lpo_type"] = lpo_type(doc)
		result["approval_history"] = json.loads(doc.get("custom_lpo_approval_history") or "[]")
		result["can_cancel"] = bool(frappe.has_permission("Purchase Order", "cancel", doc=doc))
		result["can_amend"] = bool(frappe.has_permission("Purchase Order", "amend", doc=doc))
	if doctype in {"Purchase Receipt", "Stock Entry"}:
		result["can_cancel"] = bool(frappe.has_permission(doctype, "cancel", doc=doc))
		result["can_amend"] = bool(frappe.has_permission(doctype, "amend", doc=doc))
	if doctype == "Stock Entry":
		result["source_project"] = get_warehouse_project(doc.from_warehouse) if doc.from_warehouse else ""
		result["target_project"] = get_warehouse_project(doc.to_warehouse) if doc.to_warehouse else ""
	if doc.get("amended_from"):
		result["previous_revision"] = doc.amended_from
	result["next_revision"] = frappe.db.get_value(doctype, {"amended_from": name}, "name")
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


def _connection_rows(doctype: str, names: list[str], company: str = "") -> list[dict]:
	"""Status, date and amount for each linked document (whatever fields that doctype has)."""
	if not names:
		return []
	meta = frappe.get_meta(doctype)
	fields = ["name", "docstatus"] + [field for field in ("status", "title") if meta.has_field(field)]
	date_field = next((field for field in CONNECTION_DATE_FIELDS if meta.has_field(field)), None)
	amount_field = next((field for field in CONNECTION_AMOUNT_FIELDS if meta.has_field(field)), None)
	fields += [f"{date_field} as date"] if date_field else []
	fields += [f"{amount_field} as amount"] if amount_field else []
	if not meta.is_submittable:
		fields.remove("docstatus")
	filters = {"name": ["in", names]}
	if company and meta.has_field("company"):
		filters["company"] = company
	return frappe.get_list(doctype, filters=filters, fields=fields, order_by="creation desc", limit_page_length=50)


def _receipt_direct_connections(doc) -> list[tuple[str, str, list[str]]]:
	"""Find source and downstream documents even when Desk's dashboard omits them."""
	po_names = {row.purchase_order for row in doc.items if row.purchase_order}
	if doc.get("custom_purchase_order"):
		po_names.add(doc.custom_purchase_order)
	invoice_names = frappe.get_all(
		"Purchase Invoice Item", filters={"purchase_receipt": doc.name}, pluck="parent", distinct=True, limit_page_length=50,
	)
	return_names = frappe.get_all(
		"Purchase Receipt", filters={"return_against": doc.name, "company": doc.company}, pluck="name", limit_page_length=50,
	)
	return [
		(_("Source"), "Purchase Order", sorted(po_names)),
		(_("Related"), "Purchase Invoice", invoice_names),
		(_("Returns"), "Purchase Receipt", return_names),
	]


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
	seen = defaultdict(set)
	if doctype == "Purchase Receipt":
		for label, target, names in _receipt_direct_connections(doc):
			if not names or not frappe.has_permission(target, "read"):
				continue
			rows = _connection_rows(target, names, doc.company)
			if rows:
				groups.append({"label": label, "items": [{"doctype": target, "count": len(rows), "documents": rows}]})
				seen[target].update(row.name for row in rows)
	for group in links.transactions:
		items = []
		for target in group.get("items") or []:
			found = found_by_doctype.get(target)
			if not found or not frappe.has_permission(target, "read"):
				continue
			names = [n for n in _connection_names(doctype, name, target, found, links) if n not in seen[target]]
			rows = _connection_rows(target, names, doc.company)
			if rows:
				items.append({"doctype": target, "count": len(rows), "documents": rows})
				seen[target].update(row.name for row in rows)
		if items:
			label = group.get("label") or _("Related")
			existing_group = next((entry for entry in groups if entry["label"] == label), None)
			if existing_group:
				existing_group["items"].extend(items)
			else:
				groups.append({"label": label, "items": items})

	# post-dated cheques reserve invoice amounts but are not in ERPNext's dashboard config
	if doctype == "Purchase Invoice" and frappe.db.table_exists("PDC Invoice Reference") and frappe.has_permission("Post Dated Cheques", "read"):
		pdcs = frappe.get_all("PDC Invoice Reference", filters={"reference_doctype": doctype, "reference_name": name}, pluck="parent", distinct=True)
		if pdcs:
			item = {"doctype": "Post Dated Cheques", "count": len(pdcs), "documents": _connection_rows("Post Dated Cheques", pdcs, doc.company)}
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
def get_procurement_projects(search: str = "", selected: str = "", company: str = "") -> list[dict]:
	"""Permission-aware Project choices with both the stored ID and display name."""
	_require(PURCHASE_ROLES | STOCK_ROLES)
	filters = {"company": _document_company(company)}
	if selected:
		filters["name"] = selected
	return frappe.get_list("Project", filters=filters,
		or_filters=[["name", "like", f"%{search.strip()}%"], ["project_name", "like", f"%{search.strip()}%"]] if search.strip() and not selected else None,
		fields=["name", "project_name"], order_by="name asc", limit_page_length=1 if selected else 20)


@frappe.whitelist(methods=["GET"])
def get_purchase_order_items(purchase_order: str) -> list[dict]:
	"""Return receivable PO lines; Open LPO lines remain available after full receipt."""
	_require(PURCHASE_ROLES)
	po = _controlled_doc("Purchase Order", purchase_order)
	if po.docstatus != 1:
		frappe.throw(_("Select a submitted Purchase Order."))
	open_lpo = _is_open_lpo(po)
	_validate_receivable_po(po, open_lpo)
	return [
		{
			"purchase_order_item": row.name,
			"item_code": row.item_code,
			"item_name": row.item_name,
			"remaining_qty": max(flt(row.qty) - flt(row.received_qty), 0),
			"is_open_lpo": open_lpo,
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
		if not cint(row.get("closed")) and not cint(row.get("delivered_by_supplier"))
		and (open_lpo or flt(row.qty) > flt(row.received_qty))
	]


@frappe.whitelist(methods=["POST"])
def create_controlled_item(data: str | dict) -> dict:
	"""Create a manual catalog request; CEO/System Manager requests approve immediately."""
	data = _as_dict(data)
	return create_catalog_request({"company": data.get("company"), "source": "Manual", "items": [data]})


@frappe.whitelist(methods=["POST"])
def create_purchase_order(data: str | dict) -> dict:
	_require(PURCHASE_ROLES)
	data = _as_dict(data)
	company = _document_company(data.get("company"))
	raw_request_id = data.get("creation_request_id") or ""
	if not isinstance(raw_request_id, str):
		frappe.throw(_("Invalid Purchase Order creation request ID."))
	request_id = raw_request_id.strip()
	if request_id:
		try:
			if str(UUID(request_id)) != request_id:
				raise ValueError
		except (ValueError, TypeError):
			frappe.throw(_("Invalid Purchase Order creation request ID."))
		existing = _purchase_order_for_request(request_id, company)
		if existing:
			return existing
	data.update(_normalized_allocation(data))
	data["company"] = company
	items = data.get("items") or []
	for row in items:
		row.update(_normalized_allocation(row))
	_validate_line_data(items)
	_validate_order_supplier_items(data, items)
	from construction_management.api import po_price_approvals
	price_changes = po_price_approvals.prepare_rates(company, data.get("supplier"), data.get("order_date") or today(), items)
	defaults = _allocation_defaults(data, company)
	_validate_company_links(company, project=data.get("project"), warehouse=data.get("warehouse"))
	for row in items:
		_validate_company_links(company, project=row.get("project"), warehouse=row.get("warehouse"))
	doc = frappe.new_doc("Purchase Order")
	doc.update({
		"company": company, "supplier": data.get("supplier"), "project": data.get("project"),
		"bill_no": defaults["bill_no"], "boq_item": defaults["boq_item"],
		"schedule_date": data.get("required_by"), "set_warehouse": data.get("warehouse"),
		"contact_person": data.get("contact_person") or None,
		"payment_terms_template": _payment_terms_template(data.get("payment_terms_template")),
		"tc_name": data.get("tc_name") or None, "terms": data.get("terms") or None,
		"controlled_procurement": 1,
		"transaction_date": data.get("order_date") or today(),
		"custom_lpo_type": data.get("lpo_type") or "Standard",
		"custom_creation_request_id": request_id or None,
	})
	for row in items:
		_append_item(doc, row, defaults)
	_apply_taxes(doc, data.get("taxes_and_charges"), [row.get("vat") for row in items])
	doc.flags.controlled_procurement_api = True
	if request_id:
		frappe.db.savepoint("controlled_po_creation")
	message_count = len(getattr(frappe.local, "message_log", []))
	try:
		doc.insert()
		po_price_approvals.stage(doc, price_changes)
	except frappe.UniqueValidationError:
		if not request_id:
			raise
		frappe.db.rollback(save_point="controlled_po_creation")
		existing = _purchase_order_for_request(request_id, company)
		if not existing:
			raise
		frappe.local.message_log = frappe.local.message_log[:message_count]
		return existing
	return {"doctype": doc.doctype, "name": doc.name, "price_approval_status": frappe.db.get_value("Purchase Order", doc.name, "custom_po_price_status")}


def _purchase_order_for_request(request_id: str, company: str) -> dict | None:
	rows = frappe.db.sql(
		"""select name, company, owner, controlled_procurement, is_subcontracted
		from `tabPurchase Order` where custom_creation_request_id = %s for update""",
		request_id, as_dict=True,
	)
	if not rows:
		return None
	doc = rows[0]
	if doc.company != company or doc.owner != frappe.session.user or not cint(doc.controlled_procurement) or cint(doc.is_subcontracted):
		frappe.throw(_("This Purchase Order creation request belongs to another user or company."), frappe.PermissionError)
	return {"doctype": "Purchase Order", "name": doc.name}


@frappe.whitelist(methods=["POST"])
def update_purchase_order(name: str, data: str | dict) -> dict:
	"""Replace editable draft values using the same catalog and allocation rules as creation."""
	doc = _controlled_doc("Purchase Order", name, "write")
	if doc.docstatus != 0 or not cint(doc.controlled_procurement):
		frappe.throw(_("Only a controlled draft Purchase Order can be edited here."))
	if doc.get("custom_po_price_status") in {"Pending Accounts", "Pending CEO"}:
		frappe.throw(_("This Purchase Order is locked pending CEO price approval."))
	if doc.get("custom_lpo_approval_status") in {"Pending Accounts", "Pending CEO"}:
		frappe.throw(_("This Manual LPO is awaiting approval."))
	if doc.get("custom_lpo_approval_status") == "Needs Correction" and doc.owner != frappe.session.user and "System Manager" not in _roles():
		frappe.throw(_("Only the creator can correct this Manual LPO."), frappe.PermissionError)
	data = _as_dict(data)
	if data.get("company") and data["company"] != doc.company:
		frappe.throw(_("Switch company in the workspace; the Purchase Order company cannot be changed."))
	items = data.get("items") or []
	for row in items:
		row.update(_normalized_allocation(row))
	_validate_line_data(items)
	_validate_order_supplier_items(data, items, doc)
	from construction_management.api import po_price_approvals
	price_changes = po_price_approvals.prepare_rates(doc.company, data.get("supplier"), data.get("order_date") or doc.transaction_date, items, doc)
	defaults = _allocation_defaults(data, doc.company)
	_validate_company_links(doc.company, project=data.get("project"), warehouse=data.get("warehouse"))
	for row in items:
		_validate_company_links(doc.company, project=row.get("project"), warehouse=row.get("warehouse"))
	doc.update({
		"supplier": data.get("supplier"), "transaction_date": data.get("order_date") or doc.transaction_date,
		"project": defaults["project"], "bill_no": defaults["bill_no"], "boq_item": defaults["boq_item"],
		"schedule_date": data.get("required_by"), "set_warehouse": data.get("warehouse"),
		"contact_person": data.get("contact_person") or None,
		"payment_terms_template": _payment_terms_template(data.get("payment_terms_template", doc.payment_terms_template)),
		"tc_name": data.get("tc_name") or None,
		"terms": data.get("terms") or None, "custom_lpo_type": data.get("lpo_type") or "Standard",
	})
	doc.set("items", [])
	for row in items:
		_append_item(doc, row, defaults)
	doc.set("payment_schedule", [])
	_apply_taxes(doc, data.get("taxes_and_charges"), [row.get("vat") for row in items])
	doc.flags.controlled_procurement_api = True
	doc.save()
	po_price_approvals.stage(doc, price_changes)
	return {"doctype": doc.doctype, "name": doc.name, "price_approval_status": frappe.db.get_value("Purchase Order", doc.name, "custom_po_price_status")}


@frappe.whitelist(methods=["GET"])
def get_lpo_approvals() -> dict:
	_require(ACCOUNT_ROLES | ADMIN_ROLES)
	company = _document_company(None)
	rows = frappe.get_all("Purchase Order", filters={
		"company": company, "controlled_procurement": 1, "custom_lpo_type": "Manual",
		"docstatus": 0, "custom_lpo_approval_status": ["in", ["Pending Accounts", "Pending CEO", "Needs Correction"]],
	}, fields=["name", "supplier_name", "project", "grand_total", "currency", "owner", "modified", "custom_lpo_reference", "custom_lpo_approval_status"], order_by="modified desc", limit_page_length=100)
	return {"rows": rows}


@frappe.whitelist(methods=["POST"])
def request_lpo_approval(name: str) -> dict:
	from construction_management.api.lpo_workflow import request_approval
	return request_approval(name)


@frappe.whitelist(methods=["POST"])
def approve_lpo(name: str) -> dict:
	from construction_management.api.lpo_workflow import approve
	return approve(name)


@frappe.whitelist(methods=["POST"])
def reject_lpo(name: str, comment: str) -> dict:
	from construction_management.api.lpo_workflow import reject
	return reject(name, comment)


@frappe.whitelist(methods=["POST"])
def cancel_purchase_order(name: str) -> dict:
	doc = _controlled_doc("Purchase Order", name, "cancel")
	if not cint(doc.get("controlled_procurement")) or doc.docstatus != 1:
		frappe.throw(_("Only a submitted Purchase Order can be cancelled."))
	doc.flags.controlled_procurement_api = True
	doc.cancel()
	return {"name": doc.name, "docstatus": doc.docstatus}


@frappe.whitelist(methods=["POST"])
def amend_purchase_order(name: str) -> dict:
	doc = _controlled_doc("Purchase Order", name, "amend")
	if not cint(doc.get("controlled_procurement")) or doc.docstatus != 2:
		frappe.throw(_("Cancel the Purchase Order before amending it."))
	amended = frappe.copy_doc(doc)
	amended.amended_from = doc.name
	amended.custom_lpo_approval_status = "Draft" if doc.get("custom_lpo_type") == "Manual" else None
	amended.custom_lpo_approval_history = None
	amended.flags.controlled_procurement_api = True
	amended.insert()
	return {"name": amended.name, "docstatus": amended.docstatus}


@frappe.whitelist(methods=["POST"])
def create_purchase_receipt(data: str | dict) -> dict:
	_require(PURCHASE_ROLES)
	data = _as_dict(data)
	po_name = data.get("purchase_order")
	po = _controlled_doc("Purchase Order", po_name)
	open_lpo = _is_open_lpo(po)
	_validate_receivable_po(po, open_lpo)
	if not cint(po.controlled_procurement):
		return _receive_desk_purchase_order(po, data)
	items = data.get("items") or []
	_validate_line_data(items)
	po_rows = {row.name: row for row in po.items}
	# receipt-level allocation defaults to the PO's but can be changed on the receipt
	defaults = {field: data.get(field) or po.get(field) for field in ("project", "bill_no", "boq_item")}
	_validate_allocation(defaults, po.company)
	_validate_company_links(po.company, project=defaults["project"])
	doc = frappe.new_doc("Purchase Receipt")
	doc.update({
		"company": po.company, "supplier": po.supplier, "project": defaults["project"],
		"bill_no": defaults["bill_no"], "boq_item": defaults["boq_item"],
		"posting_date": data.get("received_on"), "custom_purchase_order": po.name,
		"supplier_delivery_note": (data.get("supplier_delivery_note") or "").strip(),
		"controlled_procurement": 1,
	})
	for data_row in items:
		po_row = po_rows.get(data_row.get("purchase_order_item"))
		if not po_row or po_row.item_code != data_row.get("item_code") or cint(po_row.get("closed")) or cint(po_row.get("delivered_by_supplier")):
			frappe.throw(_("Receipt items must come from the selected Purchase Order."))
		if not open_lpo and flt(data_row.get("qty")) > flt(po_row.qty) - flt(po_row.received_qty) + 0.0001:
			frappe.throw(_("{0}: only {1} is left to receive.").format(po_row.item_code, max(flt(po_row.qty) - flt(po_row.received_qty), 0)))
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
		_apply_allocation(row, data_row if data_row.get("use_override") else {}, defaults, po.company)
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
	open_lpo = _is_open_lpo(po)

	lines = {row.get("purchase_order_item"): row for row in data.get("items") or [] if flt(row.get("qty")) > 0}
	if not lines:
		frappe.throw(_("Enter a receive qty on at least one line."))
	doc = make_purchase_receipt(po.name)
	if open_lpo:
		mapped = {row.purchase_order_item for row in doc.items}
		for po_row in po.items:
			if po_row.name in mapped or cint(po_row.get("closed")) or cint(po_row.get("delivered_by_supplier")):
				continue
			doc.append("items", {
				"item_code": po_row.item_code, "item_name": po_row.item_name,
				"description": po_row.description, "qty": 0, "received_qty": 0,
				"uom": po_row.uom, "stock_uom": po_row.stock_uom,
				"conversion_factor": po_row.conversion_factor, "rate": po_row.rate,
				"purchase_order": po.name, "purchase_order_item": po_row.name,
				"warehouse": po_row.warehouse, "project": po_row.project,
			})
	header = {field: data.get(field) or po.get(field) for field in ("project", "bill_no", "boq_item")}
	# receiving a Desk PO only needs a project (checked per line below); validate what was filled in
	if header.get("project"):
		_validate_allocation(header, po.company, mode="project_only")
	_validate_company_links(po.company, project=header["project"])
	kept = []
	for row in doc.items:
		line = lines.pop(row.purchase_order_item, None)
		if not line:
			continue
		pending = flt(row.qty)
		if not open_lpo and flt(line.get("qty")) > pending + 0.0001:
			frappe.throw(_("{0}: only {1} {2} is left to receive.").format(row.item_name or row.item_code, pending, row.uom))
		row.qty = flt(line.get("qty"))
		row.received_qty = row.qty
		row.warehouse = line.get("warehouse") or row.warehouse
		_validate_company_links(po.company, warehouse=row.warehouse)
		allocation = {field: (line if line.get("use_override") else header).get(field) for field in ("project", "bill_no", "boq_item")}
		if line.get("use_override") and allocation.get("project"):
			_validate_allocation(allocation, po.company, mode="project_only")
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
		"supplier_delivery_note": (data.get("supplier_delivery_note") or "").strip(),
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
	company = _document_company(data.get("company"))
	data["company"] = company
	items = data.get("items") or []
	_validate_line_data(items)
	source = data.get("source_warehouse")
	target = data.get("target_warehouse")
	_validate_transfer_warehouses(company, source, target)
	doc = frappe.new_doc("Stock Entry")
	doc.update({
		"company": company, "purpose": "Material Transfer", "from_warehouse": source, "to_warehouse": target,
		# mandatory in this ERPNext version; the standard type for the Material Transfer purpose
		"stock_entry_type": frappe.db.get_value("Stock Entry Type", {"purpose": "Material Transfer"}, "name", order_by="is_standard desc") or "Material Transfer",
		"posting_date": data.get("posting_date"), "controlled_procurement": 1,
	})
	for row_data in items:
		item = _catalog_item(row_data.get("item_code"))
		if item.controlled_item_type != STOCKABLE or not cint(item.is_stock_item):
			frappe.throw(_("Only controlled Stockable items can be transferred."))
		_append_item(doc, {**row_data, "source_warehouse": source, "target_warehouse": target}, {}, warehouses=True)
	doc.flags.controlled_procurement_api = True
	doc.insert()
	return {"doctype": doc.doctype, "name": doc.name}


def _validate_transfer_warehouses(company: str, source: str, target: str) -> None:
	if not source or not target or source == target:
		frappe.throw(_("Select different From and To warehouses."))
	for warehouse in (source, target):
		if not frappe.db.exists("Warehouse", {"name": warehouse, "company": company, "is_group": 0, "disabled": 0}):
			frappe.throw(_("Select an enabled leaf warehouse in company {0}.").format(company))


@frappe.whitelist(methods=["GET"])
def get_transfer_stock_preview(source_warehouse: str, item_codes: str | list[str]) -> dict:
	"""Current physical stock for controlled items in the active company's source warehouse."""
	_require(STOCK_ROLES)
	company = _document_company(None)
	if not frappe.db.exists("Warehouse", {"name": source_warehouse, "company": company, "is_group": 0, "disabled": 0}):
		frappe.throw(_("Select an enabled source warehouse in the active company."), frappe.PermissionError)
	if isinstance(item_codes, str):
		try:
			item_codes = frappe.parse_json(item_codes)
		except (ValueError, TypeError):
			frappe.throw(_("Invalid item list."))
	if not isinstance(item_codes, list) or len(item_codes) > 100 or any(not isinstance(code, str) or not code for code in item_codes):
		frappe.throw(_("Select up to 100 valid items."))
	codes = list(dict.fromkeys(item_codes))
	for code in codes:
		item = _catalog_item(code)
		if item.controlled_item_type != STOCKABLE or not cint(item.is_stock_item):
			frappe.throw(_("Only controlled Stockable items can be transferred."))
	balances = dict.fromkeys(codes, 0.0)
	if codes:
		for row in frappe.get_all("Bin", filters={"warehouse": source_warehouse, "item_code": ["in", codes]}, fields=["item_code", "actual_qty"]):
			balances[row.item_code] = flt(row.actual_qty)
	return {"warehouse": source_warehouse, "balances": balances}


@frappe.whitelist(methods=["POST"])
def update_material_transfer(name: str, data: str | dict) -> dict:
	doc = _controlled_doc("Stock Entry", name, "write")
	if doc.docstatus != 0 or not cint(doc.controlled_procurement):
		frappe.throw(_("Only a controlled draft Material Transfer can be edited here."))
	data = _as_dict(data)
	if data.get("company") and data["company"] != doc.company:
		frappe.throw(_("The transfer company cannot be changed."))
	source, target = data.get("source_warehouse"), data.get("target_warehouse")
	_validate_transfer_warehouses(doc.company, source, target)
	items = data.get("items") or []
	_validate_line_data(items)
	doc.update({"posting_date": data.get("posting_date"), "from_warehouse": source, "to_warehouse": target,
		"project": None, "bill_no": None, "boq_item": None})
	doc.set("items", [])
	for row in items:
		item = _catalog_item(row.get("item_code"))
		if item.controlled_item_type != STOCKABLE or not cint(item.is_stock_item):
			frappe.throw(_("Only controlled Stockable items can be transferred."))
		_append_item(doc, {**row, "source_warehouse": source, "target_warehouse": target}, {}, warehouses=True)
	doc.flags.controlled_procurement_api = True
	doc.save()
	return {"name": doc.name}


@frappe.whitelist(methods=["POST"])
def update_purchase_receipt(name: str, data: str | dict) -> dict:
	"""Edit a draft receipt while preserving its linked PO item identity."""
	doc = _controlled_doc("Purchase Receipt", name, "write")
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft Receive Note can be edited."))
	data = _as_dict(data)
	po_names = {row.purchase_order for row in doc.items if row.purchase_order}
	if len(po_names) != 1 or data.get("purchase_order") != next(iter(po_names)):
		frappe.throw(_("The linked Purchase Order cannot be changed on a draft Receive Note."))
	po = _controlled_doc("Purchase Order", data["purchase_order"])
	if po.company != doc.company:
		frappe.throw(_("The Purchase Order must be submitted in the same company."))
	open_lpo = _is_open_lpo(po)
	_validate_receivable_po(po, open_lpo)
	items = [row for row in data.get("items") or [] if flt(row.get("qty")) > 0]
	if not items:
		frappe.throw(_("Enter a receive qty on at least one line."))
	po_rows = {row.name: row for row in po.items}
	original_rows = {row.purchase_order_item: row for row in doc.items}
	mapped_rows = {}
	if not cint(doc.controlled_procurement):
		from erpnext.buying.doctype.purchase_order.mapper import make_purchase_receipt
		mapped_rows = {row.purchase_order_item: row for row in make_purchase_receipt(po.name).items}
	if len({row.get("purchase_order_item") for row in items}) != len(items):
		frappe.throw(_("The same Purchase Order line cannot be received twice."))
	defaults = {field: data.get(field) or po.get(field) for field in ALLOCATION_FIELDS}
	if cint(doc.controlled_procurement):
		_validate_allocation(defaults, doc.company)
	elif defaults.get("project"):
		_validate_allocation(defaults, doc.company, mode="project_only")
	doc.update({"posting_date": data.get("received_on"), "set_posting_time": 1,
		"supplier_delivery_note": (data.get("supplier_delivery_note") or "").strip(), **defaults})
	doc.set("items", [])
	for data_row in items:
		po_row = po_rows.get(data_row.get("purchase_order_item"))
		if not po_row or po_row.item_code != data_row.get("item_code") or cint(po_row.get("closed")) or cint(po_row.get("delivered_by_supplier")):
			frappe.throw(_("Receipt items must come from the selected Purchase Order."))
		pending = flt(po_row.qty) - flt(po_row.received_qty)
		if not open_lpo and flt(data_row.get("qty")) > pending + 0.0001:
			frappe.throw(_("{0}: only {1} is left to receive.").format(po_row.item_code, pending))
		warehouse = data_row.get("warehouse") or data.get("warehouse")
		_validate_company_links(doc.company, warehouse=warehouse)
		if not warehouse:
			frappe.throw(_("Select a receiving warehouse for every item."))
		allocation = data_row if data_row.get("use_override") else defaults
		project = allocation.get("project") or get_warehouse_project(warehouse)
		warehouse_project = get_warehouse_project(warehouse)
		if warehouse_project and project != warehouse_project:
			frappe.throw(_("Warehouse {0} belongs to project {1}.").format(warehouse, warehouse_project))
		if not project:
			frappe.throw(_("Select a Project for this Receive Note."))
		base_row = original_rows.get(po_row.name) or mapped_rows.get(po_row.name)
		row = doc.append("items", {**(base_row.as_dict() if base_row else {}),
			"item_code": po_row.item_code, "qty": flt(data_row.get("qty")),
			"uom": po_row.uom, "stock_uom": po_row.stock_uom, "conversion_factor": po_row.conversion_factor,
			"rate": po_row.rate, "purchase_order": po.name, "purchase_order_item": po_row.name,
			"warehouse": warehouse, "project": project})
		if cint(doc.controlled_procurement):
			_apply_allocation(row, data_row if data_row.get("use_override") else {}, defaults, doc.company)
			if warehouse_project and row.project != warehouse_project:
				frappe.throw(_("Warehouse {0} belongs to project {1}.").format(warehouse, warehouse_project))
			_set_row_type(row, _catalog_item(po_row.item_code))
		else:
			_validate_allocation({**allocation, "project": project}, doc.company, mode="project_only")
			for field in ("bill_no", "boq_item"):
				row.set(field, allocation.get(field) or None)
	_apply_taxes(doc, data.get("taxes_and_charges"), [row.get("vat") for row in items])
	doc.flags.controlled_procurement_api = True
	doc.save()
	return {"name": doc.name}


def _cancel_and_amend(doctype: str, name: str, amend: bool) -> dict:
	doc = _controlled_doc(doctype, name, "amend" if amend else "cancel")
	if amend:
		if doc.docstatus != 2:
			frappe.throw(_("Cancel the document before amending it."))
		amended = frappe.copy_doc(doc)
		amended.amended_from = doc.name
		amended.flags.controlled_procurement_api = True
		amended.insert()
		return {"name": amended.name, "docstatus": amended.docstatus}
	if doc.docstatus != 1:
		frappe.throw(_("Only submitted documents can be cancelled."))
	doc.flags.controlled_procurement_api = True
	doc.cancel()
	return {"name": doc.name, "docstatus": doc.docstatus}


@frappe.whitelist(methods=["POST"])
def cancel_purchase_receipt(name: str) -> dict:
	return _cancel_and_amend("Purchase Receipt", name, False)


@frappe.whitelist(methods=["POST"])
def amend_purchase_receipt(name: str) -> dict:
	return _cancel_and_amend("Purchase Receipt", name, True)


@frappe.whitelist(methods=["POST"])
def cancel_material_transfer(name: str) -> dict:
	return _cancel_and_amend("Stock Entry", name, False)


@frappe.whitelist(methods=["POST"])
def amend_material_transfer(name: str) -> dict:
	return _cancel_and_amend("Stock Entry", name, True)


@frappe.whitelist(methods=["POST"])
def update_purchase_order_items(name: str, items: str | list) -> dict:
	"""Change qty/rate or add/remove lines on a submitted PO (ERPNext "Update Items").

	Lines already received cannot go below their received qty or be removed; ERPNext enforces that.
	"""
	from erpnext.accounts.services.child_item_update import update_child_qty_rate

	po = _controlled_doc("Purchase Order", name, "write")
	if po.get("custom_po_price_status") in {"Pending Accounts", "Pending CEO"}:
		frappe.throw(_("This Purchase Order is locked pending CEO price approval."))
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
	if cint(po.controlled_procurement):
		from construction_management.api import po_price_approvals
		for row in items:
			row.setdefault("rate_edited", True)
		changes = po_price_approvals.prepare_rates(po.company, po.supplier, po.transaction_date, items, po)
		if changes:
			po_price_approvals.stage(po, changes, trans_items)
			return {"name": name, "price_approval_status": frappe.db.get_value("Purchase Order", name, "custom_po_price_status")}
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
	if doctype == "Purchase Order":
		from construction_management.api.lpo_workflow import lpo_type
		if cint(doc.get("controlled_procurement")) and lpo_type(doc) == "Manual":
			frappe.throw(_("Send this Manual LPO for Accounts and CEO approval instead of submitting it directly."))
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
		if not any(value is not None and str(value).strip() for value in row):
			continue
		if group == "Item Group" or not group or not description:
			exceptions.append({"row": row_number, "reason": "Missing item group or description"})
			continue
		valid.append({
			"row": row_number, "item_group": group, "item_name": description,
			"item_code": str(row[headers.get("Item Code", -1)] or "").strip() if "Item Code" in headers else "",
			"item_type": str(row[headers.get("Item Type", -1)] or STOCKABLE).strip() if "Item Type" in headers else STOCKABLE,
			"asset_category": str(row[headers.get("Asset Category", -1)] or "").strip() if "Asset Category" in headers else "",
			"expense_account": str(row[headers.get("Expense Account", -1)] or "").strip() if "Expense Account" in headers else "",
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
		from construction_management.api.controlled_price_requests import _price, approved_price_write

		current = _price(item.name, supplier, "Standard Buying", "Nos")
		if not current or flt(current.price_list_rate) != rate:
			source = getattr(frappe.flags, "controlled_catalog_price_source", None)
			if not source:
				frappe.throw(_("A CEO-approved catalog request is required to change a buying price."), frappe.PermissionError)
			with approved_price_write(source):
				if current:
					price = frappe.get_doc("Item Price", current.name)
					price.price_list_rate = rate
					price.custom_controlled_catalog_request = source if source != "legacy-seed-migration" else None
					price.save(ignore_permissions=True)
				else:
					price = frappe.get_doc({"doctype": "Item Price", "item_code": item.name,
						"price_list": "Standard Buying", "price_list_rate": rate, "buying": 1,
						"supplier": supplier, "uom": "Nos",
						"custom_controlled_catalog_request": source if source != "legacy-seed-migration" else None})
					price.insert(ignore_permissions=True)
			if source == "legacy-seed-migration":
				price.add_comment("Info", "Legacy packaged catalog seed: audited migration exception for buying price.")
	return ""


def import_catalog_from_path(path: str) -> dict:
	"""Administrator-only development helper; production uses catalog file or Desk upload."""
	_require(ADMIN_ROLES)
	rows, exceptions = _workbook_rows(Path(path))
	return _import_catalog_rows(rows, exceptions, Path(path).name, "Workbook Import", "uploaded", _rows_checksum(rows))


@frappe.whitelist(methods=["POST"])
def preview_catalog_workbook(file_url: str) -> dict:
	_require(CATALOG_ROLES)
	rows, exceptions = _workbook_rows(_uploaded_file_path(file_url))
	company = _active_company()
	valid = []
	for row in rows:
		try:
			valid.append(_catalog_request_row(row, company))
		except frappe.ValidationError as error:
			exceptions.append({"row": row["row"], "item": row["item_name"], "reason": str(error)})
	if not rows:
		exceptions.append({"row": 0, "reason": "Add at least one catalog item row."})
	return {
		"source": Path(file_url).name, "checksum": _rows_checksum(rows), "valid_rows": len(valid),
		"create": sum(not row.get("result_item") for row in valid),
		"reuse": sum(bool(row.get("result_item")) for row in valid),
		"errors": exceptions, "rows": valid,
	}


@frappe.whitelist(methods=["POST"])
def import_catalog_workbook(file_url: str) -> dict:
	_require(CATALOG_ROLES)
	rows, exceptions = _workbook_rows(_uploaded_file_path(file_url))
	if exceptions:
		frappe.throw(_("Correct workbook errors before submitting the import."))
	company = _active_company()
	prepared = []
	for row in rows:
		try:
			prepared.append(_catalog_request_row(row, company))
		except frappe.ValidationError:
			frappe.throw(_("Correct workbook errors before submitting the import."))
	return create_catalog_request({"company": company, "source": "Workbook Import", "source_file": file_url,
		"checksum": _rows_checksum(rows), "items": prepared})


def import_packaged_catalog() -> dict:
	"""Import the versioned application asset during a production migration."""
	path = Path(frappe.get_app_path("construction_management", "data", "controlled_procurement_catalog_v1.json"))
	payload = json.loads(path.read_text())
	previous = getattr(frappe.flags, "controlled_catalog_price_source", None)
	frappe.flags.controlled_catalog_price_source = "legacy-seed-migration"
	try:
		return _import_catalog_rows(
			payload["items"], [], payload["source_filename"], "Workbook Import",
			payload["version"], payload["checksum"],
		)
	finally:
		frappe.flags.controlled_catalog_price_source = previous


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


@frappe.whitelist(methods=["POST"])
def download_catalog_template() -> dict:
	"""Create the approved import template on demand so it always matches validation."""
	_require(CATALOG_ROLES)
	from openpyxl import Workbook

	book = Workbook()
	sheet = book.active
	sheet.title = "Catalog Items"
	sheet.append(["Item Code", "Description", "Item Group", "Item Type", "Asset Category", "Expense Account", "Supplier", "Rates"])
	sheet.freeze_panes = "A2"
	for column in sheet.columns:
		sheet.column_dimensions[column[0].column_letter].width = 22
	instructions = book.create_sheet("Instructions")
	for line in (
		"Add one item per row on Catalog Items; do not change the column headers.",
		"Description, Item Group, Item Type, and Supplier are required on every row.",
		"Supplier must be an existing Supplier ID; select it from the Procurement supplier list.",
		"Item Type must be Stockable, Asset, or Service.",
		"Example Stockable row: Description = Example stock item; Item Group = Products; Item Type = Stockable; Supplier = an existing Supplier ID.",
		"Asset Category is needed for Asset rows unless a company default is configured.",
		"Expense Account is needed for Service rows unless a company default is configured.",
		"Item Code is optional; Rates may be zero.",
	):
		instructions.append([line])
	instructions.column_dimensions["A"].width = 100
	output = BytesIO()
	book.save(output)
	file_doc = save_file("controlled_catalog_import_template.xlsx", output.getvalue(), None, None, is_private=0)
	return {"file_url": file_doc.file_url}


def _explicit_ceo() -> bool:
	from construction_management.api.controlled_price_requests import has_explicit_ceo_role
	return has_explicit_ceo_role()


def _catalog_request_status(items: list[dict] | None = None) -> str:
	roles = _roles()
	if items and any(flt(row.get("rate")) > 0 for row in items):
		if _explicit_ceo():
			return "Approved"
		return "Pending CEO" if roles.intersection(ACCOUNT_ROLES | {"System Manager"}) else "Pending Accounts"
	if roles.intersection(ADMIN_ROLES):
		return "Approved"
	if roles.intersection(ACCOUNT_ROLES):
		return "Pending CEO"
	return "Pending Accounts"


def _catalog_request_row(data: dict, company: str) -> dict:
	item_type = data.get("item_type") or STOCKABLE
	if item_type not in {STOCKABLE, ASSET, SERVICE}:
		frappe.throw(_("Select Stockable, Asset, or Service."))
	if not data.get("item_name") or not data.get("item_group"):
		frappe.throw(_("Every catalog row needs a Description and Item Group."))
	if not frappe.db.exists("Item Group", data["item_group"]):
		frappe.throw(_("Item Group {0} does not exist.").format(data["item_group"]))
	supplier = str(data.get("supplier") or "").strip()
	if not supplier:
		frappe.throw(_("Supplier is required for every catalog item."))
	if not frappe.db.exists("Supplier", supplier):
		frappe.throw(_("Supplier {0} does not exist.").format(supplier))
	company_rules = frappe.db.get_value(
		"Company", company, ["controlled_asset_category", "controlled_service_expense_account"], as_dict=True,
	)
	asset_category = data.get("asset_category") or company_rules.controlled_asset_category
	expense_account = data.get("expense_account") or company_rules.controlled_service_expense_account
	if item_type == ASSET and not asset_category:
		frappe.throw(_("Configure or select an Asset Category for Asset items."))
	if item_type == ASSET and asset_category and not frappe.db.exists("Asset Category", asset_category):
		frappe.throw(_("Asset Category {0} does not exist.").format(data["asset_category"]))
	if item_type == SERVICE and not expense_account:
		frappe.throw(_("Configure or select a Service Expense Account for Service items."))
	if item_type == SERVICE and expense_account:
		from redtra_customisation.redtra_customisation.service_item_validator import ServiceItemValidator

		ServiceItemValidator.validate_expense_account(expense_account, company)
	item_code = (data.get("item_code") or "").strip()
	existing = frappe.db.get_value("Item", item_code, "name") if item_code else None
	if not existing:
		existing = frappe.db.get_value("Item", {"item_name": data["item_name"], "stock_uom": "Nos", "disabled": 0}, "name")
	return {
		"item_code": item_code,
		"item_name": data["item_name"].strip(),
		"item_group": data["item_group"],
		"item_type": item_type,
		"asset_category": asset_category or "",
		"expense_account": expense_account or "",
		"supplier": supplier,
		"rate": flt(data.get("rate")),
		"action": "Update" if existing else "Create",
		"result_item": existing or "",
	}


def _append_catalog_log(doc, action: str, comment: str = "") -> None:
	doc.append("approval_log", {
		"action": action,
		"actor": frappe.session.user,
		"actioned_on": now_datetime(),
		"comment": comment,
	})


@frappe.whitelist(methods=["POST"])
def create_catalog_request(data: str | dict) -> dict:
	"""Create a catalog change request; only approval materializes Item records."""
	_require(CATALOG_ROLES)
	data = _as_dict(data)
	company = data.get("company") or _active_company()
	if company not in _allowed_companies():
		frappe.throw(_("You do not have access to company {0}.").format(company), frappe.PermissionError)
	rows = data.get("items") or []
	if not rows:
		frappe.throw(_("Add at least one catalog item."))
	prepared = [_catalog_request_row(row, company) for row in rows]
	if len({row["item_code"] or row["item_name"].casefold() for row in prepared}) != len(prepared):
		frappe.throw(_("The request contains duplicate item codes or descriptions."))
	status = _catalog_request_status(prepared)
	doc = frappe.get_doc({
		"doctype": "Controlled Catalog Request", "company": company, "status": status,
		"source": data.get("source") or "Manual", "requested_by": frappe.session.user,
		"source_file": data.get("source_file") or "", "checksum": data.get("checksum") or "", "items": prepared,
	})
	_append_catalog_log(doc, "Created")
	if status == "Pending CEO":
		_append_catalog_log(doc, "Submitted by System Manager for CEO price approval" if "System Manager" in _roles() and not _explicit_ceo() else "Accounts approved on creation")
	doc.insert(ignore_permissions=True)
	if status == "Approved":
		_materialize_catalog_request(doc)
		_append_catalog_log(doc, "Approved on creation")
		doc.save(ignore_permissions=True)
	elif status == "Pending CEO" and any(flt(row.rate) > 0 for row in doc.items):
		from construction_management.api.controlled_price_requests import _enqueue_catalog_notice
		_enqueue_catalog_notice(doc.name)
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["GET"])
def get_catalog_requests(status: str = "") -> list[dict]:
	_require(CATALOG_ROLES)
	company = _active_company()
	filters = {"company": company} if company else {"company": ["in", _allowed_companies()]}
	if status:
		filters["status"] = status
	requests = frappe.get_list("Controlled Catalog Request", filters=filters,
		fields=["name", "company", "status", "source", "requested_by", "creation", "modified", "rejection_reason"],
		order_by="modified desc", limit_page_length=100)
	if requests:
		priced = set(frappe.get_all("Controlled Catalog Request Item", filters={
			"parent": ["in", [row.name for row in requests]], "rate": [">", 0],
		}, pluck="parent", limit_page_length=0))
		for row in requests:
			row.has_price_change = row.name in priced
	return requests


@frappe.whitelist(methods=["GET"])
def get_catalog_request(name: str) -> dict:
	_require(CATALOG_ROLES)
	doc = frappe.get_doc("Controlled Catalog Request", name)
	if doc.company not in _allowed_companies():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return doc.as_dict()


def _can_approve_catalog(doc) -> bool:
	roles = _roles()
	if doc.status == "Pending CEO" and any(flt(row.rate) > 0 for row in doc.items):
		return _explicit_ceo()
	if roles.intersection(ADMIN_ROLES):
		return True
	if doc.status == "Pending Accounts":
		return bool(roles.intersection(ACCOUNT_ROLES))
	return doc.status == "Pending CEO" and "CEO" in roles


@frappe.whitelist(methods=["POST"])
def approve_catalog_request(name: str, comment: str = "") -> dict:
	_require(CATALOG_ROLES)
	doc = frappe.get_doc("Controlled Catalog Request", name)
	if doc.company not in _allowed_companies():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not _can_approve_catalog(doc):
		frappe.throw(_("You cannot approve this catalog request."), frappe.PermissionError)
	if doc.status == "Pending Accounts":
		doc.status = "Pending CEO"
		_append_catalog_log(doc, "Approved by Accounts", comment)
	else:
		doc.status = "Approved"
		_materialize_catalog_request(doc)
		_append_catalog_log(doc, "Approved by CEO" if _explicit_ceo() else "Approved by System Manager", comment)
	doc.rejection_reason = ""
	doc.save(ignore_permissions=True)
	if doc.status == "Pending CEO" and any(flt(row.rate) > 0 for row in doc.items):
		from construction_management.api.controlled_price_requests import _enqueue_catalog_notice
		_enqueue_catalog_notice(doc.name)
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def reject_catalog_request(name: str, comment: str) -> dict:
	_require(CATALOG_ROLES)
	if not (comment or "").strip():
		frappe.throw(_("A rejection reason is required."))
	doc = frappe.get_doc("Controlled Catalog Request", name)
	if doc.company not in _allowed_companies():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not _can_approve_catalog(doc):
		frappe.throw(_("You cannot reject this catalog request."), frappe.PermissionError)
	doc.status = "Needs Correction"
	doc.rejection_reason = comment.strip()
	_append_catalog_log(doc, "Rejected", doc.rejection_reason)
	doc.save(ignore_permissions=True)
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def resubmit_catalog_request(name: str, data: str | dict | None = None) -> dict:
	_require(CATALOG_ROLES)
	doc = frappe.get_doc("Controlled Catalog Request", name)
	if doc.company not in _allowed_companies():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if doc.status != "Needs Correction" or (doc.requested_by != frappe.session.user and not _roles().intersection(ADMIN_ROLES)):
		frappe.throw(_("Only the requester can correct and resubmit this request."), frappe.PermissionError)
	if data:
		payload = _as_dict(data)
		rows = payload.get("items") or []
		if not rows:
			frappe.throw(_("Add at least one catalog item."))
		doc.set("items", [_catalog_request_row(row, doc.company) for row in rows])
	else:
		for row in doc.items:
			row.supplier = _catalog_request_row(row.as_dict(), doc.company)["supplier"]
	doc.status = "Pending CEO" if _roles().intersection(ACCOUNT_ROLES | ADMIN_ROLES) else "Pending Accounts"
	doc.rejection_reason = ""
	_append_catalog_log(doc, "Resubmitted")
	doc.save(ignore_permissions=True)
	if doc.status == "Pending CEO" and any(flt(row.rate) > 0 for row in doc.items):
		from construction_management.api.controlled_price_requests import _enqueue_catalog_notice
		_enqueue_catalog_notice(doc.name)
	return {"name": doc.name, "status": doc.status}


def _materialize_catalog_request(doc) -> None:
	if any(flt(row.rate) > 0 for row in doc.items) and not _explicit_ceo():
		frappe.throw(_("A CEO must give the final decision before buying prices are applied."), frappe.PermissionError)
	previous_source = getattr(frappe.flags, "controlled_catalog_price_source", None)
	frappe.flags.controlled_catalog_price_source = doc.name
	try:
		_materialize_catalog_request_items(doc)
	finally:
		frappe.flags.controlled_catalog_price_source = previous_source


def _materialize_catalog_request_items(doc) -> None:
	for row in doc.items:
		item = frappe.get_doc("Item", row.result_item) if row.result_item else None
		if not item:
			item = frappe.new_doc("Item")
			item.item_code = row.item_code or _item_code(row.item_name)
		item.update({
			"item_name": row.item_name, "item_group": row.item_group, "stock_uom": "Nos",
			"is_purchase_item": 1, "controlled_procurement_catalog": 1,
			"controlled_item_type": row.item_type,
			"controlled_catalog_source": "Workbook Import" if doc.source == "Workbook Import" else "Manual Request",
			"controlled_catalog_version": doc.name,
		})
		if row.item_type == STOCKABLE:
			item.update({"is_stock_item": 1, "is_fixed_asset": 0})
		elif row.item_type == ASSET:
			item.update({"is_stock_item": 0, "is_fixed_asset": 1, "asset_category": row.asset_category or None})
		else:
			item.update({"is_stock_item": 0, "is_fixed_asset": 0, "company": doc.company,
				"expense_account": row.expense_account or frappe.db.get_value("Company", doc.company, "controlled_service_expense_account")})
		item.flags.controlled_procurement_api = True
		if item.is_new():
			item.insert(ignore_permissions=True)
		else:
			item.save(ignore_permissions=True)
		if row.supplier:
			_add_supplier_and_price(item, row.supplier, flt(row.rate))
			item.flags.controlled_procurement_api = True
			item.save(ignore_permissions=True)
		row.result_item = item.name


@frappe.whitelist(methods=["GET"])
def get_catalog_stock(item_code: str, company: str = "") -> dict:
	_require(CATALOG_ROLES)
	_catalog_item(item_code)
	company = company or _active_company()
	_validate_company_links(company)
	rows = frappe.db.sql(
		"""select bin.warehouse, bin.actual_qty, bin.valuation_rate
		from `tabBin` bin join `tabWarehouse` warehouse on warehouse.name = bin.warehouse
		where bin.item_code = %(item_code)s and warehouse.company = %(company)s and warehouse.is_group = 0
		order by bin.warehouse""", {"item_code": item_code, "company": company}, as_dict=True,
	)
	return {"rows": rows, "total_qty": sum(flt(row.actual_qty) for row in rows)}


@frappe.whitelist(methods=["POST"])
def record_opening_stock(data: str | dict) -> dict:
	_require(OPENING_STOCK_ROLES)
	data = _as_dict(data)
	company = data.get("company") or _active_company()
	if company not in _allowed_companies():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	rows = data.get("items") or []
	if not rows:
		frappe.throw(_("Add at least one opening-stock line."))
	doc = frappe.new_doc("Stock Reconciliation")
	doc.company, doc.posting_date = company, getdate(data.get("posting_date") or today())
	for row in rows:
		item = _catalog_item(row.get("item_code"))
		warehouse = row.get("warehouse")
		if item.controlled_item_type != STOCKABLE or not cint(item.is_stock_item):
			frappe.throw(_("Opening stock accepts Stockable catalog items only."))
		_validate_company_links(company, warehouse=warehouse)
		if not warehouse or flt(row.get("qty")) < 0 or flt(row.get("valuation_rate")) < 0:
			frappe.throw(_("Warehouse, quantity, and valuation rate must be non-negative."))
		doc.append("items", {"item_code": item.name, "warehouse": warehouse, "qty": flt(row.get("qty")),
			"valuation_rate": flt(row.get("valuation_rate"))})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return {"doctype": doc.doctype, "name": doc.name}


def validate_item(doc, method=None) -> None:
	if doc.is_new() and not _roles().intersection(ADMIN_ROLES) and not getattr(doc.flags, "controlled_procurement_api", False):
		frappe.throw(_("Only CEO and System Manager can create items."), frappe.PermissionError)
	if cint(doc.get("controlled_procurement_catalog")) and not getattr(doc.flags, "controlled_procurement_api", False):
		frappe.throw(_("Create controlled catalog items through a catalog request."), frappe.PermissionError)
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
	transfer = doc.doctype == "Stock Entry" and doc.purpose == "Material Transfer"
	if transfer:
		_validate_transfer_warehouses(doc.company, doc.from_warehouse, doc.to_warehouse)
	else:
		_validate_allocation({field: doc.get(field) for field in ALLOCATION_FIELDS}, doc.company)
	for row in doc.get("items") or []:
		item = _catalog_item(row.item_code)
		if row.uom != "Nos":
			frappe.throw(_("Controlled procurement items must use Nos."))
		_set_row_type(row, item)
		if doc.doctype == "Stock Entry" and (item.controlled_item_type != STOCKABLE or not cint(item.is_stock_item)):
			frappe.throw(_("Material Transfer accepts Stockable controlled items only."))
		if transfer:
			if row.s_warehouse != doc.from_warehouse or row.t_warehouse != doc.to_warehouse:
				frappe.throw(_("Every transfer item must use the header From and To warehouses."))
		else:
			_validate_allocation({field: row.get(field) for field in ALLOCATION_FIELDS}, doc.company)
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
		return fields + ["supplier", "supplier_name", "transaction_date", "schedule_date", "per_received", "per_billed", "controlled_procurement", "custom_lpo_type", "custom_is_provisional_po", "custom_lpo_reference", "custom_lpo_approval_status"]
	if doctype == "Purchase Receipt":
		return fields + ["supplier", "supplier_name", "posting_date", "supplier_delivery_note", "controlled_procurement"]
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


def _is_open_lpo(po) -> bool:
	from construction_management.api.lpo_workflow import lpo_type

	return lpo_type(po) == "Open"


def _validate_receivable_po(po, open_lpo: bool) -> None:
	if po.docstatus != 1 or po.status in {"Closed", "On Hold"}:
		frappe.throw(_("Select a submitted Purchase Order that is not closed or on hold."))
	if not open_lpo and (po.status in {"Completed", "Delivered"} or flt(po.per_received) >= 100):
		frappe.throw(_("This Purchase Order has no quantity left to receive."))


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
	accounts_approval_view = doctype == "Purchase Order" and ptype == "read" and bool(_roles().intersection(ACCOUNT_ROLES | ADMIN_ROLES))
	if not accounts_approval_view:
		_require(DOCUMENT_ROLES[doctype])
	doc = frappe.get_doc(doctype, name)
	if doc.company != _document_company(None):
		frappe.throw(_("Switch to the document's company in Procurement before opening it."), frappe.PermissionError)
	if accounts_approval_view and not _roles().intersection(PURCHASE_ROLES):
		if doc.company not in _allowed_companies() or not cint(doc.get("controlled_procurement")) or doc.get("custom_lpo_type") != "Manual":
			frappe.throw(_("Not permitted"), frappe.PermissionError)
	else:
		frappe.has_permission(doctype, ptype, doc=doc, throw=True)
	if not _in_workspace(doc):
		frappe.throw(_("This document is not part of Controlled Procurement."))
	return doc


@frappe.whitelist(methods=["GET"])
def get_open_lpos(search: str = "", supplier: str = "", project: str = "", start: int = 0, page_length: int = 50, controlled_only: int = 0, open_po_only: int = 0) -> dict:
	"""Submitted receivable LPOs, including fully received Open LPOs."""
	_require(PURCHASE_ROLES)
	provisional = "po.custom_is_provisional_po" if _has_open_po_field() else "0"
	conditions = [
		"po.is_subcontracted = 0", "po.docstatus = 1",
		"po.status not in %(closed)s",
		f"({provisional} = 1 or (po.per_received < 100 and po.status not in %(completed)s))",
	]
	if cint(open_po_only):
		# the Open LPOs tab lists only POs ticked "Provisional / Open PO"
		if not _has_open_po_field():
			return {"rows": [], "total_count": 0, "summary": {"open_lpos": 0, "pending_value": 0, "overdue": 0}}
		conditions.append("po.custom_is_provisional_po = 1")
	if cint(controlled_only):
		# the workspace receipt form can only receive catalog-controlled orders
		conditions.append("po.controlled_procurement = 1")
	values = {"closed": ("Closed", "On Hold"), "completed": ("Completed", "Delivered"), "today": frappe.utils.today()}
	company = _document_company(None)
	conditions.append("po.company = %(company)s")
	values["company"] = company
	if supplier:
		conditions.append("po.supplier = %(supplier)s")
		values["supplier"] = supplier
	if project:
		conditions.append("po.project = %(project)s")
		values["project"] = project
	if search:
		conditions.append("(po.name like %(search)s or po.supplier_name like %(search)s or po.project like %(search)s or po.custom_lpo_reference like %(search)s)")
		values["search"] = f"%{search.strip()}%"
	# only list POs the user can read, then aggregate pending lines in SQL
	permitted = frappe.get_list(
		"Purchase Order", filters=_scoped({"is_subcontracted": 0, "docstatus": 1}),
		pluck="name", limit_page_length=0,
	)
	if not permitted:
		return {"rows": [], "total_count": 0, "summary": {"open_lpos": 0, "pending_value": 0, "overdue": 0}}
	conditions.append("po.name in %(permitted)s")
	values["permitted"] = tuple(permitted)
	where = " and ".join(conditions)
	# "Provisional / Open PO" tick (redtra_customisation); receipts may exceed the ordered qty
	rows = frappe.db.sql(
		f"""
		select po.name, po.supplier, po.supplier_name, po.project, po.transaction_date, po.schedule_date, po.custom_lpo_reference,
			po.grand_total, po.per_received, po.per_billed, po.status, po.currency, po.controlled_procurement,
			{provisional} as is_open_po,
			sum(greatest(poi.qty - poi.received_qty, 0)) as pending_qty,
			sum(greatest(poi.qty - poi.received_qty, 0) * poi.rate) as pending_value,
			count(poi.name) as line_count,
			(po.schedule_date < %(today)s and sum(greatest(poi.qty - poi.received_qty, 0)) > 0) as is_overdue,
			datediff(%(today)s, po.transaction_date) as age_days
		from `tabPurchase Order` po
		join `tabPurchase Order Item` poi on poi.parent = po.name and ifnull(poi.closed, 0) = 0 and ifnull(poi.delivered_by_supplier, 0) = 0
		where {where}
		group by po.name
		having pending_qty > 0 or is_open_po = 1
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
	"""Comments, lifecycle events, emails, and readable tracked edits for this revision."""
	doc = _controlled_doc(doctype, name)
	comments = frappe.get_all(
		"Comment",
		filters={"reference_doctype": doctype, "reference_name": name, "comment_type": ["in", ["Comment", "Info", "Edit", "Submitted", "Cancelled"]]},
		fields=["name", "content", "owner", "comment_email", "comment_type", "creation"],
	)
	versions = frappe.get_all("Version", filters={"ref_doctype": doctype, "docname": name},
		fields=["name", "data", "owner", "creation"], order_by="creation desc", limit_page_length=100)
	emails = frappe.get_all(
		"Communication",
		filters={"reference_doctype": doctype, "reference_name": name, "communication_medium": "Email"},
		fields=["name", "subject", "content", "sender", "recipients", "cc", "sent_or_received", "delivery_status", "has_attachment", "creation"],
	)
	users = {row.owner for row in comments} | {row.sender for row in emails} | {row.owner for row in versions} | {doc.owner}
	names = dict(frappe.get_all("User", filters={"name": ["in", list(users)]}, fields=["name", "full_name"], as_list=True)) if users else {}
	activity = [{"type": "event", "name": f"created-{name}", "content": _("Document created"),
		"by": names.get(doc.owner) or doc.owner, "creation": doc.creation}] + [
		{"type": "comment" if row.comment_type == "Comment" else "event", "name": row.name,
			"content": row.content, "by": names.get(row.owner) or row.owner, "creation": row.creation}
		for row in comments
	] + [
		{
			"type": "email", "name": row.name, "subject": row.subject, "content": row.content,
			"by": names.get(row.sender) or row.sender, "recipients": row.recipients, "cc": row.cc,
			"direction": row.sent_or_received, "status": row.delivery_status,
			"has_attachment": row.has_attachment, "creation": row.creation,
		}
		for row in emails
	] + [
		{"type": "event" if _version_status_change(row.data) else "edit", "name": row.name,
			"changes": _version_changes(doctype, row.data),
			"by": names.get(row.owner) or row.owner, "creation": row.creation}
		for row in versions if _version_changes(doctype, row.data)
	]
	return sorted(activity, key=lambda row: row["creation"], reverse=True)


def _version_status_change(raw: str) -> bool:
	try:
		return any(change[0] == "docstatus" for change in json.loads(raw or "{}").get("changed") or [])
	except (TypeError, ValueError):
		return False


AUDIT_FIELDS = {
	"supplier", "transaction_date", "schedule_date", "posting_date", "supplier_delivery_note",
	"project", "bill_no", "boq_item", "set_warehouse", "from_warehouse", "to_warehouse",
	"custom_lpo_type", "custom_lpo_reference", "custom_lpo_approval_status", "taxes_and_charges",
	"remarks", "items", "item_code", "qty", "rate", "warehouse", "s_warehouse", "t_warehouse", "description",
}


def _version_changes(doctype: str, raw: str) -> list[str]:
	try:
		data = json.loads(raw or "{}")
	except (ValueError, TypeError):
		return []
	meta = frappe.get_meta(doctype)
	changes = []
	for field, old, new in data.get("changed") or []:
		if field == "docstatus":
			changes.append({1: "Submitted", 2: "Cancelled", 0: "Returned to draft"}.get(cint(new), "Status changed"))
			continue
		if field in AUDIT_FIELDS and old != new:
			label = meta.get_label(field) or field.replace("_", " ").title()
			changes.append(f"{label}: {old or '—'} → {new or '—'}")
	for table, row in data.get("added") or []:
		if table == "items":
			changes.append(f"Added item {row.get('item_code', '—')} (qty {row.get('qty', '—')})")
	for table, row in data.get("removed") or []:
		if table == "items":
			changes.append(f"Removed item {row.get('item_code', '—')}")
	for table, row_name, _, fields in data.get("row_changed") or []:
		if table == "items":
			for field, old, new in fields:
				if field in AUDIT_FIELDS and old != new:
					changes.append(f"Item {row_name}: {field.replace('_', ' ').title()} {old or '—'} → {new or '—'}")
	return changes[:30]


def _eligible_tag_user(doc, user: str) -> bool:
	if not frappe.db.exists("User", {"name": user, "enabled": 1}) or not frappe.db.exists("Raven User", {"user": user, "enabled": 1}):
		return False
	roles = set(frappe.get_roles(user))
	special_approval_view = (doc.doctype == "Purchase Order" and bool(roles.intersection(ACCOUNT_ROLES | ADMIN_ROLES))
		and cint(doc.get("controlled_procurement")) and doc.get("custom_lpo_type") == "Manual")
	allowed_role = special_approval_view or bool(roles.intersection(DOCUMENT_ROLES[doc.doctype]))
	if not allowed_role or (not special_approval_view and not frappe.has_permission(doc.doctype, "read", doc=doc, user=user)):
		return False
	company_permissions = frappe.get_all("User Permission", filters={"user": user, "allow": "Company"}, pluck="for_value")
	return not company_permissions or doc.company in company_permissions


@frappe.whitelist(methods=["GET"])
def get_comment_tag_users(doctype: str, name: str, search: str = "") -> list[dict]:
	doc = _controlled_doc(doctype, name)
	users = frappe.get_all("Raven User", filters={"enabled": 1, "type": "User"}, fields=["user", "full_name"], limit_page_length=0)
	needle = search.strip().casefold()
	return [{"user": row.user, "full_name": row.full_name} for row in users
		if row.user and (not needle or needle in row.user.casefold() or needle in (row.full_name or "").casefold())
		and _eligible_tag_user(doc, row.user)][:20]


@frappe.whitelist(methods=["POST"])
def add_document_comment(doctype: str, name: str, content: str, tagged_users: str | list | None = None) -> dict:
	doc = _controlled_doc(doctype, name)
	if not (content or "").strip():
		frappe.throw(_("Comment cannot be empty."))
	tags = json.loads(tagged_users) if isinstance(tagged_users, str) else (tagged_users or [])
	if not isinstance(tags, list) or len(tags) > 20 or len(tags) != len(set(tags)):
		frappe.throw(_("Invalid tagged users."))
	for user in tags:
		if not isinstance(user, str) or not _eligible_tag_user(doc, user) or f"@{user}" not in content:
			frappe.throw(_("{0} cannot be tagged on this document.").format(user), frappe.PermissionError)
	if tags and not frappe.db.exists("Raven Bot", "procurement bot"):
		frappe.throw(_("The procurement Raven bot is not configured; tagged comment was not posted."))
	bot = frappe.get_doc("Raven Bot", "procurement bot") if tags else None
	comment = frappe.get_doc({
		"doctype": "Comment", "comment_type": "Comment", "reference_doctype": doctype, "reference_name": name,
		"comment_email": frappe.session.user, "comment_by": frappe.utils.get_fullname(frappe.session.user),
		"content": frappe.utils.sanitize_html(content),
	})
	comment.insert(ignore_permissions=True)
	for user in tags:
		try:
			message = bot.send_direct_message(user, text=f"{frappe.utils.get_fullname(frappe.session.user)} mentioned you on {doctype} {name}: {frappe.utils.strip_html(content)[:240]}", link_doctype=doctype, link_document=name)
			if not message:
				frappe.throw(_("Raven did not deliver the notification."))
		except Exception as exc:
			frappe.throw(_("Could not notify {0} through Raven: {1}").format(user, str(exc)))
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


@frappe.whitelist(methods=["GET"])
def get_supplier_payment_terms(supplier: str) -> dict:
	"""Read the default payment terms for a supplier visible to this user."""
	_require(PURCHASE_ROLES)
	if not frappe.db.exists("Supplier", supplier):
		frappe.throw(_("Supplier {0} does not exist.").format(supplier))
	frappe.has_permission("Supplier", "read", doc=supplier, throw=True)
	return {"payment_terms": frappe.db.get_value("Supplier", supplier, "payment_terms") or ""}


@frappe.whitelist(methods=["POST"])
def set_supplier_payment_terms(supplier: str, payment_terms: str = "") -> dict:
	"""Update only the supplier's payment-terms default from Procurement."""
	_require(PURCHASE_ROLES)
	doc = frappe.get_doc("Supplier", supplier)
	doc.payment_terms = _payment_terms_template(payment_terms)
	doc.save(ignore_permissions=True)
	return {"name": doc.name, "payment_terms": doc.payment_terms or ""}


@frappe.whitelist(methods=["GET"])
def get_catalog_buying_price(item_code: str, supplier: str = "", company: str = "", order_date: str = "") -> dict:
	"""Return an applicable supplier price, then a general buying price, in company currency."""
	_require(PURCHASE_ROLES)
	company = _document_company(company)
	_catalog_item(item_code)
	if not frappe.db.get_value("Item", item_code, "is_purchase_item") or frappe.db.get_value("Item", item_code, "disabled"):
		frappe.throw(_("Item {0} is not an active buying item.").format(item_code))
	if supplier:
		if not frappe.db.exists("Supplier", supplier):
			frappe.throw(_("Supplier {0} does not exist.").format(supplier))
		frappe.has_permission("Supplier", "read", doc=supplier, throw=True)
	price_list = frappe.db.get_value("Supplier", supplier, "default_price_list") if supplier else None
	price_lists = list(dict.fromkeys([price_list, "Standard Buying"])) if price_list else ["Standard Buying"]
	rows = frappe.db.sql(
		"""select ip.name, ip.price_list_rate, ip.price_list, ip.supplier
		from `tabItem Price` ip
		join `tabPrice List` pl on pl.name = ip.price_list
		where ip.item_code = %(item_code)s and ip.buying = 1
		and ip.price_list in %(price_lists)s and pl.enabled = 1 and pl.buying = 1
		and pl.currency = %(currency)s
		and (ifnull(ip.supplier, '') = '' or ip.supplier = %(supplier)s)
		and (ifnull(ip.uom, '') = '' or ip.uom = 'Nos')
		and (ip.valid_from is null or ip.valid_from <= %(order_date)s)
		and (ip.valid_upto is null or ip.valid_upto >= %(order_date)s)
		order by (ip.supplier = %(supplier)s and %(supplier)s != '') desc,
		(ip.price_list = %(preferred_list)s) desc, ip.valid_from desc, ip.creation desc
		limit 1""",
		{
			"item_code": item_code, "supplier": supplier or "", "price_lists": price_lists,
			"currency": frappe.get_cached_value("Company", company, "default_currency"),
			"order_date": str(getdate(order_date or today())), "preferred_list": price_list or "Standard Buying",
		}, as_dict=True,
	)
	if not rows:
		return {"rate": None, "price_list": "", "item_price": "", "supplier": ""}
	return {"rate": flt(rows[0].price_list_rate), "price_list": rows[0].price_list,
		"item_price": rows[0].name, "supplier": rows[0].supplier or ""}


# Keep the Procurement API prefix stable for the Vue workspace.
from construction_management.api.controlled_price_requests import (
	approve_price_change,
	get_price_context,
	get_price_request,
	get_price_requests,
	reject_price_change,
	request_price_change,
	retry_catalog_price_notice,
	retry_price_notice,
)
from construction_management.api.controlled_price_history import get_price_history
from construction_management.api.po_price_approvals import (
	approve_accounts_po_price,
	approve_po_price,
	deliver_po_price_notice,
	get_po_price_requests,
	reject_accounts_po_price,
	reject_po_price,
	retry_po_price_notice,
)


@frappe.whitelist(methods=["POST"])
def create_supplier(data: str | dict) -> dict:
	"""Create a supplier from the controlled procurement workspace."""
	_require(PURCHASE_ROLES)
	data = _as_dict(data)
	supplier_name = (data.get("supplier_name") or "").strip()
	if not supplier_name:
		frappe.throw(_("Supplier name is required."))
	if frappe.db.exists("Supplier", {"supplier_name": supplier_name}):
		frappe.throw(_("Supplier {0} already exists.").format(supplier_name))

	supplier_group = data.get("supplier_group") or None
	if supplier_group and not frappe.db.exists("Supplier Group", supplier_group):
		frappe.throw(_("Supplier Group {0} does not exist.").format(supplier_group))

	supplier_type = data.get("supplier_type") or "Company"
	if supplier_type not in SUPPLIER_TYPES:
		frappe.throw(_("Invalid supplier type."))

	supplier = frappe.new_doc("Supplier")
	supplier.update({
		"supplier_name": supplier_name,
		"supplier_group": supplier_group,
		"supplier_type": supplier_type,
		"tax_id": (data.get("tax_id") or "").strip(),
		"payment_terms": _payment_terms_template(data.get("payment_terms")),
	})
	_set_supplier_naming_series(supplier)
	supplier.insert(ignore_permissions=True)
	return {"name": supplier.name, "supplier_name": supplier.supplier_name, "payment_terms": supplier.payment_terms or ""}


def _set_supplier_naming_series(supplier) -> None:
	"""Provide a valid series only when Supplier naming is series-based."""
	if frappe.defaults.get_global_default("supp_master_name") != "Naming Series":
		return
	series = (supplier.meta.get_field("naming_series").options or "").splitlines()
	if series:
		supplier.naming_series = series[0]


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
