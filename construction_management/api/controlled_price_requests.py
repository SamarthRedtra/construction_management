"""CEO-gated changes to shared buying prices for controlled catalog items."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
from html import escape
import json
import math
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime, today


PRICE_FIELDS = ("item_code", "price_list", "supplier", "uom", "price_list_rate", "currency", "valid_from", "valid_upto", "buying", "selling", "custom_controlled_price_request", "custom_controlled_catalog_request")
REQUEST_ROLES = {"Purchase User", "Purchase Manager", "Accounts User", "Accounts Manager", "CEO", "System Manager"}


def price_request_url(name: str) -> str:
	return f"/procurement/catalog/prices?request={quote(name, safe='')}"


def price_notice_html(message: str, name: str) -> str:
	return (f"{escape(message).replace(chr(10), '<br>')}<br>"
		f'<a href="{price_request_url(name)}">Open price request and history</a>')


def has_explicit_ceo_role(user: str | None = None) -> bool:
	"""Administrator's implicit all-roles access must not count as a CEO decision."""
	return bool(frappe.db.exists("Has Role", {
		"parent": user or frappe.session.user, "parenttype": "User", "role": "CEO",
	}))


def price_request_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
	if ptype != "read":
		return False
	user = user or frappe.session.user
	if not REQUEST_ROLES.intersection(frappe.get_roles(user)):
		return False
	companies = frappe.get_all("User Permission", filters={"user": user, "allow": "Company"}, pluck="for_value")
	return not companies or doc.company in companies


def _save_request(doc, insert: bool = False) -> None:
	doc.flags.controlled_price_request_api = True
	if insert:
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)


def _notification_event(doc, recipient: str, status: str, error: str = "") -> None:
	history = json.loads(doc.notification_history or "[]")
	history.append({"recipient": recipient, "status": status, "at": str(now_datetime()), "error": error})
	doc.notification_history = json.dumps(history)


def _procurement():
	from construction_management.api import controlled_procurement
	return controlled_procurement


def _require_company(company: str) -> None:
	api = _procurement()
	api._require(REQUEST_ROLES)
	if not company or company not in api._allowed_companies():
		frappe.throw(_("You do not have access to company {0}.").format(company), frappe.PermissionError)


def _is_controlled(item_code: str) -> bool:
	return bool(item_code and cint(frappe.db.get_value("Item", item_code, "controlled_procurement_catalog")))


def _is_buying(doc) -> bool:
	return bool(cint(doc.get("buying")) or (doc.get("price_list") and cint(frappe.db.get_value("Price List", doc.price_list, "buying"))))


def guard_item_price(doc, method=None) -> None:
	"""Document hooks reject direct writes, including a change of item/price list identity."""
	if getattr(frappe.flags, "controlled_price_write", None):
		return
	old = doc.get_doc_before_save() if not doc.is_new() else None
	controlled = (_is_controlled(doc.get("item_code")) and _is_buying(doc)) or (
		old and _is_controlled(old.get("item_code")) and _is_buying(old)
	)
	if controlled and (not old or any((doc.get(field) or "") != (old.get(field) or "") for field in PRICE_FIELDS)):
		frappe.throw(_("Controlled buying prices can only be changed through Procurement → Request price change."), frappe.PermissionError)


def guard_item_price_delete(doc, method=None) -> None:
	if _is_controlled(doc.get("item_code")) and _is_buying(doc) and not getattr(frappe.flags, "controlled_price_write", None):
		frappe.throw(_("Controlled buying prices cannot be deleted directly. Submit a Procurement price request."), frappe.PermissionError)


@contextmanager
def approved_price_write(source: str):
	"""Server-only scope; callers must have already reached an audited CEO decision."""
	previous = getattr(frappe.flags, "controlled_price_write", None)
	frappe.flags.controlled_price_write = source
	try:
		yield
	finally:
		frappe.flags.controlled_price_write = previous


