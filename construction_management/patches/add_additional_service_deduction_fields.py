# Copyright (c) 2026, Construction Management
# License: MIT

"""Fields used to deduct retention/advance from extra services on a Sales Invoice."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Sales Invoice Item": [
				{
					"fieldname": "custom_include_in_deductions",
					"label": "Include in Retention & Advance",
					"fieldtype": "Check",
					"default": "0",
					"insert_after": "boq_item",
					"description": "Use for an additional service that must receive project retention and advance deductions.",
				},
				{
					"fieldname": "custom_service_deduction",
					"label": "Additional Service Deduction",
					"fieldtype": "Check",
					"default": "0",
					"read_only": 1,
					"hidden": 1,
					"insert_after": "custom_include_in_deductions",
				},
			]
		},
		update=True,
	)
