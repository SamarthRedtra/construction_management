# Copyright (c) 2026, Construction Management
# License: MIT

"""Convert leftover non-deductible customer advance into revenue via Sales Invoice."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt, today

from construction_management.api.boq_invoice import get_advance_balance, get_or_create_advance_item

ADVANCE_RELEASE_ITEM = "ADVANCE-RELEASE"


def is_advance_release_invoice(doc) -> bool:
	return bool(cint(doc.get("custom_is_advance_release")))


def get_or_create_advance_release_item() -> str:
	if not frappe.db.exists("Item", ADVANCE_RELEASE_ITEM):
		item = frappe.new_doc("Item")
		item.item_code = ADVANCE_RELEASE_ITEM
		item.item_name = "Advance Release"
		item.item_group = "Services"
		item.stock_uom = "Nos"
		item.is_stock_item = 0
		item.is_sales_item = 1
		item.description = "Recognize leftover customer advance as revenue"
		item.insert(ignore_permissions=True)
	return ADVANCE_RELEASE_ITEM


def remaining_advance_for_release(project: str, exclude_invoice: str | None = None) -> float:
	balance = flt(get_advance_balance(project))
	if not exclude_invoice:
		return balance
	own_deduction = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(ABS(sii.amount)), 0)
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.name = %s
			AND si.docstatus IN (0, 1)
			AND sii.item_code = 'ADVANCE-DEDUCTION'
		""",
		exclude_invoice,
	)
	return flt(balance + flt(own_deduction[0][0] if own_deduction else 0))


def apply_advance_release_lines(doc, amount: float | None = None) -> float:
	if not doc.get("project"):
		frappe.throw(_("Set Project before releasing advance to revenue."))
	if cint(doc.get("custom_is_advanced")):
		frappe.throw(_("An advance invoice cannot also be an Advance Release."))

	available = remaining_advance_for_release(doc.project, doc.get("name"))
	release_amount = flt(amount) if amount is not None else available
	release_amount = flt(release_amount, 2)
	if release_amount <= 0:
		frappe.throw(_("No leftover advance to convert to revenue."))
	if release_amount > available:
		frappe.throw(
			_("Release amount ({0}) exceeds leftover advance ({1})").format(
				release_amount, available
			)
		)

	_strip_release_rows(doc)
	release_item = get_or_create_advance_release_item()
	deduction_item = get_or_create_advance_item()
	income_account = frappe.get_cached_value("Company", doc.company, "default_income_account")
	if not income_account:
		frappe.throw(_("Set Default Income Account on Company {0}").format(doc.company))
	if not frappe.db.get_value("BOQ Settings", doc.company, "advance_account"):
		frappe.throw(_("Set Advance Account in BOQ Settings for {0}").format(doc.company))
	cost_center = doc.cost_center or frappe.get_cached_value("Company", doc.company, "cost_center")
	common = {
		"qty": 1,
		"uom": "Nos",
		"conversion_factor": 1.0,
		"project": doc.project,
		"cost_center": cost_center,
		"income_account": income_account,
	}
	doc.append(
		"items",
		{
			**common,
			"item_code": release_item,
			"item_name": "Advance Release",
			"description": _("Convert leftover customer advance to revenue"),
			"rate": release_amount,
			"amount": release_amount,
		},
	)
	doc.append(
		"items",
		{
			**common,
			"item_code": deduction_item,
			"item_name": "Advance Deduction",
			"description": _("Clear leftover advance from customer"),
			"rate": -release_amount,
			"amount": -release_amount,
		},
	)
	doc.allocate_advances_automatically = 0
	doc.set("taxes", [])
	doc.taxes_and_charges = None
	return release_amount


@frappe.whitelist()
def fill_advance_release_items(sales_invoice: str, amount: float | None = None) -> dict:
	doc = frappe.get_doc("Sales Invoice", sales_invoice)
	if doc.docstatus != 0:
		frappe.throw(_("Only draft Sales Invoices can be filled."))
	doc.custom_is_advance_release = 1
	doc.custom_is_advanced = 0
	release_amount = apply_advance_release_lines(doc, amount)
	doc.flags.ignore_deduction_recalc = True
	doc.save()
	return {"status": "ok", "amount": release_amount}


@frappe.whitelist()
def prepare_advance_release_sales_invoice(project: str, amount: float | None = None) -> dict:
	if not project:
		return {"error": _("Project is required")}

	project_doc = frappe.get_doc("Project", project)
	if not project_doc.customer:
		return {"error": _("Project must have a customer assigned")}

	company = project_doc.company or frappe.defaults.get_user_default("company")
	if not company:
		return {"error": _("Company is required.")}

	si = frappe.new_doc("Sales Invoice")
	si.customer = project_doc.customer
	si.project = project
	si.company = company
	si.posting_date = today()
	si.due_date = today()
	si.custom_is_advance_release = 1
	si.custom_is_advanced = 0
	si.allocate_advances_automatically = 0
	try:
		release_amount = apply_advance_release_lines(si, amount)
	except frappe.ValidationError as exc:
		return {"error": str(exc)}

	si.flags.ignore_deduction_recalc = True
	si.insert()
	return {"invoice_name": si.name, "amount": release_amount}


def validate_advance_release(doc) -> None:
	if not is_advance_release_invoice(doc):
		return
	if cint(doc.get("custom_is_advanced")):
		frappe.throw(_("An advance invoice cannot also be an Advance Release."))
	if not doc.get("project"):
		frappe.throw(_("Set Project on an Advance Release invoice."))

	release_total = 0.0
	deduction_total = 0.0
	for row in doc.get("items") or []:
		if row.item_code == ADVANCE_RELEASE_ITEM:
			release_total += flt(row.amount)
		elif row.item_code == "ADVANCE-DEDUCTION":
			deduction_total += abs(flt(row.amount))

	if release_total <= 0 or deduction_total <= 0:
		apply_advance_release_lines(doc)
		return
	if flt(release_total, 2) != flt(deduction_total, 2):
		frappe.throw(_("Advance Release amount must equal the ADVANCE-DEDUCTION amount."))

	available = remaining_advance_for_release(doc.project, doc.get("name"))
	if flt(deduction_total, 2) > flt(available, 2):
		frappe.throw(
			_("Release amount ({0}) exceeds leftover advance ({1})").format(
				deduction_total, available
			)
		)

	doc.allocate_advances_automatically = 0
	doc.set("taxes", [])
	doc.taxes_and_charges = None


def _strip_release_rows(doc) -> None:
	for row in list(doc.get("items") or []):
		if row.item_code in (ADVANCE_RELEASE_ITEM, "ADVANCE-DEDUCTION"):
			doc.remove(row)
