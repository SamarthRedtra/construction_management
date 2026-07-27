"""Configure the CEO's ERP landing page after the CEO workspace is installed."""

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	workspace_path = frappe.get_app_path(
		"construction_management", "construction_management", "workspace", "ceo_home", "ceo_home.json"
	)
	import_file_by_path(workspace_path, force=True)
	if frappe.db.exists("Role", "CEO"):
		frappe.db.set_value("Role", "CEO", "home_page", "app/project-process-home", update_modified=False)
	if frappe.db.exists("Report", "CEO Payment Tracker"):
		report = frappe.get_doc("Report", "CEO Payment Tracker")
		if not any(row.role == "CEO" for row in report.roles):
			report.append("roles", {"role": "CEO"})
			report.save(ignore_permissions=True)
	frappe.clear_cache()
