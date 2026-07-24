# Copyright (c) 2026, Construction Management
# License: MIT

"""Backfill Raven channels for existing Projects."""

import frappe


def execute():
	if "raven" not in frappe.get_installed_apps():
		return
	if not frappe.db.exists("DocType", "Raven Channel"):
		return

	from construction_management.raven_integrations.project_channel import ensure_project_channel

	projects = frappe.get_all("Project", pluck="name")
	for name in projects:
		try:
			doc = frappe.get_doc("Project", name)
			ensure_project_channel(doc)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"Raven project channel backfill: {name}")
