# Copyright (c) 2026, Construction Management
# License: MIT

"""Run the readonly SO↔SI month-gap Connections audit on migrate.

Reports pairs where Sales Order.transaction_date and Sales Invoice.posting_date
differ by two or more months (header or line link). Does not change data.
"""

import frappe


def execute():
	if not frappe.db.has_table("Sales Invoice") or not frappe.db.has_table("Sales Order"):
		return
	if not frappe.db.has_column("Sales Invoice", "custom_sales_order"):
		return

	from construction_management.api.audit_so_si_month_mismatch import run

	rows = run(min_month_gap=2)
	frappe.logger("construction_management").info(
		"audit_so_si_month_mismatch: %s pairs with month_gap >= 2",
		len(rows),
	)
