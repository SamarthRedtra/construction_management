# Copyright (c) 2026, Construction Management and contributors

import frappe


def set_project_short_name(doc, method=None):
	if not doc.project:
		doc.custom_project_short_name = None
		return

	short_name = frappe.db.get_value("Project", doc.project, "custom_project_short_name")
	if short_name:
		doc.custom_project_short_name = short_name
