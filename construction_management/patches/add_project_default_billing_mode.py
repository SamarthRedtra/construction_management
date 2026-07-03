import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Project": [
				{
					"fieldname": "custom_default_billing_mode",
					"label": "Default Billing Mode",
					"fieldtype": "Select",
					"options": "Direct BOQ\nSales Order + PC",
					"default": "Direct BOQ",
					"insert_after": "enable_progressive_boq",
					"depends_on": "eval:doc.enable_progressive_boq",
					"description": "Default billing path pre-selected in dialogs. Both Direct Tax Invoice and Sales Order remain available.",
				}
			]
		},
		ignore_validate=True,
	)
