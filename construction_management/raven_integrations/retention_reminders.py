# Copyright (c) 2026, Construction Management
# License: MIT

"""Post TOC and DLP retention reminders into the project Raven channel."""

from __future__ import annotations

import frappe
from frappe.utils import add_days, cint, formatdate, getdate, today

from construction_management.raven_integrations.project_channel import (
	ensure_project_channel,
	_raven_installed,
)


MILESTONES = (
	("TOC", "custom_retention_toc_due_date", "TOC retention"),
	("DLP", "custom_retention_dlp_due_date", "DLP retention"),
)


def send_retention_reminders():
	if not _raven_installed() or not frappe.db.exists("DocType", "Retention Reminder Settings"):
		return
	settings = frappe.get_single("Retention Reminder Settings")
	if not cint(settings.enabled):
		return
	if not frappe.db.has_column("Project", "custom_retention_toc_due_date"):
		return

	anchor = getdate(today())
	dates = set()
	if cint(settings.notify_on_due_date):
		dates.add(anchor)
	lead = cint(settings.days_before)
	if lead:
		dates.add(add_days(anchor, lead))

	for milestone, fieldname, label in MILESTONES:
		for due in dates:
			for project in _projects_due(fieldname, due):
				_post_once(project, milestone, label, due, anchor)


def _projects_due(fieldname: str, due) -> list[str]:
	return frappe.get_all(
		"Project",
		filters={fieldname: due, "status": ["!=", "Cancelled"]},
		pluck="name",
	)


def _post_once(project: str, milestone: str, label: str, due, sent_on) -> None:
	if frappe.db.exists(
		"Retention Reminder Log",
		{"project": project, "milestone": milestone, "reminder_date": sent_on},
	):
		return
	doc = frappe.get_doc("Project", project)
	channel_id = ensure_project_channel(doc)
	if not channel_id:
		return
	from raven.api.raven_message import send_message

	project_label = doc.project_name or project
	send_message(
		channel_id,
		f"{label} for {project_label} is due on {formatdate(due)}.",
	)
	frappe.get_doc(
		{
			"doctype": "Retention Reminder Log",
			"project": project,
			"milestone": milestone,
			"reminder_date": sent_on,
		}
	).insert(ignore_permissions=True)
