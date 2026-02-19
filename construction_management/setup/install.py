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
	create_purchase_receipt_po_project_fields()
	create_warehouse_custom_fields()
	create_dpr_quantity_fields()
	create_payment_certificate_fields()
	create_purchase_order_deduction_fields()
	setup_accounting_dimensions()
	setup_advanced_general_ledger()
	frappe.db.commit()


def after_migrate():
	"""Run after bench migrate to ensure property setters are in place"""
	setup_advanced_general_ledger()
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
			"fieldname": "site_location",
			"label": "Site Location",
			"fieldtype": "Link",
			"options": "Warehouse",
			"insert_after": "retention_percentage",
			"description": "Site warehouse for material tracking. Required when Progressive BOQ is enabled.",
			"depends_on": "eval:doc.enable_progressive_boq",
			"mandatory_depends_on": "eval:doc.enable_progressive_boq && doc.!doc.__islocal"
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


def create_purchase_receipt_po_project_fields():
	"""Create custom fields for Purchase Order mapping and Project-Warehouse linking on Purchase Receipt"""
	
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
			"fetch_from": "",
			"description": "Copied from parent Purchase Receipt"
		},
	]
	
	for field_def in fields_to_create:
		try:
			create_custom_field_if_not_exists(field_def)
		except Exception as e:
			frappe.logger().error(f"Error creating custom field {field_def.get('fieldname')}: {str(e)}")
	
	frappe.logger().info("Purchase Receipt PO and Project fields created successfully")


def create_warehouse_custom_fields():
	"""Create custom fields for Warehouse to link to Project (site-level tracking)"""
	
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
	
	frappe.logger().info("Warehouse custom fields created successfully")


