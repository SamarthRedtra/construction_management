# Copyright (c) 2026, Construction Management
# License: MIT

"""Relax Account permission hard-fail when resolving party accounts.

ERPNext's get_party_account throws if the user cannot select/read the exact
Creditors/Receivable Account row. Users who can open Purchase Invoice / Supplier
(and are allowed for that Company) still need party-account resolution for
onload dashboards and credit_to defaults.
"""

from __future__ import annotations

import frappe
from frappe import _, scrub
from frappe.utils import cint

_PATCHED = False
_PATCH_VERSION = 3
_ORIGINAL_GET_PARTY_ACCOUNT = None


def install_party_account_perm_patch():
	"""Idempotent monkeypatch of erpnext.accounts.party.get_party_account."""
	global _PATCHED, _ORIGINAL_GET_PARTY_ACCOUNT

	import erpnext.accounts.party as party_mod

	current = party_mod.get_party_account
	if getattr(current, "_cm_patch_version", None) == _PATCH_VERSION:
		_PATCHED = True
		return

	# Keep a stable reference to ERPNext's original implementation
	if _ORIGINAL_GET_PARTY_ACCOUNT is None:
		if getattr(current, "_cm_original", None):
			_ORIGINAL_GET_PARTY_ACCOUNT = current._cm_original
		elif not getattr(current, "_cm_soft_account_perm", False):
			_ORIGINAL_GET_PARTY_ACCOUNT = current
		else:
			# Already wrapped by an older patch without _cm_original — cannot unwrap safely
			_ORIGINAL_GET_PARTY_ACCOUNT = current

	original = _ORIGINAL_GET_PARTY_ACCOUNT

	@frappe.whitelist()
	def get_party_account(
		party_type: str,
		party: str | None = None,
		company: str | None = None,
		include_advance: bool = False,
	):
		include_advance = cint(include_advance)
		return _get_party_account_soft(
			original,
			party_type=party_type,
			party=party,
			company=company,
			include_advance=include_advance,
		)

	get_party_account._cm_soft_account_perm = True
	get_party_account._cm_patch_version = _PATCH_VERSION
	get_party_account._cm_original = original
	party_mod.get_party_account = get_party_account
	_PATCHED = True


def _clear_permission_messages():
	"""Drop the PermissionError msgprint queued by ERPNext before our soft fallback."""
	try:
		frappe.clear_messages()
	except Exception:
		pass
	if hasattr(frappe.local, "message_log"):
		frappe.local.message_log = []


def _user_allowed_for_company(company: str | None) -> bool:
	if not company:
		return False
	user = frappe.session.user
	if user == "Administrator":
		return True
	allowed = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": "Company"},
		pluck="for_value",
	)
	if not allowed:
		return True
	return company in allowed


def _soft_account_perm_ok(account: str) -> bool:
	"""True if user may use this account for party resolution."""
	if not account:
		return True

	from frappe.permissions import has_permission

	ptype = "select" if frappe.only_has_select_perm("Account") else "read"
	if has_permission("Account", ptype, account, print_logs=False):
		return True

	company = frappe.get_cached_value("Account", account, "company")
	if company and _user_allowed_for_company(company):
		return True

	if has_permission("Account", ptype, print_logs=False) and (
		not company or _user_allowed_for_company(company)
	):
		return True

	if has_permission("Purchase Invoice", "read", print_logs=False) and (
		not company or _user_allowed_for_company(company)
	):
		return True

	if has_permission("Sales Invoice", "read", print_logs=False) and (
		not company or _user_allowed_for_company(company)
	):
		return True

	if has_permission("Supplier", "read", print_logs=False) and (
		not company or _user_allowed_for_company(company)
	):
		return True

	return False


def _empty_party_account(include_advance: bool):
	return [None, None] if include_advance else None


def _get_party_account_soft(original, *, party_type, party, company, include_advance):
	"""Run ERPNext get_party_account; on Account PermissionError, soft-resolve."""
	try:
		return original(party_type, party, company, include_advance)
	except frappe.PermissionError:
		_clear_permission_messages()

		# Supplier/Customer dashboard probes every company — skip ones the user can't access
		if company and not _user_allowed_for_company(company):
			return _empty_party_account(include_advance)

		account = _resolve_party_account(party_type, party, company)

		if include_advance and party and party_type in ("Customer", "Supplier", "Student"):
			from erpnext.accounts.party import get_party_advance_account

			advance_account = None
			try:
				advance_account = get_party_advance_account(party_type, party, company)
			except frappe.PermissionError:
				_clear_permission_messages()
				advance_account = None

			if account and not _soft_account_perm_ok(account):
				account = None
			if advance_account and not _soft_account_perm_ok(advance_account):
				advance_account = None
			if advance_account:
				return [account, advance_account]
			return [account]

		if account and not _soft_account_perm_ok(account):
			return _empty_party_account(include_advance)
		return account


def _resolve_party_account(party_type, party, company):
	"""Mirror ERPNext account resolution without permission checks."""
	from erpnext.accounts.party import get_party_gle_account, get_party_gle_currency

	if not party_type:
		frappe.throw(_("Party Type is mandatory"))
	if not company:
		frappe.throw(_("Please select a Company"))

	if not party and party_type in ["Customer", "Supplier"]:
		default_account_name = (
			"default_receivable_account" if party_type == "Customer" else "default_payable_account"
		)
		return frappe.get_cached_value("Company", company, default_account_name)

	account = frappe.db.get_value(
		"Party Account", {"parenttype": party_type, "parent": party, "company": company}, "account"
	)

	if not account and party_type in ["Customer", "Supplier"]:
		party_group_doctype = "Customer Group" if party_type == "Customer" else "Supplier Group"
		group = frappe.get_cached_value(party_type, party, scrub(party_group_doctype))
		account = frappe.db.get_value(
			"Party Account",
			{"parenttype": party_group_doctype, "parent": group, "company": company},
			"account",
		)

	if not account and party_type in ["Customer", "Supplier"]:
		default_account_name = (
			"default_receivable_account" if party_type == "Customer" else "default_payable_account"
		)
		account = frappe.get_cached_value("Company", company, default_account_name)

	existing_gle_currency = get_party_gle_currency(party_type, party, company)
	if existing_gle_currency:
		account_currency = None
		if account:
			account_currency = frappe.get_cached_value("Account", account, "account_currency")
		if (account and account_currency != existing_gle_currency) or not account:
			account = get_party_gle_account(party_type, party, company)

	if not account:
		account_type = frappe.get_cached_value("Party Type", party_type, "account_type")
		if account_type:
			default_account_name = "default_" + account_type.lower() + "_account"
			account = frappe.get_cached_value("Company", company, default_account_name)

	return account


@frappe.whitelist()
def get_party_account(
	party_type: str,
	party: str | None = None,
	company: str | None = None,
	include_advance: bool = False,
):
	install_party_account_perm_patch()
	import erpnext.accounts.party as party_mod

	return party_mod.get_party_account(party_type, party, company, include_advance)
