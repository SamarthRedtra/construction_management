# Copyright (c) 2026, Construction Management
# License: MIT

"""Relink submitted Sales Invoice lines (added via "Add BOQ service") to their Sales Order lines,
refresh Sales Order billing and the BOQ Progress Ledger, and queue a GL repost for the changed invoices.
"""

import frappe


def execute():
	if not frappe.db.has_column("Sales Invoice", "custom_source_sales_orders"):
		return

	from construction_management.api.relink_si_sales_orders import run

	run(dry_run=0)