def create_dpr_quantity_fields():
	"""
	Create quantity summary fields on Daily Progress Record.
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
	
	frappe.logger().info("DPR quantity summary fields created successfully")


def create_payment_certificate_fields():
	"""
	Create custom fields for Payment Certificate workflow.
	(Tasks 9.6-9.10: Proforma invoice and Payment Certificate integration)
	"""
	
	fields_to_create = [
		# Sales Invoice fields for proforma workflow
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
		},
		# BOQ Item fields for task/gantt
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
		},
		# Purchase Receipt BOQ dimension fields (Requirements 6.5)
		{
			"dt": "Purchase Receipt",
			"fieldname": "custom_bill_no",
			"label": "Bill No",
			"fieldtype": "Link",
			"options": "BOQ Bill",
			"insert_after": "project",
			"description": "BOQ Bill for this Purchase Receipt",
			"depends_on": "eval:doc.project"
		},
		{
			"dt": "Purchase Receipt",
			"fieldname": "custom_boq_item",
			"label": "BOQ Item",
			"fieldtype": "Link",
			"options": "BOQ Item",
			"insert_after": "custom_bill_no",
			"description": "BOQ Item for this Purchase Receipt",
			"depends_on": "eval:doc.custom_bill_no"
		}
	]
	
	for field_def in fields_to_create:
		try:
			create_custom_field_if_not_exists(field_def)
		except Exception as e:
			frappe.logger().error(f"Error creating custom field {field_def.get('fieldname')}: {str(e)}")
	
	frappe.logger().info("Payment Certificate workflow fields created successfully")


def setup_advanced_general_ledger():
	try:
		doctype = "Process Statement Of Accounts"

		# Check if doctype exists (erpnext must be installed)
		if not frappe.db.exists("DocType", doctype):
			print("doctype not found", doctype)
			frappe.logger().info(
				f"Skipping Advanced General Ledger setup: {doctype} not found"
			)
			return
		# ── 1. Add 'Advanced General Ledger' to the report Select options ──
		_ensure_report_option(doctype)

		# ── 2. Update depends_on / mandatory_depends_on for GL-specific fields ──
		# These fields check doc.report == 'General Ledger' and must also accept
		# 'Advanced General Ledger' so they remain visible on the form.
		gl_includes = "['General Ledger','Advanced General Ledger'].includes(doc.report)"

		field_property_map = [
			# from_date
			{
				"fieldname": "from_date",
				"property": "depends_on",
				"value": f"eval:(!doc.enable_auto_email && {gl_includes})",
			},
			{
				"fieldname": "from_date",
				"property": "mandatory_depends_on",
				"value": f"eval:(!doc.enable_auto_email && {gl_includes})",
			},
			# to_date
			{
				"fieldname": "to_date",
				"property": "depends_on",
				"value": f"eval:(!doc.enable_auto_email && {gl_includes})",
			},
			{
				"fieldname": "to_date",
				"property": "mandatory_depends_on",
				"value": f"eval:(!doc.enable_auto_email && {gl_includes})",
			},
			# project
			{
				"fieldname": "project",
				"property": "depends_on",
				"value": f"eval: {gl_includes}",
			},
			# currency
			{
				"fieldname": "currency",
				"property": "depends_on",
				"value": f"eval: {gl_includes}",
			},
			# categorize_by
			{
				"fieldname": "categorize_by",
				"property": "depends_on",
				"value": f"eval:{gl_includes}",
			},
			# show_net_values_in_party_account
			{
				"fieldname": "show_net_values_in_party_account",
				"property": "depends_on",
				"value": f"eval: {gl_includes}",
			},
		]

		for entry in field_property_map:
			_upsert_property_setter(
				doctype,
				entry["fieldname"],
				entry["property"],
				entry["value"],
			)

		frappe.logger().info(
			"Advanced General Ledger: PSOA property setters configured successfully"
		)

	except Exception as e:
		frappe.logger().error(f"Error setting up Advanced General Ledger: {str(e)}")


def _ensure_report_option(doctype):
	"""Ensure 'Advanced General Ledger' exists in the report Select field options."""
	fieldname = "report"

	# Use frappe.get_meta to read field options (DocType Field is not directly queryable)
	meta = frappe.get_meta(doctype)
	report_field = meta.get_field(fieldname)
	current_options = report_field.options if report_field else ""

	if not current_options:
		current_options = "General Ledger\nAccounts Receivable"

	# Check existing property setter for options
	existing_ps = frappe.db.exists(
		"Property Setter",
		{"doc_type": doctype, "field_name": fieldname, "property": "options"},
	)
	print("existing_ps", existing_ps)

	if existing_ps:
		ps = frappe.get_doc("Property Setter", existing_ps)
		if "Advanced General Ledger" not in (ps.value or ""):
			ps.value = (ps.value or current_options) + "\nAdvanced General Ledger"
			ps.save(ignore_permissions=True)
	else:
		print("current_options", current_options)
		if "Advanced General Ledger" not in current_options:
			frappe.make_property_setter(
				{
					"doctype": doctype,
					"fieldname": fieldname,
					"property": "options",
					"value": current_options + "\nAdvanced General Ledger",
				},
				validate_fields_for_doctype=False,
			)


def _upsert_property_setter(doctype, fieldname, prop, value):
	"""Create or update a single Property Setter."""
	existing = frappe.db.exists(
		"Property Setter",
		{"doc_type": doctype, "field_name": fieldname, "property": prop},
	)

	if existing:
		ps = frappe.get_doc("Property Setter", existing)
		if ps.value != value:
			ps.value = value
			ps.save(ignore_permissions=True)
	else:
		frappe.make_property_setter(
			{
				"doctype": doctype,
				"fieldname": fieldname,
				"property": prop,
				"value": value,
			},
			validate_fields_for_doctype=False,
		)


def create_purchase_order_deduction_fields():
	"""Create custom fields for retention and advance percentage on Purchase Order"""

	fields_to_create = [
		{
			"dt": "Purchase Order",
			"fieldname": "custom_retention_",
			"label": "Retention %",
			"fieldtype": "Percent",
			"insert_after": "grand_total",
			"default": "0",
			"description": "Retention percentage to deduct from Purchase Invoices and Receipts"
		},
		{
			"dt": "Purchase Order",
			"fieldname": "custom_advance_",
			"label": "Advance %",
			"fieldtype": "Percent",
			"insert_after": "custom_retention_",
			"default": "0",
			"description": "Advance percentage to deduct from Purchase Invoices and Receipts"
		}
	]

	for field_def in fields_to_create:
		try:
			create_custom_field_if_not_exists(field_def)
		except Exception as e:
			frappe.logger().error(f"Error creating custom field {field_def.get('fieldname')}: {str(e)}")

	frappe.logger().info("Purchase Order deduction fields created successfully")

