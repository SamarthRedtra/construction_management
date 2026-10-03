"""Controlled purchase-order type and Manual LPO approval lifecycle."""

import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime


LPO_TYPES = {"Standard", "Open", "Manual"}
APPROVAL_STAGES = {"Draft", "Pending Accounts", "Pending CEO", "Needs Correction", "Approved"}
ACCOUNT_ROLES = {"Accounts User", "Accounts Manager"}
ADMIN_ROLES = {"CEO", "System Manager"}


def lpo_type(doc) -> str:
	return doc.get("custom_lpo_type") or ("Open" if cint(doc.get("custom_is_provisional_po")) else "Standard")


def validate_purchase_order(doc, method=None):
	if not cint(doc.get("controlled_procurement")):
		return
	kind = lpo_type(doc)
	if kind not in LPO_TYPES:
		frappe.throw(_("Choose Standard, Open, or Manual LPO type."))
	if kind == "Open" and not frappe.get_meta("Purchase Order").has_field("custom_is_provisional_po"):
		frappe.throw(_("Open LPO requires the provisional purchase-order field to be installed."))
	previous = doc.get_doc_before_save() if not doc.is_new() else None
	if previous and previous.get("custom_lpo_type") == "Manual" and kind != "Manual" and previous.get("custom_lpo_approval_history"):
		frappe.throw(_("A Manual LPO already sent for approval cannot change type."))
	doc.custom_lpo_type = kind
	doc.custom_is_provisional_po = cint(kind == "Open")
	doc.custom_lpo_reference = (doc.get("custom_lpo_reference") or "").strip() or None
	if kind != "Manual":
		doc.custom_lpo_approval_status = None
		return
	status = doc.get("custom_lpo_approval_status") or "Draft"
	if doc.is_new() and not getattr(doc.flags, "lpo_workflow_transition", False):
		status = "Draft"
		doc.custom_lpo_approval_history = None
	if status not in APPROVAL_STAGES:
		frappe.throw(_("Invalid Manual LPO approval status."))
	if previous and not getattr(doc.flags, "lpo_workflow_transition", False):
		if (doc.get("custom_lpo_approval_history") or "") != (previous.get("custom_lpo_approval_history") or "") or status != (previous.get("custom_lpo_approval_status") or "Draft"):
			frappe.throw(_("Manual LPO approval history and status can only change through approval actions."), frappe.PermissionError)
		if doc.docstatus == 0 and previous.custom_lpo_approval_status in {"Pending Accounts", "Pending CEO", "Approved"}:
			frappe.throw(_("This Manual LPO is awaiting approval and cannot be edited."))
	doc.custom_lpo_approval_status = status


def before_submit_purchase_order(doc, method=None):
	if cint(doc.get("controlled_procurement")) and lpo_type(doc) == "Manual":
		if not getattr(doc.flags, "lpo_ceo_submit", False) or doc.custom_lpo_approval_status != "Approved":
			frappe.throw(_("Manual LPOs must be approved by Accounts and CEO before submission."), frappe.PermissionError)


def get_manual_lpo(name: str, roles: set[str], permission: str = "read"):
	from construction_management.api.controlled_procurement import _allowed_companies

	if not set(frappe.get_roles()).intersection(roles):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	# Lock the row so two approvers cannot advance the same stage simultaneously.
	frappe.db.sql("select name from `tabPurchase Order` where name = %s for update", name)
	doc = frappe.get_doc("Purchase Order", name)
	if doc.company not in _allowed_companies() or not cint(doc.get("controlled_procurement")) or lpo_type(doc) != "Manual":
		frappe.throw(_("Manual LPO is not available."), frappe.PermissionError)
	if permission and permission != "read":
		frappe.has_permission("Purchase Order", permission, doc=doc, throw=True)
	return doc


def append_history(doc, action: str, comment: str = ""):
	history = json.loads(doc.get("custom_lpo_approval_history") or "[]")
	history.append({"action": action, "user": frappe.session.user, "at": str(now_datetime()), "comment": comment})
	doc.custom_lpo_approval_history = json.dumps(history)


