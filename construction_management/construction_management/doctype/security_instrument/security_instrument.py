# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


def compute_security_outstanding_balance(amount, status, reclaim_payment_entry) -> float:
	"""Issue amount minus submitted reclaim PE; draft reclaim does not reduce."""
	if status == "Cancelled":
		return 0.0
	base = flt(amount)
	if not reclaim_payment_entry:
		return base
	rpe = frappe.db.get_value(
		"Payment Entry",
		reclaim_payment_entry,
		["docstatus", "paid_amount", "received_amount"],
		as_dict=True,
	)
	if not rpe or rpe.docstatus != 1:
		return base
	reclaimed = max(abs(flt(rpe.paid_amount)), abs(flt(rpe.received_amount)))
	return max(0.0, base - reclaimed)


def _payment_entry_security_type_flags(instrument_type: str) -> dict:
	"""Exactly one Payment Entry security-type flag is set; others cleared."""
	return {
		"custom_is_security_cheque": 1 if instrument_type == "Security Cheque" else 0,
		"custom_is_security_deposit": 1 if instrument_type == "Security Deposit" else 0,
		"custom_is_authorization_fees": 1 if instrument_type == "Authorization Fees" else 0,
	}


def create_issue_payment_entry(instrument) -> "frappe.model.document.Document":
	"""Create a draft issue Payment Entry linked to the given Security Instrument."""
	if instrument.payment_entry:
		frappe.throw(_("Issue Payment Entry already exists for this security instrument"))

	bank_account = instrument.get("bank_account")
	if not bank_account:
		frappe.throw(_("Bank / Cash Account is required to create the issue Payment Entry"))

	payment_entry = frappe.new_doc("Payment Entry")
	payment_entry.payment_type = instrument.payment_type
	payment_entry.party_type = instrument.party_type
	payment_entry.party = instrument.party
	payment_entry.company = instrument.company
	payment_entry.project = instrument.project
	payment_entry.posting_date = instrument.posting_date
	payment_entry.mode_of_payment = instrument.mode_of_payment
	payment_entry.reference_no = instrument.reference_no
	payment_entry.reference_date = instrument.reference_date if instrument.reference_no else None
	payment_entry.remarks = instrument.remarks
	payment_entry.custom_security_instrument = instrument.name
	payment_entry.custom_security_entry_role = "Issue"
	payment_entry.custom_security_redeemed = 0

	pe_meta = frappe.get_meta("Payment Entry")
	if pe_meta.has_field("pdc_cheque_number"):
		payment_entry.pdc_cheque_number = instrument.reference_no
	if pe_meta.has_field("pdc_cheque_date"):
		payment_entry.pdc_cheque_date = instrument.reference_date or instrument.posting_date

	for key, value in _payment_entry_security_type_flags(instrument.instrument_type).items():
		setattr(payment_entry, key, value)

	if instrument.payment_type == "Receive":
		payment_entry.paid_to = bank_account
	else:
		payment_entry.paid_from = bank_account
	payment_entry.paid_amount = flt(instrument.amount)
	payment_entry.received_amount = flt(instrument.amount)

	payment_entry.insert()

	instrument.db_set("payment_entry", payment_entry.name, update_modified=False)
	instrument.payment_entry = payment_entry.name
	return payment_entry


def persist_security_instrument_outstanding_balance(name: str) -> None:
	"""Keep DB field in sync when Payment Entries change without saving Security Instrument."""
	if not name or not frappe.db.exists("Security Instrument", name):
		return
	row = frappe.db.get_value(
		"Security Instrument",
		name,
		["amount", "status", "reclaim_payment_entry"],
		as_dict=True,
	)
	bal = compute_security_outstanding_balance(
		row.get("amount"),
		row.get("status"),
		row.get("reclaim_payment_entry"),
	)
	frappe.db.set_value("Security Instrument", name, "outstanding_balance", bal, update_modified=False)


