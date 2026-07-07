import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Sales Invoice": [
				{
					"fieldname": "custom_source_sales_orders",
					"label": "Source Sales Orders",
					"fieldtype": "Small Text",
					"insert_after": "custom_sales_order",
					"read_only": 1,
					"print_hide": 1,
					"description": "Comma-separated Sales Orders combined into this invoice",
				}
			]
		},
		ignore_validate=True,
	)
