"""One CEO decision for all buying-rate changes proposed on a controlled PO."""

from __future__ import annotations

import json
import math

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from construction_management.api import controlled_price_requests as prices


def _procurement():
	from construction_management.api import controlled_procurement
	return controlled_procurement


def _lines(data):
	return frappe.parse_json(data) if isinstance(data, str) else data


def _rate(value):
	rate = flt(value)
	if not math.isfinite(rate) or rate <= 0:
		frappe.throw(_("Every controlled Purchase Order item must have a rate greater than zero."))
	return rate


def _current(item_code, supplier, company, date):
	api = _procurement()
	if not api._item_has_supplier(item_code, supplier):
		frappe.throw(_("Supplier {0} must be linked to catalog item {1} before ordering it.").format(supplier, item_code))
	return api.get_catalog_buying_price(item_code, supplier, company, str(date))


def prepare_rates(company, supplier, date, rows, previous=None):
	"""Keep active rates on the PO; hold only intentionally changed rates in a proposal."""
	old_rows = list(previous.items) if previous else []
	changes = []
	for index, row in enumerate(rows):
		code = row.get("item_code")
		proposed = _rate(row.get("rate"))
		old = None
		if previous and previous.supplier == supplier:
			old = next((item for item in old_rows if item.name == row.get("docname") and item.item_code == code), None)
		if old and flt(old.rate) == proposed:
			continue  # Historical rates do not become new price requests.
		active = _current(code, supplier, company, date)
		active_rate = flt(active.get("rate")) if active.get("rate") is not None else None
		if not old and active_rate == proposed:
			continue
		if not old and not cint(row.get("rate_edited")) and proposed != active_rate:
			frappe.throw(_("The buying price for {0} changed while editing. Refresh the item price before saving.").format(code))
		if old and not cint(row.get("rate_edited")) and proposed != active_rate:
			frappe.throw(_("The buying price for {0} changed while editing. Refresh the item price before saving.").format(code))
		reason = (row.get("price_change_reason") or "").strip()
		if not reason:
			frappe.throw(_("Enter a reason for the changed buying rate of {0}.").format(code))
		price_list = active.get("price_list") or frappe.db.get_value("Supplier", supplier, "default_price_list") or "Standard Buying"
		list_info = frappe.db.get_value("Price List", price_list, ["buying", "enabled", "currency"], as_dict=True)
		if not list_info or not cint(list_info.buying) or not cint(list_info.enabled) or list_info.currency != frappe.get_cached_value("Company", company, "default_currency"):
			frappe.throw(_("Select an enabled buying Price List in the company currency before requesting this rate."))
		# General fallback is read-only for this supplier: approval creates its supplier price.
		changes.append({"index": index, "item_code": code, "rate": proposed, "reason": reason,
			"price_list": price_list, "old_po_rate": flt(old.rate) if old else active_rate,
			"old_active_rate": active_rate, "old_active_supplier": active.get("supplier") or "",
			"old_active_item_price": active.get("item_price") or ""})
		row["rate"] = flt(old.rate) if old else (active_rate if active_rate is not None else 0)
	return changes


def validate_purchase_order(doc, method=None):
	if not cint(doc.get("controlled_procurement")):
		return
	if getattr(frappe.flags, "controlled_po_price_apply", False):
		return
	previous = doc.get_doc_before_save() if not doc.is_new() else None
	if previous and previous.get("custom_po_price_status") in {"Pending Accounts", "Pending CEO"} and not getattr(doc.flags, "lpo_workflow_transition", False):
		frappe.throw(_("This Purchase Order is locked pending CEO price approval."), frappe.PermissionError)
	if getattr(doc.flags, "controlled_procurement_api", False):
		return  # Workspace endpoints already staged and validated the proposed rates.
	for index, row in enumerate(doc.items):
		if flt(row.rate) <= 0:
			frappe.throw(_("Controlled Purchase Order rates must be positive. Use Procurement to request a new buying price."))
		old = previous.items[index] if previous and index < len(previous.items) else None
		if old and old.name == row.name and flt(old.rate) == flt(row.rate):
			continue
		active = _current(row.item_code, doc.supplier, doc.company, doc.transaction_date)
		if active.get("rate") is None or flt(active.rate) != flt(row.rate):
			frappe.throw(_("A changed controlled buying rate requires a CEO price proposal in Procurement."), frappe.PermissionError)


