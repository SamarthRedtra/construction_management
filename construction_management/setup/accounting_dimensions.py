# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _


def setup_accounting_dimensions():
	"""
	Create Bill No and BOQ Item as accounting dimensions in ERPNext.
	
	This allows tracking revenue and expenses at the BOQ Bill and BOQ Item level
	in Sales Invoices, Purchase Invoices, and Journal Entries.
	"""
	dimensions = [
		{
			"document_type": "BOQ Bill",
			"label": "Bill No",
			"fieldname": "bill_no",
			"mandatory_for_bs": 0,
			"mandatory_for_pl": 0,
			"disabled": 0
		},
		{
			"document_type": "BOQ Item",
			"label": "BOQ Item",
			"fieldname": "boq_item",
			"mandatory_for_bs": 0,
			"mandatory_for_pl": 0,
			"disabled": 0
		}
	]
	
	for dim in dimensions:
		create_accounting_dimension(dim)
	
	frappe.logger().info("BOQ Accounting dimensions created successfully")


def create_accounting_dimension(dim_config: dict):
	"""
	Create a single accounting dimension if it doesn't exist.
	
	Args:
		dim_config: Dictionary with dimension configuration
	"""
	# Check if dimension already exists
	if frappe.db.exists("Accounting Dimension", {"document_type": dim_config["document_type"]}):
		frappe.logger().info(f"Accounting dimension for {dim_config['document_type']} already exists")
		return
	
	try:
		doc = frappe.new_doc("Accounting Dimension")
		doc.document_type = dim_config["document_type"]
		doc.label = dim_config.get("label", dim_config["document_type"])
		doc.fieldname = dim_config.get("fieldname")
		doc.mandatory_for_bs = dim_config.get("mandatory_for_bs", 0)
		doc.mandatory_for_pl = dim_config.get("mandatory_for_pl", 0)
		doc.disabled = dim_config.get("disabled", 0)
		doc.insert(ignore_permissions=True)
		
		frappe.logger().info(f"Created accounting dimension: {dim_config['document_type']}")
	except Exception as e:
		frappe.logger().error(f"Error creating accounting dimension {dim_config['document_type']}: {str(e)}")


def remove_accounting_dimensions():
	"""Remove BOQ accounting dimensions (for uninstall)"""
	for doc_type in ["BOQ Bill", "BOQ Item"]:
		if frappe.db.exists("Accounting Dimension", {"document_type": doc_type}):
			frappe.delete_doc("Accounting Dimension", {"document_type": doc_type}, force=True)
			frappe.logger().info(f"Removed accounting dimension: {doc_type}")
