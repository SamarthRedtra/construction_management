# Copyright (c) 2026, Construction Management
# License: MIT

"""Sales Invoice flag to convert leftover customer advance into revenue."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Sales Invoice": [
				{
					"fieldname": "custom_is_advance_release",
					"fieldtype": "Check",
					"label": "Advance Release",
					"insert_after": "custom_is_advanced",
					"description": "Convert leftover non-deductible customer advance to revenue. Net invoice is zero.",
					"allow_on_submit": 0,
					"default": "0",
				},
			],
		},
		update=True,
	)
