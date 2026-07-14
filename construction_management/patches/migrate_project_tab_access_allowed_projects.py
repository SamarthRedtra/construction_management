# Copyright (c) 2026, Construction Management
# License: MIT

import frappe

from construction_management.construction_management.doctype.project_tab_access.project_tab_access import (
	parse_allowed_projects,
)


def execute():
	if not frappe.db.has_column("Project Tab Access Rule", "allowed_projects"):
		return

	rules = frappe.get_all(
		"Project Tab Access Rule",
		fields=["name", "allowed_projects"],
	)
	for rule in rules:
		if parse_allowed_projects(rule.allowed_projects):
			continue

		projects = frappe.get_all(
			"Project Tab Access Project",
			filters={
				"parent": rule.name,
				"parenttype": "Project Tab Access Rule",
				"parentfield": "projects",
			},
			pluck="project",
		)
		if not projects:
			continue

		frappe.db.set_value(
			"Project Tab Access Rule",
			rule.name,
			"allowed_projects",
			", ".join(projects),
		)

	frappe.db.commit()
