# Copyright (c) 2026, Construction Management
# License: MIT

"""Build print context for Payment Certificate (Payable) on Purchase Invoice."""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import flt, money_in_words

from construction_management.overrides.purchase_invoice import (
	_get_linked_purchase_order,
	_is_subcontractor_purchase,
	_po_progress_row_applicable,
)

# Optional item codes for extra deduction rows (extend without template changes)
OPTIONAL_MATERIAL_DEDUCTION_ITEMS: tuple[str, ...] = ()
OPTIONAL_OTHER_DEDUCTION_ITEMS: tuple[str, ...] = ()


def build_pc_payable_print_context(doc) -> dict:
	"""Return a dict for Jinja print: Payment Certificate (Payable)."""
	if getattr(doc, "is_return", 0):
		return _na(_("Payment Certificate is not applicable for return invoices."))

	if doc.get("custom_is_advance"):
		return _na(_("Payment Certificate is not applicable for advance purchase invoices."))

	po_name = _get_linked_purchase_order(doc)
	if not po_name:
		return _na(_("Link at least one item to a Purchase Order to print this certificate."))

	prior_names, idx = _get_prior_names_and_index(po_name, doc)

	# --- Work done (PO progress fields on items) ---
	w_prev = w_this = w_cum = 0.0
	for row in doc.get("items") or []:
		if not _po_progress_row_applicable(row):
			continue
		w_prev += flt(row.get("custom_prev_amount"))
		w_this += flt(row.get("custom_current_amount"))
		w_cum += flt(row.get("custom_accumulated_amount"))

	work_done = _col(w_prev, w_this, w_cum)

	# --- Optional material / other from item codes ---
	mat = _sum_items_by_codes(doc, prior_names, OPTIONAL_MATERIAL_DEDUCTION_ITEMS)
	oth = _sum_items_by_codes(doc, prior_names, OPTIONAL_OTHER_DEDUCTION_ITEMS)

	material_deduction = _col(mat["prev"], mat["this"], mat["cum"])
	other_deduction = _col(oth["prev"], oth["this"], oth["cum"])

	# --- Retention & advance (document lines) ---
	ret = _deduction_totals(doc, prior_names, "RETENTION-DEDUCTION")
	adv = _deduction_totals(doc, prior_names, "ADVANCE-DEDUCTION")

	# --- Total due for payment ---
	total_due = _col(
		work_done["previous"] - material_deduction["previous"],
		work_done["this"] - material_deduction["this"],
		work_done["cumulative"] - material_deduction["cumulative"],
	)

	# Sub total = Total due - advance - retention - other (matches sample)
	sub_total = _col(
		total_due["previous"] - adv["previous"] - ret["previous"] - other_deduction["previous"],
		total_due["this"] - adv["this"] - ret["this"] - other_deduction["this"],
		total_due["cumulative"] - adv["cumulative"] - ret["cumulative"] - other_deduction["cumulative"],
	)

	# Separate "Advance" row (e.g. PURCHASE-ADVANCE release) — usually zero
	padv = _deduction_totals(doc, prior_names, "PURCHASE-ADVANCE")
	advance_row = _col(padv["previous"], padv["this"], padv["cumulative"])
	addition = _col(0.0, 0.0, 0.0)

	# --- VAT (sum of tax rows on each invoice) ---
	vat_prev = sum(_pi_tax_total(n) for n in prior_names)
	vat_this = _pi_tax_total(doc.name)
	vat_cum = vat_prev + vat_this
	vat = _col(vat_prev, vat_this, vat_cum)

	# --- Prev payment (PE allocations) ---
	pe_prev = _pe_allocated_sum(prior_names, doc.company)
	pe_this = _pe_allocated_sum([doc.name], doc.company)
	pe_cum = pe_prev + pe_this
	prev_payment = _col(pe_prev, pe_this, pe_cum)

	# Total amount = Sub total + VAT - Prev payment (per column)
	total_amount = _col(
		sub_total["previous"] + vat["previous"] - prev_payment["previous"],
		sub_total["this"] + vat["this"] - prev_payment["this"],
		sub_total["cumulative"] + vat["cumulative"] - prev_payment["cumulative"],
	)

	# Total deduction row in sample is often blank — expose sum for optional display
	total_deduction_sum = _col(
		adv["previous"] + ret["previous"] + other_deduction["previous"],
		adv["this"] + ret["this"] + other_deduction["this"],
		adv["cumulative"] + ret["cumulative"] + other_deduction["cumulative"],
	)

	# Ledger reference (BOQ Settings accounts)
	ledger = _ledger_balances(doc, po_name)

	# Header / meta
	company_name = frappe.db.get_value("Company", doc.company, "company_name") or doc.company
	project_row = (
		frappe.db.get_value("Project", doc.project, ["name", "project_name"], as_dict=True)
		if doc.project
		else None
	)

	po = frappe.get_cached_doc("Purchase Order", po_name)
	scope = _clean_scope_text(_project_scope_text(doc.project) if doc.project else "")
	if not scope:
		# Prefer explicit PO remarks first; titles are often short / templated
		scope = _clean_scope_text(po.get("remarks") or "") or _clean_scope_text(po.get("title") or "")

	agreement_parts = []
	if po.get("order_confirmation_no"):
		agreement_parts.append(str(po.order_confirmation_no))
	if po.get("order_confirmation_date"):
		agreement_parts.append(_("dated {0}").format(frappe.format_date(po.order_confirmation_date)))
	agreement_label = " ".join(agreement_parts) if agreement_parts else "—"

	contract_type = "—"
	if po.get("bill_no"):
		contract_type = str(po.bill_no)

	pc_serial = idx + 1
	supplier_inv = doc.get("custom_supplier_invoice_no") or "—"
	work_upto = doc.get("bill_date") or doc.posting_date

	words = ""
	try:
		words = money_in_words(flt(total_amount["this"]), doc.currency)
	except Exception:
		words = ""

	return {
		"applicable": True,
		"reason": None,
		"company_name": company_name,
		"company": doc.company,
		"currency": doc.currency,
		"supplier_name": _supplier_display(doc),
		"supplier": doc.supplier,
		"project": doc.project,
		"project_code": project_row["name"] if project_row else "",
		"project_name": (project_row["project_name"] if project_row else "") or doc.project or "",
		"scope_of_work": scope or "—",
		"trn": doc.get("tax_id") or frappe.db.get_value("Supplier", doc.supplier, "tax_id") or "—",
		"agreement_label": agreement_label,
		"contract_type": contract_type,
		"purchase_order": po_name,
		"pc_serial": pc_serial,
		"pc_date": doc.posting_date,
		"supplier_inv_no": supplier_inv,
		"work_done_upto": work_upto,
		"is_subcontractor": bool(_is_subcontractor_purchase(doc)),
		"work_done": work_done,
		"material_deduction": material_deduction,
		"total_due_for_payment": total_due,
		"advance_deduction": _col(adv["previous"], adv["this"], adv["cumulative"]),
		"retention": _col(ret["previous"], ret["this"], ret["cumulative"]),
		"other_deduction": other_deduction,
		"total_deduction": _col(0.0, 0.0, 0.0),
		"total_deduction_computed": total_deduction_sum,
		"sub_total": sub_total,
		"advance_row": advance_row,
		"addition": addition,
		"vat": vat,
		"prev_payment": prev_payment,
		"total_amount": total_amount,
		"amount_in_words": words,
		"retention_ledger_balance": ledger.get("retention"),
		"advance_ledger_balance": ledger.get("advance"),
		"ledger_scope_note": ledger.get("note"),
		"retention_lines_cumulative": ret["cumulative"],
		"advance_lines_cumulative": adv["cumulative"],
	}


