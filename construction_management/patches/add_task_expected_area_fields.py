# Copyright (c) 2026, Construction Management
# License: MIT

import frappe

from construction_management.patches.v2_enhancements import create_custom_field_if_not_exists


def execute():
	task_fields = [
		{
			"dt": "Task",
			"fieldname": "expected_area",
			"label": "Expected Area",
			"fieldtype": "Float",
			"insert_after": "completed_qty",
			"description": "Area expected to be covered by this sub-task",
		},
	]

	log_fields = [
		{
			"dt": "Task Progress Log",
			"fieldname": "expected_area",
			"label": "Expected Area",
			"fieldtype": "Float",
			"insert_after": "qty_updated",
		},
	]

	for field_def in task_fields + log_fields:
		create_custom_field_if_not_exists(field_def)

	frappe.db.commit()