class SecurityInstrument(Document):
	ALLOWED_INSTRUMENT_TYPES = ("Security Cheque", "Security Deposit", "Authorization Fees")

	def validate(self):
		if self.instrument_type and self.instrument_type not in self.ALLOWED_INSTRUMENT_TYPES:
			frappe.throw(
				_("Instrument Type must be one of: {0}").format(", ".join(self.ALLOWED_INSTRUMENT_TYPES))
			)
		self.validate_amount()
		self.validate_project_context()
		self.validate_reference_details()
		if self._action == "submit":
			self.validate_issue_details()
		self.outstanding_balance = compute_security_outstanding_balance(
			self.amount,
			self.status,
			self.reclaim_payment_entry,
		)

	def validate_issue_details(self):
		if self.payment_entry:
			frappe.throw(_("Issue Payment Entry already exists for this security instrument"))
		if not self.bank_account:
			frappe.throw(_("Bank / Cash Account is required before submitting"))

	def on_submit(self):
		create_issue_payment_entry(self)

	def before_cancel(self):
		for payment_entry_name in filter(None, [self.payment_entry, self.reclaim_payment_entry]):
			if not frappe.db.exists("Payment Entry", payment_entry_name):
				continue
			pe = frappe.get_doc("Payment Entry", payment_entry_name)
			if pe.docstatus == 1:
				pe.flags.ignore_links = True
				pe.cancel()
			elif pe.docstatus == 0:
				frappe.delete_doc("Payment Entry", payment_entry_name, ignore_permissions=True)

	def on_cancel(self):
		self.mark_cancelled()

	def validate_amount(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be greater than zero"))

	def validate_project_context(self):
		if self.bill_no:
			bill_project = frappe.db.get_value("BOQ Bill", self.bill_no, "project")
			if bill_project != self.project:
				frappe.throw(_("BOQ Bill {0} does not belong to Project {1}").format(self.bill_no, self.project))

		if self.boq_item:
			boq_item_values = frappe.db.get_value(
				"BOQ Item",
				self.boq_item,
				["project", "parent_bill"],
			)
			if not boq_item_values:
				frappe.throw(_("BOQ Item {0} does not exist").format(self.boq_item))
			boq_item_project, parent_bill = boq_item_values
			if boq_item_project != self.project:
				frappe.throw(_("BOQ Item {0} does not belong to Project {1}").format(self.boq_item, self.project))
			if self.bill_no and parent_bill != self.bill_no:
				frappe.throw(_("BOQ Item {0} does not belong to BOQ Bill {1}").format(self.boq_item, self.bill_no))

	def validate_reference_details(self):
		if self.instrument_type == "Security Cheque" and not self.reference_no:
			frappe.throw(_("Cheque / Reference No is mandatory for Security Cheque"))
		if self.instrument_type == "Security Cheque" and not self.reference_date:
			frappe.throw(_("Reference Date is mandatory for Security Cheque"))

	def mark_issued(self):
		self.db_set("status", "Issued", update_modified=False)
		self.status = "Issued"
		self._update_payment_entry_reclaim_flags(False, None)

	def mark_reclaimed(self, reclaimed_on=None):
		reclaimed_on = reclaimed_on or today()
		frappe.db.set_value(
			"Security Instrument",
			self.name,
			{
				"status": "Reclaimed",
				"redeemed_on": reclaimed_on,
			},
			update_modified=False,
		)
		self.status = "Reclaimed"
		self.redeemed_on = reclaimed_on
		self._update_payment_entry_reclaim_flags(True, reclaimed_on)

	def revert_to_issued(self):
		frappe.db.set_value(
			"Security Instrument",
			self.name,
			{
				"status": "Issued",
				"redeemed_on": None,
				"reclaim_payment_entry": None,
			},
			update_modified=False,
		)
		self.status = "Issued"
		self.redeemed_on = None
		self.reclaim_payment_entry = None
		self._update_payment_entry_reclaim_flags(False, None)

	def mark_cancelled(self):
		self.db_set("status", "Cancelled", update_modified=False)
		self.status = "Cancelled"

	def _update_payment_entry_reclaim_flags(self, reclaimed, reclaimed_on):
		for payment_entry in filter(None, [self.payment_entry, self.reclaim_payment_entry]):
			frappe.db.set_value(
				"Payment Entry",
				payment_entry,
				{
					"custom_security_redeemed": 1 if reclaimed else 0,
					"custom_security_redeemed_on": reclaimed_on,
				},
				update_modified=False,
			)
