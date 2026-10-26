# Copyright (c) 2026, Construction Management
# License: MIT

"""Create supplier-wise draft LPOs from MRG LPO Created - (Decoded ) 24.10.2026.xlsx.

Order date is fixed at 2025-09-04; warehouse/project is Stores - MRG / 100.

Runs after apply_item_trail_list_migration on migrate (see patches.txt).

Manual:
  bench --site skada.local execute \\
    construction_management.patches.create_pos_from_po_creation_sheet.execute

Stock / negative balances (not auto-migrated — needs site plan_hash):
  1. Corrected-stock SRs already in patches.txt (stage → apply → repost to 2026-09-30).
  2. If legacy negatives remain after item linking, run mrg_stock_duplicate_repair
     preview/apply + revaluation.finish per
     construction_management/scripts/mrg_stock_duplicate_repair/README.md
     (local trial plan_hash example under artifacts/mrg_stock_investigation_2026-10-22/).
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

import frappe
from frappe.utils import cint, flt, getdate

from construction_management.api import controlled_procurement as cp

COMPANY = "M R G INSULATION WORKS L.L.C"
WAREHOUSE = "Stores - MRG"
PROJECT = "100"  # 100 MRG Store — receiving store; site allocation later
ORDER_DATE = "2025-09-04"
SHEET_NAME = "New Item Fetch Sheet"
XLSX_NAME = "MRG LPO Created - (Decoded ) 24.10.2026.xlsx"
REMARKS_PREFIX = "MRG LPO Created 24.10.2026"
RESULT_CSV = "PO_CREATION_FROM_SHEET_RESULT.csv"

# Sheet item_code → correct catalog code (name-driven fixes from requester)
ITEM_REMAPS = {
	("CP-PRIMER_D41_(16_KG)_CAN", "PRIMER SOPRADERE HT (200LTR /DRUM)"): "CP-PRIMER__SOPRADERE_HT_(200LTR_/DRUM)",
	(
		"CP-WEBERDRY_116_FX_SP__WHITE___(_PART_A_13.63_KG+_PART_B_4.67_KG)",
		"WEBERDRY 116 FX SP GREY ( PART A 13.63 KG+ PART B 4.67 KG)",
	): "CP-WEBERDRY_116_FX_SP__GREY____(_PART_A_13.63_KG+_PART_B_4.67_KG)",
}


def execute():
	"""Parse sheet, create one draft controlled PO per supplier, write result CSV."""
	frappe.set_user("Administrator")
	frappe.defaults.set_user_default("Company", COMPANY)
	# ERPNext inventory dimensions require this column; sync Inventory Dimension if missing.
	if not frappe.db.has_column("Inventory Dimension", "mandatory_depends_on_backend"):
		frappe.reload_doc("stock", "doctype", "inventory_dimension", force=True)
		frappe.db.commit()
	if not frappe.db.has_column("Inventory Dimension", "mandatory_depends_on_backend"):
		frappe.throw(
			"Inventory Dimension is missing mandatory_depends_on_backend. "
			"Reload the Inventory Dimension DocType before creating POs."
		)
	groups = load_supplier_groups(xlsx_path())
	results = []
	for group_key in sorted(groups.keys(), key=lambda k: (k[0], k[1])):
		group = groups[group_key]
		sheet_supplier = group["sheet_supplier"]
		try:
			supplier = resolve_supplier(sheet_supplier)
		except Exception as exc:
			results.append({
				"supplier": sheet_supplier,
				"new_po": "",
				"status": "skipped",
				"line_count": len(group["items"]),
				"remarks": group["remarks"],
				"warnings": str(exc),
				"rate_sources": "",
			})
			_log(f"skipped {sheet_supplier}: {exc}")
			continue
		existing = find_existing_po(supplier, group["remarks"])
		if existing:
			results.append({
				"supplier": supplier,
				"new_po": existing,
				"status": "already_created",
				"line_count": len(group["items"]),
				"remarks": group["remarks"],
				"warnings": "",
				"rate_sources": "",
			})
			_log(f"already_created {existing} for {supplier}")
			continue
		try:
			for part in split_group_unique_item_rates(group):
				existing_part = find_existing_po(supplier, part["remarks"])
				if existing_part:
					results.append({
						"supplier": supplier,
						"new_po": existing_part,
						"status": "already_created",
						"line_count": len(part["items"]),
						"remarks": part["remarks"],
						"warnings": "",
						"rate_sources": "",
					})
					_log(f"already_created {existing_part} for {supplier}")
					continue
				outcome = create_supplier_po(supplier, part)
				results.append(outcome)
				frappe.db.commit()
				_log(f"created {outcome['new_po']} for {supplier} ({outcome['line_count']} lines)")
		except Exception as exc:
			frappe.db.rollback()
			results.append({
				"supplier": supplier,
				"new_po": "",
				"status": "skipped",
				"line_count": len(group["items"]),
				"remarks": group["remarks"],
				"warnings": str(exc),
				"rate_sources": "",
			})
			_log(f"skipped {supplier}: {exc}")
	write_result_csv(results)
	created = sum(1 for r in results if r["status"] == "created")
	already = sum(1 for r in results if r["status"] == "already_created")
	skipped = sum(1 for r in results if r["status"] == "skipped")
	print(
		f"Done: {created} created, {already} already_created, "
		f"{skipped} skipped, {len(results)} suppliers"
	)
	return {
		"created": created,
		"already_created": already,
		"skipped": skipped,
		"results": results,
	}


def xlsx_path() -> Path:
	"""Prefer packaged app data; fall back to bench root copy."""
	data_path = Path(__file__).resolve().parents[1] / "data" / XLSX_NAME
	if data_path.is_file():
		return data_path
	bench_path = Path(frappe.utils.get_bench_path()) / XLSX_NAME
	if bench_path.is_file():
		return bench_path
	frappe.throw(f"PO Creation workbook missing: tried {data_path} and {bench_path}")


def load_supplier_groups(path: Path) -> dict[tuple[str, str], dict]:
	"""One draft PO per original LPO ref (avoids multi-rate CEO conflicts on one PO).

	Forward-fill refs/supplier; coalesce qty by (item_code, unit_price) within that LPO.
	"""
	import openpyxl

	ws = openpyxl.load_workbook(path, data_only=True)[SHEET_NAME]
	rows = list(ws.iter_rows(values_only=True))[1:]
	current_refs = ""
	current_supplier = ""
	# (supplier, refs) -> (item_code, rate_key) -> line bucket
	raw: dict[tuple[str, str], dict[tuple[str, str], dict]] = defaultdict(dict)

	for row in rows:
		if not row or not any(c is not None and str(c).strip() for c in row[:11]):
			continue
		refs = _cell(row[0])
		supplier = _cell(row[3])
		code = _cell(row[4])
		name = _cell(row[5])
		qty = flt(row[7])
		rate = flt(row[8])
		if refs:
			current_refs = refs
		if supplier:
			current_supplier = supplier
		if not current_supplier or not current_refs or not code or qty <= 0 or rate <= 0:
			continue
		code = apply_remap(code, name)
		# One PO per first/primary LPO number in the refs cell
		primary_ref = _split_refs(current_refs)[0]
		group_key = (current_supplier, primary_ref)
		rate_key = f"{flt(rate):.6f}"
		bucket = raw[group_key].setdefault(
			(code, rate_key),
			{"qty": 0.0, "item_name": name, "rate": flt(rate)},
		)
		bucket["qty"] += qty
		bucket["item_name"] = name or bucket["item_name"]
		bucket["rate"] = flt(rate)

	groups = {}
	for (supplier, primary_ref), items_map in raw.items():
		groups[(supplier, primary_ref)] = {
			"sheet_supplier": supplier,
			"remarks": f"{REMARKS_PREFIX} | Original LPO: {primary_ref}",
			"ref_list": [primary_ref],
			"items": [
				{
					"item_code": code,
					"qty": data["qty"],
					"item_name": data["item_name"],
					"rate": data["rate"],
				}
				for (code, _rate_key), data in sorted(items_map.items(), key=lambda kv: (kv[0][0], kv[0][1]))
			],
		}
	return groups


def apply_remap(code: str, name: str) -> str:
	for (old_code, old_name), new_code in ITEM_REMAPS.items():
		if code == old_code and _normalize_name(name) == _normalize_name(old_name):
			return new_code
	if code == "CP-PRIMER_D41_(16_KG)_CAN" and "SOPRADERE" in name.upper():
		return "CP-PRIMER__SOPRADERE_HT_(200LTR_/DRUM)"
	if "WEBERDRY 116 FX SP GREY" in name.upper() and "WHITE" in code:
		return "CP-WEBERDRY_116_FX_SP__GREY____(_PART_A_13.63_KG+_PART_B_4.67_KG)"
	return code


def split_group_unique_item_rates(group: dict) -> list[dict]:
	"""CEO proposals allow one rate per item per PO; split when one LPO has multi-rates."""
	batches: list[list[dict]] = []
	for line in group["items"]:
		placed = False
		for batch in batches:
			if any(row["item_code"] == line["item_code"] for row in batch):
				continue
			batch.append(line)
			placed = True
			break
		if not placed:
			batches.append([line])
	if len(batches) <= 1:
		return [group]
	parts = []
	for idx, items in enumerate(batches, start=1):
		parts.append({
			**group,
			"items": items,
			"remarks": f"{group['remarks']} | part {idx}/{len(batches)}",
		})
	return parts


def find_existing_po(supplier: str, remarks: str) -> str | None:
	"""Idempotent re-run: reuse draft PO created earlier for same supplier+remarks."""
	if not remarks:
		return None
	return frappe.db.get_value(
		"Purchase Order",
		{
			"supplier": supplier,
			"company": COMPANY,
			"docstatus": 0,
			"controlled_procurement": 1,
			"remarks": remarks,
		},
		"name",
	)


def resolve_supplier(sheet_name: str) -> str:
	"""Match sheet supplier to ERPNext name (sheet often collapses double spaces)."""
	name = (sheet_name or "").strip()
	if not name:
		frappe.throw("Supplier missing on sheet row")
	if frappe.db.exists("Supplier", name):
		return name
	compact = " ".join(name.split())
	rows = frappe.db.sql(
		"""
		SELECT name FROM `tabSupplier`
		WHERE REPLACE(REPLACE(REPLACE(name, '  ', ' '), '  ', ' '), '  ', ' ') = %s
		LIMIT 2
		""",
		(compact,),
	)
	# Prefer exact whitespace-normalized equality in Python for multi-space names
	candidates = frappe.get_all("Supplier", fields=["name"], limit=5000)
	matches = [row.name for row in candidates if " ".join(row.name.split()) == compact]
	if len(matches) == 1:
		return matches[0]
	if len(matches) > 1:
		frappe.throw(f"Ambiguous supplier for {name!r}: {matches}")
	if rows:
		return rows[0][0]
	frappe.throw(f"Supplier missing: {name}")


def create_supplier_po(supplier: str, group: dict) -> dict:
	"""`supplier` must already be the ERPNext Supplier name (see resolve_supplier)."""
	if not frappe.db.exists("Warehouse", WAREHOUSE):
		frappe.throw(f"Warehouse missing: {WAREHOUSE}")
	if not frappe.db.exists("Project", PROJECT):
		frappe.throw(f"Project missing: {PROJECT}")

	warnings = []
	po_items = []
	rate_sources = []
	order_date = getdate(ORDER_DATE)
	for line in group["items"]:
		item_code = line["item_code"]
		meta = frappe.db.get_value(
			"Item",
			item_code,
			["name", "stock_uom", "controlled_procurement_catalog", "disabled", "is_purchase_item"],
			as_dict=True,
		)
		if not meta:
			frappe.throw(f"Item missing: {item_code}")
		if cint(meta.disabled) or not cint(meta.is_purchase_item):
			frappe.throw(f"Item not purchase-active: {item_code}")
		if not cint(meta.controlled_procurement_catalog):
			frappe.throw(f"Item not in controlled catalog: {item_code}")
		ensure_item_supplier(item_code, supplier)
		rate = flt(line["rate"])
		if rate <= 0:
			frappe.throw(f"No positive sheet rate for {item_code}")
		catalog = cp.get_catalog_buying_price(item_code, supplier, COMPANY, str(order_date))
		catalog_rate = flt(catalog.get("rate")) if catalog.get("rate") is not None else None
		row = {
			"item_code": item_code,
			"qty": line["qty"],
			"rate": rate,
			"uom": meta.stock_uom,
			"warehouse": WAREHOUSE,
			"project": PROJECT,
		}
		if catalog_rate is None or abs(flt(catalog_rate) - flt(rate)) > 0.0001:
			row["rate_edited"] = 1
			row["price_change_reason"] = (
				"Migrated from MRG LPO Created sheet 24.10.2026 (Original LPO consolidation)"
			)
			warnings.append(f"{item_code}: sheet rate {rate} vs catalog {catalog_rate}")
		rate_sources.append(f"{item_code}=sheet:{rate}")
		po_items.append(row)

	_ensure_po_subcontract_attr()
	result = cp.create_purchase_order({
		"company": COMPANY,
		"supplier": supplier,
		"warehouse": WAREHOUSE,
		"project": PROJECT,
		"order_date": str(order_date),
		"required_by": str(frappe.utils.add_days(order_date, 7)),
		"lpo_type": "Standard",
		"creation_request_id": str(uuid4()),
		"items": po_items,
	})
	po_name = result["name"]
	frappe.db.set_value("Purchase Order", po_name, "remarks", group["remarks"], update_modified=False)
	return {
		"supplier": supplier,
		"new_po": po_name,
		"status": "created",
		"line_count": len(po_items),
		"remarks": group["remarks"],
		"warnings": "; ".join(warnings),
		"rate_sources": " | ".join(rate_sources),
	}


def ensure_item_supplier(item_code: str, supplier: str) -> None:
	if cp._item_has_supplier(item_code, supplier):
		return
	item = frappe.get_doc("Item", item_code)
	item.append("supplier_items", {"supplier": supplier})
	item.flags.controlled_procurement_api = True
	item.flags.ignore_permissions = True
	item.save()


def _ensure_po_subcontract_attr() -> None:
	"""Patch missing ERPNext attribute used for some non-stock PO lines."""
	from erpnext.buying.doctype.purchase_order.purchase_order import PurchaseOrder

	if not hasattr(PurchaseOrder, "is_old_subcontracting_flow"):
		PurchaseOrder.is_old_subcontracting_flow = property(lambda self: 0)  # type: ignore[attr-defined]


def write_result_csv(results: list[dict]) -> Path:
	path = Path(__file__).with_name(RESULT_CSV)
	fields = ["supplier", "new_po", "status", "line_count", "remarks", "warnings", "rate_sources"]
	with path.open("w", newline="", encoding="utf-8") as handle:
		writer = csv.DictWriter(handle, fieldnames=fields)
		writer.writeheader()
		for row in results:
			writer.writerow({k: row.get(k, "") for k in fields})
	_log(f"wrote {path}")
	return path


def _split_refs(value: str) -> list[str]:
	if not value:
		return []
	parts = []
	for chunk in value.replace(";", ",").split(","):
		part = chunk.strip()
		if part:
			parts.append(part)
	return parts


def _cell(value) -> str:
	return str(value or "").strip()


def _normalize_name(value: str) -> str:
	return " ".join((value or "").split()).casefold()


def _log(message: str) -> None:
	frappe.logger("po_creation_sheet").info(message)
	print(message)
