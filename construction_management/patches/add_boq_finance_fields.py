
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
	custom_fields = {
		"BOQ Item": [
			{
				"fieldname": "total_retention_amount",
				"label": "Total Retention Deducted",
				"fieldtype": "Currency",
				"read_only": 1,
				"insert_after": "balance_amount"
			},
			{
				"fieldname": "total_advance_deducted",
				"label": "Total Advance Utilized",
				"fieldtype": "Currency",
				"read_only": 1,
				"insert_after": "total_retention_amount"
			}
		],
		"BOQ Bill": [
			{
				"fieldname": "total_retention_amount",
				"label": "Total Retention",
				"fieldtype": "Currency",
				"read_only": 1,
				"insert_after": "total_amount" 
			},
			{
				"fieldname": "total_advance_deducted",
				"label": "Total Advance Utilized",
				"fieldtype": "Currency",
				"read_only": 1,
				"insert_after": "total_retention_amount"
			}
		]
	}
	
	create_custom_fields(custom_fields, update=True)
