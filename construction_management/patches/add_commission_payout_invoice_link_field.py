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
		"hidden": 1,
		"insert_after": "custom_is_commission_payout",
		"no_copy": 1,
	})

	backfill_commission_sales_invoice_links()
	frappe.clear_cache(doctype="Payment Entry")
	frappe.db.commit()


def backfill_commission_sales_invoice_links():
	if not frappe.db.has_column("Payment Entry", "custom_commission_sales_invoice"):
		return

	has_flag = frappe.db.has_column("Payment Entry", "custom_is_commission_payout")
	flag_filter = " OR IFNULL(custom_is_commission_payout, 0) = 1" if has_flag else ""

	rows = frappe.db.sql(
		f"""
		SELECT name, company, project, party AS employee, paid_amount, reference_no, remarks, paid_to
		FROM `tabPayment Entry`
		WHERE IFNULL(custom_commission_sales_invoice, '') = ''
		  AND payment_type = 'Pay'
		  AND party_type = 'Employee'
		  AND docstatus < 2
		  AND IFNULL(project, '') != ''
		  AND (
			remarks LIKE %s
			{flag_filter}
		  )
		""",
		(f"{COMMISSION_PAYOUT_REMARK_PREFIX}%",),
		as_dict=True,
	)

	payable_rows = frappe.db.sql(
		"""
		SELECT pe.name, pe.company, pe.project, pe.party AS employee, pe.paid_amount,
			pe.reference_no, pe.remarks, pe.paid_to
		FROM `tabPayment Entry` pe
		INNER JOIN `tabBOQ Settings` bs ON bs.name = pe.company
		WHERE IFNULL(pe.custom_commission_sales_invoice, '') = ''
		  AND pe.payment_type = 'Pay'
		  AND pe.party_type = 'Employee'
		  AND pe.docstatus < 2
		  AND IFNULL(pe.project, '') != ''
		  AND pe.paid_to = bs.sales_commission_payable_account
		""",
		as_dict=True,
	)

	seen = {row.name for row in rows}
	for row in payable_rows:
		if row.name not in seen:
			rows.append(row)
			seen.add(row.name)

	for row in rows:
		invoice = _extract_invoice(row)
		if not invoice:
			invoice = _infer_invoice_from_project_payout(row)
		if invoice:
			frappe.db.set_value(
				"Payment Entry",
				row.name,
				{
					"custom_commission_sales_invoice": invoice,
					"custom_is_commission_payout": 1,
					"remarks": f"{COMMISSION_PAYOUT_REMARK_PREFIX}{invoice}",
					"custom_remarks": 1,
				},
				update_modified=False,
			)


def _infer_invoice_from_project_payout(row) -> str | None:
	try:
		from construction_management.api.project_commission_data import _get_commission_payout_resolution
		from redtra_customisation.redtra_customisation.report.sales_person_commission_payment_summary.sales_person_commission_payment_summary import (
			get_entries,
		)
	except ImportError:
		return None

	project = row.get("project")
	company = row.get("company")
	if not project or not company:
		return None

	entries = get_entries({
		"company": company,
		"project": project,
		"doc_type": "Sales Invoice",
	}) or []
	resolution = _get_commission_payout_resolution(project, company, entries)
	return resolution.get("invoice_by_payment", {}).get(row.name)


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
