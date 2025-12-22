# Copyright (c) 2024, Construction Management
# License: MIT

import frappe


def execute():
	"""Create custom fields for splitting Purchase Receipt items by project"""
	
	fields_to_create = [
		{
			"dt": "Purchase Receipt",
			"fieldname": "split_item_by_project_section",
			"label": "Split Items by Project",
			"fieldtype": "Section Break",
			"insert_after": "project",
			"collapsible": 1
		},
		{
			"dt": "Purchase Receipt",
			"fieldname": "split_item_by_project",
			"label": "Enable Item Splitting",
			"fieldtype": "Check",
			"insert_after": "split_item_by_project_section",
			"default": "0",
			"description": "Enable to split item quantities across multiple rows for different projects"
		},
		{
			"dt": "Purchase Receipt",
			"fieldname": "split_quantity",
			"label": "Split Quantity",
			"fieldtype": "Float",
			"insert_after": "split_item_by_project",
			"default": "0",
			"description": "Quantity per row when splitting (e.g., if total qty is 40 and split qty is 6, creates 7 rows: 6 rows with qty 6, 1 row with qty 4)",
			"depends_on": "eval:doc.split_item_by_project",
			"non_negative": 1
		},
		{
			"dt": "Purchase Receipt",
			"fieldname": "split_button",
			"label": "Split Selected Items",
			"fieldtype": "Button",
			"insert_after": "split_quantity",
			"depends_on": "eval:doc.split_item_by_project && doc.split_quantity > 0"
		},
		{
			"dt": "Purchase Receipt",
			"fieldname": "column_break_split",
			"fieldtype": "Column Break",
			"insert_after": "split_button"
		},
		{
			"dt": "Purchase Receipt",
			"fieldname": "split_info",
			"label": "Instructions",
			"fieldtype": "Small Text",
			"insert_after": "column_break_split",
			"read_only": 1,
			"default": "Click 'Split Selected Items' to split items with quantity >= Split Quantity. You can select which items to split from the dialog.",
			"depends_on": "eval:doc.split_item_by_project"
		}
	]
	
	for field_def in fields_to_create:
		try:
			create_custom_field_if_not_exists(field_def)
		except Exception as e:
			frappe.logger().error(f"Error creating custom field {field_def.get('fieldname')}: {str(e)}")
	
	frappe.db.commit()
	print("Purchase Receipt split fields created successfully")


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

