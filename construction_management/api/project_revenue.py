# Copyright (c) 2026, Construction Management
# License: MIT

"""Shared project revenue calculations for operational reports."""

from __future__ import annotations

import frappe
from frappe.utils import flt


def get_project_billed_revenue(project: str) -> float:
	"""Return submitted BOQ revenue excluding VAT, advances, and deductions."""
	if not project:
		return 0.0

	advance_clause = ""
	if frappe.db.has_column("Sales Invoice", "custom_is_advanced"):
		advance_clause = "AND IFNULL(si.custom_is_advanced, 0) = 0"

	result = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(sii.base_net_amount), 0)
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.project = %s
		  AND si.docstatus = 1
		  {advance_clause}
		  AND IFNULL(sii.boq_item, '') != ''
		  AND IFNULL(sii.item_code, '') NOT IN ('RETENTION-DEDUCTION', 'ADVANCE-DEDUCTION')
		""",
		project,
	)
	return flt(result[0][0]) if result else 0.0
