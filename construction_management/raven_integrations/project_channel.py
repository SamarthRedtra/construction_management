# Copyright (c) 2026, Construction Management
# License: MIT

"""Auto-create and sync Raven channels linked to Project documents."""

from __future__ import annotations

import frappe
from frappe import _


def after_insert(doc, method=None):
	if not _raven_installed():
		return
	ensure_project_channel(doc)


def on_update(doc, method=None):
	if not _raven_installed():
		return
	channel_id = ensure_project_channel(doc)
	if channel_id:
		sync_project_channel_members(doc, channel_id)


def on_trash(doc, method=None):
	if not _raven_installed():
		return
	frappe.db.delete("Raven Channel", {"linked_doctype": "Project", "linked_document": doc.name})


def ensure_project_channel(doc) -> str | None:
	"""Create or return the Raven Channel linked to this Project."""
	existing = get_channel_for_project(doc.name)
	if existing:
		_store_channel_on_project(doc.name, existing)
		_sync_channel_meta(doc, existing)
		return existing

	channel = frappe.new_doc("Raven Channel")
	channel.channel_name = get_channel_name_for_project(doc)
	channel.type = "Private"
	channel.channel_description = _channel_description_for_project(doc)
	channel.is_synced = 1
	channel.linked_doctype = "Project"
	channel.linked_document = doc.name

	workspace = _resolve_workspace(doc)
	if workspace:
		channel.workspace = workspace

	channel.insert(ignore_permissions=True)
	_store_channel_on_project(doc.name, channel.name)
	sync_project_channel_members(doc, channel.name)
	return channel.name


def sync_project_channel_members(doc, channel_id: str | None = None) -> None:
	"""Sync Raven Channel Members from Project Team Employees → Raven Users."""
	channel_id = channel_id or get_channel_for_project(doc.name)
	if not channel_id:
		return

	desired_raven_users = _team_raven_user_ids(doc)
	existing = frappe.get_all(
		"Raven Channel Member",
		filters={"channel_id": channel_id, "is_synced": 1},
		fields=["name", "user_id", "linked_doctype", "linked_document"],
	)
	existing_by_user = {row.user_id: row for row in existing if row.user_id}

	for raven_user, employee_id in desired_raven_users.items():
		if raven_user in existing_by_user:
			continue
		member = frappe.get_doc(
			{
				"doctype": "Raven Channel Member",
				"channel_id": channel_id,
				"user_id": raven_user,
				"is_synced": 1,
				"linked_doctype": "Employee",
				"linked_document": employee_id,
			}
		)
		member.insert(ignore_permissions=True)

	desired_set = set(desired_raven_users.keys())
	for row in existing:
		if row.user_id and row.user_id not in desired_set:
			frappe.db.delete("Raven Channel Member", row.name)


def get_channel_for_project(project: str) -> str | None:
	if not project:
		return None

	if frappe.db.has_column("Project", "custom_raven_channel"):
		stored = frappe.db.get_value("Project", project, "custom_raven_channel")
		if stored and frappe.db.exists("Raven Channel", stored):
			return stored

	channels = frappe.get_all(
		"Raven Channel",
		filters={"linked_doctype": "Project", "linked_document": project},
		pluck="name",
		limit=1,
	)
	return channels[0] if channels else None


def get_channel_name_for_project(doc) -> str:
	"""Build a Raven channel name that includes Project No when available."""
	project_no = (getattr(doc, "custom_project_no", None) or "").strip()
	project_name = (getattr(doc, "project_name", None) or "").strip()
	parts = []
	if project_no:
		parts.append(project_no)
	if project_name:
		parts.append(project_name)
	source = " - ".join(parts) if parts else (doc.name or "project")
	channel_name = ""
	prev = ""
	for char in source:
		if char.isalnum():
			channel_name += char
			prev = char
		elif prev != "-":
			channel_name += "-"
			prev = "-"
	return (channel_name.strip("-") or doc.name)[:140]


