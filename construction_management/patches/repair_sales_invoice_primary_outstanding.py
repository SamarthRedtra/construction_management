# Copyright (c) 2026, Construction Management
# License: MIT

"""Repair Sales Invoice outstanding values overwritten by retention PLE rows."""

import frappe

from construction_management.overrides.invoice_outstanding import (
	update_primary_account_outstanding,
)


def execute():
	invoices = frappe.db.sql(
		"""
		SELECT DISTINCT si.name
		FROM `tabSales Invoice` si
		INNER JOIN `tabPayment Ledger Entry` ple
			ON ple.against_voucher_type = 'Sales Invoice'
			AND ple.against_voucher_no = si.name
			AND ple.account = si.debit_to
			AND ple.party_type = 'Customer'
			AND ple.party = si.customer
			AND ple.delinked = 0
		WHERE si.docstatus = 1
		""",
		pluck=True,
	)
	for invoice in invoices:
		update_primary_account_outstanding("Sales Invoice", invoice)
