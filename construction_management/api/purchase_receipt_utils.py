# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _


@frappe.whitelist()
def get_warehouse_project(warehouse, company=None):
	"""
	Get the linked project for a warehouse.
	
	Args:
		warehouse: Warehouse name
		company: Optional company to validate the project against
		
	Returns:
		Project name if linked, else None
	"""
	if not warehouse:
		return None

	fields = ["custom_project"]

	# Some sites may not have a standard `project` field on Warehouse; check before querying
	if frappe.db.has_column("Warehouse", "project"):
		fields.append("project")

	project_data = frappe.db.get_value(
		"Warehouse",
		warehouse,
		fields,
		as_dict=True,
	)

	if not project_data:
		return None

	# Prefer the custom link, fallback to the standard project field
	project = project_data.get("custom_project") or project_data.get("project")

	if project and company:
		project_company = frappe.db.get_value("Project", project, "company")
		if project_company and project_company != company:
			# Ignore projects belonging to another company
			return None

	return project


@frappe.whitelist()
def get_project_warehouse(project):
	"""
	Get a warehouse linked to the given project (prefers custom_project link, falls back to standard project field).
	Returns the first matching warehouse name.
	"""
	if not project:
		return None

	warehouse = frappe.db.get_value("Warehouse", {"custom_project": project}, "name")

	if not warehouse and frappe.db.has_column("Warehouse", "project"):
		warehouse = frappe.db.get_value("Warehouse", {"project": project}, "name")

	return warehouse
