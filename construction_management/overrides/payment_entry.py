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

	if not _is_commission_payout_entry(doc):
		return

	doc.custom_is_commission_payout = 1
	_sync_commission_payout_link(doc)

	if payable_account:
		doc.paid_to = payable_account
		doc.paid_to_account_currency = frappe.db.get_value(
			"Account", payable_account, "account_currency"
		)


def validate(doc, method=None):
	"""Commission payout must carry a Sales Invoice link; normal PEs are unaffected."""
	if not _is_commission_payout_entry(doc):
		return

	_sync_commission_payout_link(doc)

	if not frappe.db.has_column("Payment Entry", "custom_commission_sales_invoice"):
		return
	if not (doc.get("custom_commission_sales_invoice") or "").strip():
		frappe.throw(
			frappe._("Commission Sales Invoice is required for commission payout Payment Entries")
		)


def _is_commission_payout_entry(doc) -> bool:
	"""True only when this PE is explicitly a commission payout, not every employee payment."""
	from construction_management.api.project_commission_data import COMMISSION_PAYOUT_REMARK_PREFIX

	if cint(doc.get("custom_is_commission_payout")):
		return True
	if (doc.get("custom_commission_sales_invoice") or "").strip():
		return True
	if COMMISSION_PAYOUT_REMARK_PREFIX in (doc.get("remarks") or ""):
		return True
	return False


def _sync_commission_payout_link(doc) -> None:
	"""Populate commission invoice link + remarks from any available source."""
	from construction_management.api.project_commission_data import (
		_commission_payout_remark,
		_extract_invoice_from_commission_pe,
	)

	if not frappe.db.has_column("Payment Entry", "custom_commission_sales_invoice"):
		return

	linked_invoice = (doc.get("custom_commission_sales_invoice") or "").strip()
	if not linked_invoice:
		linked_invoice = _extract_invoice_from_commission_pe(doc) or ""

	if linked_invoice:
		doc.custom_commission_sales_invoice = linked_invoice
		doc.remarks = _commission_payout_remark(linked_invoice)
		doc.custom_remarks = 1


def _stamp_commission_payout_invoice_link(doc):
	if not _is_commission_payout_entry(doc):
		return
	if not frappe.db.has_column("Payment Entry", "custom_commission_sales_invoice"):
		return

	from construction_management.api.project_commission_data import _commission_payout_remark

	linked_invoice = (doc.get("custom_commission_sales_invoice") or "").strip()
	if not linked_invoice:
		_sync_commission_payout_link(doc)
		linked_invoice = (doc.get("custom_commission_sales_invoice") or "").strip()

	if linked_invoice and doc.custom_commission_sales_invoice != linked_invoice:
		frappe.db.set_value(
			"Payment Entry",
			doc.name,
			{
				"custom_commission_sales_invoice": linked_invoice,
				"remarks": _commission_payout_remark(linked_invoice),
				"custom_remarks": 1,
				"custom_is_commission_payout": 1,
			},
			update_modified=False,
		)


def on_submit(doc, method):
	"""Handle Payment Entry submission to check for linked advance invoices"""
	_stamp_commission_payout_invoice_link(doc)
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
			pi = frappe.get_doc("Purchase Invoice", ref.reference_name)

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
