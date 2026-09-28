"""Rename project Raven channels to "<Project ID>-<Project Short Name>".

Only the display name (channel_name) changes; channel IDs, members and messages are untouched.
"""

import frappe

from construction_management.raven_integrations.project_channel import get_channel_name_for_project


def execute():
	if not frappe.db.exists("DocType", "Raven Channel") or not frappe.db.has_column("Project", "custom_project_short_name"):
		return

	channels = frappe.get_all(
		"Raven Channel",
		filters={"linked_doctype": "Project", "linked_document": ["is", "set"]},
		fields=["name", "channel_name", "linked_document"],
	)
	for channel in channels:
		project = frappe.db.get_value(
			"Project", channel.linked_document, ["name", "project_name", "custom_project_short_name"], as_dict=True
		)
		if not project:
			continue
		new_name = get_channel_name_for_project(project)
		if new_name and new_name != channel.channel_name:
			frappe.db.set_value("Raven Channel", channel.name, "channel_name", new_name, update_modified=False)
