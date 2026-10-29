# Copyright (c) 2026, Construction Management
# License: MIT

"""Option to calculate Sales Invoice advance deduction on amount after additional discount."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Sales Invoice": [
				{
					"fieldname": "custom_advance_after_discount",
					"fieldtype": "Check",
					"label": "Advance After Discount",
					"insert_after": "custom_retention_after_discount",
					"description": (
						"When checked, advance % is applied on work amount after "
						"additional discount (not before discount). Still capped by "
						"available advance."
					),
					"allow_on_submit": 0,
					"default": "0",
				},
			],
		},
		update=True,
	)
