
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
	custom_fields = {
		"BOQ Progress Ledger": [
			{
				"fieldname": "retention_amount",
				"label": "Retention Amount",
				"fieldtype": "Currency",
				"read_only": 1,
				"insert_after": "tax_invoice_amount"
			},
			{
				"fieldname": "variance_amount",
				"label": "Variance Amount", 
				"fieldtype": "Currency",
				"read_only": 1,
				"insert_after": "retention_amount"
			}
		]
	}
	
	create_custom_fields(custom_fields, update=True)
