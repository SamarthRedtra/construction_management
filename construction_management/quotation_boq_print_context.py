# Copyright (c) 2026, Construction Management
# License: MIT

"""Build print context for BOQ-style Quotation print format."""

from __future__ import annotations

import frappe
from frappe.utils import flt, formatdate, get_url

from construction_management.quotation_boq_hierarchy import (
	HIERARCHY_TWO_LEVEL,
	resolve_hierarchy_mode,
)


def build_boq_quotation_print_context(doc) -> dict:
	"""Return header meta, structured BOQ rows, totals, and terms for Jinja print."""
	company = frappe.get_cached_value(
		"Company",
		doc.company,
		["company_name", "tax_id", "company_logo", "default_letter_head"],
		as_dict=True,
	) or {}

	header = {
		"quotation_ref": doc.get("custom_quotation_ref") or doc.name,
		"date": formatdate(doc.transaction_date),
		"company_trn": company.get("tax_id") or "",
		"main_contractor": doc.get("custom_main_contractor") or "",
		"project_title": doc.get("custom_project_title") or "",
		"site_address": doc.get("custom_site_address") or "",
		"site_location": doc.get("custom_site_location") or "",
		"contact": doc.get("custom_contact") or "",
		"client_name": doc.get("custom_client_name")
		or doc.get("customer_name")
		or doc.get("party_name")
		or "",
		"attention": doc.get("custom_attention") or "",
		"consultant": doc.get("custom_consultant") or "",
		"company_name": company.get("company_name") or doc.company,
	}

	logo_url = ""
	if company.get("company_logo"):
		logo_url = get_url(company.company_logo)

	letter_head = _get_letter_head(doc, company.get("default_letter_head"))
	hierarchy_mode = resolve_hierarchy_mode(doc.company, doc.get("custom_boq_lines") or [])
	sections, total_excl = _group_boq_lines(
		doc.get("custom_boq_lines") or [],
		hierarchy_mode=hierarchy_mode,
	)
	vat_amount, vat_label = _vat_from_doc(doc, total_excl)

	boq_html = doc.get("custom_boq_html") or ""
	if not boq_html and sections:
		from construction_management.api.quotation_boq import lines_to_boq_html

		boq_html = lines_to_boq_html(doc.get("custom_boq_lines") or [], include_totals=True)

	return {
		"header": header,
		"logo_url": logo_url,
		"letter_head": letter_head,
		"hierarchy_mode": hierarchy_mode,
		"sections": sections,
		"totals": {
			"total_excl_vat": total_excl,
			"vat_amount": vat_amount,
			"total_incl_vat": total_excl + vat_amount,
			"vat_label": vat_label,
		},
		"boq_html": boq_html,
		"terms_html": doc.get("terms") or "",
		"payment_terms": doc.get("custom_payment_terms") or "",
		"exclusion": doc.get("custom_exclusion") or "",
		"validity": doc.get("custom_validity") or "",
		"currency": doc.currency or "AED",
	}


def _get_letter_head(doc, default_letter_head: str | None) -> dict | None:
	letter_head_name = doc.get("letter_head") or default_letter_head
	if not letter_head_name:
		return None

	from frappe.www.printview import get_letter_head

	lh_doc = frappe._dict({"letter_head": letter_head_name, "company": doc.company})
	return get_letter_head(lh_doc, 0)


def _group_boq_lines(lines: list, hierarchy_mode: str | None = None) -> tuple[list[dict], float]:
	ordered = sorted(lines, key=lambda row: row.idx or 0)
	two_level = hierarchy_mode == HIERARCHY_TWO_LEVEL
	sections: list[dict] = []
	current_section: dict | None = None
	current_parent: dict | None = None
	total_excl = 0.0

	for row in ordered:
		line_type = row.get("line_type") or "Parent"

		if line_type == "Section":
			if two_level:
				continue
			title = (row.get("section_title") or row.get("description") or "").strip()
			current_section = {"title": title, "parents": []}
			sections.append(current_section)
			current_parent = None
			continue

		if not current_section:
			current_section = {"title": "", "parents": []}
			sections.append(current_section)

		if line_type == "Parent":
			section_title = (row.get("section_title") or "").strip()
			if two_level and section_title and section_title != current_section.get("title"):
				current_section = {"title": section_title, "parents": []}
				sections.append(current_section)
				current_parent = None

			current_parent = {
				"no": row.get("parent_no") or "",
				"description": row.get("description") or "",
				"subs": [],
			}
			current_section["parents"].append(current_parent)
			continue

		if line_type == "Sub":
			parent_no = row.get("parent_no")
			if parent_no:
				matched_parent = _find_parent_in_section(current_section, parent_no)
				if matched_parent:
					current_parent = matched_parent
				else:
					current_parent = {
						"no": parent_no,
						"description": "",
						"subs": [],
					}
					current_section["parents"].append(current_parent)
			elif not current_parent:
				current_parent = {
					"no": row.get("parent_no") or "",
					"description": "",
					"subs": [],
				}
				current_section["parents"].append(current_parent)

			sub = _format_sub_row(row)
			current_parent["subs"].append(sub)
			if sub["include_in_total"]:
				total_excl += flt(sub["amount"])

	return sections, total_excl


def _find_parent_in_section(section: dict, parent_no) -> dict | None:
	target = str(parent_no or "").strip()
	if not target:
		return None
	for parent in section.get("parents") or []:
		if str(parent.get("no") or "").strip() == target:
			return parent
	return None


def _format_sub_row(row) -> dict:
	display_mode = row.get("display_mode") or "Normal"
	qty = flt(row.get("qty"))
	rate = flt(row.get("rate"))
	amount = flt(row.get("amount"))
	if display_mode == "Normal" and not amount:
		amount = qty * rate

	if display_mode == "N/A":
		rate_display = "-"
		amount_display = "N/A"
	elif display_mode == "Rate Only":
		rate_display = rate
		amount_display = "Rate only"
	else:
		rate_display = rate
		amount_display = amount

	return {
		"sub_no": row.get("sub_no") or "",
		"description": row.get("description") or "",
		"uom": row.get("uom") or "",
		"qty": qty,
		"rate": rate,
		"amount": amount,
		"display_mode": display_mode,
		"rate_display": rate_display,
		"amount_display": amount_display,
		"include_in_total": display_mode == "Normal",
	}


def _vat_from_doc(doc, total_excl: float) -> tuple[float, str]:
	vat_amount = flt(doc.get("total_taxes_and_charges"))
	if not vat_amount and doc.get("taxes"):
		vat_amount = sum(flt(t.tax_amount) for t in doc.taxes)

	# Default 5% when no tax rows (matches typical UAE tender quotes)
	if not vat_amount and total_excl:
		vat_amount = flt(total_excl) * 0.05

	vat_label = "5% VAT"
	for tax in doc.get("taxes") or []:
		if tax.get("description"):
			vat_label = tax.description
			break
		if flt(tax.get("rate")):
			vat_label = f"{flt(tax.rate)}% VAT"
			break

	return vat_amount, vat_label
