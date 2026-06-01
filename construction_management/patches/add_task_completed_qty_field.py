# Copyright (c) 2026, Construction Management
# License: MIT

import frappe

from construction_management.patches.v2_enhancements import create_custom_field_if_not_exists


def execute():
	"""Ensure Task.completed_qty exists for BOQ sub-task progress tracking."""
	task_fields = [
		{
			"dt": "Task",
			"fieldname": "completed_qty",
			"label": "Completed Qty",
			"fieldtype": "Float",
			"insert_after": "progress",
			"default": "0",
			"description": "Cumulative area/quantity completed (sum of daily progress logs)",
		},
	]

	for field_def in task_fields:
		create_custom_field_if_not_exists(field_def)

	frappe.db.commit()
