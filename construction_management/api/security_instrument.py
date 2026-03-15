# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt, today


@frappe.whitelist()
def create_security_payment_entry(
	project,
	instrument_type,
	amount,
	bank_account,
	payment_type="Receive",
	party_type=None,
	party=None,
	mode_of_payment=None,
	posting_date=None,
	bill_no=None,
	boq_item=None,
	reference_no=None,
	reference_date=None,
	remarks=None,
):
	project_doc = frappe.get_doc("Project", project)
	company = project_doc.company or frappe.defaults.get_user_default("Company")
	if not company:
		frappe.throw(_("Company is required to create a security payment entry"))

	party_type = party_type or ("Customer" if project_doc.customer else None)
	party = party or (project_doc.customer if party_type == "Customer" else None)

	if not party_type or not party:
		frappe.throw(_("Party Type and Party are required"))

	amount = flt(amount)
	if amount <= 0:
		frappe.throw(_("Amount must be greater than zero"))

	posting_date = posting_date or today()
	reference_date = reference_date or posting_date

	instrument = frappe.get_doc(
		{
			"doctype": "Security Instrument",
			"instrument_type": instrument_type,
			"project": project,
			"bill_no": bill_no,
			"boq_item": boq_item,
			"company": company,
			"posting_date": posting_date,
			"payment_type": payment_type,
			"party_type": party_type,
			"party": party,
			"amount": amount,
			"mode_of_payment": mode_of_payment,
			"reference_no": reference_no,
			"reference_date": reference_date,
			"remarks": remarks,
		}
	)
	instrument.insert()

	payment_entry = frappe.new_doc("Payment Entry")
	payment_entry.payment_type = payment_type
	payment_entry.party_type = party_type
	payment_entry.party = party
	payment_entry.company = company
	payment_entry.project = project
	payment_entry.posting_date = posting_date
	payment_entry.mode_of_payment = mode_of_payment
	payment_entry.reference_no = reference_no
	payment_entry.reference_date = reference_date if reference_no else None
	payment_entry.remarks = remarks
	payment_entry.custom_security_instrument = instrument.name
	payment_entry.custom_security_entry_role = "Issue"
	payment_entry.custom_is_security_cheque = 1 if instrument_type == "Security Cheque" else 0
	payment_entry.custom_is_security_deposit = 1 if instrument_type == "Security Deposit" else 0
	payment_entry.custom_security_redeemed = 0

	if payment_type == "Receive":
		payment_entry.paid_to = bank_account
		payment_entry.paid_amount = amount
		payment_entry.received_amount = amount
	else:
		payment_entry.paid_from = bank_account
		payment_entry.paid_amount = amount
		payment_entry.received_amount = amount

	payment_entry.insert()

	instrument.db_set("payment_entry", payment_entry.name, update_modified=False)
	instrument.payment_entry = payment_entry.name

	return {
		"payment_entry": payment_entry.name,
		"security_instrument": instrument.name,
	}


@frappe.whitelist()
def reclaim_security_instrument(name):
	instrument = frappe.get_doc("Security Instrument", name)
	if instrument.status == "Cancelled":
		frappe.throw(_("Cancelled security instruments cannot be reclaimed"))

	if not instrument.payment_entry:
		frappe.throw(_("Issue Payment Entry is required before reclaim"))

	if instrument.reclaim_payment_entry and frappe.db.exists("Payment Entry", instrument.reclaim_payment_entry):
		existing_reclaim_entry = frappe.get_doc("Payment Entry", instrument.reclaim_payment_entry)
		if existing_reclaim_entry.docstatus != 2:
			frappe.throw(_("A reclaim Payment Entry already exists for this security instrument"))

	issue_payment_entry = frappe.get_doc("Payment Entry", instrument.payment_entry)
	reclaim_values = build_reclaim_payment_entry_values(instrument, issue_payment_entry)

	reclaim_payment_entry = frappe.new_doc("Payment Entry")
	reclaim_payment_entry.update(reclaim_values)
	reclaim_payment_entry.insert()

	instrument.db_set("reclaim_payment_entry", reclaim_payment_entry.name, update_modified=False)
	instrument.reclaim_payment_entry = reclaim_payment_entry.name
	instrument.mark_reclaimed(reclaim_payment_entry.posting_date)

	return {
		"name": instrument.name,
		"status": "Reclaimed",
		"payment_entry": reclaim_payment_entry.name,
	}


@frappe.whitelist()
def get_project_security_summary(project):
	rows = frappe.db.sql(
		"""
		SELECT
			instrument_type,
			COUNT(*) AS instrument_count,
			COALESCE(SUM(amount), 0) AS total_amount
		FROM `tabSecurity Instrument`
		WHERE project = %s
		  AND status IN ('Draft', 'Issued')
		GROUP BY instrument_type
		""",
		project,
		as_dict=True,
	)

	summary = {
		"security_cheque_total": 0,
		"security_cheque_count": 0,
		"security_deposit_total": 0,
		"security_deposit_count": 0,
	}

	for row in rows:
		if row.instrument_type == "Security Cheque":
			summary["security_cheque_total"] = flt(row.total_amount)
			summary["security_cheque_count"] = row.instrument_count or 0
		elif row.instrument_type == "Security Deposit":
			summary["security_deposit_total"] = flt(row.total_amount)
			summary["security_deposit_count"] = row.instrument_count or 0

	return summary


@frappe.whitelist()
def get_security_cheque_number_card():
	return _get_security_number_card_response("Security Cheque")


@frappe.whitelist()
def get_security_deposit_number_card():
	return _get_security_number_card_response("Security Deposit")


def build_reclaim_payment_entry_values(instrument, issue_payment_entry):
	issue_payment_type = issue_payment_entry.payment_type
	if issue_payment_type == "Pay":
		reclaim_payment_type = "Receive"
		bank_account = issue_payment_entry.paid_from
		account_field = "paid_to"
	else:
		reclaim_payment_type = "Pay"
		bank_account = issue_payment_entry.paid_to
		account_field = "paid_from"

	if not bank_account:
		frappe.throw(_("Bank / Cash account is missing on the issue Payment Entry"))

	values = {
		"payment_type": reclaim_payment_type,
		"party_type": issue_payment_entry.party_type,
		"party": issue_payment_entry.party,
		"company": issue_payment_entry.company,
		"project": issue_payment_entry.project,
		"posting_date": today(),
		"mode_of_payment": issue_payment_entry.mode_of_payment,
		"reference_no": issue_payment_entry.reference_no,
		"reference_date": issue_payment_entry.reference_date,
		"remarks": _("{0} against Security Instrument {1}").format(
			"Reclaim entry",
			instrument.name,
		),
		"custom_security_instrument": instrument.name,
		"custom_security_entry_role": "Reclaim",
		"custom_is_security_cheque": 1 if instrument.instrument_type == "Security Cheque" else 0,
		"custom_is_security_deposit": 1 if instrument.instrument_type == "Security Deposit" else 0,
		"custom_security_redeemed": 1,
		"custom_security_redeemed_on": today(),
		"paid_amount": flt(instrument.amount),
		"received_amount": flt(instrument.amount),
		account_field: bank_account,
	}

	return values


def _get_security_number_card_response(instrument_type):
	value = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(amount), 0) AS total_amount
		FROM `tabSecurity Instrument`
		WHERE instrument_type = %s
		  AND status IN ('Draft', 'Issued')
		""",
		instrument_type,
	)[0][0]

	return {
		"value": flt(value),
		"fieldtype": "Currency",
		"route": ["List", "Security Instrument"],
		"route_options": {
			"instrument_type": instrument_type,
		},
	}