def _identity(item_code: str, supplier: str, price_list: str, uom: str) -> str:
	return hashlib.sha256(json.dumps([item_code, supplier or "", price_list, uom or "Nos"]).encode()).hexdigest()


def _price(item_code: str, supplier: str, price_list: str, uom: str):
	rows = frappe.db.sql("""select name, price_list_rate, modified from `tabItem Price`
		where item_code = %(item)s and ifnull(supplier, '') = %(supplier)s
		and price_list = %(price_list)s and (ifnull(uom, '') = '' or uom = %(uom)s) and buying = 1
		and (valid_from is null or valid_from <= %(date)s)
		and (valid_upto is null or valid_upto >= %(date)s)
		order by (uom = %(uom)s) desc, valid_from desc, creation desc limit 1""", {
			"item": item_code, "supplier": supplier or "", "price_list": price_list, "uom": uom, "date": today(),
		}, as_dict=True)
	return rows[0] if rows else None


def _ceo_users(company: str, exclude: str = "") -> list[str]:
	users = frappe.get_all("Has Role", filters={"role": "CEO", "parenttype": "User"}, pluck="parent", limit_page_length=0)
	eligible = []
	for user in sorted(set(users)):
		if user == exclude or not frappe.db.exists("User", {"name": user, "enabled": 1}):
			continue
		if not frappe.db.exists("Raven User", {"user": user, "enabled": 1}):
			continue
		permissions = frappe.get_all("User Permission", filters={"user": user, "allow": "Company"}, pluck="for_value")
		if not permissions or company in permissions:
			eligible.append(user)
	return eligible


@frappe.whitelist(methods=["GET"])
def get_price_context(item_code: str, company: str = "", supplier: str = "", price_list: str = "Standard Buying") -> dict:
	company = company or _procurement()._active_company()
	_require_company(company)
	_procurement()._catalog_item(item_code)
	if supplier and not _procurement()._item_has_supplier(item_code, supplier):
		frappe.throw(_("Supplier is not linked to this item."))
	list_info = frappe.db.get_value("Price List", price_list, ["buying", "enabled", "currency"], as_dict=True)
	if not list_info or not cint(list_info.buying) or not cint(list_info.enabled):
		frappe.throw(_("Select an enabled buying Price List."))
	if list_info.currency != frappe.get_cached_value("Company", company, "default_currency"):
		frappe.throw(_("The buying Price List currency must match the company currency."))
	current = _price(item_code, supplier, price_list, "Nos")
	fallback = _price(item_code, "", price_list, "Nos") if supplier and not current else None
	return {
		"item_code": item_code, "supplier": supplier, "price_list": price_list,
		"item_price": current.name if current else "",
		"rate": flt(current.price_list_rate) if current else None,
		"fallback_rate": flt(fallback.price_list_rate) if fallback else None,
		"fallback_item_price": fallback.name if fallback else "",
		"currency": list_info.currency,
		"suppliers": frappe.get_all("Item Supplier", filters={"parent": item_code, "parenttype": "Item"}, pluck="supplier"),
	}


def _enqueue_notice(name: str) -> None:
	frappe.db.after_commit.add(lambda: frappe.enqueue(
		"construction_management.api.controlled_price_requests.deliver_price_notice",
		queue="short", request_name=name,
	))


def _enqueue_catalog_notice(name: str) -> None:
	frappe.db.after_commit.add(lambda: frappe.enqueue(
		"construction_management.api.controlled_price_requests.deliver_catalog_notice",
		queue="short", request_name=name,
	))


