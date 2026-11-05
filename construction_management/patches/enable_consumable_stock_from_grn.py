# Copyright (c) 2026, Construction Management
# License: MIT

"""Enable Maintain Stock on CSV consumables and book GRN qty via Stock Reconciliation."""

from __future__ import annotations

import frappe

from construction_management.scripts.enable_consumable_stock_from_grn import (
	CSV_NAME,
	default_csv_path,
	run,
)

CUTOVER_MARKER = "Enable Maintain Stock cutover for controlled consumables"


def execute():
	if not default_csv_path().is_file():
		frappe.logger("construction_management").warning(
			f"Skipping consumable stock enable: CSV missing ({CSV_NAME})"
		)
		return
	if _already_applied():
		frappe.logger("construction_management").info(
			"Skipping consumable stock enable: cutover Stock Reconciliation already present"
		)
		return

	summary = run(dry_run=0)
	frappe.logger("construction_management").info(
		"Consumable stock enable applied: "
		f"enabled={summary.get('enabled_count')} "
		f"documents={len(summary.get('documents') or [])} "
		f"bookable_qty={summary.get('bookable_qty')}"
	)


def _already_applied() -> bool:
	return bool(
		frappe.db.exists(
			"Comment",
			{
				"comment_type": "Info",
				"reference_doctype": "Stock Reconciliation",
				"content": ("like", f"%{CUTOVER_MARKER}%"),
			},
		)
	)
