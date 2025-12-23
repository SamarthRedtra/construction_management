# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _


@frappe.whitelist()
def get_warehouse_project(warehouse):
	"""
	Get the linked project for a warehouse.
	
	Args:
		warehouse: Warehouse name
		
	Returns:
		Project name if linked, else None
	"""
	if not warehouse:
		return None

	project_data = frappe.db.get_value(
		"Warehouse",
		warehouse,
		["custom_project", "project"],
		as_dict=True,
	)

	if not project_data:
		return None

	# Prefer the custom link, fallback to the standard project field
	return project_data.get("custom_project") or project_data.get("project")
