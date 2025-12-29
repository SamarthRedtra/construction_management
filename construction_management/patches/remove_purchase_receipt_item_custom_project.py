# Copyright (c) 2024, Construction Management
# License: MIT
"""
Patch: remove the legacy custom_project field from Purchase Receipt Item.
"""

import frappe


def execute():
	# Remove the Custom Field if it exists
	if frappe.db.exists("Custom Field", {"dt": "Purchase Receipt Item", "fieldname": "custom_project"}):
		frappe.delete_doc("Custom Field", "Purchase Receipt Item-custom_project", ignore_permissions=True)
		frappe.clear_cache(doctype="Purchase Receipt Item")