def before_submit_purchase_order(doc, method=None):
	if cint(doc.get("controlled_procurement")) and doc.get("custom_po_price_status") in {"Pending Accounts", "Pending CEO"}:
		frappe.throw(_("This Purchase Order is pending CEO price approval and cannot be submitted."), frappe.PermissionError)
	if cint(doc.get("controlled_procurement")) and any(flt(row.rate) <= 0 for row in doc.items):
		frappe.throw(_("Every controlled Purchase Order item needs a positive approved rate."))


def validate_purchase_order_item(doc, method=None):
	"""Cover ERPNext's direct submitted Update Items endpoint (it saves children first)."""
	if getattr(frappe.flags, "controlled_po_price_apply", False) or not doc.get("parent"):
		return
	if not frappe.db.exists("Purchase Order", doc.parent):
		return
	po = frappe.db.get_value("Purchase Order", doc.parent,
		["controlled_procurement", "company", "supplier", "transaction_date", "custom_po_price_status", "docstatus"], as_dict=True)
	if not po or not cint(po.controlled_procurement):
		return
	if po.docstatus != 1:
		return  # Draft parent validation handles rate changes; staged drafts may have a zero placeholder.
	if po.custom_po_price_status in {"Pending Accounts", "Pending CEO"}:
		frappe.throw(_("This Purchase Order is locked pending CEO price approval."), frappe.PermissionError)
	previous = doc.get_doc_before_save() if not doc.is_new() else None
	if previous and flt(previous.rate) == flt(doc.rate):
		return
	if flt(doc.rate) <= 0:
		frappe.throw(_("Controlled Purchase Order rates must be positive."))
	active = _current(doc.item_code, po.supplier, po.company, po.transaction_date)
	if active.get("rate") is None or flt(active.rate) != flt(doc.rate):
		frappe.throw(_("A changed controlled buying rate requires CEO approval through Procurement."), frappe.PermissionError)


def stage(doc, changes, submitted_items=None):
	if not changes:
		return None
	if doc.get("custom_po_price_status") in {"Pending Accounts", "Pending CEO"}:
		frappe.throw(_("This Purchase Order already has a pending price proposal."))
	identities = {}
	for change in changes:
		identity = (change["item_code"], change["price_list"])
		if identity in identities and identities[identity]["rate"] != change["rate"]:
			frappe.throw(_("The same item and price list cannot have two proposed rates in one order."))
		identities[identity] = change
	requests = []
	for change in sorted(identities.values(), key=lambda row: (row["item_code"], row["price_list"])):
		frappe.db.sql("select name from `tabItem` where name = %s for update", change["item_code"])
		uom = frappe.db.get_value("Item", change["item_code"], "stock_uom")
		key = prices._identity(change["item_code"], doc.supplier, change["price_list"], uom)
		if frappe.db.exists("Controlled Buying Price Request", {"active_identity": key}):
			frappe.throw(_("A buying-price request is already pending for {0} and {1}.").format(change["item_code"], doc.supplier))
		current = prices._price(change["item_code"], doc.supplier, change["price_list"], uom)
		request = frappe.get_doc({
			"doctype": "Controlled Buying Price Request", "company": doc.company,
			"purchase_order": doc.name, "item_code": change["item_code"],
			"supplier": doc.supplier, "price_list": change["price_list"], "uom": uom,
			"currency": doc.currency, "target_item_price": current.name if current else "",
			"target_modified": current.modified if current else None,
			"old_rate": flt(current.price_list_rate) if current else 0,
			"proposed_rate": change["rate"], "reason": change["reason"],
			"requested_by": frappe.session.user, "requested_on": now_datetime(),
			"status": "Pending CEO", "active_identity": key, "notification_status": "Pending",
		})
		prices._save_request(request, insert=True)
		requests.append(request.name)
	proposal = {"requests": requests, "changes": changes, "submitted_items": submitted_items,
		"po_modified": str(doc.modified), "requested_by": frappe.session.user, "requested_on": str(now_datetime())}
	status = "Pending Accounts" if doc.docstatus == 1 and doc.get("custom_lpo_type") == "Manual" else "Pending CEO"
	frappe.db.set_value("Purchase Order", doc.name, {
		"custom_po_price_status": status, "custom_po_price_proposal": json.dumps(proposal),
		"custom_po_price_notification": "Pending", "custom_po_price_notification_error": "",
		"custom_po_price_notified_users": "[]",
	}, update_modified=False)
	if prices.has_explicit_ceo_role() and doc.get("custom_lpo_type") != "Manual":
		approve_po_price(doc.name, "Approved on CEO creation")
		_enqueue_notice(doc.name)
	elif doc.get("custom_lpo_type") != "Manual":
		_enqueue_notice(doc.name)
	return proposal


