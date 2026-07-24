# Copyright (c) 2026, Construction Management
# License: MIT

"""Allow selecting Sales Manager Approver without User read permission."""

import frappe


def execute():
	name = "Quotation-custom_sales_manager_approver"
	if not frappe.db.exists("Custom Field", name):
		return
	frappe.db.set_value(
		"Custom Field",
		name,
		{
			"ignore_user_permissions": 1,
			"read_only": 0,
			"allow_on_submit": 1,
		},
		update_modified=False,
	)
	frappe.clear_cache(doctype="Quotation")
