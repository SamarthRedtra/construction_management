# Copyright (c) 2026, Construction Management
# License: MIT

"""Helpers for drum-style items whose purchase UOM is Nos but stock UOM is Kg."""

from __future__ import annotations

import frappe
from frappe.utils import flt


def get_drum_conversion_factor(item_code: str, uom: str) -> float:
	"""Return DRUM conversion factor when a line uses Nos for a drum item."""
	if uom != "Nos":
		return 0

	drum_cf = flt(
		frappe.db.get_value(
			"UOM Conversion Detail",
			{"parent": item_code, "uom": "DRUM"},
			"conversion_factor",
		)
	)
	return drum_cf if drum_cf > 1 else 0


def apply_drum_uom_conversion(row) -> bool:
	"""
	Fix Nos @ CF 1 lines on drum items so stock_qty is in Kg.

	Returns True when conversion_factor was updated.
	"""
	drum_cf = get_drum_conversion_factor(row.item_code, row.uom)
	if not drum_cf or flt(row.conversion_factor) != 1:
		return False

	row.conversion_factor = drum_cf
	row.stock_qty = flt(row.qty) * drum_cf
	if flt(row.rate):
		row.stock_uom_rate = flt(row.rate) / drum_cf
	return True


def apply_drum_uom_conversion_for_items(items) -> None:
	for row in items or []:
		if not row.get("item_code"):
			continue
		apply_drum_uom_conversion(row)
