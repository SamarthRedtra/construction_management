# Copyright (c) 2026, Construction Management
# License: MIT

"""Move Raven channels for already Completed projects into the completed group.

The sidebar reads Raven Channel.custom_project_completed. That flag is written
on Project save. This sets it once for channels that already exist.
"""

import frappe


def execute():
	if "raven" not in frappe.get_installed_apps():
		return
	if not frappe.db.exists("DocType", "Raven Channel"):
		return
	if not frappe.db.has_column("Raven Channel", "custom_project_completed"):
		return

	if frappe.db.has_column("Project", "custom_raven_channel"):
		frappe.db.sql(
			"""
			UPDATE `tabRaven Channel` c
			LEFT JOIN `tabProject` linked
				ON c.linked_doctype = 'Project' AND linked.name = c.linked_document
			LEFT JOIN `tabProject` stored
				ON stored.custom_raven_channel = c.name
			SET c.custom_project_completed = IF(IFNULL(linked.status, stored.status) = 'Completed', 1, 0)
			WHERE IFNULL(c.is_thread, 0) = 0
				AND (linked.name IS NOT NULL OR stored.name IS NOT NULL)
			"""
		)
		return

	frappe.db.sql(
		"""
		UPDATE `tabRaven Channel` c
		INNER JOIN `tabProject` linked
			ON c.linked_doctype = 'Project' AND linked.name = c.linked_document
		SET c.custom_project_completed = IF(linked.status = 'Completed', 1, 0)
		WHERE IFNULL(c.is_thread, 0) = 0
		"""
	)
