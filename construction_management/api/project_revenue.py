# Copyright (c) 2026, Construction Management
# License: MIT

"""Shared project revenue calculations for operational reports."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt


def _sales_account_for_company(company: str) -> str | None:
	"""Use the company's Sales ledger. Fall back to Sales Account only when Sales is absent."""
	for account_name in ("Sales", "Sales Account"):
		account = frappe.db.get_value(
			"Account",
			{"account_name": account_name, "company": company, "is_group": 0},
			"name",
		)
		if account:
			return account
	return None


def get_project_sales_gl_balance(project: str) -> float | None:
	"""All-time Sales account balance for the project's company. None if no sales ledger exists."""
	if not project:
		return None
	company = frappe.db.get_value("Project", project, "company")
	if not company:
		return None
	account = _sales_account_for_company(company)
	if not account:
		frappe.msgprint(
			_(
				"Neither Sales nor Sales Account was found for {0}. Actual Revenue Value was left unchanged."
			).format(company)
		)
		return None
	result = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(credit), 0) - COALESCE(SUM(debit), 0)
		FROM `tabGL Entry`
		WHERE project = %s AND account = %s AND is_cancelled = 0
		""",
		(project, account),
	)
	return flt(result[0][0]) if result else 0.0


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
