# Copyright (c) 2024, Construction Management
# License: MIT

import frappe


def execute():
	"""
	Add Project link field to Warehouse DocType for site-level project tracking.
	(Task 2.1: Add Project field to Warehouse)
	"""
	
	fields_to_create = [
		{
			"dt": "Warehouse",
			"fieldname": "custom_project",
			"label": "Project",
			"fieldtype": "Link",
			"options": "Project",
			"insert_after": "company",
			"description": "Link this warehouse/site to a specific project for material tracking"
		}
	]
	
	for field_def in fields_to_create:
		try:
			create_custom_field_if_not_exists(field_def)
		except Exception as e:
			frappe.logger().error(f"Error creating custom field {field_def.get('fieldname')}: {str(e)}")
	
	frappe.db.commit()
	print("Warehouse Project field created successfully")


def create_custom_field_if_not_exists(field_def):
	"""Create a custom field if it doesn't already exist"""
	dt = field_def.get("dt")
	fieldname = field_def.get("fieldname")
	
	# Check if field already exists
	if frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fieldname}):
		frappe.logger().info(f"Custom field {dt}-{fieldname} already exists, skipping")
		return
	
	# Create the custom field
	doc = frappe.new_doc("Custom Field")
	doc.update(field_def)
	doc.flags.ignore_validate = True
	doc.insert(ignore_permissions=True)
	frappe.logger().info(f"Created custom field {dt}-{fieldname}")

