# Copyright (c) 2026, Construction Management
# License: MIT

import json

import frappe
from frappe import _
from frappe.utils import flt

from construction_management.api.collection_pc_override import upsert_collection_pc_override
from construction_management.api.project_collection_data import (
	get_collection_expected_payments as _get_collection_expected_payments,
	get_collection_invoice_portfolio as _get_collection_invoice_portfolio,
	get_collection_portfolio as _get_collection_portfolio,
	get_collection_project_rows,
)


@frappe.whitelist()
def get_collection_portfolio(company: str, filters: str | dict | None = None) -> list[dict]:
	if not company:
		frappe.throw(_("Company is required"))

	if isinstance(filters, str):
		filters = json.loads(filters) if filters else {}
	filters = filters or {}

	return _get_collection_portfolio(company, filters)


@frappe.whitelist()
def get_collection_invoice_portfolio(company: str, filters: str | dict | None = None) -> list[dict]:
	if not company:
		frappe.throw(_("Company is required"))
	if isinstance(filters, str):
		filters = json.loads(filters) if filters else {}
	return _get_collection_invoice_portfolio(company, filters or {})


@frappe.whitelist()
def get_collection_expected_payments(company: str, filters: str | dict | None = None) -> dict:
	if isinstance(filters, str):
		filters = json.loads(filters) if filters else {}
	return _get_collection_expected_payments(company, filters or {})


@frappe.whitelist()
def save_collection_payment_certificate(
	project: str,
	reference_doctype: str,
	reference_name: str,
	certificate_date: str | None = None,
	pc_amount=None,
	attachment: str | None = None,
) -> dict:
	"""Save the PC date, certified amount, and uploaded certificate against an invoice row."""
	result = upsert_collection_pc_override(
		project,
		reference_doctype,
		reference_name,
		pc_date=certificate_date,
		pc_amount=flt(pc_amount),
		update_date=True,
		update_amount=True,
	)
	if attachment:
		frappe.db.set_value("Project SOA Follow Up", result["name"], "attachment", attachment, update_modified=True)
	result["attachment"] = attachment or ""
	frappe.db.commit()
	return result


@frappe.whitelist()
def get_collection_project_detail(project: str) -> dict:
	if not project:
		frappe.throw(_("Project is required"))

	return get_collection_project_rows(project)


@frappe.whitelist()
def update_payment_certificate_date(payment_certificate: str, certificate_date: str | None = None) -> dict:
	"""Set Payment Certificate.custom_certificate_date from Collection Manager row."""
	if not payment_certificate:
		frappe.throw(_("Payment Certificate is required"))
	if not frappe.db.exists("Payment Certificate", payment_certificate):
		frappe.throw(_("Payment Certificate {0} not found").format(payment_certificate))
	if not frappe.db.has_column("Payment Certificate", "custom_certificate_date"):
		frappe.throw(_("Certificate Date field is not installed. Run bench migrate."))

	frappe.db.set_value(
		"Payment Certificate",
		payment_certificate,
		"custom_certificate_date",
		certificate_date or None,
		update_modified=True,
	)
	frappe.db.commit()
	return {
		"payment_certificate": payment_certificate,
		"certificate_date": certificate_date,
	}


@frappe.whitelist()
def update_payment_certificate_amount(payment_certificate: str, accepted_amount=None) -> dict:
	"""Set Payment Certificate.accepted_amount from Collection Manager row."""
	if not payment_certificate:
		frappe.throw(_("Payment Certificate is required"))
	if not frappe.db.exists("Payment Certificate", payment_certificate):
		frappe.throw(_("Payment Certificate {0} not found").format(payment_certificate))

	amount = flt(accepted_amount)
	frappe.db.set_value(
		"Payment Certificate",
		payment_certificate,
		"accepted_amount",
		amount,
		update_modified=True,
	)
	if frappe.db.has_column("Payment Certificate", "grand_total"):
		frappe.db.set_value(
			"Payment Certificate",
			payment_certificate,
			"grand_total",
			amount,
			update_modified=False,
		)
	frappe.db.commit()
	return {
		"payment_certificate": payment_certificate,
		"accepted_amount": amount,
	}


@frappe.whitelist()
def update_collection_pc_date(
	project: str,
	certificate_date: str | None = None,
	payment_certificate: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> dict:
	"""Persist PC Date from Collection Manager."""
	if not project:
		frappe.throw(_("Project is required"))

	payment_certificate = (payment_certificate or "").strip()
	if payment_certificate and frappe.db.exists("Payment Certificate", payment_certificate):
		return update_payment_certificate_date(payment_certificate, certificate_date)

	if not reference_doctype or not reference_name:
		frappe.throw(_("Row reference is required to save PC Date."))

	return upsert_collection_pc_override(
		project,
		reference_doctype,
		reference_name,
		pc_date=certificate_date,
		update_date=True,
	)


@frappe.whitelist()
def update_collection_pc_amount(
	project: str,
	pc_amount=None,
	payment_certificate: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> dict:
	"""Persist PC Amount from Collection Manager."""
	if not project:
		frappe.throw(_("Project is required"))

	amount = flt(pc_amount) if pc_amount not in (None, "") else 0
	payment_certificate = (payment_certificate or "").strip()
	if payment_certificate and frappe.db.exists("Payment Certificate", payment_certificate):
		return update_payment_certificate_amount(payment_certificate, amount)

	if not reference_doctype or not reference_name:
		frappe.throw(_("Row reference is required to save PC Amount."))

	return upsert_collection_pc_override(
		project,
		reference_doctype,
		reference_name,
		pc_amount=amount,
		update_amount=True,
	)
