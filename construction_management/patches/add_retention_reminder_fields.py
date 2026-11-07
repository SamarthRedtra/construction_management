# Copyright (c) 2026, Construction Management
# License: MIT

"""Project TOC/DLP dates and the completed-project flag on Raven channels."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Project": [
				{
					"fieldname": "custom_retention_toc_due_date",
					"label": "Retention TOC Due Date",
					"fieldtype": "Date",
					"insert_after": "expected_end_date",
				},
				{
					"fieldname": "custom_retention_dlp_due_date",
					"label": "Retention DLP Due Date",
					"fieldtype": "Date",
					"insert_after": "custom_retention_toc_due_date",
				},
			]
		},
		update=True,
	)
	if frappe.db.exists("DocType", "Raven Channel"):
		create_custom_fields(
			{
				"Raven Channel": [
					{
						"fieldname": "custom_project_completed",
						"label": "Completed Project",
						"fieldtype": "Check",
						"insert_after": "is_archived",
						"read_only": 1,
						"hidden": 1,
					}
				]
			},
			update=True,
		)
	# Single DocTypes report as existing via db.exists even before the settings row is saved.
	has_settings = frappe.db.sql(
		"select 1 from `tabSingles` where doctype=%s limit 1",
		"Retention Reminder Settings",
	)
	if frappe.db.exists("DocType", "Retention Reminder Settings") and not has_settings:
		frappe.get_doc(
			{
				"doctype": "Retention Reminder Settings",
				"enabled": 1,
				"days_before": 7,
				"notify_on_due_date": 1,
			}
		).insert(ignore_permissions=True)
