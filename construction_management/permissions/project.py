# Copyright (c) 2026, Construction Management
# License: MIT

import frappe

from construction_management.construction_management.doctype.project_tab_access.project_tab_access import (
	get_user_project_scope,
)


def get_project_permission_query_conditions(user: str | None = None) -> str | None:
	user = user or frappe.session.user

	if user == "Administrator":
		return None

	scope = get_user_project_scope(user)
	if scope is None:
		return None

	if not scope:
		return "1=0"

	escaped = ", ".join(frappe.db.escape(project) for project in scope)
	return f"`tabProject`.name in ({escaped})"


def has_project_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
	"""Controller hook — can only *deny*; role permissions still gate create/write/read.

	Project Tab Access scopes which existing projects a user may open.
	It must not deny create/write on unsaved new Project docs (they are not in scope yet).
	"""
	user = user or frappe.session.user

	if user == "Administrator":
		return True

	scope = get_user_project_scope(user)
	if scope is None:
		# No PTA document filter — Role Permission Manager still applies
		return True

	# New Project: not yet named / not in allowed list. Do not deny here.
	# Create still requires Projects User / Projects Manager (or equivalent) via roles.
	if _is_unsaved_project(doc):
		return True

	return doc.name in scope


def _is_unsaved_project(doc) -> bool:
	if getattr(doc, "is_new", None) and callable(doc.is_new) and doc.is_new():
		return True
	name = getattr(doc, "name", None)
	if not name:
		return True
	return isinstance(name, str) and name.startswith("new-")
