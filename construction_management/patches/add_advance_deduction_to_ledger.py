
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
	custom_fields = {
		"BOQ Progress Ledger": [
			{
				"fieldname": "advance_deduction",
				"label": "Advance Deduction",
				"fieldtype": "Currency",
				"read_only": 1,
				"insert_after": "variance_amount"
			}
		]
	}
	
	create_custom_fields(custom_fields, update=True)
