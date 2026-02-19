# Copyright (c) 2024, Construction Management
# License: MIT

"""
Patch to set ignore_user_permissions on Project Engineer and Sales Engineer custom fields.

When user dc@mrggroup.ae (or similar) has User Permission restricted to Company = MRG only,
Project 1101 was hidden in list view because the Project Engineer links to an Employee from
another company. User Permissions on Employee were filtering out projects where the
project engineer is from a different company.

Setting ignore_user_permissions = 1 on these Link fields ensures the list view filters
only by Project.company (and other allowed fields), not by the linked Employee's company.
"""

import frappe


def execute():
	"""Set ignore_user_permissions on Project Engineer and Sales Engineer custom fields"""
	fields_to_update = [
		"Project-custom_project_engineer",
		"Project-custom_sales_engineer",
	]

	for field_name in fields_to_update:
		if frappe.db.exists("Custom Field", field_name):
			frappe.db.set_value("Custom Field", field_name, "ignore_user_permissions", 1)
			print(f"Updated {field_name}: ignore_user_permissions = 1")
		else:
			print(f"Custom Field {field_name} not found, skipping")

	frappe.db.commit()

	# Reload Project meta so ignore_user_permissions is picked up
	frappe.reload_doctype("Project")
