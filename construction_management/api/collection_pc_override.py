# Copyright (c) 2026, Construction Management
# License: MIT

"""Collection Manager PC date/amount persistence helpers."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

COLLECTION_PC_STATUSES = ("Collection PC", "PC Date", "PC Amount")


def upsert_collection_pc_override(
	project: str,
	reference_doctype: str,
	reference_name: str,
	*,
	pc_date=None,
	pc_amount=None,
	update_date: bool = False,
	update_amount: bool = False,
) -> dict:
	"""Create or update one follow-up that stores Collection Manager PC date/amount."""
	if not project or not reference_doctype or not reference_name:
		frappe.throw(_("Project, reference doctype, and reference name are required"))

	existing = _find_collection_pc_follow_up(project, reference_doctype, reference_name)
	has_pc_amount = frappe.db.has_column("Project SOA Follow Up", "pc_amount")

	if existing:
		values = {"status": "Collection PC", "remarks": _("PC fields set from Collection Manager")}
		if update_date:
			values["follow_up_date"] = getdate(pc_date) if pc_date else None
		if update_amount and has_pc_amount:
			values["pc_amount"] = flt(pc_amount)
		frappe.db.set_value("Project SOA Follow Up", existing, values, update_modified=True)
		name = existing
	else:
		doc = frappe.new_doc("Project SOA Follow Up")
		doc.project = project
		doc.reference_doctype = reference_doctype
		doc.reference_name = reference_name
		doc.status = "Collection PC"
		doc.remarks = _("PC fields set from Collection Manager")
		doc.follow_up_date = getdate(pc_date) if (update_date and pc_date) else getdate(today())
		if update_amount and has_pc_amount:
			doc.pc_amount = flt(pc_amount)
		doc.insert(ignore_permissions=True)
		name = doc.name

	frappe.db.commit()
	return {
		"name": name,
		"project": project,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"pc_date": pc_date if update_date else None,
		"pc_amount": flt(pc_amount) if update_amount else None,
		"via": "follow_up",
	}


def _find_collection_pc_follow_up(project: str, reference_doctype: str, reference_name: str) -> str | None:
	# Prefer a single Collection PC row; else reuse any legacy PC Date/Amount row.
	name = frappe.db.get_value(
		"Project SOA Follow Up",
		{
			"project": project,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"status": "Collection PC",
		},
		"name",
		order_by="modified desc",
	)
	if name:
		return name
	return frappe.db.get_value(
		"Project SOA Follow Up",
		{
			"project": project,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"status": ("in", ["PC Date", "PC Amount"]),
		},
		"name",
		order_by="modified desc",
	)


def upsert_collection_due_date(
	project: str, reference_doctype: str, reference_name: str, due_date=None
) -> dict:
	"""Store the Collection Manager due date on the row's Project SOA Follow Up."""
	existing = _find_collection_pc_follow_up(project, reference_doctype, reference_name)
	if not existing:
		existing = frappe.db.get_value(
			"Project SOA Follow Up",
			{
				"project": project,
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
			},
			"name",
			order_by="modified desc",
		)

	if existing:
		frappe.db.set_value(
			"Project SOA Follow Up",
			existing,
			"collection_due_date",
			getdate(due_date) if due_date else None,
			update_modified=True,
		)
		name = existing
	else:
		doc = frappe.new_doc("Project SOA Follow Up")
		doc.project = project
		doc.reference_doctype = reference_doctype
		doc.reference_name = reference_name
		doc.status = "Collection Due Date"
		doc.follow_up_date = getdate(due_date) if due_date else getdate(today())
		doc.collection_due_date = getdate(due_date) if due_date else None
		doc.remarks = _("Collection due date set from Collection Manager")
		doc.insert(ignore_permissions=True)
		name = doc.name

	frappe.db.commit()
	return {
		"name": name,
		"project": project,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"due_date": due_date,
		"via": "follow_up",
	}


def merge_collection_pc_overlays(rows: list[dict], follow_ups: list[dict]) -> None:
	"""
	Merge PC date/amount from all Collection PC follow-ups onto rows.

	Unlike generic follow-up overlay (latest-only), this aggregates every matching
	Collection PC / PC Date / PC Amount follow-up for the row reference.
	"""
	by_ref: dict[tuple[str, str], dict] = {}

	def _bucket(key):
		return by_ref.setdefault(
			key,
			{"pc_date": None, "pc_amount": None, "payment_certificate": None, "attachment": None},
		)

	# 1) Authoritative Collection PC rows win
	for fu in follow_ups or []:
		if (fu.get("status") or "") != "Collection PC":
			continue
		key = (fu.get("reference_doctype"), fu.get("reference_name"))
		bucket = _bucket(key)
		if fu.get("follow_up_date"):
			bucket["pc_date"] = fu.get("follow_up_date")
		if fu.get("pc_amount") is not None:
			bucket["pc_amount"] = flt(fu.get("pc_amount"))
		if fu.get("payment_certificate"):
			bucket["payment_certificate"] = fu.get("payment_certificate")
		if fu.get("attachment"):
			bucket["attachment"] = fu.get("attachment")

	# 2) Legacy PC Date / PC Amount fill only missing fields (newest-first list)
	for fu in follow_ups or []:
		status = fu.get("status") or ""
		if status not in ("PC Date", "PC Amount"):
			continue
		key = (fu.get("reference_doctype"), fu.get("reference_name"))
		bucket = _bucket(key)
		if status == "PC Date" and fu.get("follow_up_date") and not bucket["pc_date"]:
			bucket["pc_date"] = fu.get("follow_up_date")
		if status == "PC Amount" and flt(fu.get("pc_amount")) and bucket["pc_amount"] is None:
			bucket["pc_amount"] = flt(fu.get("pc_amount"))
		if fu.get("payment_certificate") and not bucket["payment_certificate"]:
			bucket["payment_certificate"] = fu.get("payment_certificate")
		if fu.get("attachment") and not bucket["attachment"]:
			bucket["attachment"] = fu.get("attachment")

	for row in rows:
		key = (row.get("reference_doctype"), row.get("reference_name"))
		bucket = by_ref.get(key)
		if not bucket:
			continue
		if bucket.get("pc_date"):
			row["pc_date"] = bucket["pc_date"]
		if bucket.get("pc_amount") is not None:
			row["pc_amt"] = flt(bucket["pc_amount"])
		if bucket.get("payment_certificate") and not row.get("payment_certificate"):
			row["payment_certificate"] = bucket["payment_certificate"]
		if bucket.get("attachment"):
			row["pc_attachment"] = bucket["attachment"]
