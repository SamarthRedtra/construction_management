
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
	custom_fields = {
		"Sales Invoice": [
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
