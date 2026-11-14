"""Repair combined Tax Invoices that bill multiple source SOs on one aggregated item row."""

import frappe


def execute():
	if not frappe.db.has_column("Sales Invoice", "custom_source_sales_orders"):
		return

	from construction_management.api.repair_combined_si_sales_orders import run

	run(dry_run=0, invoices=None)