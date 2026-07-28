# Copyright (c) 2026, Construction Management
# License: MIT

"""Auto-create and sync Raven channels linked to Project documents."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint


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
		sync_project_channel_members(doc, existing)
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
	notification_preferences = _team_notification_preferences(doc)
	workspace = frappe.db.get_value("Raven Channel", channel_id, "workspace")

	# Ensure Desk User has Raven User role + Raven User is enabled (required for member list UI).
	for raven_user in list(desired_raven_users.keys()):
		_ensure_raven_user_ready(raven_user)
		# Raven only allows channel membership for workspace members.
		_ensure_workspace_member(workspace, raven_user)

	existing = frappe.get_all(
		"Raven Channel Member",
		filters={"channel_id": channel_id, "is_synced": 1},
		fields=["name", "user_id", "linked_doctype", "linked_document", "notification_preference"],
	)
	existing_by_user = {row.user_id: row for row in existing if row.user_id}

	changed = False
	for raven_user, employee_id in desired_raven_users.items():
		notification_preference = notification_preferences.get(employee_id, "All Messages")
		if raven_user in existing_by_user:
			existing_member = existing_by_user[raven_user]
			if existing_member.notification_preference != notification_preference:
				member_doc = frappe.get_doc("Raven Channel Member", existing_member.name)
				member_doc.notification_preference = notification_preference
				member_doc.flags.ignore_permissions = True
				member_doc.save(ignore_permissions=True)
				changed = True
			continue
		# Skip if already a non-synced member of this channel (avoid duplicate).
		if frappe.db.exists(
			"Raven Channel Member", {"channel_id": channel_id, "user_id": raven_user}
		):
			continue
		member = frappe.get_doc(
			{
				"doctype": "Raven Channel Member",
				"channel_id": channel_id,
				"user_id": raven_user,
				"is_synced": 1,
				"linked_doctype": "Employee",
				"linked_document": employee_id,
				"notification_preference": notification_preference,
			}
		)
		member.insert(ignore_permissions=True)
		changed = True

	desired_set = set(desired_raven_users.keys())
	for row in existing:
		if row.user_id and row.user_id not in desired_set:
			frappe.db.delete("Raven Channel Member", row.name)
			changed = True

	# Always clear Raven member list cache so UI shows fresh members.
	_clear_raven_channel_members_cache(channel_id)
	if workspace:
		_clear_raven_workspace_members_cache(workspace)
	if changed:
		_clear_raven_users_list_cache()


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
	"""Map Raven User name → Employee name for project team rows.

	Resolution order per employee:
	1. Employee.user_id → Raven User
	2. Employee emails → User → Raven User
	3. Name match against Raven User.full_name (unique match only)
	"""
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

	emp_rows = frappe.get_all(
		"Employee",
		filters={"name": ("in", employees)},
		fields=[
			"name",
			"employee_name",
			"user_id",
			"company_email",
			"personal_email",
			"prefered_email",
		],
	)
	if not emp_rows:
		return {}

	result: dict[str, str] = {}
	for emp in emp_rows:
		raven_user = _resolve_raven_user_for_employee(emp)
		if raven_user:
			result[raven_user] = emp.name
	return result


def _team_notification_preferences(doc) -> dict[str, str]:
	"""Map each Project Team Employee to their selected Raven notification preference."""
	preferences: dict[str, str] = {}
	for row in doc.get("custom_project_team") or []:
		employee = row.get("employee")
		if employee and employee not in preferences:
			preferences[employee] = (
				"Mentions Only"
				if row.get("notification_preference") == "Mentions Only"
				else "All Messages"
			)
	return preferences


def _resolve_raven_user_for_employee(emp) -> str | None:
	"""Resolve Raven User for one Employee row (as_dict / Document)."""
	user_id = (emp.get("user_id") if isinstance(emp, dict) else emp.user_id) or None
	if user_id:
		raven = _ensure_raven_user_for_user(user_id)
		if raven:
			return raven

	emails = []
	for key in ("company_email", "personal_email", "prefered_email"):
		val = emp.get(key) if isinstance(emp, dict) else emp.get(key)
		if val:
			emails.append(str(val).strip())
	for email in emails:
		if frappe.db.exists("User", email):
			raven = _ensure_raven_user_for_user(email)
			if raven:
				_maybe_link_employee_user(emp.get("name") if isinstance(emp, dict) else emp.name, email)
				return raven

	employee_name = emp.get("employee_name") if isinstance(emp, dict) else emp.employee_name
	matched_user = _match_user_by_employee_name(employee_name)
	if matched_user:
		raven = _ensure_raven_user_for_user(matched_user)
		if raven:
			_maybe_link_employee_user(emp.get("name") if isinstance(emp, dict) else emp.name, matched_user)
			return raven
	return None


def _maybe_link_employee_user(employee: str, user: str) -> None:
	"""Persist Employee.user_id when empty so future syncs are direct."""
	if not employee or not user:
		return
	if frappe.db.get_value("Employee", employee, "user_id"):
		return
	if not frappe.db.exists("User", user):
		return
	try:
		frappe.db.set_value("Employee", employee, "user_id", user, update_modified=False)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Link Employee {employee} → User {user}")


def _ensure_raven_user_for_user(user: str) -> str | None:
	"""Return Raven User name for Desk User; create enabled Raven User if missing."""
	if not user or not frappe.db.exists("User", user):
		return None
	existing = frappe.db.get_value("Raven User", {"user": user}, "name")
	if existing:
		_ensure_raven_user_ready(existing)
		return existing
	try:
		doc = frappe.get_doc(
			{
				"doctype": "Raven User",
				"user": user,
				"type": "User",
				"enabled": 1,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		_ensure_desk_user_has_raven_role(user)
		_clear_raven_users_list_cache()
		return doc.name
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Ensure Raven User for {user}")
		existing = frappe.db.get_value("Raven User", {"user": user}, "name")
		if existing:
			_ensure_raven_user_ready(existing)
		return existing


def _ensure_raven_user_ready(raven_user: str) -> None:
	"""Enable Raven User + ensure linked Desk User has Raven User role."""
	if not raven_user or not frappe.db.exists("Raven User", raven_user):
		return
	row = frappe.db.get_value("Raven User", raven_user, ["user", "enabled"], as_dict=True) or {}
	if not cint(row.get("enabled")):
		frappe.db.set_value("Raven User", raven_user, "enabled", 1, update_modified=False)
	if row.get("user"):
		_ensure_desk_user_has_raven_role(row.user)


def _ensure_desk_user_has_raven_role(user: str) -> None:
	"""Add Raven User role to Desk User when missing."""
	if not user or user == "Guest":
		return
	if not frappe.db.exists("User", user):
		return
	if frappe.db.exists("Has Role", {"parent": user, "role": "Raven User"}):
		return
	if not frappe.db.exists("Role", "Raven User"):
		return

	try:
		user_doc = frappe.get_doc("User", user)
		user_doc.flags.ignore_permissions = True
		user_doc.add_roles("Raven User")
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Add Raven User role via add_roles for {user}")

	# Some User save hooks strip roles; fall back to direct Has Role insert.
	if frappe.db.exists("Has Role", {"parent": user, "role": "Raven User"}):
		frappe.clear_cache(user=user)
		return

	try:
		max_idx = frappe.db.sql(
			"SELECT IFNULL(MAX(idx), 0) FROM `tabHas Role` WHERE parent=%s",
			(user,),
		)[0][0]
		frappe.get_doc(
			{
				"doctype": "Has Role",
				"parent": user,
				"parenttype": "User",
				"parentfield": "roles",
				"role": "Raven User",
				"idx": int(max_idx) + 1,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=user)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Add Raven User role via Has Role for {user}")


def _ensure_workspace_member(workspace: str | None, raven_user: str) -> None:
	"""Ensure Raven User is a member of the channel's workspace (required by Raven)."""
	if not workspace or not raven_user:
		return
	if not frappe.db.exists("DocType", "Raven Workspace Member"):
		return
	if not frappe.db.exists("Raven Workspace", workspace):
		return
	if frappe.db.exists(
		"Raven Workspace Member", {"workspace": workspace, "user": raven_user}
	):
		return
	try:
		member = frappe.get_doc(
			{
				"doctype": "Raven Workspace Member",
				"workspace": workspace,
				"user": raven_user,
				"is_admin": 0,
			}
		)
		member.flags.ignore_permissions = True
		member.insert(ignore_permissions=True)
		_clear_raven_workspace_members_cache(workspace)
	except Exception:
		# Duplicate / race is fine
		if not frappe.db.exists(
			"Raven Workspace Member", {"workspace": workspace, "user": raven_user}
		):
			frappe.log_error(
				frappe.get_traceback(),
				f"Add Raven Workspace Member {raven_user} → {workspace}",
			)


