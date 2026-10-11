"""Run the guarded MRG catalog and stock-snapshot preflight during deployment."""

import frappe

from construction_management.api import mrg_stock_snapshot


def execute():
	if not frappe.db.exists("Company", mrg_stock_snapshot.COMPANY):
		return
	mrg_stock_snapshot.activate_report_warehouses()
	result = mrg_stock_snapshot.run()
	frappe.logger("controlled_procurement").info({"event": "mrg_stock_snapshot", **result})