def transition(doc, status: str, action: str, comment: str = ""):
	doc.custom_lpo_approval_status = status
	append_history(doc, action, comment)
	doc.flags.controlled_procurement_api = True
	doc.flags.lpo_workflow_transition = True
	doc.flags.ignore_permissions = True
	doc.save()
	if doc.get("custom_po_price_status") == "Pending CEO":
		from construction_management.api import po_price_approvals
		if status == "Needs Correction":
			po_price_approvals._finish(doc, "Needs Correction", comment or "Manual LPO returned for correction")
		else:
			proposal = json.loads(doc.custom_po_price_proposal or "{}")
			proposal["po_modified"] = str(doc.modified)
			frappe.db.set_value("Purchase Order", doc.name, "custom_po_price_proposal", json.dumps(proposal), update_modified=False)
			if status == "Pending CEO":
				po_price_approvals._enqueue_notice(doc.name)
	return {"name": doc.name, "approval_status": status, "docstatus": doc.docstatus}


def request_approval(name: str) -> dict:
	from construction_management.api.controlled_procurement import PURCHASE_ROLES

	doc = get_manual_lpo(name, PURCHASE_ROLES, "write")
	if doc.docstatus != 0 or doc.custom_lpo_approval_status not in {"Draft", "Needs Correction"}:
		frappe.throw(_("Only a draft or corrected Manual LPO can be sent for approval."))
	if doc.custom_lpo_approval_status == "Needs Correction" and doc.owner != frappe.session.user and "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only the creator can resubmit this Manual LPO."), frappe.PermissionError)
	return transition(doc, "Pending Accounts", "Requested approval")


def approve(name: str) -> dict:
	doc = get_manual_lpo(name, ACCOUNT_ROLES | ADMIN_ROLES)
	if doc.docstatus != 0:
		frappe.throw(_("This LPO is no longer a draft."))
	roles = set(frappe.get_roles())
	if doc.custom_lpo_approval_status == "Pending Accounts" and roles.intersection(ACCOUNT_ROLES | {"System Manager"}):
		return transition(doc, "Pending CEO", "Accounts approved")
	if doc.custom_lpo_approval_status == "Pending CEO" and roles.intersection(ADMIN_ROLES):
		if doc.get("custom_po_price_status") == "Pending CEO":
			from construction_management.api import po_price_approvals
			frappe.flags.manual_lpo_ceo_approval = True
			try:
				result = po_price_approvals.approve_po_price(doc.name)
			finally:
				frappe.flags.manual_lpo_ceo_approval = False
			if result["status"] != "Approved":
				doc.reload()
				transition(doc, "Needs Correction", "Price approval needs correction", result.get("reason") or "Active price or PO changed")
				return {"name": doc.name, "approval_status": "Needs Correction", "price_approval_status": result["status"], "docstatus": 0}
			doc.reload()
		transition(doc, "Approved", "CEO approved" if "CEO" in roles else "System Manager approved")
		doc.flags.lpo_ceo_submit = True
		doc.flags.controlled_procurement_api = True
		doc.flags.lpo_workflow_transition = True
		doc.flags.ignore_permissions = True
		doc.submit()
		return {"name": doc.name, "approval_status": "Approved", "docstatus": doc.docstatus}
	frappe.throw(_("You cannot approve this Manual LPO at its current stage."), frappe.PermissionError)


def reject(name: str, comment: str) -> dict:
	doc = get_manual_lpo(name, ACCOUNT_ROLES | ADMIN_ROLES)
	if not (comment or "").strip():
		frappe.throw(_("Enter a rejection reason."))
	roles = set(frappe.get_roles())
	if doc.docstatus != 0 or not (
		(doc.custom_lpo_approval_status == "Pending Accounts" and roles.intersection(ACCOUNT_ROLES | {"System Manager"}))
		or (doc.custom_lpo_approval_status == "Pending CEO" and roles.intersection(ADMIN_ROLES))
	):
		frappe.throw(_("You cannot reject this Manual LPO at its current stage."), frappe.PermissionError)
	return transition(doc, "Needs Correction", "Rejected", comment.strip())