@frappe.whitelist(methods=["POST"])
def approve_accounts_po_price(name: str) -> dict:
	frappe.db.sql("select name from `tabPurchase Order` where name = %s for update", name)
	doc = frappe.get_doc("Purchase Order", name)
	prices._require_company(doc.company)
	if not any(frappe.db.exists("Has Role", {"parent": frappe.session.user, "parenttype": "User", "role": role})
		for role in ("Accounts User", "Accounts Manager")):
		frappe.throw(_("Only an assigned Accounts user can approve the first Manual LPO price stage."), frappe.PermissionError)
	if doc.docstatus != 1 or doc.get("custom_lpo_type") != "Manual" or doc.custom_po_price_status != "Pending Accounts":
		frappe.throw(_("This Manual LPO price proposal is not awaiting Accounts."))
	frappe.db.set_value("Purchase Order", name, {
		"custom_po_price_status": "Pending CEO",
		"custom_po_price_history": _history(doc, "Accounts approved"),
	}, update_modified=False)
	_enqueue_notice(name)
	return {"name": name, "status": "Pending CEO"}


def _enqueue_notice(name):
	frappe.db.after_commit.add(lambda: frappe.enqueue(
		"construction_management.api.po_price_approvals.deliver_po_price_notice", queue="short", name=name))


def _history(doc, action, comment=""):
	history = json.loads(doc.get("custom_po_price_history") or "[]")
	proposal = json.loads(doc.get("custom_po_price_proposal") or "{}")
	history.append({"action": action, "by": frappe.session.user, "at": str(now_datetime()),
		"comment": comment, "requested_by": proposal.get("requested_by"),
		"changes": proposal.get("changes", []), "requests": proposal.get("requests", [])})
	return json.dumps(history)


def _finish(doc, status, comment=""):
	frappe.db.set_value("Purchase Order", doc.name, {
		"custom_po_price_status": status, "custom_po_price_history": _history(doc, status, comment),
		"custom_po_price_proposal": None,
	}, update_modified=False)
	for name in json.loads(doc.custom_po_price_proposal or "{}").get("requests", []):
		request = frappe.get_doc("Controlled Buying Price Request", name)
		if request.status == "Pending CEO":
			request.status = status
			request.active_identity = None
			request.decided_by = frappe.session.user
			request.decided_on = now_datetime()
			request.decision_comment = comment
			prices._save_request(request)


