# Copyright (c) 2026, Construction Management
# License: MIT

"""Company-level approvers for the Quotation approval sequence."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Company": [
				{
					"fieldname": "custom_quotation_approval_section",
					"fieldtype": "Section Break",
					"label": "Quotation Approval",
					"insert_after": "default_letter_head",
				},
				{
					"fieldname": "custom_quotation_sales_manager",
					"fieldtype": "Link",
					"label": "Quotation Sales Manager",
					"options": "User",
					"insert_after": "custom_quotation_approval_section",
					"description": "Legacy single-user field. Use Quotation Sales Managers instead.",
				},
				{
					"fieldname": "custom_quotation_director",
					"fieldtype": "Link",
					"label": "Quotation Director",
					"options": "User",
					"insert_after": "custom_quotation_sales_manager",
					"description": "Legacy single-user field. Use Quotation Directors instead.",
				},
			]
		},
		update=True,
	)
