# Copyright (c) 2026, Construction Management
# License: MIT

"""Add Project Estimates panel fields on Project form."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Project": [
				{
					"fieldname": "custom_project_estimates_section",
					"fieldtype": "Section Break",
					"label": "Project Estimates",
					"insert_after": "construction_dashboard",
					"collapsible": 0,
				},
				{
					"fieldname": "custom_project_estimates_html",
					"fieldtype": "HTML",
					"label": "Project Estimates",
					"insert_after": "custom_project_estimates_section",
				},
			]
		},
		update=True,
	)
