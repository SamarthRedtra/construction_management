# Copyright (c) 2026, Construction Management
# License: MIT

import frappe

no_cache = 1


@frappe.whitelist()
def get_project_raven_channels(company: str | None = None) -> list[dict]:
	"""List Raven Channels linked to Projects (optional company filter)."""
	if "raven" not in frappe.get_installed_apps():
		return []
	if not frappe.has_permission("Raven Channel", "read"):
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)

	conditions = [
		"rc.linked_doctype = 'Project'",
		"IFNULL(rc.linked_document, '') != ''",
	]
	args: dict = {}
	if company:
		conditions.append("p.company = %(company)s")
		args["company"] = company

	return frappe.db.sql(
		f"""
		SELECT
			rc.name AS channel_id,
			rc.channel_name,
			rc.linked_document AS project,
			p.project_name,
			p.company,
			p.custom_project_no
		FROM `tabRaven Channel` rc
		LEFT JOIN `tabProject` p ON p.name = rc.linked_document
		WHERE {' AND '.join(conditions)}
		ORDER BY rc.channel_name ASC
		""",
		args,
		as_dict=True,
	)