@frappe.whitelist(methods=["POST"])
def approve_po_price(name: str, comment: str = "") -> dict:
	frappe.db.sql("select name from `tabPurchase Order` where name = %s for update", name)
	doc = frappe.get_doc("Purchase Order", name)
	prices._require_company(doc.company)
	if not prices.has_explicit_ceo_role():
		frappe.throw(_("Only a user explicitly assigned the CEO role can approve PO buying-rate changes."), frappe.PermissionError)
	if doc.custom_po_price_status != "Pending CEO":
		frappe.throw(_("This Purchase Order has no pending price decision."))
	if doc.get("custom_lpo_type") == "Manual" and doc.docstatus == 0 and doc.get("custom_lpo_approval_status") != "Pending CEO":
		frappe.throw(_("Manual LPO price approval follows Accounts approval."))
	if doc.get("custom_lpo_type") == "Manual" and doc.docstatus == 0 and not getattr(frappe.flags, "manual_lpo_ceo_approval", False):
		frappe.throw(_("Approve the Manual LPO in its Accounts → CEO workflow to apply this price proposal."))
	proposal = json.loads(doc.custom_po_price_proposal)
	if str(doc.modified) != proposal["po_modified"]:
		_finish(doc, "Needs Correction", "The Purchase Order changed during approval. Submit a new proposal.")
		return {"name": name, "status": "Needs Correction"}
	requests = [frappe.get_doc("Controlled Buying Price Request", request_name) for request_name in proposal["requests"]]
	for request in sorted(requests, key=lambda row: row.item_code):
		frappe.db.sql("select name from `tabItem` where name = %s for update", request.item_code)
		current = prices._price(request.item_code, request.supplier, request.price_list, request.uom)
		if ((current.name if current else "") != (request.target_item_price or "")
			or (current and (flt(current.price_list_rate) != flt(request.old_rate) or str(current.modified) != str(request.target_modified)))):
			_finish(doc, "Needs Correction", "An active buying price changed during approval. Submit a new proposal.")
			return {"name": name, "status": "Needs Correction"}
	frappe.db.savepoint("po_price_approval")
	try:
		for request in requests:
			prices._approve(request, comment)
			if request.status != "Approved":
				raise frappe.ValidationError("A buying price changed during approval.")
		frappe.flags.controlled_po_price_apply = True
		try:
			if proposal.get("submitted_items") is not None:
				from erpnext.accounts.services.child_item_update import update_child_qty_rate
				update_child_qty_rate("Purchase Order", json.dumps(proposal["submitted_items"]), name)
			else:
				doc.reload()
				for change in proposal["changes"]:
					doc.items[change["index"]].rate = change["rate"]
				doc.flags.controlled_procurement_api = True
				doc.flags.lpo_workflow_transition = True
				doc.save(ignore_permissions=True)
		finally:
			frappe.flags.controlled_po_price_apply = False
		frappe.db.set_value("Purchase Order", name, {
			"custom_po_price_status": "Approved", "custom_po_price_proposal": None,
			"custom_po_price_history": _history(doc, "Approved", comment),
		}, update_modified=False)
	except Exception as exc:
		frappe.db.rollback(save_point="po_price_approval")
		doc.reload()
		_finish(doc, "Needs Correction", str(exc)[:500])
		return {"name": name, "status": "Needs Correction", "reason": str(exc)}
	return {"name": name, "status": "Approved"}


@frappe.whitelist(methods=["POST"])
def reject_po_price(name: str, comment: str) -> dict:
	frappe.db.sql("select name from `tabPurchase Order` where name = %s for update", name)
	doc = frappe.get_doc("Purchase Order", name)
	prices._require_company(doc.company)
	if not prices.has_explicit_ceo_role():
		frappe.throw(_("Only an explicitly assigned CEO can reject PO buying-rate changes."), frappe.PermissionError)
	if doc.custom_po_price_status != "Pending CEO" or not (comment or "").strip():
		frappe.throw(_("A pending proposal and rejection reason are required."))
	_finish(doc, "Rejected", comment.strip())
	if doc.get("custom_lpo_type") == "Manual" and doc.get("custom_lpo_approval_status") == "Pending CEO":
		from construction_management.api import lpo_workflow
		doc.reload()
		lpo_workflow.transition(doc, "Needs Correction", "CEO rejected buying price", comment.strip())
	return {"name": name, "status": "Rejected"}


@frappe.whitelist(methods=["POST"])
def reject_accounts_po_price(name: str, comment: str) -> dict:
	frappe.db.sql("select name from `tabPurchase Order` where name = %s for update", name)
	doc = frappe.get_doc("Purchase Order", name)
	prices._require_company(doc.company)
	if not any(frappe.db.exists("Has Role", {"parent": frappe.session.user, "parenttype": "User", "role": role})
		for role in ("Accounts User", "Accounts Manager")):
		frappe.throw(_("Only an assigned Accounts user can reject this Manual LPO price stage."), frappe.PermissionError)
	if doc.custom_po_price_status != "Pending Accounts" or not (comment or "").strip():
		frappe.throw(_("A pending Accounts proposal and rejection reason are required."))
	_finish(doc, "Rejected", comment.strip())
	return {"name": name, "status": "Rejected"}