def _project_scope_text(project_name: str) -> str:
	"""First non-empty scope field available on this site's Project doctype."""
	if not project_name:
		return ""
	for field in ("project_details", "description", "notes"):
		if not frappe.db.has_column("Project", field):
			continue
		val = frappe.db.get_value("Project", project_name, field)
		if val:
			return str(val).strip()
	return ""


def _clean_scope_text(val: str) -> str:
	"""Remove templated placeholders like '{supplier_name}' from scope fields."""
	s = (val or "").strip()
	if not s:
		return ""
	if re.search(r"\{[^}]+\}", s):
		return ""
	return s


def _supplier_display(doc) -> str:
	name = (getattr(doc, "supplier_name", None) or "").strip()
	code = (getattr(doc, "supplier", None) or "").strip()
	if name and code:
		return f"{name} ({code})"
	return name or code or ""


def _na(reason: str) -> dict:
	return {
		"applicable": False,
		"reason": reason,
		"company_name": "",
		"currency": "",
		"amount_in_words": "",
	}


def _col(previous: float, this: float, cumulative: float) -> dict:
	return {
		"previous": flt(previous, 2),
		"this": flt(this, 2),
		"cumulative": flt(cumulative, 2),
	}


def _get_prior_names_and_index(po_name: str, doc) -> tuple[list[str], int]:
	"""Submitted non-advance PIs for this PO, ordered; return priors before current doc and PC index (0-based)."""
	rows = frappe.db.sql(
		"""
		SELECT pi.name, pi.posting_date, pi.creation
		FROM `tabPurchase Invoice` pi
		WHERE pi.docstatus = 1
		  AND IFNULL(pi.custom_is_advance, 0) = 0
		  AND EXISTS (
			SELECT 1 FROM `tabPurchase Invoice Item` pii
			WHERE pii.parent = pi.name AND pii.purchase_order = %s
		  )
		ORDER BY pi.posting_date ASC, pi.creation ASC, pi.name ASC
		""",
		(po_name,),
		as_dict=True,
	)
	ordered = [r.name for r in rows]
	current_key = (doc.posting_date, getattr(doc, "creation", None) or "", doc.name)
	if doc.name in ordered:
		i = ordered.index(doc.name)
		return ordered[:i], i
	priors = []
	for r in rows:
		key = (r.posting_date, r.creation or "", r.name)
		if key < current_key:
			priors.append(r.name)
	return priors, len(priors)


