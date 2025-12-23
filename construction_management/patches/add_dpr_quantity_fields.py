# Copyright (c) 2024, Construction Management
# License: MIT

import frappe


def execute():
	"""
	Add quantity summary fields to Daily Progress Record DocType.
	(Task 3.1: Add quantity fields to DPR DocType)
	"""
	
	fields_to_create = [
		{
			"dt": "Daily Progress Record",
			"fieldname": "total_labour_hours",
			"label": "Total Labour Hours",
			"fieldtype": "Float",
			"insert_after": "labour_cost",
			"read_only": 1,
			"precision": "2"
		},
		{
			"dt": "Daily Progress Record",
			"fieldname": "total_material_qty",
			"label": "Total Material Qty",
			"fieldtype": "Float",
			"insert_after": "material_cost",
			"read_only": 1,
			"precision": "2"
		},
		{
			"dt": "Daily Progress Record",
			"fieldname": "total_asset_hours",
			"label": "Total Asset Hours",
			"fieldtype": "Float",
			"insert_after": "asset_cost",
			"read_only": 1,
			"precision": "2"
		},
		{
			"dt": "Daily Progress Record",
			"fieldname": "total_subcontract_qty",
			"label": "Total Subcontract Qty",
			"fieldtype": "Float",
			"insert_after": "subcontract_cost",
			"read_only": 1,
			"precision": "2"
		},
		{
			"dt": "Daily Progress Record",
			"fieldname": "total_expense_count",
			"label": "Total Expense Count",
			"fieldtype": "Int",
			"insert_after": "expense_cost",
			"read_only": 1
		}
	]
	
	for field_def in fields_to_create:
		try:
			create_custom_field_if_not_exists(field_def)
		except Exception as e:
			frappe.logger().error(f"Error creating custom field {field_def.get('fieldname')}: {str(e)}")
	
	frappe.db.commit()
	print("DPR quantity summary fields created successfully")


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

