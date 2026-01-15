
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
	custom_fields = {
		"Sales Invoice": [
			{
				"fieldname": "custom_is_proforma",
				"label": "Is Proforma Invoice",
				"fieldtype": "Check",
				"default": "0",
				"insert_after": "customer_address",
				"description": "Check if this is a proforma invoice for progressive billing"
			},
			{
				"fieldname": "custom_payment_certificate",
				"label": "Payment Certificate",
				"fieldtype": "Link",
				"options": "Payment Certificate",
				"insert_after": "custom_is_proforma",
				"read_only": 1,
				"description": "Linked Payment Certificate"
			},
			{
				"fieldname": "custom_proforma_invoice",
				"label": "Proforma Invoice",
				"fieldtype": "Link",
				"options": "Proforma Invoice",
				"insert_after": "custom_payment_certificate",
				"read_only": 1,
				"description": "Linked Proforma Invoice"
			}
		]
	}
	
	create_custom_fields(custom_fields, update=True)