def _sum_items_by_codes(doc, prior_names: list[str], codes: tuple[str, ...]) -> dict:
	if not codes:
		return {"prev": 0.0, "this": 0.0, "cum": 0.0}
	prev = _sum_amount_for_items(prior_names, codes)
	this = sum(
		abs(flt(r.amount))
		for r in (doc.get("items") or [])
		if r.get("item_code") in codes
	)
	return {"prev": prev, "this": this, "cum": prev + this}


def _sum_amount_for_items(pi_names: list[str], codes: tuple[str, ...]) -> float:
	if not pi_names or not codes:
		return 0.0
	ph = ", ".join(["%s"] * len(pi_names))
	rows = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(ABS(pii.amount)), 0)
		FROM `tabPurchase Invoice Item` pii
		WHERE pii.parent IN ({ph})
		  AND pii.item_code IN ({", ".join(["%s"] * len(codes))})
		""",
		tuple(pi_names) + tuple(codes),
	)
	return flt(rows[0][0] if rows else 0)


def _deduction_totals(doc, prior_names: list[str], item_code: str) -> dict:
	prev = _sum_amount_for_items(prior_names, (item_code,))
	this = sum(
		abs(flt(r.amount))
		for r in (doc.get("items") or [])
		if r.get("item_code") == item_code
	)
	return {
		"previous": prev,
		"this": this,
		"cumulative": prev + this,
	}


def _pi_tax_total(pi_name: str) -> float:
	if not pi_name:
		return 0.0
	r = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(tax_amount), 0)
		FROM `tabPurchase Taxes and Charges`
		WHERE parent = %s
		  AND parenttype = 'Purchase Invoice'
		""",
		(pi_name,),
	)
	return flt(r[0][0] if r else 0)


def _pe_allocated_sum(pi_names: list[str], company: str | None) -> float:
	if not pi_names:
		return 0.0
	ph = ", ".join(["%s"] * len(pi_names))
	vals = list(pi_names)
	q = f"""
		SELECT COALESCE(SUM(per.allocated_amount), 0)
		FROM `tabPayment Entry Reference` per
		INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
		WHERE pe.docstatus = 1
		  AND per.reference_doctype = 'Purchase Invoice'
		  AND per.reference_name IN ({ph})
	"""
	if company:
		q += " AND pe.company = %s"
		vals.append(company)
	return flt(frappe.db.sql(q, tuple(vals))[0][0])


def _pi_names_for_po(po_name: str) -> list[str]:
	rows = frappe.db.sql(
		"""
		SELECT DISTINCT pi.name
		FROM `tabPurchase Invoice` pi
		INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
		WHERE pii.purchase_order = %s
		  AND pi.docstatus = 1
		""",
		(po_name,),
	)
	return [r[0] for r in rows]


def _ledger_balances(doc, po_name: str) -> dict:
	boq = frappe.db.get_value(
		"BOQ Settings",
		doc.company,
		["purchase_retention_account", "purchase_advance_account"],
		as_dict=True,
	) or {}
	ret_acc = boq.get("purchase_retention_account")
	adv_acc = boq.get("purchase_advance_account")
	if not ret_acc and not adv_acc:
		return {"retention": None, "advance": None, "note": _("BOQ Settings purchase accounts not set.")}

	pi_scope = _pi_names_for_po(po_name)
	if not pi_scope:
		return {"retention": None, "advance": None, "note": _("No submitted purchase invoices found for PO.")}

	accounts = [a for a in (ret_acc, adv_acc) if a]
	aph = ", ".join(["%s"] * len(accounts))
	piph = ", ".join(["%s"] * len(pi_scope))

	q = f"""
		SELECT gle.account, COALESCE(SUM(gle.debit - gle.credit), 0) AS bal
		FROM `tabGL Entry` gle
		WHERE gle.is_cancelled = 0
		  AND gle.company = %s
		  AND gle.account IN ({aph})
		  AND gle.party_type = 'Supplier'
		  AND gle.party = %s
		  AND gle.posting_date <= %s
		  AND gle.voucher_no IN ({piph})
	"""
	params: list = [doc.company] + accounts + [doc.supplier, doc.posting_date] + pi_scope
	if doc.project:
		q += " AND (gle.project = %s OR gle.project IS NULL)"
		params.append(doc.project)

	q += " GROUP BY gle.account"
	rows = frappe.db.sql(q, tuple(params), as_dict=True)
	out = {r.account: flt(r.bal) for r in rows}
	return {
		"retention": out.get(ret_acc) if ret_acc else None,
		"advance": out.get(adv_acc) if adv_acc else None,
		"note": _("GL (debit − credit) for BOQ purchase retention/advance accounts; PIs linked to this PO; through certificate posting date."),
	}
