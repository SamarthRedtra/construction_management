# Copyright (c) 2026, Construction Management
# License: MIT

"""Print context for controlled Purchase Order (LPO) Jinja formats."""

from __future__ import annotations

import re

import frappe
from frappe.utils import get_url, strip_html

from construction_management.api.lpo_workflow import lpo_type

LPO_TYPE_LABELS = {
	"Standard": "Standard LPO",
	"Open": "Open LPO",
	"Manual": "Manual LPO",
}

DEFAULT_MRG_TRN = "100054873300003"


def get_lpo_print_context(doc) -> dict:
	"""Jinja hook: context for LPO print formats on Purchase Order."""
	return build_lpo_print_context(doc)


def build_lpo_print_context(doc) -> dict:
	kind = lpo_type(doc)
	company_trn = (doc.get("company_trn") or "").strip()
	if not company_trn and doc.get("company"):
		company_trn = frappe.db.get_value("Company", doc.company, "tax_id") or ""
	if not company_trn:
		company_trn = DEFAULT_MRG_TRN

	supplier_trn = ""
	if doc.get("supplier"):
		if frappe.db.has_column("Supplier", "custom_trn_no"):
			supplier_trn = frappe.db.get_value("Supplier", doc.supplier, "custom_trn_no") or ""

	prepared_by = doc.owner
	if doc.owner:
		prepared_by = frappe.db.get_value("User", doc.owner, "full_name") or doc.owner

	show_mrg_delivery_contact = (doc.get("company") or "").strip().upper() != "SKADA CONSTRUCTION L.L.C"

	company_name = doc.get("company") or ""
	logo_url = ""
	if doc.get("company"):
		company_row = frappe.db.get_value(
			"Company",
			doc.company,
			["company_name", "company_logo"],
			as_dict=True,
		)
		if company_row:
			company_name = company_row.company_name or company_name
			if company_row.company_logo:
				logo_url = get_url(company_row.company_logo)

	return {
		"lpo_type": kind,
		"lpo_type_label": LPO_TYPE_LABELS.get(kind, kind),
		"lpo_reference": (doc.get("custom_lpo_reference") or "").strip(),
		"approval_status": (doc.get("custom_lpo_approval_status") or "").strip(),
		"company_trn": company_trn,
		"company_name": company_name,
		"logo_url": logo_url,
		"supplier_trn": supplier_trn,
		"prepared_by": prepared_by,
		"show_mrg_delivery_contact": show_mrg_delivery_contact,
		"is_open_lpo": kind == "Open",
	}


def _norm_print_text(value: str | None) -> str:
	return re.sub(r"\s+", " ", strip_html(value or "")).strip()


def get_po_item_print_block(item) -> dict:
	"""Description cell: item catalogue text on top, extra line notes below when present."""
	label = _norm_print_text(item.get("item_name") or item.get("item_code"))
	line = _norm_print_text(item.get("description"))
	item_desc = ""
	if item.get("item_code"):
		item_desc = _norm_print_text(frappe.db.get_value("Item", item.item_code, "description"))

	description = ""
	notes = ""
	if item_desc and item_desc.casefold() != label.casefold():
		description = item_desc

	if line and line.casefold() != label.casefold():
		if line.casefold() == description.casefold():
			pass
		elif description:
			notes = line
		else:
			description = line

	return {
		"description": description,
		"notes": notes,
		"has_content": bool(description or notes),
	}


def get_po_item_line_notes(item) -> str:
	"""Return extra line notes only (legacy helper)."""
	return get_po_item_print_block(item).get("notes") or ""