# Copyright (c) 2026, Construction Management
# License: MIT

"""Resync Raven channel members from Project Team assignments for all projects."""

import frappe


def execute():
	if "raven" not in frappe.get_installed_apps():
		return
	if not frappe.db.exists("DocType", "Raven Channel"):
		return

	from construction_management.raven_integrations.project_channel import (
		ensure_project_channel,
		sync_project_channel_members,
	)

	created = 0
	synced = 0
	errors = 0

	projects = frappe.get_all("Project", pluck="name")
	for name in projects:
		try:
			doc = frappe.get_doc("Project", name)
			had_channel = bool(
				frappe.db.exists(
					"Raven Channel",
					{"linked_doctype": "Project", "linked_document": name},
				)
			)
			channel_id = ensure_project_channel(doc)
			if channel_id:
				sync_project_channel_members(doc, channel_id)
				synced += 1
				if not had_channel:
					created += 1
			frappe.db.commit()
		except Exception:
			errors += 1
			frappe.db.rollback()
			frappe.log_error(
				frappe.get_traceback(),
				f"Raven project channel member backfill: {name}",
			)

	msg = (
		f"Raven channel member backfill: projects={len(projects)}, "
		f"synced={synced}, channels_created={created}, errors={errors}"
	)
	print(msg)
	frappe.logger("project_channel").info(msg)
