# Copyright (c) 2026, Construction Management
# License: MIT

"""Document-level opt-out for retention on Sales Order."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Sales Order": [
				{
					"fieldname": "custom_skip_retention_deduction",
					"fieldtype": "Check",
					"label": "Skip Retention Deduction",
					"insert_after": "custom_skip_advance_deduction",
					"description": (
						"When checked, no RETENTION-DEDUCTION rows are added even if "
						"the project has a retention %."
					),
					"allow_on_submit": 0,
					"default": "0",
				},
			],
		},
		update=True,
	)