def _clear_raven_workspace_members_cache(workspace: str) -> None:
	if not workspace:
		return
	try:
		from raven.utils import delete_workspace_members_cache

		delete_workspace_members_cache(workspace)
	except Exception:
		frappe.cache().delete_value(f"raven:workspace_members:{workspace}")


def _clear_raven_channel_members_cache(channel_id: str) -> None:
	if not channel_id:
		return
	try:
		from raven.utils import delete_channel_members_cache

		delete_channel_members_cache(channel_id)
	except Exception:
		frappe.cache().delete_value(f"raven:channel_members:{channel_id}")


def _clear_raven_users_list_cache() -> None:
	try:
		from raven.api.raven_users import get_users

		if hasattr(get_users, "clear_cache"):
			get_users.clear_cache()
	except Exception:
		pass


def _normalize_person_name(name: str | None) -> str:
	import re

	text = re.sub(r"\([^)]*\)", " ", name or "")
	text = re.sub(r"[^A-Za-z0-9 ]+", " ", text)
	return re.sub(r"\s+", " ", text).strip().upper()


def _match_user_by_employee_name(employee_name: str | None) -> str | None:
	"""Unique User match from Raven User / User full names."""
	target = _normalize_person_name(employee_name)
	if not target or len(target) < 3:
		return None

	raven_rows = frappe.get_all("Raven User", fields=["name", "user", "full_name"], filters={"enabled": 1})
	hits = []
	for row in raven_rows:
		candidate = _normalize_person_name(row.full_name) or _normalize_person_name(row.user)
		if _person_names_match(target, candidate):
			hits.append(row.user)
	hits = list({h for h in hits if h})
	if len(hits) == 1:
		return hits[0]

	# Fallback: enabled System Users by full_name
	users = frappe.get_all(
		"User",
		filters={"enabled": 1, "user_type": "System User"},
		fields=["name", "full_name"],
	)
	uhits = []
	for row in users:
		if _person_names_match(target, _normalize_person_name(row.full_name)):
			uhits.append(row.name)
	uhits = list({h for h in uhits if h})
	if len(uhits) == 1:
		return uhits[0]
	return None


