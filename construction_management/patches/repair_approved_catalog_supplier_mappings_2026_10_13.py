"""Repair approved controlled-catalog supplier mappings that were not materialized."""

from __future__ import annotations

import csv
from collections import defaultdict
from contextlib import contextmanager
from io import StringIO

import frappe
from frappe.utils import flt
from frappe.utils.file_manager import save_file

from construction_management.api import controlled_procurement
from construction_management.api.controlled_price_requests import _price


PATCH_DATE = "2026-10-13"


def execute():
	result = run()
	frappe.logger("controlled_procurement").info(
		{"event": "repair_approved_catalog_supplier_mappings_2026_10_13", **result}
	)


def run() -> dict:
	"""Restore supplier links and approved buying prices from approved catalog requests."""
	targets = preflight()
	outcomes = []
	for target in targets:
		outcomes.append(_repair_target(target))
	audit_files = _save_audits(outcomes)
	return {
		"approved_mappings": len(targets),
		"supplier_links_added": sum(outcome["supplier_link_added"] for outcome in outcomes),
		"prices_added": sum(outcome["price_added"] for outcome in outcomes),
		"no_op": not any(outcome["supplier_link_added"] or outcome["price_added"] for outcome in outcomes),
		"audit_files": audit_files,
	}


def preflight() -> list[dict]:
	"""Validate every approved mapping before any Item or Item Price is changed."""
	targets = _approved_targets()
	if not targets:
		return []

	items = _items_by_name({target["item_code"] for target in targets})
	suppliers = _suppliers_by_name({target["supplier"] for target in targets})
	links = _existing_supplier_links(set(items), set(suppliers))
	errors = []
	for target in targets:
		item = items.get(target["item_code"])
		supplier = suppliers.get(target["supplier"])
		if not item or item.disabled or not item.is_purchase_item or not item.controlled_procurement_catalog:
			errors.append(f"{target['request']}: invalid controlled Item {target['item_code']}")
			continue
		if not supplier or supplier.disabled:
			errors.append(f"{target['request']}: invalid Supplier {target['supplier']}")
			continue

		price = _price(item.name, supplier.name, "Standard Buying", item.stock_uom) if target["rate"] > 0 else None
		if price and abs(flt(price.price_list_rate) - target["rate"]) > 0.000001:
			errors.append(
				f"{target['request']}: conflicting buying price for {item.name} / {supplier.name}"
			)
			continue
		target.update(
			{
				"item": item,
				"supplier_doc": supplier,
				"supplier_link_exists": (item.name, supplier.name) in links,
				"price_exists": bool(price),
			}
		)
	if errors:
		frappe.throw("Approved catalog supplier repair preflight failed: " + "; ".join(errors[:10]))
	return targets


def _approved_targets() -> list[dict]:
	rows = frappe.db.sql(
		"""
		SELECT request.name AS request, request.company, item_row.result_item AS item_code,
			item_row.item_name, item_row.supplier, item_row.rate
		FROM `tabControlled Catalog Request` request
		INNER JOIN `tabControlled Catalog Request Item` item_row ON item_row.parent = request.name
		WHERE request.status = 'Approved'
			AND COALESCE(item_row.result_item, '') != ''
			AND COALESCE(item_row.supplier, '') != ''
		ORDER BY request.name, item_row.idx
		""",
		as_dict=True,
	)
	targets = {}
	for row in rows:
		key = (row.item_code, row.supplier)
		target = targets.setdefault(
			key,
			{
				"request": row.request,
				"requests": [row.request],
				"company": row.company,
				"item_code": row.item_code,
				"item_name": row.item_name,
				"supplier": row.supplier,
				"rate": flt(row.rate),
			},
		)
		if row.request not in target["requests"]:
			target["requests"].append(row.request)
		if abs(target["rate"] - flt(row.rate)) > 0.000001:
			frappe.throw(
				f"Approved catalog requests disagree on the buying price for {row.item_code} / {row.supplier}."
			)
	return sorted(targets.values(), key=lambda target: (target["company"], target["item_code"], target["supplier"]))


def _items_by_name(item_codes: set[str]) -> dict:
	return {
		item.name: item
		for item in frappe.get_all(
			"Item",
			filters={"name": ["in", sorted(item_codes)]},
			fields=["name", "item_name", "stock_uom", "disabled", "is_purchase_item", "controlled_procurement_catalog"],
			limit_page_length=0,
		)
	}


def _suppliers_by_name(supplier_names: set[str]) -> dict:
	return {
		supplier.name: supplier
		for supplier in frappe.get_all(
			"Supplier",
			filters={"name": ["in", sorted(supplier_names)]},
			fields=["name", "disabled"],
			limit_page_length=0,
		)
	}


def _existing_supplier_links(item_codes: set[str], supplier_names: set[str]) -> set[tuple[str, str]]:
	return {
		(row.parent, row.supplier)
		for row in frappe.get_all(
			"Item Supplier",
			filters={"parent": ["in", sorted(item_codes)], "parenttype": "Item", "supplier": ["in", sorted(supplier_names)]},
			fields=["parent", "supplier"],
			limit_page_length=0,
		)
	}


def _repair_target(target: dict) -> dict:
	supplier_link_added = not target["supplier_link_exists"]
	price_added = target["rate"] > 0 and not target["price_exists"]
	if supplier_link_added or price_added:
		with _approved_price_source(target["request"]):
			item = frappe.get_doc("Item", target["item_code"])
			controlled_procurement._apply_catalog_supplier_mapping(
				item, target["supplier"], target["rate"], target["item_name"]
			)
	return {
		**target,
		"supplier_link_added": supplier_link_added,
		"price_added": price_added,
	}


@contextmanager
def _approved_price_source(request: str):
	previous = getattr(frappe.flags, "controlled_catalog_price_source", None)
	frappe.flags.controlled_catalog_price_source = request
	try:
		yield
	finally:
		frappe.flags.controlled_catalog_price_source = previous


def _save_audits(outcomes: list[dict]) -> list[str]:
	by_company = defaultdict(list)
	for outcome in outcomes:
		by_company[outcome["company"]].append(outcome)
	urls = []
	for company, company_outcomes in by_company.items():
		filename = f"approved_catalog_supplier_repair_{PATCH_DATE}.csv"
		existing = frappe.get_all(
			"File",
			filters={"file_name": filename, "attached_to_doctype": "Company", "attached_to_name": company},
			pluck="file_url",
			limit_page_length=1,
		)
		if existing:
			urls.append(existing[0])
			continue

		content = StringIO()
		writer = csv.writer(content)
		writer.writerow(["Requests", "Item Code", "Item Name", "Supplier", "Approved Rate", "Supplier Link", "Buying Price"])
		for outcome in company_outcomes:
			writer.writerow(
				[
					", ".join(outcome["requests"]),
					outcome["item_code"],
					outcome["item_name"],
					outcome["supplier"],
					outcome["rate"],
					"Added" if outcome["supplier_link_added"] else "Already linked",
					"Added" if outcome["price_added"] else "Already matching or not requested",
				]
			)
		file_doc = save_file(filename, content.getvalue().encode(), "Company", company, is_private=1)
		urls.append(file_doc.file_url)
	return urls
