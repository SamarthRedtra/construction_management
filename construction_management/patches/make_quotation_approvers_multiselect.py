# Copyright (c) 2026, Construction Management
# License: MIT

"""Add multi-user approvers while retaining old single-user settings as a fallback."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Company": [
				{
					"fieldname": "custom_quotation_sales_managers",
					"fieldtype": "Table MultiSelect",
					"label": "Quotation Sales Managers",
					"options": "Quotation Approval User",
					"insert_after": "custom_quotation_sales_manager",
					"description": "One or more managers receive submitted quotations first and upload the cost sheet.",
				},
				{
					"fieldname": "custom_quotation_directors",
					"fieldtype": "Table MultiSelect",
					"label": "Quotation Directors",
					"options": "Quotation Approval User",
					"insert_after": "custom_quotation_director",
					"description": "Directors receive an alert and can act for a non-responsive Sales Manager.",
				},
			]
		},
		update=True,
	)
	# Keep the original single-user values as a server fallback, but avoid duplicate settings in the form.
	for fieldname in ("custom_quotation_sales_manager", "custom_quotation_director"):
		frappe.db.set_value("Custom Field", {"dt": "Company", "fieldname": fieldname}, "hidden", 1)
