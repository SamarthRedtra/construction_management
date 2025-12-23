# Copyright (c) 2024, Construction Management
# License: MIT

"""
Comprehensive patch for Construction Management V2 Enhancements.
Creates all custom fields for:
- DPR quantity summary
- Warehouse project linking
- Payment Certificate workflow
- BOQ task/Gantt fields
"""

import frappe


def execute():
	"""Create all custom fields for V2 enhancements"""
	
	print("Creating V2 Enhancement custom fields...")
	
	# DPR Quantity Fields (Task 3.1)
	dpr_quantity_fields = [
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
	
	# Warehouse Project Field (Task 2.1)
	warehouse_fields = [
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
	
	# Payment Certificate workflow fields (Task 9.6)
	payment_cert_fields = [
		{
			"dt": "Sales Invoice",
			"fieldname": "custom_is_proforma",
			"label": "Is Proforma",
			"fieldtype": "Check",
			"insert_after": "is_return",
			"default": "0",
			"description": "Mark as proforma/draft invoice awaiting customer approval"
		},
		{
			"dt": "Sales Invoice",
			"fieldname": "custom_payment_certificate",
			"label": "Payment Certificate",
			"fieldtype": "Link",
			"options": "Payment Certificate",
			"insert_after": "custom_is_proforma",
			"read_only": 1,
			"description": "Linked Payment Certificate"
		},
		{
			"dt": "Sales Invoice",
			"fieldname": "custom_converted_to_tax_invoice",
			"label": "Converted to Tax Invoice",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"insert_after": "custom_payment_certificate",
			"read_only": 1,
			"description": "Tax invoice created from this proforma",
			"depends_on": "eval:doc.custom_is_proforma"
		}
	]
	
	# BOQ Item task/Gantt fields (Task 7.1)
	boq_item_fields = [
		{
			"dt": "BOQ Item",
			"fieldname": "is_task",
			"label": "Is Task",
			"fieldtype": "Check",
			"insert_after": "linked_task",
			"default": "0",
			"description": "Include this item in Gantt chart as a task"
		},
		{
			"dt": "BOQ Item",
			"fieldname": "start_date",
			"label": "Start Date",
			"fieldtype": "Date",
			"insert_after": "is_task",
			"depends_on": "eval:doc.is_task"
		},
		{
			"dt": "BOQ Item",
			"fieldname": "end_date",
			"label": "End Date",
			"fieldtype": "Date",
			"insert_after": "start_date",
			"depends_on": "eval:doc.is_task"
		},
		{
			"dt": "BOQ Item",
			"fieldname": "completed_qty",
			"label": "Completed Qty",
			"fieldtype": "Float",
			"insert_after": "qty",
			"default": "0",
			"description": "Quantity completed (for progress tracking)"
		}
	]
	
	# Combine all fields
	all_fields = dpr_quantity_fields + warehouse_fields + payment_cert_fields + boq_item_fields
	
	created_count = 0
	for field_def in all_fields:
		try:
			if create_custom_field_if_not_exists(field_def):
				created_count += 1
		except Exception as e:
			frappe.logger().error(f"Error creating custom field {field_def.get('fieldname')}: {str(e)}")
	
	frappe.db.commit()
	print(f"V2 Enhancement custom fields: {created_count} created")


def create_custom_field_if_not_exists(field_def):
	"""Create a custom field if it doesn't already exist"""
	dt = field_def.get("dt")
	fieldname = field_def.get("fieldname")
	
	# Check if field already exists
	if frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fieldname}):
		frappe.logger().info(f"Custom field {dt}-{fieldname} already exists, skipping")
		return False
	
	# Create the custom field
	doc = frappe.new_doc("Custom Field")
	doc.update(field_def)
	doc.flags.ignore_validate = True
	doc.insert(ignore_permissions=True)
	frappe.logger().info(f"Created custom field {dt}-{fieldname}")
	return True

