# Copyright (c) 2026, Construction Management
# License: MIT

"""Dedicated Sales Invoice link on commission payout Payment Entries."""

import frappe

from construction_management.patches.v2_enhancements import create_custom_field_if_not_exists

COMMISSION_PAYOUT_REMARK_PREFIX = "Commission payout for Sales Invoice "


def execute():
	create_custom_field_if_not_exists({
		"dt": "Payment Entry",
		"fieldname": "custom_commission_sales_invoice",
		"label": "Commission Sales Invoice",
		"fieldtype": "Link",
		"options": "Sales Invoice",
		"read_only": 1,
		"hidden": 0,
		"insert_after": "custom_is_commission_payout",
		"no_copy": 1,
	})

	_ensure_commission_invoice_field_visible()
	relink_all_commission_payouts()
	frappe.clear_cache(doctype="Payment Entry")
	frappe.db.commit()


def _ensure_commission_invoice_field_visible():
	"""Show the linked invoice on Payment Entry — required for commission payouts."""
	fieldname = "Payment Entry-custom_commission_sales_invoice"
	if frappe.db.exists("Custom Field", fieldname):
		frappe.db.set_value(
			"Custom Field",
			fieldname,
			{"hidden": 0, "read_only": 1, "label": "Commission Sales Invoice"},
			update_modified=False,
		)


def relink_all_commission_payouts():
	"""Recompute invoice links for every commission payout Payment Entry."""
	if not frappe.db.has_column("Payment Entry", "custom_commission_sales_invoice"):
		return

	rows = frappe.db.sql(
		"""
		SELECT pe.name, pe.company, pe.project
		FROM `tabPayment Entry` pe
		INNER JOIN `tabBOQ Settings` bs ON bs.name = pe.company
		WHERE pe.payment_type = 'Pay'
		  AND pe.party_type = 'Employee'
		  AND pe.docstatus < 2
		  AND IFNULL(pe.project, '') != ''
		  AND pe.paid_to = bs.sales_commission_payable_account
		ORDER BY pe.posting_date ASC, pe.name ASC
		""",
		as_dict=True,
	)

	# Clear stale links first so resolution is recomputed from scratch.
	for row in rows:
		frappe.db.set_value(
			"Payment Entry",
			row.name,
			"custom_commission_sales_invoice",
			None,
			update_modified=False,
		)

	projects = sorted({(row.project, row.company) for row in rows if row.project and row.company})
	for project, company in projects:
		_relink_project_commission_payouts(project, company)


def _relink_project_commission_payouts(project: str, company: str) -> None:
	try:
		from construction_management.api.project_commission_data import _get_commission_payout_resolution
		from redtra_customisation.redtra_customisation.report.sales_person_commission_payment_summary.sales_person_commission_payment_summary import (
			get_entries,
		)
	except ImportError:
		return

	entries = get_entries({
		"company": company,
		"project": project,
		"doc_type": "Sales Invoice",
	}) or []
	resolution = _get_commission_payout_resolution(project, company, entries)
	for pe_name, invoice in (resolution.get("invoice_by_payment") or {}).items():
		frappe.db.set_value(
			"Payment Entry",
			pe_name,
			{
				"custom_commission_sales_invoice": invoice,
				"custom_is_commission_payout": 1,
				"remarks": f"{COMMISSION_PAYOUT_REMARK_PREFIX}{invoice}",
				"custom_remarks": 1,
			},
			update_modified=False,
		)


def backfill_commission_sales_invoice_links():
	relink_all_commission_payouts()


def _extract_invoice(row) -> str | None:
	ref = (row.get("reference_no") or "").strip()
	if ref and frappe.db.exists("Sales Invoice", ref):
		return ref

	remarks = row.get("remarks") or ""
	if COMMISSION_PAYOUT_REMARK_PREFIX in remarks:
		rest = remarks.split(COMMISSION_PAYOUT_REMARK_PREFIX, 1)[1].strip()
		invoice = rest.split()[0] if rest else ""
		if invoice and frappe.db.exists("Sales Invoice", invoice):
			return invoice
	return None
