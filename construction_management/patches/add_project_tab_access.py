# Copyright (c) 2026, Construction Management
# License: MIT

import frappe


def execute():
	if not frappe.db.exists("Project Tab Access", "Project Tab Access"):
		doc = frappe.new_doc("Project Tab Access")
		doc.enabled = 0
		doc.insert(ignore_permissions=True)
