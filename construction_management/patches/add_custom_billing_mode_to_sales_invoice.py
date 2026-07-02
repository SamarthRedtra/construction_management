import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Sales Invoice": [
				{
					"fieldname": "custom_billing_mode",
					"label": "Billing Mode",
					"fieldtype": "Select",
					"options": "Direct BOQ\nSales Order\nPayment Certificate",
					"insert_after": "custom_sales_order",
					"read_only": 1,
					"allow_on_submit": 1,
					"description": "How this invoice was created from construction billing",
				}
			]
		},
		ignore_validate=True,
	)
