# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe.utils import cint, flt

from construction_management.overrides.sales_invoice import (
	create_boq_advance_payment_from_pe_allocation,
)


def before_validate(doc, method=None):
	"""Keep commission payout PE on Sales Commission Payable (not Employee payable)."""
	if doc.payment_type != "Pay" or doc.party_type != "Employee" or not doc.company:
		return

	from construction_management.api.sales_commission_gl import require_commission_posting_accounts

	try:
		payable_account = require_commission_posting_accounts(doc.company)["payable_account"]
	except Exception:
		return

	if doc.paid_to == payable_account:
		doc.custom_is_commission_payout = 1

	if not cint(doc.get("custom_is_commission_payout")):
		return

	doc.paid_to = payable_account
	doc.paid_to_account_currency = frappe.db.get_value(
		"Account", payable_account, "account_currency"
	)
	doc.custom_remarks = 1
	if doc.get("reference_no") and not (doc.remarks or "").startswith(
		"Commission payout for Sales Invoice "
	):
		from construction_management.api.project_commission_data import _commission_payout_remark

		if frappe.db.exists("Sales Invoice", doc.reference_no):
			doc.remarks = _commission_payout_remark(doc.reference_no)


def on_submit(doc, method):
	"""Handle Payment Entry submission to check for linked advance invoices"""
	for ref in doc.get("references"):
		if ref.reference_doctype == "Sales Invoice":
			si = frappe.get_doc("Sales Invoice", ref.reference_name)
			if (
				si.get("custom_is_advanced")
				and si.docstatus == 1
				and flt(ref.allocated_amount) > 0
			):
				create_boq_advance_payment_from_pe_allocation(
					si.name,
					doc.name,
					ref.allocated_amount,
					posting_date=doc.posting_date,
					project=doc.project,
				)

		elif ref.reference_doctype == "Purchase Invoice":
			# Get the latest state of the purchase invoice
			pi = frappe.get_doc("Purchase Invoice", ref.reference_name)

			# Check if it's an advance purchase invoice and if it's now Paid
			if pi.get("custom_is_advance") and pi.status == "Paid" and pi.docstatus == 1:
				from construction_management.overrides.purchase_invoice import (
					_is_subcontractor_purchase,
					create_purchase_advance_payment,
				)
				if _is_subcontractor_purchase(pi):
					create_purchase_advance_payment(pi)

	sync_security_instrument_status(doc, "Issued")
	_sync_security_instrument_outstanding(doc)


def on_cancel(doc, method):
	sync_security_instrument_status(doc, "Cancelled")
	_sync_security_instrument_outstanding(doc)


def _sync_security_instrument_outstanding(doc):
	security_instrument = doc.get("custom_security_instrument")
	if not security_instrument:
		return
	from construction_management.construction_management.doctype.security_instrument.security_instrument import (
		persist_security_instrument_outstanding_balance,
	)

	persist_security_instrument_outstanding_balance(security_instrument)


def sync_security_instrument_status(doc, status):
	security_instrument = doc.get("custom_security_instrument")
	if not security_instrument or not frappe.db.exists("Security Instrument", security_instrument):
		return

	instrument = frappe.get_doc("Security Instrument", security_instrument)
	role = doc.get("custom_security_entry_role") or "Issue"

	if role == "Reclaim":
		if status == "Issued":
			instrument.mark_reclaimed(doc.posting_date)
		elif status == "Cancelled":
			if instrument.payment_entry and frappe.db.exists("Payment Entry", instrument.payment_entry):
				issue_entry = frappe.get_doc("Payment Entry", instrument.payment_entry)
				if issue_entry.docstatus != 2:
					instrument.revert_to_issued()
					return
			instrument.mark_cancelled()
		return

	if status == "Issued":
		instrument.mark_issued()
	elif status == "Cancelled":
		instrument.mark_cancelled()
