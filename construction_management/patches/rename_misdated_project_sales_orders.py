"""Rename project Sales Orders (PINV) whose name month does not match their transaction date.

A draft re-dated into another month should have been renamed on save, but the rename hook failed,
so e.g. PINV/1178/2026-OCT/2 is dated 30 Sep. Each such order gets the next free number of its real
month; Frappe updates every link (invoices, journal entries, ledgers) to the new name.
"""

import frappe
from frappe.model.rename_doc import rename_doc

from construction_management.project_document_naming import allocate_project_document_name, format_period


def execute():
	for order in frappe.get_all(
		"Sales Order",
		filters={"name": ["like", "PINV/%"], "docstatus": ["<", 2]},
		fields=["name", "transaction_date"],
	):
		parts = order.name.split("/")
		if len(parts) != 4 or not order.transaction_date or parts[2] == format_period(order.transaction_date):
			continue
		doc = frappe.get_doc("Sales Order", order.name)
		new_name = allocate_project_document_name(doc)
		if new_name and new_name != order.name:
			rename_doc("Sales Order", order.name, new_name, force=True, ignore_permissions=True, show_alert=False)
