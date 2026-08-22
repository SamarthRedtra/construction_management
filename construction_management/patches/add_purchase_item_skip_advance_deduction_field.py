# Copyright (c) 2026, Construction Management
# License: MIT

"""Line-level opt-out for advance recovery on Purchase Invoice / Purchase Receipt items."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Purchase Invoice Item": [
				{
					"fieldname": "custom_skip_advance_deduction",
					"fieldtype": "Check",
					"label": "Skip Advance Deduction",
					"insert_after": "boq_item",
					"description": "When checked, this line is excluded from ADVANCE-DEDUCTION calculation.",
					"allow_on_submit": 0,
					"default": "0",
					"in_list_view": 1,
					"columns": 1,
				},
			],
			"Purchase Receipt Item": [
				{
					"fieldname": "custom_skip_advance_deduction",
					"fieldtype": "Check",
					"label": "Skip Advance Deduction",
					"insert_after": "boq_item",
					"description": "When checked, this line is excluded from ADVANCE-DEDUCTION calculation.",
					"allow_on_submit": 0,
					"default": "0",
					"in_list_view": 1,
					"columns": 1,
				},
			],
			"Purchase Order Item": [
				{
					"fieldname": "custom_skip_advance_deduction",
					"fieldtype": "Check",
					"label": "Skip Advance Deduction",
					"insert_after": "boq_item",
					"description": "When checked, this PO line is excluded from advance recovery on PR/PI.",
					"allow_on_submit": 0,
					"default": "0",
					"in_list_view": 1,
					"columns": 1,
				},
			],
		},
		update=True,
	)
