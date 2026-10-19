# Copyright (c) 2026, Construction Management
# License: MIT

"""Apply Item Trail List mapping on migrate (name_only / rename_code / merge).

Does not cancel PO/GRN. Rename and merge rewrite Link fields in place.
Fill apply_item_trail_list_migration.csv before production deploy.
"""

from __future__ import annotations

import csv
from pathlib import Path

import frappe
from frappe import _
from frappe.utils import cstr

ACTIONS = ("name_only", "rename_code", "merge")
ACTION_ORDER = {"name_only": 0, "rename_code": 1, "merge": 2}
MERGE_FIELDS = ("stock_uom", "is_stock_item", "has_serial_no", "has_batch_no")
CSV_NAME = "apply_item_trail_list_migration.csv"


def execute():
	rows = load_mapping_rows(mapping_csv_path())
	if not rows:
		_log("No Item Trail mapping rows; nothing to apply.")
		return
	run(rows)


def run(rows: list[dict]) -> dict:
	"""Validate and apply mapping rows. Used by execute() and unit tests."""
	validated = [validate_row(row, index) for index, row in enumerate(rows, start=2)]
	validated.sort(key=lambda row: (ACTION_ORDER[row["action"]], row["old_item_code"]))
	results = {"applied": [], "skipped": [], "failed": []}
	for row in validated:
		try:
			outcome = apply_row(row)
			results[outcome["status"]].append(outcome)
			_log(f"{outcome['status']}: {outcome['detail']}")
			if outcome["status"] == "applied":
				frappe.db.commit()
		except Exception as exc:
			frappe.db.rollback()
			detail = f"{row['action']} {row['old_item_code']}: {exc}"
			results["failed"].append({"status": "failed", "detail": detail, "row": row})
			_log(f"failed: {detail}")
	if results["failed"]:
		summary = "; ".join(item["detail"] for item in results["failed"][:20])
		extra = f" (+{len(results['failed']) - 20} more)" if len(results["failed"]) > 20 else ""
		frappe.throw(
			_("Item Trail migration failed for {0} row(s): {1}{2}").format(
				len(results["failed"]), summary, extra
			)
		)
	return results


def mapping_csv_path() -> Path:
	return Path(__file__).with_name(CSV_NAME)


def load_mapping_rows(path: Path | str) -> list[dict]:
	path = Path(path)
	if not path.is_file():
		frappe.throw(_("Item Trail mapping file missing: {0}").format(path))
	with path.open(newline="", encoding="utf-8-sig") as handle:
		reader = csv.DictReader(handle)
		if not reader.fieldnames:
			return []
		required = {"old_item_code", "new_item_code", "new_item_name", "action"}
		missing = required - {name.strip() for name in reader.fieldnames if name}
		if missing:
			frappe.throw(_("Item Trail mapping CSV missing columns: {0}").format(", ".join(sorted(missing))))
		rows = []
		for raw in reader:
			row = {
				"old_item_code": _cell(raw.get("old_item_code")),
				"new_item_code": _cell(raw.get("new_item_code")),
				"new_item_name": _cell(raw.get("new_item_name")),
				"action": _cell(raw.get("action")).lower(),
			}
			if not any(row.values()):
				continue
			rows.append(row)
		return rows


def validate_row(row: dict, line_no: int) -> dict:
	action = row.get("action") or ""
	old = row.get("old_item_code") or ""
	new = row.get("new_item_code") or ""
	name = row.get("new_item_name") or ""
	if action not in ACTIONS:
		frappe.throw(_("Line {0}: action must be one of {1}.").format(line_no, ", ".join(ACTIONS)))
	if not old:
		frappe.throw(_("Line {0}: old_item_code is required.").format(line_no))
	if action == "name_only" and not name:
		frappe.throw(_("Line {0}: new_item_name is required for name_only.").format(line_no))
	if action in {"rename_code", "merge"} and not new:
		frappe.throw(_("Line {0}: new_item_code is required for {1}.").format(line_no, action))
	if action == "rename_code" and old == new:
		frappe.throw(_("Line {0}: rename_code old and new item codes must differ.").format(line_no))
	if action == "merge" and old == new:
		frappe.throw(_("Line {0}: merge old and new item codes must differ.").format(line_no))
	return {
		"old_item_code": old,
		"new_item_code": new,
		"new_item_name": name,
		"action": action,
	}


