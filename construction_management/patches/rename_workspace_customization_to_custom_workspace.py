# Copyright (c) 2026, Construction Management
# License: MIT

"""Preserve workspace customizations across the Frappe DocType rename."""

from __future__ import annotations

import frappe
from frappe.model.rename_doc import rename_doc

OLD_DOCTYPE = "Workspace Customization"
NEW_DOCTYPE = "Custom Workspace"

LOGGER = frappe.logger("construction_management")


def execute():
	old_doctype_exists = bool(frappe.db.exists("DocType", OLD_DOCTYPE))
	new_doctype_exists = bool(frappe.db.exists("DocType", NEW_DOCTYPE))
	old_table_exists = frappe.db.table_exists(OLD_DOCTYPE)
	new_table_exists = frappe.db.table_exists(NEW_DOCTYPE)

	if new_doctype_exists or new_table_exists:
		if old_doctype_exists or old_table_exists:
			frappe.throw(
				f"Cannot migrate {OLD_DOCTYPE}: both the old and new Custom Workspace schemas exist."
			)
		_reload_custom_workspace()
		LOGGER.info(f"Skip workspace rename: {NEW_DOCTYPE} already exists")
		return

	if old_doctype_exists != old_table_exists:
		frappe.throw(
			f"Cannot migrate {OLD_DOCTYPE}: its DocType record and database table are inconsistent."
		)

	if not old_doctype_exists:
		_reload_custom_workspace()
		LOGGER.info(f"Created missing {NEW_DOCTYPE} schema")
		return

	row_count = frappe.db.count(OLD_DOCTYPE)
	rename_doc("DocType", OLD_DOCTYPE, NEW_DOCTYPE, force=True)
	_reload_custom_workspace()

	if frappe.db.count(NEW_DOCTYPE) != row_count:
		frappe.throw(f"{NEW_DOCTYPE} row count changed during migration")

	LOGGER.info(f"Renamed {OLD_DOCTYPE} to {NEW_DOCTYPE}; preserved {row_count} row(s)")


def _reload_custom_workspace() -> None:
	frappe.reload_doc("desk", "doctype", "custom_workspace")
