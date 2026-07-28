"""Clear cached workspace data after the Sales Desk layout is installed."""

import frappe


def execute():
	frappe.clear_cache()