@frappe.whitelist(methods=["POST"])
def request_price_change(data: str | dict) -> dict:
	data = frappe.parse_json(data) if isinstance(data, str) else (data or {})
	company = data.get("company") or _procurement()._active_company()
	_require_company(company)
	item_code = (data.get("item_code") or "").strip()
	_procurement()._catalog_item(item_code)
	if frappe.db.get_value("Item", item_code, "disabled"):
		frappe.throw(_("The catalog item is disabled."))
	supplier = (data.get("supplier") or "").strip()
	if supplier and not _procurement()._item_has_supplier(item_code, supplier):
		frappe.throw(_("Supplier {0} is not linked to item {1}.").format(supplier, item_code))
	price_list = (data.get("price_list") or "Standard Buying").strip()
	list_info = frappe.db.get_value("Price List", price_list, ["buying", "enabled", "currency"], as_dict=True)
	if not list_info or not cint(list_info.buying) or not cint(list_info.enabled):
		frappe.throw(_("Select an enabled buying Price List."))
	if list_info.currency != frappe.get_cached_value("Company", company, "default_currency"):
		frappe.throw(_("The buying Price List currency must match the company currency."))
	rate = flt(data.get("proposed_rate"))
	if not math.isfinite(rate) or rate <= 0:
		frappe.throw(_("Proposed rate must be greater than zero."))
	reason = (data.get("reason") or "").strip()
	if not reason:
		frappe.throw(_("Enter a reason for the price change."))
	uom = "Nos"
	key = _identity(item_code, supplier, price_list, uom)
	frappe.db.sql("select name from `tabItem` where name = %s for update", item_code)
	if frappe.db.exists("Controlled Buying Price Request", {"active_identity": key}):
		frappe.throw(_("A price request for this item, supplier, and price list is already pending CEO approval."))
	current = _price(item_code, supplier, price_list, uom)
	if current and flt(current.price_list_rate) == rate:
		frappe.throw(_("The proposed rate is already active."))
	actor_is_ceo = has_explicit_ceo_role()
	doc = frappe.get_doc({
		"doctype": "Controlled Buying Price Request", "company": company,
		"item_code": item_code, "supplier": supplier, "price_list": price_list,
		"uom": uom, "currency": list_info.currency,
		"target_item_price": current.name if current else "",
		"target_modified": current.modified if current else None,
		"old_rate": flt(current.price_list_rate) if current else 0,
		"proposed_rate": rate, "reason": reason,
		"requested_by": frappe.session.user, "requested_on": now_datetime(),
		"status": "Pending CEO", "active_identity": key,
		"notification_status": "Pending",
	})
	_save_request(doc, insert=True)
	if actor_is_ceo:
		_approve(doc, "Approved on CEO creation")
	_enqueue_notice(doc.name)
	return {"name": doc.name, "status": doc.status, "notification_status": doc.notification_status}


def _approval_access(doc) -> None:
	_require_company(doc.company)
	if not has_explicit_ceo_role():
		frappe.throw(_("Only a CEO can approve or reject controlled buying prices."), frappe.PermissionError)


def _approve(doc, comment: str = "") -> None:
	if doc.status != "Pending CEO":
		frappe.throw(_("This price request is no longer pending."))
	frappe.db.sql("select name from `tabItem` where name = %s for update", doc.item_code)
	current = _price(doc.item_code, doc.supplier or "", doc.price_list, doc.uom)
	if (current.name if current else "") != (doc.target_item_price or "") or (
		current and (flt(current.price_list_rate) != flt(doc.old_rate) or str(current.modified) != str(doc.target_modified))
	):
		doc.status = "Needs Correction"
		doc.active_identity = None
		doc.decision_comment = "Active buying price changed while approval was pending. Submit a new request."
		doc.decided_by = frappe.session.user
		doc.decided_on = now_datetime()
		_save_request(doc)
		return
	with approved_price_write(doc.name):
		if current:
			price = frappe.get_doc("Item Price", current.name)
			price.price_list_rate = doc.proposed_rate
			price.custom_controlled_price_request = doc.name
			price.save(ignore_permissions=True)
		else:
			price = frappe.get_doc({
				"doctype": "Item Price", "item_code": doc.item_code,
				"supplier": doc.supplier or None, "price_list": doc.price_list,
				"uom": doc.uom, "buying": 1,
				"price_list_rate": doc.proposed_rate,
				"custom_controlled_price_request": doc.name,
			})
			price.insert(ignore_permissions=True)
	doc.result_item_price = price.name
	doc.status = "Approved"
	doc.active_identity = None
	doc.decided_by = frappe.session.user
	doc.decided_on = now_datetime()
	doc.decision_comment = comment or ""
	_save_request(doc)


