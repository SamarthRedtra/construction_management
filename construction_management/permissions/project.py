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
	user = user or frappe.session.user

	if user == "Administrator":
		return True

	scope = get_user_project_scope(user)
	if scope is None:
		return True

	# Project Tab Access only restricts which *existing* projects are visible.
	# New Project docs use temporary names (new-project-...) that are never in
	# scope — returning False here incorrectly blocks Save with
	# "You need the 'create' permission on Project".
	if ptype == "create":
		return True

	docname = getattr(doc, "name", None)
	if not docname:
		return True
	if isinstance(docname, str) and docname.startswith("new-"):
		return True
	if getattr(doc, "is_new", None) and callable(doc.is_new) and doc.is_new():
		return True

	return docname in scope
