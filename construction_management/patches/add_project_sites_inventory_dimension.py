# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _


def execute():
	"""
	Create Inventory Dimension for Project Sites
	This will automatically create custom fields in all stock transactions
	"""
	# Check if Inventory Dimension for Project Sites already exists
	if frappe.db.exists("Inventory Dimension", {"reference_document": "Project Sites"}):
		print("Inventory Dimension for Project Sites already exists")
		return
	
	try:
		# Create Inventory Dimension
		inventory_dim = frappe.get_doc({
			"doctype": "Inventory Dimension",
			"reference_document": "Project Sites",
			"dimension_name": "Project Sites",
			"apply_to_all_doctypes": 1,
			"istable": 0,
			"source_fieldname": "project_sites",
			"target_fieldname": "project_sites",
			"type_of_transaction": "Outward",
			"condition": "",
			"fetch_from_parent": "",
			"disabled": 0
		})
		
		inventory_dim.insert(ignore_permissions=True)
		frappe.db.commit()
		
		print(f"Created Inventory Dimension: {inventory_dim.name}")
		print("Custom fields will be automatically created in stock transactions")
		
	except Exception as e:
		print(f"Error creating Inventory Dimension: {str(e)}")
		frappe.log_error(f"Error in add_project_sites_inventory_dimension patch: {str(e)}")