@frappe.whitelist(methods=["POST"])
def approve_price_change(name: str, comment: str = "") -> dict:
	doc = frappe.get_doc("Controlled Buying Price Request", name)
	_approval_access(doc)
	if doc.get("purchase_order"):
		frappe.throw(_("This price is part of a grouped Purchase Order decision. Approve the Purchase Order proposal instead."))
	frappe.db.sql("select name from `tabControlled Buying Price Request` where name = %s for update", name)
	doc.reload()
	_approve(doc, comment)
	return {"name": doc.name, "status": doc.status, "result_item_price": doc.result_item_price}


@frappe.whitelist(methods=["POST"])
def reject_price_change(name: str, comment: str) -> dict:
	doc = frappe.get_doc("Controlled Buying Price Request", name)
	_approval_access(doc)
	if doc.get("purchase_order"):
		frappe.throw(_("This price is part of a grouped Purchase Order decision. Reject the Purchase Order proposal instead."))
	if not (comment or "").strip():
		frappe.throw(_("A rejection reason is required."))
	frappe.db.sql("select name from `tabControlled Buying Price Request` where name = %s for update", name)
	doc.reload()
	if doc.status != "Pending CEO":
		frappe.throw(_("This price request is no longer pending."))
	doc.status = "Rejected"
	doc.active_identity = None
	doc.decision_comment = comment.strip()
	doc.decided_by = frappe.session.user
	doc.decided_on = now_datetime()
	_save_request(doc)
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["GET"])
def get_price_requests(status: str = "") -> list[dict]:
	api = _procurement()
	api._require(REQUEST_ROLES)
	companies = api._allowed_companies()
	active = api._active_company()
	filters = {"company": active, "purchase_order": ["is", "not set"]} if active in companies else ({"company": ["in", companies], "purchase_order": ["is", "not set"]} if companies else {"name": "__none__"})
	if status:
		filters["status"] = status
	return frappe.get_all("Controlled Buying Price Request", filters=filters,
		fields=["name", "company", "item_code", "supplier", "price_list", "currency", "target_item_price", "old_rate", "proposed_rate", "status", "requested_by", "requested_on", "decided_by", "decided_on", "decision_comment", "notification_status", "notification_error"],
		order_by="creation desc", limit_page_length=200)


@frappe.whitelist(methods=["GET"])
def get_price_request(name: str) -> dict:
	doc = frappe.get_doc("Controlled Buying Price Request", name)
	_require_company(doc.company)
	return doc.as_dict()


