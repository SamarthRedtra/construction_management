# Copyright (c) 2026, Construction Management
# License: MIT

"""Quotation BOQ hierarchy helpers (2-level vs 3-level)."""

from __future__ import annotations

import frappe

HIERARCHY_THREE_LEVEL = "3 Level (Section + Parent + Sub)"
HIERARCHY_TWO_LEVEL = "2 Level (Parent + Sub)"


def get_quotation_boq_hierarchy(company: str | None) -> str:
	if not company or not frappe.db.exists("BOQ Settings", company):
		return HIERARCHY_THREE_LEVEL

	value = frappe.db.get_value("BOQ Settings", company, "quotation_boq_hierarchy")
	return value or HIERARCHY_THREE_LEVEL


def is_two_level_hierarchy(company: str | None) -> bool:
	return get_quotation_boq_hierarchy(company) == HIERARCHY_TWO_LEVEL


def resolve_hierarchy_mode(company: str | None, lines: list) -> str:
	"""Use BOQ Settings, but fall back to line data when no Section rows exist."""
	configured = get_quotation_boq_hierarchy(company)
	if configured == HIERARCHY_TWO_LEVEL:
		return HIERARCHY_TWO_LEVEL

	if lines and not any((row.get("line_type") or "Parent") == "Section" for row in lines):
		return HIERARCHY_TWO_LEVEL

	return HIERARCHY_THREE_LEVEL
