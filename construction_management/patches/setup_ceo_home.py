"""Configure the CEO's ERP landing page after the CEO workspace is installed."""

import frappe


def execute():
	if frappe.db.exists("Role", "CEO"):
		frappe.db.set_value("Role", "CEO", "home_page", "app/project-process-home", update_modified=False)
	if frappe.db.exists("Report", "CEO Payment Tracker"):
		role_filter = {
			"parent": "CEO Payment Tracker",
			"parenttype": "Report",
			"parentfield": "roles",
			"role": "CEO",
		}
		if not frappe.db.exists("Has Role", role_filter):
			frappe.get_doc({"doctype": "Has Role", **role_filter}).insert(ignore_permissions=True)
	frappe.clear_cache()
