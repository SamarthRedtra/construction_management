# Copyright (c) 2026, Construction Management
# License: MIT

"""Document-level opt-out for advance recovery on Sales Invoice / Sales Order."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Sales Invoice": [
				{
					"fieldname": "custom_skip_advance_deduction",
					"fieldtype": "Check",
					"label": "Skip Advance Deduction",
					"insert_after": "custom_advanced_percentage",
					"description": "When checked, no ADVANCE-DEDUCTION rows are added even if advance balance exists.",
					"allow_on_submit": 0,
					"default": "0",
				},
			],
			"Sales Order": [
				{
					"fieldname": "custom_skip_advance_deduction",
					"fieldtype": "Check",
					"label": "Skip Advance Deduction",
					"insert_after": "project",
					"description": "When checked, no ADVANCE-DEDUCTION rows are added even if advance balance exists.",
					"allow_on_submit": 0,
					"default": "0",
				},
			],
		},
		update=True,
	)
