"""Reconcile controlled-catalog Item Groups from Item Tree Part 2 (4)."""

from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from io import StringIO
from pathlib import Path

import frappe
from frappe.utils.file_manager import save_file
from openpyxl import load_workbook

from construction_management.api import controlled_procurement as catalog


COMPANY = "M R G INSULATION WORKS L.L.C"
PATCH_DATE = "2026-10-13"
SOURCE_PATH = Path(__file__).resolve().parents[1] / "data" / "controlled_catalog_item_tree_part_2_v4.xlsx"
SOURCE_SHA256 = "2a6dc86458c0f6b470ddce47e6fa23b56f799fccb5dc28ceac19c5628606a496"
ITEM_TYPES = {
	"material in stock": "Stockable",
	"consumable": "Consumable",
	"asset": "Asset",
	"service": "Service",
}


def execute():
	result = run()
	frappe.logger("controlled_procurement").info(
		{"event": "repair_controlled_catalog_item_groups_2026_10_13", **result}
	)


def run() -> dict:
	"""Apply only workbook-backed Item Group corrections and keep reruns safe."""
	targets = preflight()
	outcomes = [_apply_target(target) for target in targets]
	return {
		"source_sha256": SOURCE_SHA256,
		"targets": len(targets),
		"updated": sum(outcome["updated"] for outcome in outcomes),
		"no_op": not outcomes,
		"audit_files": _save_audit(outcomes),
	}


def preflight() -> list[dict]:
	"""Validate workbook data and all candidate Items before changing any Item Group."""
	expected = _source_entries()
	groups = _item_groups()
	missing_groups = sorted({
		option["item_group"]
		for entry in expected.values()
		for option in _entry_options(entry)
		if _key(option["item_group"]) not in groups
	})
	if missing_groups:
		frappe.throw("Item Group repair preflight failed: missing Item Groups " + ", ".join(missing_groups))

	items_by_name = defaultdict(list)
	for item in frappe.get_all(
		"Item",
		filters={"controlled_procurement_catalog": 1},
		fields=["name", "item_name", "item_group", "stock_uom", "controlled_item_type", "is_purchase_item"],
		limit_page_length=0,
	):
		items_by_name[_key(item.item_name)].append(item)

	targets = []
	for item_name, entry in expected.items():
		all_items = items_by_name.get(item_name, [])
		items = [item for item in all_items if not item.disabled]
		if not items and all_items:
			frappe.throw(
				"Item Group repair preflight failed: no active controlled Item for " + entry["item_name"]
			)
		options = _entry_options(entry)
		if not items or all(any(_item_matches_source(item, option, groups) for option in options) for item in items):
			continue
		if len(items) != 1 or len(options) != 1:
			frappe.throw(
				"Item Group repair preflight failed: ambiguous controlled Items for " + entry["item_name"]
			)
		option = options[0]
		target_group = groups[_key(option["item_group"])]
		item = items[0]
		if not item.is_purchase_item:
			frappe.throw(f"Item Group repair preflight failed: {item.name} is not purchasable")
		if _key(item.stock_uom) != _key(option["stock_uom"]) or item.controlled_item_type != option["item_type"]:
			frappe.throw(
				"Item Group repair preflight failed: workbook type or UOM differs for " + item.name
			)
		targets.append({
			"item_code": item.name,
			"item_name": item.item_name,
			"current_group": item.item_group,
			"target_group": target_group,
			"source_row": option["source_row"],
		})
	return sorted(targets, key=lambda target: target["item_code"])


def _source_entries() -> dict[str, dict]:
	if not SOURCE_PATH.exists() or _source_checksum() != SOURCE_SHA256:
		frappe.throw("The packaged Item Tree Part 2 (4) workbook checksum is invalid.")
	book = load_workbook(SOURCE_PATH, read_only=True, data_only=True)
	if "Sheet2" not in book:
		frappe.throw("Item Group repair preflight failed: Sheet2 is missing from the workbook.")

	entries = {}
	for number, values in enumerate(book["Sheet2"].values, 1):
		if number <= 2 or len(values) < 6 or not values[0] or not values[1]:
			continue
		item_group = str(values[0]).strip()
		item_name = str(values[1]).strip()
		if _key(item_group) == "item group":
			continue
		item_type = ITEM_TYPES.get(_key(values[5]))
		if not item_type:
			frappe.throw(f"Item Group repair preflight failed: unsupported allocation on workbook row {number}.")
		try:
			stock_uom = catalog._catalog_uom(values[3])
		except frappe.ValidationError as error:
			frappe.throw(f"Item Group repair preflight failed on workbook row {number}: {error}")
		entry = {
			"source_row": number,
			"item_name": item_name,
			"item_group": item_group,
			"item_type": item_type,
			"stock_uom": stock_uom,
		}
		key = _key(item_name)
		previous = entries.get(key)
		if previous:
			variants = previous.setdefault("variants", [_entry_option(previous)])
			candidate = (_key(item_group), item_type, _key(stock_uom))
			if candidate not in {
				(_key(option["item_group"]), option["item_type"], _key(option["stock_uom"]))
				for option in variants
			}:
				variants.append(entry)
		else:
			entries[key] = entry
	return entries


def _item_groups() -> dict[str, str]:
	return {
		_key(name): name
		for name in frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name", limit_page_length=0)
	}


def _entry_option(entry: dict) -> dict:
	return {key: entry[key] for key in ("source_row", "item_name", "item_group", "item_type", "stock_uom")}


def _entry_options(entry: dict) -> list[dict]:
	return entry.get("variants") or [_entry_option(entry)]


def _item_matches_source(item, option: dict, groups: dict[str, str]) -> bool:
	return (
		item.item_group == groups[_key(option["item_group"])]
		and _key(item.stock_uom) == _key(option["stock_uom"])
		and item.controlled_item_type == option["item_type"]
	)


def _apply_target(target: dict) -> dict:
	item = frappe.get_doc("Item", target["item_code"])
	if item.disabled or not item.is_purchase_item or not item.controlled_procurement_catalog:
		frappe.throw(f"Item Group repair failed: {item.name} is no longer an active controlled catalog Item.")
	if item.item_group == target["target_group"]:
		return {**target, "updated": False}
	item.item_group = target["target_group"]
	item.flags.controlled_procurement_api = True
	item.save(ignore_permissions=True)
	return {**target, "updated": True}


def _save_audit(outcomes: list[dict]) -> list[str]:
	filename = f"controlled_catalog_item_group_repair_{PATCH_DATE}.csv"
	existing = frappe.get_all(
		"File",
		filters={
			"file_name": ["like", f"{filename.removesuffix('.csv')}%"],
			"attached_to_doctype": "Company",
			"attached_to_name": COMPANY,
		},
		pluck="file_url",
		limit_page_length=1,
	)
	if existing:
		return existing
	if not outcomes:
		return []

	content = StringIO()
	writer = csv.writer(content)
	writer.writerow(["Source SHA256", "Source Row", "Item Code", "Description", "Previous Group", "Target Group", "Result"])
	for outcome in outcomes:
		writer.writerow([
			SOURCE_SHA256,
			outcome["source_row"],
			outcome["item_code"],
			outcome["item_name"],
			outcome["current_group"],
			outcome["target_group"],
			"Updated" if outcome["updated"] else "Already correct",
		])
	file_doc = save_file(filename, content.getvalue().encode(), "Company", COMPANY, is_private=1)
	return [file_doc.file_url]


def _source_checksum() -> str:
	return hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest()


def _key(value) -> str:
	return " ".join(str(value or "").split()).casefold()
