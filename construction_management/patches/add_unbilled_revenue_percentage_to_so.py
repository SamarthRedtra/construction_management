import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
	custom_fields = {
		"Sales Order": [
			{
				"fieldname": "custom_unbilled_revenue_percentage",
				"label": "Unbilled Revenue Percentage",
				"fieldtype": "Percent",
				"insert_after": "custom_net_amount",
				"description": "Percentage of net total to be recognized as unbilled revenue upon order submission",
				"default": 100
			}
		],
		"BOQ Settings": [
			{
				"fieldname": "enable_so_unearned_revenue_jv",
				"label": "Enable SO Unearned Revenue JV",
				"fieldtype": "Check",
				"description": "Post unearned revenue JV on Sales Order submit and handle accounting within Sales Invoice",
				"insert_after": "section_break_so_unearned"
			}
		]
	}
	# BOQ Settings already has this field, but I'll include it in the logic 
	# Actually, I checked BOQ Settings and it's already there in the JSON.
	# I will only add to Sales Order.

	create_custom_fields({
		"Sales Order": [
			{
				"fieldname": "custom_unbilled_revenue_percentage",
				"label": "Unbilled Revenue Percentage",
				"fieldtype": "Percent",
				"insert_after": "order_type",
				"description": "Percentage of net total to be recognized as unbilled revenue upon order submission",
				"default": 100
			}
		]
	}, ignore_validate=True)
