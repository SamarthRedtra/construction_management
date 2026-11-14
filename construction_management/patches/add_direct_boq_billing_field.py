# Copyright (c) 2026, Construction Management
# License: MIT

"""Flag Sales Invoice Item rows added via Direct BOQ mode on the Add BOQ Service dialog."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Sales Invoice Item": [
				{
					"fieldname": "custom_direct_boq_billing",
					"label": "Direct BOQ Billing",
					"fieldtype": "Check",
					"default": "0",
					"read_only": 1,
					"hidden": 1,
					"print_hide": 1,
					"insert_after": "custom_service_deduction",
					"description": "Set when the line was added without a Sales Order link.",
				},
			]
		},
		update=True,
	)