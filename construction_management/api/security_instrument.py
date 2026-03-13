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
	payment_entry.reference_date = posting_date if reference_no else None
	payment_entry.remarks = remarks
	payment_entry.custom_security_instrument = instrument.name
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
def mark_security_instrument_redeemed(name):
	instrument = frappe.get_doc("Security Instrument", name)
	if instrument.status == "Cancelled":
		frappe.throw(_("Cancelled security instruments cannot be redeemed"))

	if instrument.status != "Redeemed":
		instrument.mark_redeemed()

	return {"name": instrument.name, "status": "Redeemed"}


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
