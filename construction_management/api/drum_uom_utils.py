# Copyright (c) 2026, Construction Management
# License: MIT

"""Apply item-specific package conversions when a row is entered in Nos."""

from __future__ import annotations

import frappe
from frappe.utils import flt


def get_package_conversion_factor(item_code: str, uom: str) -> float:
	"""Return the configured conversion for a package UOM such as Nos."""
	if uom != "Nos":
		return 0

	conversion_factor = flt(
		frappe.db.get_value(
			"UOM Conversion Detail",
			{"parent": item_code, "uom": uom},
			"conversion_factor",
		)
	)
	if conversion_factor > 1:
		return conversion_factor

	# Compatibility for drum items created before a Nos conversion was added.
	conversion_factor = flt(
		frappe.db.get_value(
			"UOM Conversion Detail",
			{"parent": item_code, "uom": "DRUM"},
			"conversion_factor",
		)
	)
	return conversion_factor if conversion_factor > 1 else 0


def get_drum_conversion_factor(item_code: str, uom: str) -> float:
	"""Backward-compatible alias used by older patches."""
	return get_package_conversion_factor(item_code, uom)


def apply_drum_uom_conversion(row) -> bool:
	"""
	Fix Nos @ CF 1 lines on drum items so stock_qty is in Kg.

	Returns True when conversion_factor was updated.
	"""
	package_cf = get_package_conversion_factor(row.item_code, row.uom)
	if not package_cf or flt(row.conversion_factor) != 1:
		return False

	row.conversion_factor = package_cf
	row.stock_qty = flt(row.qty) * package_cf
	if flt(row.rate):
		row.stock_uom_rate = flt(row.rate) / package_cf
	return True


def apply_drum_uom_conversion_for_items(items) -> None:
	for row in items or []:
		if not row.get("item_code"):
			continue
		apply_drum_uom_conversion(row)


def apply_stock_entry_uom_conversion(doc, method=None) -> None:
	"""Apply configured Nos conversions to draft Stock Entry rows."""
	for row in doc.get("items") or []:
		if not row.get("item_code"):
			continue

		package_cf = get_package_conversion_factor(row.item_code, row.uom)
		if not package_cf or flt(row.conversion_factor) != 1:
			continue

		row.conversion_factor = package_cf
		row.transfer_qty = flt(row.qty) * package_cf
