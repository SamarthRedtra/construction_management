# Copyright (c) 2024, Construction Management
# License: MIT

import frappe


def execute():
	"""Add Purchase Order and Project fields to Purchase Receipt and Purchase Receipt Item"""
	
	fields_to_create = [
		# Purchase Receipt - Parent Level
		{
			"dt": "Purchase Receipt",
			"fieldname": "custom_purchase_order",
			"label": "Purchase Order",
			"fieldtype": "Link",
			"options": "Purchase Order",
			"insert_after": "supplier",
			"in_list_view": 1,
			"in_standard_filter": 1,
			"description": "Link to the Purchase Order for this receipt"
		},
		# Purchase Receipt Item - Child Level
		{
			"dt": "Purchase Receipt Item",
			"fieldname": "custom_purchase_order",
			"label": "Purchase Order",
			"fieldtype": "Link",
			"options": "Purchase Order",
			"insert_after": "item_code",
			"read_only": 1,
			"description": "Copied from parent Purchase Receipt"
		},
		{
			"dt": "Purchase Receipt Item",
			"fieldname": "custom_project",
			"label": "Project",
			"fieldtype": "Link",
			"options": "Project",
			"insert_after": "warehouse",
			"in_list_view": 1,
			"description": "Project linked to the warehouse"
		}
	]
	
	for field_def in fields_to_create:
		create_custom_field_if_not_exists(field_def)
	
	frappe.db.commit()
	print("Purchase Receipt PO and Project fields created successfully")


def create_custom_field_if_not_exists(field_def):
	"""Create a custom field if it doesn't exist"""
	dt = field_def.get("dt")
	fieldname = field_def.get("fieldname")
	
	if frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fieldname}):
		print(f"Custom field {dt}-{fieldname} already exists, skipping")
		return
	
	doc = frappe.new_doc("Custom Field")
	doc.update(field_def)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_validate = True
	doc.insert(ignore_permissions=True)
	print(f"Created custom field {dt}-{fieldname}")

