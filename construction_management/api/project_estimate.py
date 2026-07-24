# Copyright (c) 2026, Construction Management
# License: MIT

"""Project Estimate helpers: activity math, template apply, SI overrun lookup."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt


def calculate_activity_row(row) -> None:
	"""Apply Excel-style formulas on a Project Estimate Activity row."""
	material_cost = flt(row.est_qty) * flt(row.unit_price)
	labour_cost = (flt(row.skilled) * flt(row.skilled_rate)) + (
		flt(row.unskilled) * flt(row.unskilled_rate)
	)
	area = flt(row.est_area)
	total_cost = material_cost + labour_cost

	row.material_cost = material_cost
	row.labour_cost = labour_cost
	row.labour_cost_per_m2 = (labour_cost / area) if area else 0.0
	row.total_cost = total_cost
	row.cost_per_m2 = (total_cost / area) if area else 0.0


@frappe.whitelist()
def apply_estimation_template(project_estimate: str | None = None, estimation_template: str | None = None, boq_item: str | None = None):
	"""
	Return activity rows hydrated from Estimation Template for the given BOQ Item area.

	Used by the client when Estimation Template is selected.
	"""
	if not estimation_template:
		frappe.throw(_("Estimation Template is required"))

	template = frappe.get_doc("Estimation Template", estimation_template)
	est_area = 0.0
	if boq_item:
		est_area = flt(frappe.db.get_value("BOQ Item", boq_item, "total_qty"))

	rows = []
	for activity in template.activities or []:
		row = {
			"manufacturer": activity.manufacturer,
			"material": activity.material,
			"est_area": est_area,
			"est_qty": flt(activity.est_qty),
			"unit_price": flt(activity.unit_price),
			"skilled": flt(activity.skilled),
			"unskilled": flt(activity.unskilled),
			"skilled_rate": flt(activity.skilled_rate),
			"unskilled_rate": flt(activity.unskilled_rate),
			"remarks": "",
		}
		# Use a simple namespace for calculate_activity_row
		ns = frappe._dict(row)
		calculate_activity_row(ns)
		row.update(
			{
				"material_cost": flt(ns.material_cost),
				"labour_cost": flt(ns.labour_cost),
				"labour_cost_per_m2": flt(ns.labour_cost_per_m2),
				"total_cost": flt(ns.total_cost),
				"cost_per_m2": flt(ns.cost_per_m2),
			}
		)
		rows.append(row)

	return {"activities": rows, "est_area": est_area}


@frappe.whitelist()
def get_project_estimates(project: str):
	"""List Project Estimates for a Project (for Project form panel)."""
	if not project:
		frappe.throw(_("Project is required"))
	if not frappe.has_permission("Project", "read", project):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	rows = frappe.get_all(
		"Project Estimate",
		filters={"project": project},
		fields=[
			"name",
			"boq_bill",
			"boq_item",
			"estimation_template",
			"total_material_cost",
			"total_labour_cost",
			"total_estimated_cost",
			"cost_per_m2",
			"docstatus",
			"modified",
		],
		order_by="modified desc",
	)

	# Enrich with BOQ item labels
	item_names = list({r.boq_item for r in rows if r.boq_item})
	item_map = {}
	if item_names:
		item_map = {
			d.name: (d.item_code or d.label or d.description or d.name)
			for d in frappe.get_all(
				"BOQ Item",
				filters={"name": ("in", item_names)},
				fields=["name", "item_code", "label", "description"],
			)
		}

	for row in rows:
		row["boq_item_label"] = item_map.get(row.boq_item) or row.boq_item
		row["status"] = {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(row.docstatus, "")

	return {"estimates": rows, "count": len(rows)}


@frappe.whitelist()
def get_boq_estimate_overruns(sales_invoice: str | None = None, boq_items: str | None = None):
	"""
	Return BOQ items on a Sales Invoice (or explicit list) where actual cost exceeds estimate.

	Soft-alert only — never throws for overrun.
	"""
	import json

	from construction_management.api.boq_ledger import get_cost_to_date

	item_names = []
	if sales_invoice and frappe.db.exists("Sales Invoice", sales_invoice):
		item_names = [
			r.boq_item
			for r in frappe.get_all(
				"Sales Invoice Item",
				filters={"parent": sales_invoice, "boq_item": ["is", "set"]},
				fields=["boq_item"],
			)
			if r.boq_item
		]

	if not item_names and boq_items:
		if isinstance(boq_items, str):
			try:
				boq_items = json.loads(boq_items)
			except Exception:
				boq_items = [x.strip() for x in boq_items.split(",") if x.strip()]
		item_names = list(boq_items or [])

	item_names = list({n for n in item_names if n})
	overruns = []

	for name in item_names:
		boq = frappe.db.get_value(
			"BOQ Item",
			name,
			["name", "item_code", "label", "description", "total_estimated_cost", "total_qty"],
			as_dict=True,
		)
		if not boq:
			continue

		estimated = flt(boq.total_estimated_cost)
		if estimated <= 0:
			continue

		actual = flt(get_cost_to_date(name))
		if actual <= estimated:
			continue

		exceed = actual - estimated
		pct = (exceed / estimated) * 100.0 if estimated else 0.0
		overruns.append(
			{
				"boq_item": boq.name,
				"item_code": boq.item_code or "",
				"label": boq.label or boq.description or boq.name,
				"estimated": estimated,
				"actual": actual,
				"exceed": exceed,
				"percent_over": pct,
			}
		)

	return {
		"has_overruns": bool(overruns),
		"count": len(overruns),
		"overruns": overruns,
	}
