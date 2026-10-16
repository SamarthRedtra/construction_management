"""Outgoing mail for controlled catalogue approvals and Procurement documents."""

from __future__ import annotations

from html import escape
from urllib.parse import quote

import frappe
from frappe import _


DEFAULT_EMAIL_ACCOUNTS = {
	"M R G INSULATION WORKS L.L.C": "MRG Purchase",
	"SKADA CONSTRUCTION L.L.C": "Skada Purchase",
}


def outgoing_sender(company: str) -> str:
	"""Never let Procurement mail fall back to an unrelated site-wide account."""
	configured = frappe.conf.get("controlled_procurement_email_accounts") or {}
	if isinstance(configured, str):
		configured = frappe.parse_json(configured)
	if not isinstance(configured, dict):
		frappe.throw(_("Procurement outgoing Email Account configuration must map companies to account names."), frappe.OutgoingEmailError)
	account_name = configured.get(company) or DEFAULT_EMAIL_ACCOUNTS.get(company)
	if not account_name:
		frappe.throw(_("Configure a Procurement outgoing Email Account for {0}.").format(company), frappe.OutgoingEmailError)
	account = frappe.db.get_value("Email Account", account_name, ["email_id", "enable_outgoing"], as_dict=True)
	if not account or not account.enable_outgoing or not account.email_id:
		frappe.throw(_("Procurement outgoing Email Account {0} is missing or disabled.").format(account_name), frappe.OutgoingEmailError)
	return account.email_id


def catalog_approval_recipients(company: str, status: str, requester: str = "") -> list[str]:
	from construction_management.api.controlled_procurement import CATALOG_CEO_USERS

	role = "Accounts Manager" if status == "Pending Accounts" else "CEO"
	users = set(frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent", limit_page_length=0))
	if status == "Pending CEO":
		users &= CATALOG_CEO_USERS
	recipients = []
	for user in sorted(users):
		if status == "Pending Accounts" and user == requester:
			continue
		if not frappe.db.exists("User", {"name": user, "enabled": 1}):
			continue
		permissions = frappe.get_all("User Permission", filters={"user": user, "allow": "Company"}, pluck="for_value")
		if not permissions or company in permissions:
			recipients.append(user)
	return recipients


def enqueue_approval_email(name: str, status: str) -> None:
	frappe.db.after_commit.add(lambda: frappe.enqueue(
		"construction_management.api.catalog_email.deliver_approval_email",
		queue="short", name=name, expected_status=status,
	))


def deliver_approval_email(name: str, expected_status: str) -> None:
	if expected_status not in {"Pending Accounts", "Pending CEO"}:
		return
	frappe.db.sql("select name from `tabControlled Catalog Request` where name = %s for update", name)
	doc = frappe.get_doc("Controlled Catalog Request", name)
	if doc.status != expected_status or getattr(doc, "approval_email_queue", None):
		return
	try:
		users = catalog_approval_recipients(doc.company, expected_status, doc.requested_by)
		recipients = [email for user in users
			if (email := frappe.db.get_value("User", user, "email")) and frappe.utils.validate_email_address(email)]
		if not recipients:
			raise ValueError(f"No eligible {expected_status.removeprefix('Pending ')} approvers for {doc.company}.")
		sender = outgoing_sender(doc.company)
		url = frappe.utils.get_url(f"/procurement/catalog/approvals?request={quote(doc.name, safe='')}")
		stage = "Accounts Manager" if expected_status == "Pending Accounts" else "CEO"
		queue = frappe.sendmail(
			recipients=recipients, sender=sender,
			subject=f"Catalogue request {doc.name} awaits {stage} approval",
			message=(f"Catalogue request {escape(doc.name)} for {escape(doc.company)} is pending your approval. "
				f'<a href="{escape(url, quote=True)}">Open Procurement approvals</a>.'),
			reference_doctype=doc.doctype, reference_name=doc.name, add_unsubscribe_link=0,
		)
		if not queue:
			raise RuntimeError("Frappe did not create an Email Queue entry.")
		if hasattr(doc, "approval_email_queue"):
			doc.approval_email_queue = queue.name
		if hasattr(doc, "approval_email_error"):
			doc.approval_email_error = ""
	except Exception as exc:
		frappe.db.rollback()
		doc = frappe.get_doc("Controlled Catalog Request", name)
		if doc.status != expected_status:
			return
		if hasattr(doc, "approval_email_error"):
			doc.approval_email_error = str(exc)[:500]
		frappe.log_error(title=f"Catalogue approval email {name}", message=frappe.get_traceback())
	doc.flags.controlled_catalog_request_api = True
	doc.save(ignore_permissions=True)
