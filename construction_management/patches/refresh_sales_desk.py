"""Sync the standard Sales Desk workspace layout."""

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	workspace_path = frappe.get_app_path(
		"construction_management", "construction_management", "workspace", "sales_desk", "sales_desk.json"
	)
	import_file_by_path(workspace_path, force=True)
	frappe.clear_cache()
