# Copyright (c) 2026, Construction Management
# License: MIT

"""Smoke tests for Project Estimation end-to-end flow."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from construction_management.api.project_estimate import (
	apply_estimation_template,
	calculate_activity_row,
	get_boq_estimate_overruns,
	get_project_estimates,
)


class TestProjectEstimationSmoke(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.template_name = "SMOKE-Waterproofing-Estimate"
		cls.estimate_name = None
		cls.boq_item = None
		cls.project = None
		cls.boq_bill = None
		cls._snapshot = None

	@classmethod
	def tearDownClass(cls):
		# Restore BOQ estimate fields if we posted
		if cls.boq_item and cls._snapshot:
			frappe.db.set_value("BOQ Item", cls.boq_item, cls._snapshot, update_modified=False)
		if cls.estimate_name and frappe.db.exists("Project Estimate", cls.estimate_name):
			doc = frappe.get_doc("Project Estimate", cls.estimate_name)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc("Project Estimate", cls.estimate_name, force=1, ignore_permissions=True)
		# Cancelled docs leave amend trail; wipe any leftover drafts with our template
		for name in frappe.get_all(
			"Project Estimate",
			filters={"estimation_template": cls.template_name},
			pluck="name",
		):
			doc = frappe.get_doc("Project Estimate", name)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc("Project Estimate", name, force=1, ignore_permissions=True)
		if frappe.db.exists("Estimation Template", cls.template_name):
			frappe.delete_doc("Estimation Template", cls.template_name, force=1, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def _pick_boq_context(self):
		"""Find a Project + Bill + Item with qty > 0 for smoke posting."""
		item = frappe.db.sql(
			"""
			SELECT bi.name, bi.parent_bill, bi.project, bi.total_qty
			FROM `tabBOQ Item` bi
			INNER JOIN `tabProject` p ON p.name = bi.project
			WHERE IFNULL(bi.total_qty, 0) > 0
				AND bi.parent_bill IS NOT NULL
				AND bi.project IS NOT NULL
			ORDER BY bi.modified DESC
			LIMIT 1
			""",
			as_dict=True,
		)
		self.assertTrue(item, "No BOQ Item with qty found for smoke test")
		row = item[0]
		self.__class__.project = row.project
		self.__class__.boq_bill = row.parent_bill
		self.__class__.boq_item = row.name
		return row

	def test_01_excel_activity_formulas(self):
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
		self.assertAlmostEqual(flt(row.material_cost), 86.25, places=2)
		self.assertAlmostEqual(flt(row.labour_cost), 1560.0, places=2)
		self.assertAlmostEqual(flt(row.labour_cost_per_m2), 1.56, places=2)
		self.assertAlmostEqual(flt(row.total_cost), 1646.25, places=2)
		self.assertAlmostEqual(flt(row.cost_per_m2), 1.64625, places=4)

	def test_02_create_estimation_template(self):
		if frappe.db.exists("Estimation Template", self.template_name):
			frappe.delete_doc("Estimation Template", self.template_name, force=1)

		doc = frappe.get_doc(
			{
				"doctype": "Estimation Template",
				"template_name": self.template_name,
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
		frappe.db.commit()
		self.assertEqual(doc.name, self.template_name)
		self.assertEqual(len(doc.activities), 2)

	def test_03_apply_template_uses_boq_area(self):
		ctx = self._pick_boq_context()
		if not frappe.db.exists("Estimation Template", self.template_name):
			self.test_02_create_estimation_template()

		result = apply_estimation_template(
			estimation_template=self.template_name,
			boq_item=ctx.name,
		)
		self.assertTrue(result["activities"])
		self.assertEqual(len(result["activities"]), 2)
		self.assertAlmostEqual(flt(result["est_area"]), flt(ctx.total_qty), places=4)
		for activity in result["activities"]:
			self.assertAlmostEqual(flt(activity["est_area"]), flt(ctx.total_qty), places=4)
			self.assertGreater(flt(activity["total_cost"]), 0)

	def test_04_project_estimate_submit_posts_to_boq(self):
		ctx = self._pick_boq_context()
		if not frappe.db.exists("Estimation Template", self.template_name):
			self.test_02_create_estimation_template()

		boq = frappe.get_doc("BOQ Item", ctx.name)
		self.__class__._snapshot = {
			"estimated_material_cost_per_unit": flt(boq.estimated_material_cost_per_unit),
			"estimated_labour_cost_per_unit": flt(boq.estimated_labour_cost_per_unit),
			"estimated_material_cost": flt(boq.estimated_material_cost),
			"estimated_labour_cost": flt(boq.estimated_labour_cost),
			"total_estimated_cost": flt(boq.total_estimated_cost),
		}

		hydrated = apply_estimation_template(
			estimation_template=self.template_name,
			boq_item=ctx.name,
		)

		estimate = frappe.get_doc(
			{
				"doctype": "Project Estimate",
				"project": ctx.project,
				"boq_bill": ctx.parent_bill,
				"boq_item": ctx.name,
				"estimation_template": self.template_name,
				"activities": hydrated["activities"],
			}
		)
		estimate.insert(ignore_permissions=True)
		estimate.submit()
		frappe.db.commit()
		self.__class__.estimate_name = estimate.name

		self.assertEqual(estimate.docstatus, 1)
		self.assertGreater(flt(estimate.total_material_cost), 0)
		self.assertGreater(flt(estimate.total_labour_cost), 0)
		self.assertAlmostEqual(
			flt(estimate.total_estimated_cost),
			flt(estimate.total_material_cost) + flt(estimate.total_labour_cost),
			places=2,
		)

		boq.reload()
		qty = flt(boq.total_qty)
		self.assertAlmostEqual(
			flt(boq.estimated_material_cost_per_unit),
			flt(estimate.total_material_cost) / qty,
			places=4,
		)
		self.assertAlmostEqual(
			flt(boq.estimated_labour_cost_per_unit),
			flt(estimate.total_labour_cost) / qty,
			places=4,
		)
		self.assertGreater(flt(boq.total_estimated_cost), 0)

	def test_05_project_estimates_list_api(self):
		ctx = self._pick_boq_context()
		result = get_project_estimates(ctx.project)
		self.assertIn("estimates", result)
		self.assertIn("count", result)
		if self.estimate_name:
			names = [r.name for r in result["estimates"]]
			self.assertIn(self.estimate_name, names)

	def test_06_overrun_api_soft_no_throw(self):
		ctx = self._pick_boq_context()
		# Soft API must never throw for overrun comparison
		result = get_boq_estimate_overruns(boq_items=[ctx.name])
		self.assertIn("has_overruns", result)
		self.assertIn("overruns", result)
		self.assertIn("count", result)
		self.assertIsInstance(result["overruns"], list)

	def test_07_link_validation_rejects_mismatched_bill(self):
		ctx = self._pick_boq_context()
		if not frappe.db.exists("Estimation Template", self.template_name):
			self.test_02_create_estimation_template()

		other_bill = frappe.db.sql(
			"""
			SELECT name FROM `tabBOQ Bill`
			WHERE project = %s AND name != %s
			LIMIT 1
			""",
			(ctx.project, ctx.parent_bill),
		)
		if not other_bill:
			self.skipTest("No alternate BOQ Bill on same project for mismatch test")

		hydrated = apply_estimation_template(
			estimation_template=self.template_name,
			boq_item=ctx.name,
		)
		estimate = frappe.get_doc(
			{
				"doctype": "Project Estimate",
				"project": ctx.project,
				"boq_bill": other_bill[0][0],
				"boq_item": ctx.name,
				"estimation_template": self.template_name,
				"activities": hydrated["activities"],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			estimate.insert(ignore_permissions=True)

	def test_08_raven_channel_name_includes_project_no(self):
		from construction_management.raven_integrations.project_channel import (
			get_channel_name_for_project,
		)

		doc = frappe._dict(
			name="PROJ-X",
			project_name="Combo Waterproofing",
			custom_project_no="SK-2026-014",
		)
		name = get_channel_name_for_project(doc)
		self.assertTrue(name.startswith("SK-2026-014"))
		self.assertIn("Combo", name)