@frappe.whitelist(methods=["GET"])
def get_po_price_requests() -> list[dict]:
	api = _procurement()
	api._require(prices.REQUEST_ROLES)
	company = api._document_company(None)
	return frappe.get_all("Purchase Order", filters={"company": company, "controlled_procurement": 1,
		"custom_po_price_status": ["in", ["Pending Accounts", "Pending CEO", "Approved", "Rejected", "Needs Correction"]]},
		fields=["name", "docstatus", "company", "supplier", "currency", "custom_lpo_type", "custom_lpo_approval_status", "custom_po_price_status", "custom_po_price_proposal",
			"custom_po_price_history", "custom_po_price_notification", "custom_po_price_notification_error", "owner", "modified"],
		order_by="modified desc", limit_page_length=100)


def deliver_po_price_notice(name: str) -> None:
	doc = frappe.get_doc("Purchase Order", name)
	if doc.custom_po_price_status not in ("Pending CEO", "Approved"):
		return
	proposal = json.loads(doc.get("custom_po_price_proposal") or "{}")
	history = json.loads(doc.get("custom_po_price_history") or "[]")
	requester = proposal.get("requested_by") or (history[-1].get("requested_by") if history else None) or doc.owner
	recipients = prices._ceo_users(doc.company, requester if doc.custom_po_price_status == "Approved" else "")
	delivered = set(json.loads(doc.get("custom_po_price_notified_users") or "[]"))
	errors = []
	if not recipients and doc.custom_po_price_status == "Pending CEO":
		errors.append("No enabled Raven CEO has access to this company.")
	for user in recipients:
		if user in delivered:
			continue
		try:
			bot = frappe.get_doc("Raven Bot", "procurement bot")
			verb = "approved" if doc.custom_po_price_status == "Approved" else "requests CEO approval for"
			message = bot.send_direct_message(user,
				text=prices.price_notice_html(
					f"{requester} {verb} buying-rate changes on Purchase Order {name} ({doc.company}).\n"
					+ _notice_lines(proposal.get("changes") or (history[-1].get("changes", []) if history else []), doc.supplier, doc.currency),
					name))
			if not message:
				raise RuntimeError("Raven returned no message")
			delivered.add(user)
			frappe.db.set_value("Purchase Order", name, "custom_po_price_notified_users", json.dumps(sorted(delivered)), update_modified=False)
			frappe.db.commit()
		except Exception as exc:
			frappe.db.rollback()
			errors.append(f"{user}: {exc}")
	frappe.db.set_value("Purchase Order", name, {
		"custom_po_price_notification": "Failed" if errors else "Delivered",
		"custom_po_price_notification_error": "\n".join(errors),
	}, update_modified=False)


def _notice_lines(changes, supplier, currency):
	lines = []
	for change in changes:
		old = change.get("old_active_rate", change.get("old_po_rate"))
		if supplier and change.get("old_active_supplier") == "" and change.get("old_active_item_price"):
			old_label = f"New supplier price (general fallback {currency} {old})"
		else:
			old_label = f"{currency} {old}" if old is not None else "New price"
		lines.append(f"{change['item_code']} · {supplier or 'General'} · {change['price_list']}: "
			f"{old_label} → {currency} {change['rate']}. Reason: {change['reason']}")
	return "\n".join(lines)


@frappe.whitelist(methods=["POST"])
def retry_po_price_notice(name: str) -> dict:
	doc = frappe.get_doc("Purchase Order", name)
	prices._require_company(doc.company)
	proposal = json.loads(doc.get("custom_po_price_proposal") or "{}")
	history = json.loads(doc.get("custom_po_price_history") or "[]")
	requester = proposal.get("requested_by") or (history[-1].get("requested_by") if history else None) or doc.owner
	if frappe.session.user != requester and not prices.has_explicit_ceo_role():
		frappe.throw(_("Only the requester or a CEO can retry this notice."), frappe.PermissionError)
	if doc.custom_po_price_status not in ("Pending CEO", "Approved"):
		frappe.throw(_("This proposal no longer needs a Raven notice."))
	_enqueue_notice(name)
	return {"name": name, "notification_status": "Retry queued"}