def apply_row(row: dict) -> dict:
	action = row["action"]
	if action == "name_only":
		return _apply_name_only(row)
	if action == "rename_code":
		return _apply_rename(row, merge=False)
	return _apply_rename(row, merge=True)


def _apply_name_only(row: dict) -> dict:
	old = row["old_item_code"]
	target_name = row["new_item_name"]
	if not frappe.db.exists("Item", old):
		return _skip(row, f"name_only {old}: Item missing")
	current = frappe.db.get_value("Item", old, "item_name")
	if cstr(current) == target_name:
		return _skip(row, f"name_only {old}: item_name already {target_name!r}")
	_set_item_name(old, target_name)
	return _applied(row, f"name_only {old}: item_name → {target_name!r}")


def _apply_rename(row: dict, merge: bool) -> dict:
	old = row["old_item_code"]
	new = row["new_item_code"]
	label = "merge" if merge else "rename_code"
	old_exists = frappe.db.exists("Item", old)
	new_exists = frappe.db.exists("Item", new)

	if not old_exists and new_exists:
		if row["new_item_name"]:
			_set_item_name_if_needed(new, row["new_item_name"])
		return _skip(row, f"{label} {old} → {new}: already migrated")
	if not old_exists:
		return _fail(row, f"{label} {old} → {new}: old Item missing")
	if merge:
		if not new_exists:
			return _fail(row, f"merge {old} → {new}: target Item missing")
		blocker = merge_blocker(old, new)
		if blocker:
			return _fail(row, f"merge {old} → {new}: {blocker}")
	elif new_exists:
		return _fail(row, f"rename_code {old} → {new}: target already exists (use merge)")

	frappe.rename_doc(
		"Item",
		old,
		new,
		force=True,
		merge=merge,
		ignore_permissions=True,
		show_alert=False,
		rebuild_search=False,
	)
	if row["new_item_name"]:
		_set_item_name_if_needed(new, row["new_item_name"])
	return _applied(row, f"{label} {old} → {new}")


def merge_blocker(old: str, new: str) -> str | None:
	"""Pre-check ERPNext merge property and SR conflicts."""
	old_props = frappe.db.get_value("Item", old, MERGE_FIELDS, as_dict=True)
	new_props = frappe.db.get_value("Item", new, MERGE_FIELDS, as_dict=True)
	if not old_props or not new_props:
		return "Item properties unavailable"
	for field in MERGE_FIELDS:
		if cstr(old_props.get(field)) != cstr(new_props.get(field)):
			return f"{field} differs ({old_props.get(field)!r} vs {new_props.get(field)!r})"
	parents = frappe.db.sql(
		"""
		select parent
		from `tabStock Reconciliation Item`
		where docstatus = 1 and item_code in (%s, %s)
		group by parent
		having count(distinct item_code) > 1
		""",
		(old, new),
		pluck=True,
	)
	if parents:
		return f"both items on submitted Stock Reconciliation {', '.join(parents[:5])}"
	return None


def _set_item_name_if_needed(item_code: str, item_name: str) -> None:
	if cstr(frappe.db.get_value("Item", item_code, "item_name")) == item_name:
		return
	_set_item_name(item_code, item_name)


def _set_item_name(item_code: str, item_name: str) -> None:
	item = frappe.get_doc("Item", item_code)
	item.item_name = item_name
	item.flags.controlled_procurement_api = True
	item.flags.ignore_permissions = True
	item.save()


def _cell(value) -> str:
	return " ".join(str(value or "").split())


def _applied(row: dict, detail: str) -> dict:
	return {"status": "applied", "detail": detail, "row": row}


def _skip(row: dict, detail: str) -> dict:
	return {"status": "skipped", "detail": detail, "row": row}


def _fail(row: dict, detail: str) -> dict:
	"""Record a business failure without raising; run() aggregates these."""
	raise frappe.ValidationError(detail)


def _log(message: str) -> None:
	frappe.logger("item_trail_migration").info(message)
