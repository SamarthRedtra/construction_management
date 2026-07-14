# Copyright (c) 2026, Construction Management
# License: MIT

import frappe


def execute():
	if not frappe.db.has_column("Project Tab Access Rule", "tab"):
		return

	if not frappe.db.has_column("Project Tab Access Rule", "tabs"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabProject Tab Access Rule`
		SET tabs = tab
		WHERE IFNULL(tabs, '') = '' AND IFNULL(tab, '') != ''
		"""
	)
	frappe.db.commit()
