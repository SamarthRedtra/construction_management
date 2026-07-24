# Copyright (c) 2026, Construction Management
# License: MIT

"""Runnable site smoke suite for Project Estimation.

Usage:
  bench --site skada.local execute construction_management.tests.run_project_estimation_smoke.run
"""

from __future__ import annotations

import frappe
from frappe.utils import flt


def run():
	results = []

	def check(name: str, cond: bool, detail: str = ""):
		results.append((name, bool(cond), detail))
		print(("PASS" if cond else "FAIL"), "-", name, detail or "")

	from construction_management.api.project_estimate import (
		apply_estimation_template,
		calculate_activity_row,
		get_boq_estimate_overruns,
		get_project_estimates,
	)
	from construction_management.raven_integrations.project_channel import (
		get_channel_name_for_project,
	)

	# 1) Excel formulas
	row = frappe._dict(
		est_qty=7.5,
		unit_price=11.5,
		skilled=4,
		unskilled=8,
		skilled_rate=150,
		unskilled_rate=120,
		est_area=1000,
	)
	calculate_activity_row(row)
	check(
		"excel formulas",
		abs(flt(row.material_cost) - 86.25) < 0.01
		and abs(flt(row.labour_cost) - 1560) < 0.01
		and abs(flt(row.total_cost) - 1646.25) < 0.01,
		f"mat={row.material_cost} lab={row.labour_cost}",
	)

	# 2) DocTypes / panel field
	check("Estimation Template DocType", bool(frappe.db.exists("DocType", "Estimation Template")))
	check("Project Estimate DocType", bool(frappe.db.exists("DocType", "Project Estimate")))
	check(
		"Project estimates HTML field",
		bool(frappe.db.exists("Custom Field", "Project-custom_project_estimates_html")),
	)

	# 3) Live BOQ context
	ctx_rows = frappe.db.sql(
		"""
		SELECT bi.name, bi.parent_bill, bi.project, bi.total_qty
		FROM `tabBOQ Item` bi
		WHERE IFNULL(bi.total_qty, 0) > 0
			AND bi.parent_bill IS NOT NULL
			AND bi.project IS NOT NULL
		ORDER BY bi.modified DESC
		LIMIT 1
		""",
		as_dict=True,
	)
	check("BOQ context available", bool(ctx_rows), str(ctx_rows[0] if ctx_rows else None))
	if not ctx_rows:
		return _finish(results)
	ctx = ctx_rows[0]

	tpl = "SMOKE-Waterproofing-Estimate"
	_cleanup_smoke_docs(tpl)

	# 4) Template
	doc = frappe.get_doc(
		{
			"doctype": "Estimation Template",
			"template_name": tpl,
			"activities": [
				{
					"manufacturer": "SHERIDAN",
					"material": "NEOPOL SRS45",
					"est_qty": 7.5,
					"unit_price": 11.5,
					"skilled": 4,
					"unskilled": 8,
					"skilled_rate": 150,
					"unskilled_rate": 120,
				},
				{
					"manufacturer": "SHERIDAN",
					"material": "NEOSEAL 509",
					"est_qty": 40,
					"unit_price": 215,
					"skilled": 0,
					"unskilled": 6,
					"skilled_rate": 150,
					"unskilled_rate": 120,
				},
			],
		}
	)
	doc.insert(ignore_permissions=True)
	check("create Estimation Template", doc.name == tpl, f"rows={len(doc.activities)}")

	# 5) Apply template
	hydrated = apply_estimation_template(estimation_template=tpl, boq_item=ctx.name)
	check(
		"apply template",
		len(hydrated["activities"]) == 2
		and abs(flt(hydrated["est_area"]) - flt(ctx.total_qty)) < 0.0001,
		f"area={hydrated['est_area']} qty={ctx.total_qty}",
	)

	# 6) Submit + post to BOQ
	boq = frappe.get_doc("BOQ Item", ctx.name)
	snapshot = {
		"estimated_material_cost_per_unit": flt(boq.estimated_material_cost_per_unit),
		"estimated_labour_cost_per_unit": flt(boq.estimated_labour_cost_per_unit),
		"estimated_material_cost": flt(boq.estimated_material_cost),
		"estimated_labour_cost": flt(boq.estimated_labour_cost),
		"total_estimated_cost": flt(boq.total_estimated_cost),
	}

	estimate = frappe.get_doc(
		{
			"doctype": "Project Estimate",
			"project": ctx.project,
			"boq_bill": ctx.parent_bill,
			"boq_item": ctx.name,
			"estimation_template": tpl,
			"activities": hydrated["activities"],
		}
	)
	estimate.insert(ignore_permissions=True)
	estimate.submit()
	check("submit Project Estimate", estimate.docstatus == 1, estimate.name)
	check(
		"estimate totals",
		flt(estimate.total_estimated_cost) > 0
		and abs(
			flt(estimate.total_estimated_cost)
			- (flt(estimate.total_material_cost) + flt(estimate.total_labour_cost))
		)
		< 0.01,
		f"total={estimate.total_estimated_cost}",
	)

	boq.reload()
	qty = flt(boq.total_qty)
	mat_pu = flt(estimate.total_material_cost) / qty
	lab_pu = flt(estimate.total_labour_cost) / qty
	check(
		"posted material/unit to BOQ",
		abs(flt(boq.estimated_material_cost_per_unit) - mat_pu) < 0.01,
		f"boq={boq.estimated_material_cost_per_unit} expect={mat_pu}",
	)
	check(
		"posted labour/unit to BOQ",
		abs(flt(boq.estimated_labour_cost_per_unit) - lab_pu) < 0.01,
		f"boq={boq.estimated_labour_cost_per_unit} expect={lab_pu}",
	)
	check("BOQ total_estimated_cost > 0", flt(boq.total_estimated_cost) > 0, str(boq.total_estimated_cost))

	# 7) List API
	listed = get_project_estimates(ctx.project)
	check(
		"get_project_estimates lists submitted",
		estimate.name in [r.name for r in listed["estimates"]],
		f"count={listed['count']}",
	)

	# 8) Soft overrun API
	ovr = get_boq_estimate_overruns(boq_items=[ctx.name])
	check(
		"overrun API soft response",
		"has_overruns" in ovr and isinstance(ovr["overruns"], list),
		str(ovr["count"]),
	)

	# 9) Link validation
	other = frappe.db.sql(
		"SELECT name FROM `tabBOQ Bill` WHERE project=%s AND name!=%s LIMIT 1",
		(ctx.project, ctx.parent_bill),
	)
	if other:
		bad = frappe.get_doc(
			{
				"doctype": "Project Estimate",
				"project": ctx.project,
				"boq_bill": other[0][0],
				"boq_item": ctx.name,
				"estimation_template": tpl,
				"activities": hydrated["activities"],
			}
		)
		threw = False
		try:
			bad.insert(ignore_permissions=True)
		except frappe.ValidationError:
			threw = True
		check("rejects mismatched bill/item", threw)
	else:
		check("rejects mismatched bill/item", True, "skipped-no-alt-bill")

	# 10) Raven naming
	ch = get_channel_name_for_project(
		frappe._dict(
			name="X",
			project_name="Combo Waterproofing",
			custom_project_no="SK-2026-014",
		)
	)
	check("raven channel includes project no", ch.startswith("SK-2026-014") and "Combo" in ch, ch)

	# Cleanup
	estimate.cancel()
	frappe.db.set_value("BOQ Item", ctx.name, snapshot, update_modified=False)
	_cleanup_smoke_docs(tpl)
	frappe.db.commit()
	check("cleanup done", not frappe.db.exists("Estimation Template", tpl))

	return _finish(results)


def _cleanup_smoke_docs(tpl: str):
	for pe in frappe.get_all("Project Estimate", filters={"estimation_template": tpl}, pluck="name"):
		d = frappe.get_doc("Project Estimate", pe)
		if d.docstatus == 1:
			d.cancel()
		frappe.delete_doc("Project Estimate", pe, force=1, ignore_permissions=True)
	if frappe.db.exists("Estimation Template", tpl):
		frappe.delete_doc("Estimation Template", tpl, force=1, ignore_permissions=True)


def _finish(results):
	failed = [n for n, c, _ in results if not c]
	print("\n==== PROJECT ESTIMATION SMOKE SUMMARY ====")
	print(f"{len(results) - len(failed)}/{len(results)} passed")
	if failed:
		print("FAILED:", ", ".join(failed))
		frappe.throw(f"Smoke failed: {', '.join(failed)}")
	print("ALL SMOKE TESTS PASSED")
	return {"passed": len(results) - len(failed), "total": len(results), "failed": failed}
