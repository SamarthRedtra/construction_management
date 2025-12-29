# Copyright (c) 2024, Construction Management
# License: MIT

"""
Patch to sync Sales Invoice schema with doctype definition.

This patch ensures the exempt_from_sales_tax column exists in the Sales Invoice table.
This field was added to ERPNext but may not have been synced to the database.
"""

import frappe


def execute():
	"""Add missing columns to Sales Invoice table if they don't exist."""
	
	# Check if column exists
	columns = frappe.db.sql("""
		SELECT COLUMN_NAME 
		FROM INFORMATION_SCHEMA.COLUMNS 
		WHERE TABLE_NAME = 'tabSales Invoice' 
		AND COLUMN_NAME = 'exempt_from_sales_tax'
	""", as_dict=True)
	
	if not columns:
		# Add the missing column
		frappe.db.sql("""
			ALTER TABLE `tabSales Invoice` 
			ADD COLUMN `exempt_from_sales_tax` INT(1) DEFAULT 0
		""")
		frappe.db.commit()
		print("Added exempt_from_sales_tax column to Sales Invoice table")
	
	# Reload the doctype to ensure schema is in sync
	frappe.reload_doctype("Sales Invoice")