def _channel_description_for_project(doc) -> str:
	project_no = (getattr(doc, "custom_project_no", None) or "").strip()
	label = doc.project_name or doc.name
	if project_no:
		return _("Channel for Project {0} - {1}").format(project_no, label)
	return _("Channel for Project - {0}").format(label)


def _team_raven_user_ids(doc) -> dict[str, str]:
	"""Map Raven User name → Employee name for project team rows."""
	employees = []
	for row in doc.get("custom_project_team") or []:
		if row.get("employee"):
			employees.append(row.get("employee"))
	for field in ("custom_project_engineer", "custom_sales_engineer"):
		emp = getattr(doc, field, None)
		if emp:
			employees.append(emp)

	employees = list({e for e in employees if e})
	if not employees:
		return {}

	user_map = {
		row.name: row.user_id
		for row in frappe.get_all(
			"Employee",
			filters={"name": ("in", employees)},
			fields=["name", "user_id"],
		)
		if row.user_id
	}
	if not user_map:
		return {}

	raven_users = frappe.get_all(
		"Raven User",
		filters={"user": ("in", list(user_map.values()))},
		fields=["name", "user"],
	)
	user_to_raven = {row.user: row.name for row in raven_users}

	result = {}
	for employee, user_id in user_map.items():
		raven_user = user_to_raven.get(user_id)
		if raven_user:
			result[raven_user] = employee
	return result


def _resolve_workspace(doc) -> str | None:
	company = getattr(doc, "company", None)
	if company and frappe.db.exists("DocType", "Raven HR Company Workspace"):
		mapped = frappe.get_all(
			"Raven HR Company Workspace",
			filters={"company": company},
			pluck="raven_workspace",
			limit=1,
		)
		if mapped:
			return mapped[0]

	filters = {}
	if frappe.db.has_column("Raven Workspace", "disabled"):
		filters["disabled"] = 0
	workspaces = frappe.get_all(
		"Raven Workspace",
		filters=filters,
		pluck="name",
		order_by="creation asc",
		limit=1,
	)
	return workspaces[0] if workspaces else None


def _sync_channel_meta(doc, channel_id: str) -> None:
	frappe.db.set_value(
		"Raven Channel",
		channel_id,
		{
			"channel_name": get_channel_name_for_project(doc),
			"channel_description": _channel_description_for_project(doc),
		},
		update_modified=False,
	)


def _store_channel_on_project(project: str, channel_id: str) -> None:
	if not frappe.db.has_column("Project", "custom_raven_channel"):
		return
	current = frappe.db.get_value("Project", project, "custom_raven_channel")
	if current != channel_id:
		frappe.db.set_value(
			"Project",
			project,
			"custom_raven_channel",
			channel_id,
			update_modified=False,
		)


def _raven_installed() -> bool:
	return "raven" in frappe.get_installed_apps() and frappe.db.exists("DocType", "Raven Channel")


@frappe.whitelist()
def get_project_channel_messages(project: str, limit: int = 15) -> dict:
	"""Return recent Raven messages for a Project channel (for form panel)."""
	if not project:
		frappe.throw(_("Project is required"))
	if not frappe.has_permission("Project", "read", project):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not _raven_installed():
		return {"channel_id": None, "messages": [], "url": None}

	doc = frappe.get_doc("Project", project)
	channel_id = ensure_project_channel(doc)
	if not channel_id:
		return {"channel_id": None, "messages": [], "url": None}

	limit = _cint_limit(limit)
	messages = frappe.get_all(
		"Raven Message",
		filters={"channel_id": channel_id},
		fields=["name", "owner", "creation", "text", "content", "message_type", "file"],
		order_by="creation desc",
		limit=limit,
	)

	return {
		"channel_id": channel_id,
		"channel_name": frappe.db.get_value("Raven Channel", channel_id, "channel_name"),
		"project_no": getattr(doc, "custom_project_no", None) or "",
		"messages": messages,
		"url": f"/raven/channel/{channel_id}",
	}


def _cint_limit(limit) -> int:
	try:
		value = int(limit or 15)
	except (TypeError, ValueError):
		value = 15
	return max(1, min(value, 50))
