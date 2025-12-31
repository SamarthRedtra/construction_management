# Copyright (c) 2024, Construction Management
# License: MIT

"""
Patch to create Warehouse as an Inventory Dimension for site-level stock tracking.
This enables mandatory warehouse selection in DPR and other stock transactions.
Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
"""

import frappe
from frappe import _


def execute():
	"""
	Create Warehouse as an Inventory Dimension to enable site-level stock tracking.
	This patch ensures that all stock movements can be tracked by warehouse/site location.
	"""
	try:
		# Check if Warehouse dimension already exists
		if frappe.db.exists("Inventory Dimension", {"reference_document": "Warehouse"}):
			frappe.logger().info("Warehouse Inventory Dimension already exists")
			return
		
		# Create Warehouse as Inventory Dimension
		create_warehouse_inventory_dimension()
		
		# Update existing stock transactions if needed
		update_existing_stock_transactions()
		
		frappe.db.commit()
		frappe.logger().info("Warehouse Inventory Dimension created successfully")
		
	except Exception as e:
		frappe.logger().error(f"Error creating Warehouse Inventory Dimension: {str(e)}")
		frappe.db.rollback()
		raise


def create_warehouse_inventory_dimension():
	"""Create Warehouse as an Inventory Dimension"""
	
	# Create the Inventory Dimension document
	dimension_doc = frappe.new_doc("Inventory Dimension")
	dimension_doc.update({
		"reference_document": "Warehouse",
		"apply_to_all_doctypes": 1,
		"istable": 0,
		"condition": "",
		"mandatory_depends_on": "",
		"type_of_transaction": "Both",
		"dimension_name": "Warehouse",
		"fetch_from_parent": "",
		"source_fieldname": "warehouse",
		"target_fieldname": "warehouse",
		"disabled": 0
	})
	
	# Add document types where this dimension should apply
	document_types = [
		"Stock Entry",
		"Stock Reconciliation", 
		"Purchase Receipt",
		"Purchase Invoice",
		"Sales Invoice",
		"Delivery Note",
		"Material Request",
		"Stock Ledger Entry",
		"Daily Progress Record"
	]
	
	for doctype in document_types:
		if frappe.db.exists("DocType", doctype):
			dimension_doc.append("applicable_on_document_type", {
				"document_type": doctype,
				"condition": ""
			})
	
	# Insert the dimension
	dimension_doc.flags.ignore_permissions = True
	dimension_doc.flags.ignore_validate = True
	dimension_doc.insert()
	
	frappe.logger().info("Warehouse Inventory Dimension document created")


def update_existing_stock_transactions():
	"""
	Update existing stock transactions to ensure warehouse dimension compliance.
	This is important for data consistency after enabling the dimension.
	"""
	
	# Update Stock Ledger Entries without proper warehouse dimension
	frappe.db.sql("""
		UPDATE `tabStock Ledger Entry` 
		SET warehouse = COALESCE(warehouse, 'Stores - SKADA')
		WHERE warehouse IS NULL OR warehouse = ''
	""")
	
	# Update Daily Progress Records to have default warehouse if project has site_location
	frappe.db.sql("""
		UPDATE `tabDaily Progress Record` dpr
		JOIN `tabProject` p ON dpr.project = p.name
		SET dpr.warehouse = p.site_location
		WHERE p.site_location IS NOT NULL 
		AND p.site_location != ''
		AND (dpr.warehouse IS NULL OR dpr.warehouse = '')
	""")
	
	frappe.logger().info("Updated existing stock transactions for warehouse dimension compliance")


def validate_warehouse_dimension_setup():
	"""
	Validate that the warehouse dimension is properly set up and working.
	This function can be called to verify the patch was successful.
	"""
	
	# Check if dimension exists
	if not frappe.db.exists("Inventory Dimension", {"reference_document": "Warehouse"}):
		return False, "Warehouse Inventory Dimension not found"
	
	# Check if dimension is enabled
	dimension = frappe.get_doc("Inventory Dimension", {"reference_document": "Warehouse"})
	if dimension.disabled:
		return False, "Warehouse Inventory Dimension is disabled"
	
	# Check if applicable document types are configured
	applicable_docs = [d.document_type for d in dimension.applicable_on_document_type]
	required_docs = ["Stock Entry", "Purchase Receipt", "Daily Progress Record"]
	
	for doc in required_docs:
		if doc not in applicable_docs:
			return False, f"Warehouse dimension not configured for {doc}"
	
	return True, "Warehouse Inventory Dimension is properly configured"


# Utility function for BOQ Settings integration
def get_mandatory_warehouse_for_company(company):
	"""
	Get the mandatory warehouse setting for a company.
	This will be used by BOQ Settings to enforce warehouse selection.
	"""
	
	# Check if company has BOQ Settings configured
	boq_settings = frappe.db.get_value("BOQ Settings", {"company": company}, 
									   ["mandatory_site_location", "default_warehouse"], as_dict=True)
	
	if boq_settings and boq_settings.mandatory_site_location:
		return boq_settings.default_warehouse
	
	return None


def enforce_warehouse_in_dpr(doc, method=None):
	"""
	Hook function to enforce warehouse selection in Daily Progress Record.
	This should be called from hooks.py as a validation hook.
	"""
	
	if not doc.warehouse and doc.project:
		# Get project's site location
		project_warehouse = frappe.db.get_value("Project", doc.project, "site_location")
		
		if project_warehouse:
			doc.warehouse = project_warehouse
		else:
			# Check if company requires mandatory warehouse
			company = frappe.db.get_value("Project", doc.project, "company")
			mandatory_warehouse = get_mandatory_warehouse_for_company(company)
			
			if mandatory_warehouse:
				frappe.throw(_("Warehouse/Site Location is mandatory for DPR entries. Please set site location in Project or configure BOQ Settings."))


def setup_warehouse_dimension_hooks():
	"""
	Setup hooks for warehouse dimension enforcement.
	This should be called from hooks.py to register validation hooks.
	"""
	
	# Register DPR validation hook
	frappe.flags.warehouse_dimension_hooks_setup = True
	
	return {
		"Daily Progress Record": {
			"validate": "construction_management.patches.v1_0.create_warehouse_inventory_dimension.enforce_warehouse_in_dpr"
		}
	}