def _person_names_match(a: str, b: str) -> bool:
	if not a or not b:
		return False
	if a == b:
		return True
	if a.startswith(b) or b.startswith(a):
		return True
	at, bt = a.split(), b.split()
	if len(at) >= 2 and len(bt) >= 2 and at[0] == bt[0] and at[1] == bt[1]:
		return True
	# Contiguous token window: "WAQAR TARIQ" inside "MUHAMMAD WAQAR TARIQ …"
	shorter, longer = (at, bt) if len(at) <= len(bt) else (bt, at)
	if len(shorter) >= 2 and _tokens_contiguous(shorter, longer):
		return True
	# Single strong token (len>=5) unique-ish overlap for short raven names like "TAQREEB"
	if len(shorter) == 1 and len(shorter[0]) >= 5 and shorter[0] in longer:
		return True
	if len(at) >= 1 and len(bt) >= 1 and at[0] == bt[0] and len(at[0]) >= 4:
		if len(at) >= 2 and at[1] in bt:
			return True
	return False


def _tokens_contiguous(needle: list[str], haystack: list[str]) -> bool:
	n, m = len(needle), len(haystack)
	if n == 0 or n > m:
		return False
	for i in range(m - n + 1):
		if haystack[i : i + n] == needle:
			return True
	return False


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


