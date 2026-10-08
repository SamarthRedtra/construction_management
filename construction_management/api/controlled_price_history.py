"""Audited, shared buying-price history for a controlled catalog item."""

import json

import frappe
from frappe import _
from frappe.utils import flt

from construction_management.api import controlled_price_requests as prices


@frappe.whitelist(methods=["GET"])
def get_price_history(item_code: str, supplier: str = "", price_list: str = "Standard Buying",
		uom: str = "", company: str = "", start: int = 0, page_length: int = 20) -> dict:
	api = prices._procurement()
	company = company or api._active_company()
	prices._require_company(company)
	item = api._catalog_item(item_code)
	uom = uom or item.stock_uom
	supplier = (supplier or "").strip()
	if supplier and not api._item_has_supplier(item_code, supplier):
		frappe.throw(_("Supplier is not linked to this catalog item."), frappe.PermissionError)
	if uom != item.stock_uom:
		frappe.throw(_("Price history must use the item's stock UOM {0}.").format(item.stock_uom))
	list_info = frappe.db.get_value("Price List", price_list, ["buying", "enabled", "currency"], as_dict=True)
	if not list_info or not list_info.buying or not list_info.enabled:
		frappe.throw(_("Select an enabled buying Price List."))
	if list_info.currency != frappe.get_cached_value("Company", company, "default_currency"):
		frappe.throw(_("The buying Price List currency must match the company currency."))
	start = max(0, int(start))
	page_length = min(50, max(1, int(page_length)))
	filters = {"item_code": item_code, "supplier": supplier if supplier else ["is", "not set"], "price_list": price_list,
		"uom": uom, "status": "Approved"}
	fields = ["name", "company", "item_code", "price_list", "old_rate", "proposed_rate", "currency", "reason",
		"decided_by", "decided_on", "purchase_order", "target_item_price", "result_item_price"]
	rows = frappe.get_all("Controlled Buying Price Request", filters=filters, fields=fields,
		order_by="decided_on desc, creation desc", start=start, page_length=page_length)
	current = prices._price(item_code, supplier, price_list, uom)
	general = prices._price(item_code, "", price_list, uom) if supplier else None
	po_changes = _po_change_snapshots(rows)
	return {
		"item_code": item_code, "supplier": supplier, "price_list": price_list,
		"uom": uom, "currency": list_info.currency,
		"current": {"item_price": current.name, "rate": flt(current.price_list_rate)} if current else None,
		"general": {"item_price": general.name, "rate": flt(general.price_list_rate)} if general else None,
		"catalog_origin": _catalog_origin(current, item_code, supplier, price_list),
		"rows": [{**row, "source": "Purchase Order" if row.purchase_order else "Price request",
			"old_rate": flt(row.old_rate) if row.target_item_price else None,
			"general_fallback_rate": po_changes.get(row.name, {}).get("general_fallback_rate"),
			"proposed_rate": flt(row.proposed_rate)} for row in rows],
		"has_more": len(rows) == page_length,
	}


def _po_change_snapshots(rows) -> dict:
	request_identity = {row.name: (row.item_code, row.price_list) for row in rows if row.purchase_order}
	order_names = sorted({row.purchase_order for row in rows if row.purchase_order})
	if not order_names:
		return {}
	orders = frappe.get_all("Purchase Order", filters={"name": ["in", order_names]},
		fields=["name", "custom_po_price_history"], limit_page_length=len(order_names))
	snapshots = {}
	for order in orders:
		for event in json.loads(order.custom_po_price_history or "[]"):
			if event.get("action") != "Approved":
				continue
			for request_name in event.get("requests") or []:
				identity = request_identity.get(request_name)
				change = next((entry for entry in event.get("changes") or []
					if (entry.get("item_code"), entry.get("price_list")) == identity), {})
				if change.get("old_active_supplier") == "" and change.get("old_active_item_price"):
					snapshots[request_name] = {"general_fallback_rate": change.get("old_active_rate")}
	return snapshots


def _catalog_origin(current, item_code: str, supplier: str, price_list: str) -> dict | None:
	if not current or price_list != "Standard Buying":
		return None
	request_name = frappe.db.get_value("Item Price", current.name, "custom_controlled_catalog_request")
	if not request_name:
		return None
	request = frappe.db.get_value("Controlled Catalog Request", request_name,
		["company", "status"], as_dict=True)
	if not request or request.status != "Approved":
		return None
	items = frappe.get_all("Controlled Catalog Request Item", filters={
		"parent": request_name, "result_item": item_code, "supplier": supplier,
		"rate": flt(current.price_list_rate),
	}, fields=["name"], limit_page_length=1)
	if not items:
		return None
	log = frappe.get_all("Controlled Catalog Approval Log", filters={
		"parent": request_name, "action": ["in", ["Approved by CEO", "Approved by System Manager", "Approved on creation"]],
	}, fields=["actor", "actioned_on"], order_by="actioned_on desc", limit_page_length=1)
	return {"request": request_name, "company": request.company,
		"rate": flt(current.price_list_rate), "approved_by": log[0].actor if log else None,
		"approved_on": log[0].actioned_on if log else None}
