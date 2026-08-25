# Copyright (c) 2026, Construction Management
# License: MIT

"""
Project Closure API - Advance and Retention helpers
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_existing_project_closure(project: str) -> dict:
	"""
	Get existing Project Closure for a project that is not cancelled.

	Args:
		project: Project name

	Returns:
		dict with name if found, else empty
	"""
	if not project:
		return {}
	name = frappe.db.get_value(
		"Project Closure",
		{"project": project, "docstatus": ["<", 2]},
		"name",
		order_by="creation desc"
	)
	return {"name": name} if name else {}


@frappe.whitelist()
def prepare_advance_release_sales_invoice(project: str, amount: float | None = None) -> dict:
	from construction_management.api.advance_release import prepare_advance_release_sales_invoice as _prepare

	return _prepare(project, amount)


@frappe.whitelist()
def prepare_advance_sales_invoice(project: str) -> dict:
	"""
	Create a new Sales Invoice with is_advance ticked, project populated,
	and advance item pre-populated. Returns the invoice name for redirection.

	Args:
		project: Project name

	Returns:
		dict with invoice_name or error
	"""
	if not project:
		return {"error": _("Project is required")}

	project_doc = frappe.get_doc("Project", project)
	if not project_doc.customer:
		return {"error": _("Project must have a customer assigned")}

	company = project_doc.company or frappe.defaults.get_user_default("company")
	if not company:
		return {"error": _("Company is required. Set default company or project company.")}

	# Get advance item and percentage from BOQ Settings
	boq_settings = frappe.db.get_value(
		"BOQ Settings",
		{"company": company},
		["default_advance_item"],
		as_dict=True,
	)
	advance_item = boq_settings.default_advance_item if boq_settings else None

	if not advance_item:
		return {"error": _("Please set Default Advance Item in BOQ Settings for company {0}").format(company)}

	# Get total BOQ value for amount calculation
	total_boq_value = frappe.db.get_value(
		"Project BOQ",
		{"project": project},
		"total_estimated_boq_value"
	) or frappe.db.get_value("Project BOQ", {"project": project}, "total_boq_value") or 0

	# Default advance percentage from project or 10%
	advance_pct = flt(getattr(project_doc, "advance_deduction", None)) or 10
	amount = flt(total_boq_value) * advance_pct / 100 if total_boq_value else 0

	# Create new Sales Invoice
	si = frappe.new_doc("Sales Invoice")
	si.customer = project_doc.customer
	si.project = project
	si.company = company
	si.custom_is_advanced = 1
	si.custom_advanced_percentage = advance_pct

	if amount > 0:
		si.append("items", {
			"item_code": advance_item,
			"qty": 1,
			"rate": amount,
			"amount": amount,
		})

	si.insert()

	return {"invoice_name": si.name}
