# Copyright (c) 2026, Construction Management
# License: MIT

"""Print context for Sales Order BOQ Progress (proforma) format."""

from __future__ import annotations

import frappe
from frappe.utils import flt, formatdate, money_in_words

DEDUCTION_ITEM_CODES = ("RETENTION-DEDUCTION", "ADVANCE-DEDUCTION")
DEFAULT_VAT_RATE = 5.0


def get_so_boq_progress_print_context(doc) -> dict:
	return build(doc)


def build(doc) -> dict:
	"""Totals and line rows matching the BOQ Progress print layout."""
	ret_percent = _retention_percent(doc)
	vat_rate = _vat_rate(doc)
	ledger_map = _ledger_map(doc.name)

	items = []
	gross_p = gross_c = gross_t = 0.0
	ret_c = adv_c = 0.0
	prev_paid = 0.0
	idx = 0

	for entry in ledger_map.values():
		prev_paid += flt(entry.get("tax_invoice_amount"))

	for item in doc.get("items") or []:
		if flt(item.amount) <= 0:
			continue
		if item.item_code in DEDUCTION_ITEM_CODES:
			continue
		idx += 1
		ledger = ledger_map.get(item.boq_item) or {}
		prev_amount = flt(ledger.get("prev_amount"))
		prev_qty = flt(ledger.get("prev_qty"))
		current_amount = flt(item.amount)
		current_qty = flt(item.qty)
		total_amount = prev_amount + current_amount
		percentage = ledger.get("percentage")
		if percentage is None:
			percentage = 0

		items.append(
			{
				"idx": idx,
				"description": item.description or item.item_name or item.item_code,
				"uom": item.uom or "",
				"percentage": flt(percentage),
				"prev_qty": prev_qty,
				"current_qty": current_qty,
				"total_qty": prev_qty + current_qty,
				"rate": flt(item.rate),
				"prev_amount": prev_amount,
				"current_amount": current_amount,
				"total_amount": total_amount,
			}
		)

		gross_p += prev_amount
		gross_c += current_amount
		gross_t += total_amount
		if ledger:
			ret_c += flt(ledger.get("retention_amount"))
			adv_c += flt(ledger.get("advance_deduction"))
		else:
			ret_c += current_amount * ret_percent / 100.0

	adv_p = 0.0
	tax_c = flt(doc.get("total_taxes_and_charges"))
	disc_c = abs(flt(doc.get("discount_amount")))
	ret_p = gross_p * ret_percent / 100.0
	tax_p = gross_p * vat_rate / 100.0
	net_c = gross_c - ret_c - adv_c + tax_c - disc_c

	currency = doc.currency or "AED"
	words = money_in_words(flt(net_c), currency) or ""

	return {
		"header": _header(doc),
		"currency": currency,
		"rows": items,
		"totals": {
			"gross_p": gross_p,
			"gross_c": gross_c,
			"gross_t": gross_t,
			"ret_percent": ret_percent,
			"ret_p": ret_p,
			"ret_c": ret_c,
			"ret_t": ret_p + ret_c,
			"adv_p": adv_p,
			"adv_c": adv_c,
			"adv_t": adv_p + adv_c,
			"vat_rate": vat_rate,
			"tax_p": tax_p,
			"tax_c": tax_c,
			"tax_t": tax_p + tax_c,
			"disc_c": disc_c,
			"prev_paid": prev_paid,
			"net_c": net_c,
		},
		"amount_in_words": words,
		"terms": doc.get("terms") or "",
		"company": doc.company,
		"customer_name": doc.customer_name or "",
	}


def _header(doc) -> dict:
	customer_trn = ""
	customer_tel = ""
	if doc.customer:
		fields = ["mobile_no"]
		if frappe.db.has_column("Customer", "custom_trn"):
			fields.append("custom_trn")
		row = frappe.db.get_value("Customer", doc.customer, fields, as_dict=True) or {}
		customer_trn = row.get("custom_trn") or ""
		customer_tel = row.get("mobile_no") or ""

	project_name = doc.project or ""
	if doc.project:
		project_name = (
			frappe.db.get_value("Project", doc.project, "project_name") or doc.project
		)

	company_trn = ""
	company_trn_label = "TRN"
	if doc.company:
		company = frappe.db.get_value(
			"Company", doc.company, ["tax_id", "abbr"], as_dict=True
		) or {}
		company_trn = company.get("tax_id") or ""
		if company.get("abbr"):
			company_trn_label = f"{company.abbr} TRN"

	name = doc.name or ""
	document_date = doc.get("transaction_date") or doc.get("posting_date")
	return {
		"customer_name": doc.customer_name or "",
		"customer_tel": customer_tel,
		"customer_trn": customer_trn or "N/A",
		"subject": f"Invoice # : {name.split('-')[-1] if name else ''}",
		"date": formatdate(document_date) if document_date else "",
		"invoice_no": name,
		"project_name": project_name,
		"company_trn": company_trn,
		"company_trn_label": company_trn_label,
	}


def _retention_percent(doc) -> float:
	if not doc.project:
		return 10.0
	percent = frappe.db.get_value("Project", doc.project, "retention_percentage")
	return flt(percent) if percent else 10.0


def _vat_rate(doc) -> float:
	for tax in doc.get("taxes") or []:
		if flt(tax.rate):
			return flt(tax.rate)
	return DEFAULT_VAT_RATE


def _ledger_map(reference_name: str) -> dict:
	if not reference_name:
		return {}
	entries = frappe.get_all(
		"BOQ Progress Ledger",
		filters={"reference_name": reference_name},
		fields=[
			"boq_item",
			"prev_amount",
			"current_amount",
			"accumulated_amount",
			"retention_amount",
			"advance_deduction",
			"prev_qty",
			"percentage",
			"tax_invoice_amount",
		],
	)
	return {row.boq_item: row for row in entries if row.boq_item}
