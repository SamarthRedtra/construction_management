# Copyright (c) 2026, Construction Management
# License: MIT

"""Restore the native v17 Stock Entry layout and its accounting dimensions tab."""

import frappe


STALE_PROPERTY_SETTERS = (
	"Stock Entry-main-field_order",
	"Stock Entry-accounting_dimensions_section-hidden",
)


def execute():
	frappe.db.delete("Property Setter", {"name": ["in", STALE_PROPERTY_SETTERS]})
	frappe.clear_cache(doctype="Stock Entry")
