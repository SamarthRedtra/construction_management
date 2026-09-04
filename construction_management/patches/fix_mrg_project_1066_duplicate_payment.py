# Copyright (c) 2026, Construction Management
# License: MIT

"""Remove the duplicate project 1066 receipt and reconcile the original payment."""

from __future__ import annotations

import frappe
from erpnext.accounts.utils import reconcile_against_document
from frappe.utils import flt, getdate

COMPANY = "M R G INSULATION WORKS L.L.C"
PARTY = "Plus Palace General Contracting L.L.C"
PROJECT = "1066"
INVOICE = "ACC-SINV-2026-00016"
ORIGINAL_PAYMENT = "MRG-PE-00008"
DUPLICATE_PAYMENT = "MRG-PE-00009"
RECEIVABLE_ACCOUNT = "Debtors - MRG"
AMOUNT = 17850.0
ADVANCE_AMOUNT = 17000.0


def execute() -> None:
	if not all(
		frappe.db.exists(doctype, name)
		for doctype, name in (
			("Sales Invoice", INVOICE),
			("Payment Entry", ORIGINAL_PAYMENT),
			("Payment Entry", DUPLICATE_PAYMENT),
		)
	):
		return

	original = frappe.get_doc("Payment Entry", ORIGINAL_PAYMENT)
	duplicate = frappe.get_doc("Payment Entry", DUPLICATE_PAYMENT)
	invoice = frappe.get_doc("Sales Invoice", INVOICE)
	_validate_documents(original, duplicate, invoice)

	if duplicate.docstatus == 1:
		duplicate.flags.ignore_permissions = True
		duplicate.cancel()
	_cancel_duplicate_advance_records()

	if not frappe.db.exists(
		"Payment Entry Reference",
		{"parent": ORIGINAL_PAYMENT, "reference_doctype": "Sales Invoice", "reference_name": INVOICE},
	):
		_reconcile_original_payment()

	_validate_result()


def _cancel_duplicate_advance_records() -> None:
	for name in frappe.get_all(
		"BOQ Advance Payment",
		filters={"project": PROJECT, "reference": DUPLICATE_PAYMENT, "docstatus": 1},
		pluck="name",
	):
		advance = frappe.get_doc("BOQ Advance Payment", name)
		if flt(advance.amount) != ADVANCE_AMOUNT or advance.linked_invoice != INVOICE:
			frappe.throw(f"BOQ Advance Payment {name} no longer matches the duplicate receipt")
		advance.flags.ignore_permissions = True
		advance.cancel()


def _validate_documents(original, duplicate, invoice) -> None:
	for payment in (original, duplicate):
		if (
			payment.company != COMPANY
			or payment.party_type != "Customer"
			or payment.party != PARTY
			or payment.project != PROJECT
			or payment.paid_from != RECEIVABLE_ACCOUNT
			or flt(payment.paid_amount) != AMOUNT
			or payment.reference_no != "1518"
			or getdate(payment.reference_date) != getdate("2024-09-04")
		):
			frappe.throw(f"Payment Entry {payment.name} no longer matches the project 1066 correction")

	if original.docstatus != 1 or getdate(original.posting_date) != getdate("2024-09-04"):
		frappe.throw(f"Payment Entry {ORIGINAL_PAYMENT} must be the submitted 2024 receipt")
	if duplicate.docstatus not in (1, 2) or getdate(duplicate.posting_date) != getdate("2025-09-04"):
		frappe.throw(f"Payment Entry {DUPLICATE_PAYMENT} must be the duplicate 2025 receipt")
	if (
		invoice.docstatus != 1
		or invoice.company != COMPANY
		or invoice.customer != PARTY
		or invoice.project != PROJECT
		or invoice.debit_to != RECEIVABLE_ACCOUNT
		or flt(invoice.grand_total) != AMOUNT
	):
		frappe.throw(f"Sales Invoice {INVOICE} no longer matches the project 1066 correction")


def _reconcile_original_payment() -> None:
	unallocated_amount = flt(frappe.db.get_value("Payment Entry", ORIGINAL_PAYMENT, "unallocated_amount"))
	outstanding_amount = flt(frappe.db.get_value("Sales Invoice", INVOICE, "outstanding_amount"))
	if unallocated_amount != AMOUNT or outstanding_amount != AMOUNT:
		frappe.throw(
			f"Expected AED {AMOUNT:g} unallocated on {ORIGINAL_PAYMENT} and outstanding on {INVOICE}"
		)

	reconcile_against_document([
		frappe._dict(
			voucher_type="Payment Entry",
			voucher_no=ORIGINAL_PAYMENT,
			voucher_detail_no=None,
			against_voucher_type="Sales Invoice",
			against_voucher=INVOICE,
			account=RECEIVABLE_ACCOUNT,
			party_type="Customer",
			party=PARTY,
			is_advance=1,
			dr_or_cr="credit_in_account_currency",
			unreconciled_amount=AMOUNT,
			unadjusted_amount=AMOUNT,
			allocated_amount=AMOUNT,
			grand_total=AMOUNT,
			outstanding_amount=AMOUNT,
			exchange_rate=1,
			difference_amount=0,
			difference_posting_date=None,
			dimensions={},
		)
	])


def _validate_result() -> None:
	allocated_amount = frappe.db.get_value(
		"Payment Entry Reference",
		{"parent": ORIGINAL_PAYMENT, "reference_doctype": "Sales Invoice", "reference_name": INVOICE},
		"allocated_amount",
	)
	if (
		frappe.db.get_value("Payment Entry", DUPLICATE_PAYMENT, "docstatus") != 2
		or frappe.db.exists(
			"BOQ Advance Payment",
			{"project": PROJECT, "reference": DUPLICATE_PAYMENT, "docstatus": 1},
		)
		or flt(allocated_amount) != AMOUNT
		or flt(frappe.db.get_value("Payment Entry", ORIGINAL_PAYMENT, "unallocated_amount")) != 0
		or flt(frappe.db.get_value("Sales Invoice", INVOICE, "outstanding_amount")) != 0
	):
		frappe.throw("Project 1066 payment correction did not reach the expected state")
