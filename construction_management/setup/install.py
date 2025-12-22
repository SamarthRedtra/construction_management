# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _



def before_install():
	""" delete Project Estimation Custom Field In Project if exists"""
	if frappe.db.exists("Custom Field","Project-custom_project_estimation"):
		frappe.db.delete("Custom Field","Project-custom_project_estimation")
		frappe.db.commit()
		print("Project Estimation Custom Field deleted successfully")

	else:
		print("Project Estimation Custom Field does not exist")

def after_install():
	"""Setup custom fields and configurations after app installation"""
	create_boq_custom_fields()
	create_stock_entry_custom_fields()
	create_purchase_receipt_split_fields()
	setup_accounting_dimensions()
	frappe.db.commit()


def setup_accounting_dimensions():
	"""Setup BOQ accounting dimensions"""
	from construction_management.setup.accounting_dimensions import setup_accounting_dimensions as setup_dims
	try:
		setup_dims()
	except Exception as e:
		frappe.logger().error(f"Error setting up accounting dimensions: {str(e)}")


def create_boq_custom_fields():
	"""Create custom fields for BOQ Progressive Billing feature on Project doctype"""
	
	fields_to_create = [
		{
			"dt": "Project",
			"fieldname": "enable_progressive_boq",
			"label": "Enable Progressive BOQ",
			"fieldtype": "Check",
			"insert_after": "status",
			"default": "0",
			"description": "Enable BOQ Progressive Billing features in Construction tab",
			"in_standard_filter": 1
		},
		{
			"dt": "Project",
			"fieldname": "retention_percentage",
			"label": "Retention %",
			"fieldtype": "Percent",
			"insert_after": "enable_progressive_boq",
			"default": "0",
			"description": "Retention percentage to deduct from progressive billing invoices",
			"depends_on": "eval:doc.enable_progressive_boq"
		},
		{
			"dt": "Project",
			"fieldname": "construction_dashboard_section",
			"label": "BOQ Management",
			"fieldtype": "Section Break",
			"insert_after": "notes",
			"collapsible": 0,
			"depends_on": "eval:doc.enable_progressive_boq"
		},
		{
			"dt": "Project",
			"fieldname": "construction_dashboard",
			"label": "BOQ Dashboard",
			"fieldtype": "HTML",
			"insert_after": "construction_dashboard_section",
			"depends_on": "eval:doc.enable_progressive_boq"
		}
	]
	
	for field_def in fields_to_create:
		try:
			create_custom_field_if_not_exists(field_def)
		except Exception as e:
			frappe.logger().error(f"Error creating custom field {field_def.get('fieldname')}: {str(e)}")
	
	frappe.logger().info("BOQ Progressive Billing custom fields created successfully")


def create_stock_entry_custom_fields():
	"""Create custom fields for Stock Entry Item to link BOQ dimensions"""
	
	fields_to_create = [
		{
			"dt": "Stock Entry Detail",
			"fieldname": "boq_item",
			"label": "BOQ Item",
			"fieldtype": "Link",
			"options": "BOQ Item",
			"insert_after": "project"
		},
		{
			"dt": "Stock Entry Detail",
			"fieldname": "bill_no",
			"label": "Bill No",
			"fieldtype": "Link",
			"options": "BOQ Bill",
			"insert_after": "boq_item"
		}
	]
	
	for field_def in fields_to_create:
		try:
			create_custom_field_if_not_exists(field_def)
		except Exception as e:
			frappe.logger().error(f"Error creating custom field {field_def.get('fieldname')}: {str(e)}")
	
	frappe.logger().info("Stock Entry custom fields created successfully")


def create_purchase_receipt_split_fields():
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
	
	frappe.logger().info("Purchase Receipt split fields created successfully")


def create_custom_field_if_not_exists(field_def):
	"""Create a custom field if it doesn't already exist"""
	dt = field_def.get("dt")
	fieldname = field_def.get("fieldname")
	
	# Check if field already exists
	if frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fieldname}):
		frappe.logger().info(f"Custom field {dt}-{fieldname} already exists")
		return
	
	# Create the custom field
	doc = frappe.new_doc("Custom Field")
	doc.update(field_def)
	doc.flags.ignore_validate = True
	doc.insert(ignore_permissions=True)
	frappe.logger().info(f"Created custom field {dt}-{fieldname}")