@frappe.whitelist()
def add_users_to_raven_channels(
	users=None, channel_ids=None, notification_preference: str = "All Messages"
) -> dict:
	"""
	Add one/many Desk Users to one/many Raven Channels (project-linked or any).
	Members are inserted with is_synced=0 so Project team sync will not remove them.
	"""
	if not _raven_installed():
		frappe.throw(_("Raven is not installed"))
	if not frappe.has_permission("Raven Channel", "write"):
		frappe.throw(_("Not permitted to modify Raven channels"), frappe.PermissionError)

	users = _as_list(users)
	channel_ids = _as_list(channel_ids)
	notification_preference = _notification_preference(notification_preference)
	if not users:
		frappe.throw(_("Select at least one User"))
	if not channel_ids:
		frappe.throw(_("Select at least one Raven Channel"))

	raven_users = _resolve_raven_users(users)
	if not raven_users:
		frappe.throw(_("None of the selected users have a Raven User profile"))

	for raven_user in raven_users:
		_ensure_raven_user_ready(raven_user)

	added = 0
	updated = 0
	missing_channels = []

	for channel_id in channel_ids:
		if not frappe.db.exists("Raven Channel", channel_id):
			missing_channels.append(channel_id)
			continue
		workspace = frappe.db.get_value("Raven Channel", channel_id, "workspace")
		for raven_user in raven_users:
			_ensure_workspace_member(workspace, raven_user)
		existing = {
			member.user_id: member.name
			for member in frappe.get_all(
				"Raven Channel Member",
				filters={"channel_id": channel_id, "user_id": ("in", raven_users)},
				fields=["name", "user_id"],
			)
		}
		for raven_user in raven_users:
			if raven_user in existing:
				member = frappe.get_doc("Raven Channel Member", existing[raven_user])
				if member.notification_preference != notification_preference:
					member.notification_preference = notification_preference
					member.flags.ignore_permissions = True
					member.save(ignore_permissions=True)
				else:
					# Repair any old topic subscription left behind before this preference existed.
					member.sync_notification_subscription()
				updated += 1
				continue
			member = frappe.get_doc(
				{
					"doctype": "Raven Channel Member",
					"channel_id": channel_id,
					"user_id": raven_user,
					"is_synced": 0,
					"notification_preference": notification_preference,
				}
			)
			member.flags.ignore_permissions = True
			member.insert(ignore_permissions=True)
			added += 1
		_clear_raven_channel_members_cache(channel_id)
		if workspace:
			_clear_raven_workspace_members_cache(workspace)

	_clear_raven_users_list_cache()
	return {
		"added": added,
		"updated": updated,
		"raven_users": raven_users,
		"missing_channels": missing_channels,
	}


def _as_list(value) -> list[str]:
	if value is None:
		return []
	if isinstance(value, str):
		import json

		value = value.strip()
		if not value:
			return []
		if value.startswith("["):
			try:
				parsed = json.loads(value)
				if isinstance(parsed, list):
					return [str(v).strip() for v in parsed if str(v).strip()]
			except Exception:
				pass
		return [v.strip() for v in value.split(",") if v.strip()]
	if isinstance(value, (list, tuple, set)):
		return [str(v).strip() for v in value if str(v).strip()]
	return [str(value).strip()] if str(value).strip() else []


def _notification_preference(value: str | None) -> str:
	return "Mentions Only" if value == "Mentions Only" else "All Messages"


def _resolve_raven_users(users: list[str]) -> list[str]:
	"""Accept Desk User names or Raven User names; return Raven User names."""
	resolved = []
	for name in users:
		if frappe.db.exists("Raven User", name):
			_ensure_raven_user_ready(name)
			resolved.append(name)
			continue
		# Desk User → ensure Raven User exists (+ role)
		raven = _ensure_raven_user_for_user(name)
		if raven:
			resolved.append(raven)
			continue
		# Raven User by user field
		raven = frappe.db.get_value("Raven User", {"user": name}, "name")
		if raven:
			_ensure_raven_user_ready(raven)
			resolved.append(raven)
	# unique, preserve order
	seen = set()
	out = []
	for ru in resolved:
		if ru not in seen:
			seen.add(ru)
			out.append(ru)
	return out


def _cint_limit(limit) -> int:
	try:
		value = int(limit or 15)
	except (TypeError, ValueError):
		value = 15
	return max(1, min(value, 50))
