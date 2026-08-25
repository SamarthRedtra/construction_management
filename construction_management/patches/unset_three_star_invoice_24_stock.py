# Copyright (c) 2026, Construction Management
# License: MIT

"""Unset Maintain Stock on THREE STAR invoice #24 PO items."""

from __future__ import annotations

import frappe

PO_NAMES = ("SKD-LPO-00463", "SKD-LPO-00464-1")


def execute():
	existing_pos = [name for name in PO_NAMES if frappe.db.exists("Purchase Order", name)]
	if not existing_pos:
		return

	item_codes = frappe.get_all(
		"Purchase Order Item",
		filters={"parent": ["in", existing_pos], "docstatus": 1},
		pluck="item_code",
		distinct=True,
	)
	if not item_codes:
		return

	updated = []
	for item_code in item_codes:
		if not frappe.db.exists("Item", item_code):
			continue
		if frappe.db.get_value("Item", item_code, "is_stock_item"):
			frappe.db.set_value("Item", item_code, "is_stock_item", 0, update_modified=False)
			updated.append(item_code)

	if not updated:
		frappe.logger("construction_management").info(
			"Skip THREE STAR invoice #24: PO items already have Maintain Stock off"
		)
		return

	frappe.logger("construction_management").info(
		f"Unset Maintain Stock on {', '.join(updated)} from {', '.join(existing_pos)}"
	)
