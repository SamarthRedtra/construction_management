"""Automatic consumption of controlled Consumables after inbound stock movements."""

import frappe
from frappe import _
from frappe.utils import cint, flt

from construction_management.api import bulk_material_issue


SOURCE_PURCHASE_RECEIPT = "Purchase Receipt"
SOURCE_STOCK_ENTRY = "Stock Entry"
MATERIAL_TRANSFER = "Material Transfer"
PURCHASE_RECEIPT_LINK = "custom_source_purchase_receipt"
TRANSFER_LINK = "custom_source_material_transfer"


def on_submit(doc, method=None):
	"""Consume eligible controlled Consumables received through a Purchase Receipt."""
	if cint(getattr(doc, "is_return", 0)) or not _auto_consumption_enabled():
		return
	_create_source_issue(doc, SOURCE_PURCHASE_RECEIPT, PURCHASE_RECEIPT_LINK, "warehouse", "stock_qty")


def on_transfer_submit(doc, method=None):
	"""Consume eligible controlled Consumables after they arrive at a transfer destination."""
	if doc.stock_entry_type != MATERIAL_TRANSFER or cint(getattr(doc, "is_return", 0)) or not _auto_consumption_enabled():
		return
	_create_source_issue(doc, SOURCE_STOCK_ENTRY, TRANSFER_LINK, "t_warehouse", "qty")


def cancel_linked_issue(receipt):
	"""Reverse receipt consumption before ERPNext cancels the receipt."""
	_cancel_source_issue(receipt, PURCHASE_RECEIPT_LINK)


def cancel_linked_transfer_issue(transfer, method=None):
	"""Reverse transfer consumption before ERPNext cancels its source transfer."""
	if transfer.stock_entry_type == MATERIAL_TRANSFER:
		_cancel_source_issue(transfer, TRANSFER_LINK)


def _auto_consumption_enabled() -> bool:
	return bool(cint(frappe.db.get_single_value(
		"Redtra Custom Setting", "auto_consume_controlled_consumables_on_receipt"
	)))


def _create_source_issue(doc, source_doctype: str, link_field: str, warehouse_field: str, quantity_field: str):
	if frappe.db.exists("Stock Entry", {link_field: doc.name, "docstatus": ["!=", 2]}):
		return
	rows = _eligible_rows(doc, source_doctype, warehouse_field, quantity_field)
	if not rows:
		return
	issue = bulk_material_issue._create_material_issue_for_source(
		rows, stock_entry_type=bulk_material_issue.MATERIAL_ISSUE_TYPE
	)
	if not issue:
		return
	frappe.db.set_value("Stock Entry", issue.name, link_field, doc.name, update_modified=False)
	doc.add_comment("Info", _("Consumables auto-consumed by Material Issue {0}.").format(issue.name))


def _eligible_rows(doc, source_doctype: str, warehouse_field: str, quantity_field: str) -> list[dict]:
	item_codes = {row.item_code for row in doc.items if row.item_code}
	item_types = _controlled_item_types(item_codes)
	warehouse_names = {row.get(warehouse_field) for row in doc.items if row.get(warehouse_field)}
	skip_warehouses = _skip_auto_consumption_warehouses(warehouse_names)
	rows = []
	for row in doc.items:
		quantity = flt(row.get(quantity_field))
		if item_types.get(row.item_code) != "Consumable" or quantity <= 0:
			continue
		warehouse = row.get(warehouse_field)
		if not warehouse:
			frappe.throw(_("Consumable row {0} has no receiving warehouse.").format(row.idx))
		if warehouse in skip_warehouses:
			continue
		rows.append({
			"source_doctype": source_doctype,
			"source_name": doc.name,
			"source_posting_date": doc.posting_date,
			"source_line_name": row.name,
			"company": doc.company,
			"item_code": row.item_code,
			"warehouse": warehouse,
			"qty": quantity,
			"project": row.get("project") or doc.get("project"),
			"boq_item": row.get("boq_item"),
			"bill_no": row.get("bill_no"),
		})
	return rows


def _controlled_item_types(item_codes: set[str]) -> dict[str, str]:
	if not item_codes:
		return {}
	return {
		row.name: row.controlled_item_type
		for row in frappe.get_all(
			"Item",
			filters={"name": ["in", list(item_codes)], "controlled_procurement_catalog": 1},
			fields=["name", "controlled_item_type"],
		)
	}


def _skip_auto_consumption_warehouses(warehouse_names: set[str]) -> set[str]:
	if not warehouse_names or not frappe.db.has_column(
		"Warehouse", "custom_skip_auto_consumption_for_consumables"
	):
		return set()
	return set(frappe.get_all(
		"Warehouse",
		filters={
			"name": ["in", list(warehouse_names)],
			"custom_skip_auto_consumption_for_consumables": 1,
		},
		pluck="name",
	))


def _cancel_source_issue(source, link_field: str):
	for name in frappe.get_all(
		"Stock Entry",
		filters={link_field: source.name, "docstatus": 1},
		pluck="name",
	):
		issue = frappe.get_doc("Stock Entry", name)
		if issue.company != source.company or issue.stock_entry_type != "Material Issue":
			frappe.throw(_("Linked Stock Entry {0} is not the expected consumable issue.").format(name))
		issue.flags.controlled_procurement_api = True
		issue.cancel()