def deliver_price_notice(request_name: str) -> None:
	"""One durable receipt per CEO; retries skip recipients already delivered."""
	doc = frappe.get_doc("Controlled Buying Price Request", request_name)
	recipients = _ceo_users(doc.company, doc.requested_by if doc.status == "Approved" else "")
	if not recipients:
		doc.notification_status = "Delivered" if doc.status == "Approved" else "Failed"
		doc.notification_error = "" if doc.status == "Approved" else "No enabled Raven CEO has access to this company."
		_notification_event(doc, "", doc.notification_status, doc.notification_error)
		_save_request(doc)
		return
	delivered = set(json.loads(doc.notified_users or "[]"))
	errors = []
	verb = "approved" if doc.status == "Approved" else "requests approval of"
	old_label = f"{doc.currency} {doc.old_rate}" if doc.target_item_price else "New price"
	if doc.supplier and not doc.target_item_price:
		general = _price(doc.item_code, "", doc.price_list, doc.uom)
		if general:
			old_label = f"New supplier price (general fallback currently {doc.currency} {general.price_list_rate})"
	notice = price_notice_html(
		f"{doc.requested_by} {verb} buying price {doc.item_code} ({doc.supplier or 'General'} · {doc.price_list}): "
		f"{old_label} → {doc.currency} {doc.proposed_rate}. Reason: {doc.reason}.", doc.name)
	for user in recipients:
		frappe.db.sql("select name from `tabControlled Buying Price Request` where name = %s for update", request_name)
		doc.reload()
		delivered = set(json.loads(doc.notified_users or "[]"))
		if user in delivered:
			continue
		try:
			bot = frappe.get_doc("Raven Bot", "procurement bot")
			message = bot.send_direct_message(user,
				text=notice)
			if not message:
				raise RuntimeError("Raven returned no message")
			delivered.add(user)
			doc.notified_users = json.dumps(sorted(delivered))
			_notification_event(doc, user, "Delivered")
			_save_request(doc)
			frappe.db.commit()
		except Exception as exc:
			frappe.db.rollback()
			errors.append(f"{user}: {exc}")
			doc.reload()
			_notification_event(doc, user, "Failed", str(exc))
			_save_request(doc)
			frappe.db.commit()
	doc.notification_status = "Failed" if errors else "Delivered"
	doc.notification_error = "\n".join(errors)
	_save_request(doc)


def deliver_catalog_notice(request_name: str) -> None:
	doc = frappe.get_doc("Controlled Catalog Request", request_name)
	if doc.status != "Pending CEO":
		return
	recipients = _ceo_users(doc.company)
	delivered = set(json.loads(doc.price_notified_users or "[]"))
	errors = []
	if not recipients:
		errors.append("No enabled Raven CEO has access to this company.")
	for user in recipients:
		frappe.db.sql("select name from `tabControlled Catalog Request` where name = %s for update", request_name)
		doc.reload()
		delivered = set(json.loads(doc.price_notified_users or "[]"))
		if user in delivered:
			continue
		try:
			bot = frappe.get_doc("Raven Bot", "procurement bot")
			message = bot.send_direct_message(user,
				text=f"Catalog request {doc.name} has a buying price awaiting CEO approval for {doc.company}.",
				link_doctype=doc.doctype, link_document=doc.name)
			if not message:
				raise RuntimeError("Raven returned no message")
			delivered.add(user)
			doc.price_notified_users = json.dumps(sorted(delivered))
			doc.save(ignore_permissions=True)
			frappe.db.commit()
		except Exception as exc:
			frappe.db.rollback()
			errors.append(f"{user}: {exc}")
	doc.price_notification_status = "Failed" if errors else "Delivered"
	doc.price_notification_error = "\n".join(errors)
	doc.save(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def retry_price_notice(name: str) -> dict:
	doc = frappe.get_doc("Controlled Buying Price Request", name)
	_require_company(doc.company)
	if frappe.session.user != doc.requested_by and not has_explicit_ceo_role() and "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only the requester or an approver can retry notifications."), frappe.PermissionError)
	_enqueue_notice(name)
	return {"name": name, "notification_status": "Retry queued"}


@frappe.whitelist(methods=["POST"])
def retry_catalog_price_notice(name: str) -> dict:
	doc = frappe.get_doc("Controlled Catalog Request", name)
	_require_company(doc.company)
	if frappe.session.user != doc.requested_by and not has_explicit_ceo_role() and "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only the requester or an approver can retry notifications."), frappe.PermissionError)
	if doc.status != "Pending CEO" or not any(flt(row.rate) > 0 for row in doc.items):
		frappe.throw(_("This catalog request has no pending CEO buying-price decision."))
	_enqueue_catalog_notice(name)
	return {"name": name, "notification_status": "Retry queued"}
