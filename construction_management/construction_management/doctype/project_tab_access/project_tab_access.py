# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document


TAB_FIELDNAMES = {
	"Details": "__details",
	"Connections": "connections_tab",
	"Construction": "construction_tab",
	"Approved Materials": "custom_approved_materials_tab",
	"Costing": "costing_tab",
	"Progress": "monitor_progress_tab",
	"Project SOA": "project_soa_tab",
	"Project Commission": "project_commission_tab",
	"Dashboard": "custom_dashboard",
	"More Info": "more_info_tab",
}


class ProjectTabAccess(Document):
	def validate(self):
		for row in self.rules or []:
			if not row.tabs:
				frappe.throw(_("Row {0}: Select at least one tab").format(row.idx))
			if not row.role and not row.user:
				frappe.throw(_("Row {0}: Set either Role or User").format(row.idx))

			for project in parse_allowed_projects(row.allowed_projects):
				if not frappe.db.exists("Project", project):
					frappe.throw(
						_("Row {0}: Project {1} does not exist").format(row.idx, project)
					)


def parse_tabs(tabs_value: str | None) -> list[str]:
	if not tabs_value:
		return []
	return [tab.strip() for tab in tabs_value.split(",") if tab.strip()]


def parse_allowed_projects(projects_value: str | None) -> list[str]:
	if not projects_value:
		return []
	return [project.strip() for project in projects_value.split(",") if project.strip()]


def _user_matches_rule(user: str, roles: set[str], rule) -> bool:
	if rule.user and rule.user == user:
		return True
	if rule.role and rule.role in roles:
		return True
	return False


def _get_rule_projects(rule) -> list[str]:
	projects = parse_allowed_projects(getattr(rule, "allowed_projects", None))
	if projects:
		return projects

	return frappe.get_all(
		"Project Tab Access Project",
		filters={
			"parent": rule.name,
			"parenttype": "Project Tab Access Rule",
			"parentfield": "projects",
		},
		pluck="project",
	)


def get_user_project_scope(user: str | None = None) -> list[str] | None:
	"""Return allowed project names, or None when the user can access all projects."""
	user = user or frappe.session.user
	settings = frappe.get_single("Project Tab Access")

	if not settings.enabled:
		return None

	roles = set(frappe.get_roles(user))
	matching_rules = [
		row for row in settings.rules or [] if _user_matches_rule(user, roles, row)
	]

	if not matching_rules:
		return None

	allowed_projects: set[str] = set()
	for rule in matching_rules:
		projects = _get_rule_projects(rule)
		if not projects:
			return None
		allowed_projects.update(projects)

	return sorted(allowed_projects)


@frappe.whitelist()
def get_project_tab_access_config() -> dict:
	"""Return tab access rules for the Project form."""
	settings = frappe.get_single("Project Tab Access")
	if not settings.enabled:
		return {"enabled": False, "restricted_tabs": {}}

	restricted_tabs: dict[str, list[dict]] = {}
	for row in settings.rules or []:
		for tab_label in parse_tabs(row.tabs):
			fieldname = TAB_FIELDNAMES.get(tab_label)
			if not fieldname:
				continue
			restricted_tabs.setdefault(fieldname, []).append(
				{
					"tab": tab_label,
					"role": row.role or "",
					"user": row.user or "",
				}
			)

	return {
		"enabled": True,
		"restricted_tabs": restricted_tabs,
	}
