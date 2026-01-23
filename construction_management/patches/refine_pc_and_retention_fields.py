import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
	custom_fields = {
		"Payment Certificate": [
			{
				"fieldname": "retention_amount",
				"label": "Retention Amount",
				"fieldtype": "Currency",
				"insert_after": "accepted_amount",
				"read_only": 1
			},
			{
				"fieldname": "retention_percentage",
				"label": "Retention %",
				"fieldtype": "Percent",
				"insert_after": "retention_amount"
			}
		],
		"Sales Invoice": [
			{
				"fieldname": "custom_retention_amount",
				"label": "Retention Amount",
				"fieldtype": "Currency",
				"insert_after": "custom_payment_certificate",
				"read_only": 1
			},
			{
				"fieldname": "custom_retention_percentage",
				"label": "Retention %",
				"fieldtype": "Percent",
				"insert_after": "custom_retention_amount",
				"read_only": 1
			},
			{
				"fieldname": "custom_retention_account",
				"label": "Retention Account",
				"fieldtype": "Link",
				"options": "Account",
				"insert_after": "custom_retention_percentage",
				"read_only": 1
			},
			{
				"fieldname": "custom_sales_order",
				"label": "Sales Order",
				"fieldtype": "Link",
				"options": "Sales Order",
				"insert_after": "project",
				"read_only": 1
			}
		]
	}
	create_custom_fields(custom_fields, update=True)
