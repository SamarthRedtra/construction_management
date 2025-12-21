# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _


def after_install():
	"""Setup custom fields and configurations after app installation"""
	create_boq_custom_fields()
	create_stock_entry_custom_fields()
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
