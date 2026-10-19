# Copyright (c) 2026, Construction Management
# License: MIT

"""Option to calculate Sales Invoice retention on amount after additional discount."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Sales Invoice": [
				{
					"fieldname": "custom_retention_after_discount",
					"fieldtype": "Check",
					"label": "Retention After Discount",
					"insert_after": "custom_skip_advance_deduction",
					"description": (
						"When checked, retention % is applied on work amount after "
						"additional discount (not on gross before discount)."
					),
					"allow_on_submit": 0,
					"default": "0",
				},
			],
		},
		update=True,
	)
