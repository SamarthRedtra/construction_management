# Copyright (c) 2026, Construction Management
# License: MIT
"""
Update item_name only for LPO / purchase-flow corrections.

Reads name-change rows from LPO LIST.xlsx (ACTION REQUIRED 1 column) and updates:
- Item.item_name
- Purchase Order Item / Purchase Receipt Item / Purchase Invoice Item item_name

Item code (name) is NOT changed. UOM, rate, conversion are out of scope.

Usage:
  bench --site skada.local execute construction_management.scripts.lpo_item_name_update.run
  bench --site skada.local execute construction_management.scripts.lpo_item_name_update.run --kwargs '{"dry_run": 0}'
  bench --site skada.local execute construction_management.scripts.lpo_item_name_update.run --kwargs '{"xlsx_path": "/path/LPO LIST.xlsx", "dry_run": 1}'
"""

from __future__ import annotations

import re
from pathlib import Path

import frappe
from frappe.utils import cint

PURCHASE_CHILD_TABLES = (
	"Purchase Order Item",
	"Purchase Receipt Item",
	"Purchase Invoice Item",
)

# Fallback if Excel parsing misses a row (item_code -> new item_name).
HARDCODED_RENAMES = {
	"BIFLEX PL 4MM /200 GSM": "BIFLEX PL 4MM /180 GSM",
	"120GSM Geo-textile layer": "AWAZEL TEX 120 GSM (2.9 X 100)290 M²/ ROLL",
	"NW 120 GSM PET -WHITE (3 MTR *100 MTR)": "GEOTEC -120GSM GEOTEXTILE  (3 X 100)300 M²/ ROLL",
	"AWAZEL PU 4048 POLYOL": "AWAZEL PU 4048 POLYOL (220KG) DRUM",
	"FILLER BOARD 10MM THICK WITH 7CM CUTTING PCS": "BITUMEN IMPEREGNATED BOARD 10 MM -CUTTING",
	"PROTECTION BOARD  (3.2mmx2mx1m)": "MS40 200CM MEMBRANE PROTECTION BOARD 4MM 300 M2",
}


def run(dry_run=1, xlsx_path=None, item_codes=None):
	dry_run = cint(dry_run)
	item_codes = _normalize_item_codes(item_codes)
	renames = _load_renames(xlsx_path)
	if item_codes:
		renames = {k: v for k, v in renames.items() if k in item_codes}

	if not renames:
		print("No item name updates found.")
		return {"updated_items": 0, "updated_rows": 0, "dry_run": bool(dry_run)}

	print(f"{'DRY RUN' if dry_run else 'LIVE RUN'} — {len(renames)} item(s) to update:")
	for old_code, new_name in renames.items():
		print(f"  {old_code}")
		print(f"    -> {new_name}")

	stats = {"updated_items": 0, "updated_rows": 0, "missing_items": [], "dry_run": bool(dry_run)}

	for old_code, new_name in renames.items():
		if not frappe.db.exists("Item", old_code):
			stats["missing_items"].append(old_code)
			print(f"  SKIP (Item not found): {old_code}")
			continue

		current_name = frappe.db.get_value("Item", old_code, "item_name")
		if (current_name or "").strip() == new_name.strip():
			print(f"  OK (already correct): {old_code}")
		else:
			print(f"  Item: {old_code} | {current_name!r} -> {new_name!r}")
			if not dry_run:
				frappe.db.set_value("Item", old_code, "item_name", new_name, update_modified=False)
			stats["updated_items"] += 1

		for doctype in PURCHASE_CHILD_TABLES:
			rows = frappe.get_all(
				doctype,
				filters={"item_code": old_code},
				fields=["name", "parent", "item_name"],
			)
			for row in rows:
				if (row.item_name or "").strip() == new_name.strip():
					continue
				print(
					f"    {doctype}: {row.parent} | {row.item_name!r} -> {new_name!r}"
				)
				if not dry_run:
					frappe.db.set_value(doctype, row.name, "item_name", new_name, update_modified=False)
				stats["updated_rows"] += 1

	if not dry_run:
		frappe.db.commit()
		print("Committed.")
	else:
		print("Dry run complete — pass dry_run=0 to apply.")

	if stats["missing_items"]:
		print("Missing items:", ", ".join(stats["missing_items"]))

	return stats


def _normalize_item_codes(item_codes):
	if not item_codes:
		return None
	if isinstance(item_codes, str):
		item_codes = [x.strip() for x in item_codes.split(",") if x.strip()]
	return set(item_codes)


def _load_renames(xlsx_path=None):
	renames = {}
	xlsx_path = Path(xlsx_path) if xlsx_path else _default_xlsx_path()
	if xlsx_path.exists():
		try:
			import pandas as pd
		except ImportError:
			print(f"pandas not available — using hardcoded mapping only ({xlsx_path})")
		else:
			df = pd.read_excel(xlsx_path)
			for _, row in df.iterrows():
				item_code = _extract_item_code(row.get("ITEM"))
				new_name = _extract_new_name(row.get("ACTION REQUIRED 1"), row.get("ITEM"))
				if item_code and new_name:
					renames[item_code] = new_name

	# Hardcoded mapping wins over Excel parsing (handles names with parentheses).
	renames.update(HARDCODED_RENAMES)
	return renames


def _default_xlsx_path():
	# bench root: sites/../LPO LIST.xlsx
	bench_path = Path(frappe.get_site_path("..", "..", "LPO LIST.xlsx"))
	if bench_path.exists():
		return bench_path
	return Path(frappe.get_site_path("..", "LPO LIST.xlsx"))


def _extract_item_code(item_value):
	if item_value is None or (isinstance(item_value, float) and str(item_value) == "nan"):
		return None
	text = str(item_value).strip()
	if not text or text.lower() == "nan":
		return None
	if ":" in text:
		left, right = [part.strip() for part in text.split(":", 1)]
		return left or right
	return text


def _extract_new_name(action_value, item_value):
	if action_value is None or (isinstance(action_value, float) and str(action_value) == "nan"):
		return None

	action = str(action_value).strip()
	if not action or action.upper().startswith("SAME AS"):
		return None

	upper = action.upper()
	if any(
		token in upper
		for token in (
			"ADD CONVERSION",
			"CHANGE TO BD",
			"CHANGE TO PAIL",
			"CHANGE RATE",
			"ITEM CREATED IN NOS",
		)
	):
		return None

	match = re.search(
		r"(?:CHANGE NAME TO|CHANE ITEM TO|CHANE NAME TO)\s*\(",
		action,
		flags=re.IGNORECASE,
	)
	if match:
		return _clean_new_name(action[match.end() :])

	# e.g. row 16: action is only the target description
	if "CHANGE" not in upper and _extract_item_code(item_value):
		return _clean_new_name(action)

	return None


def _clean_new_name(name):
	name = re.split(r"\)\s*AND\b", name, maxsplit=1, flags=re.IGNORECASE)[0].strip()
	if name.endswith(")"):
		name = name[:-1].strip()
	return name
