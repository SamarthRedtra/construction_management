# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from construction_management.api.quotation_boq import (
	import_boq_lines_from_estimation,
	lines_to_boq_html,
)
from construction_management.quotation_boq_print_context import build_boq_quotation_print_context


class TestQuotationBOQPrint(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.defaults.get_defaults().company

	def test_lines_to_html_includes_section_parent_sub(self):
		lines = [
			frappe._dict(
				idx=1,
				line_type="Section",
				section_title="THERMAL PROTECTION",
				description="THERMAL PROTECTION",
			),
			frappe._dict(idx=2, line_type="Parent", parent_no="1", description="Parent item"),
			frappe._dict(
				idx=3,
				line_type="Sub",
				sub_no="A",
				description="Sub item",
				uom="m2",
				qty=100,
				rate=10,
				amount=1000,
				display_mode="Normal",
			),
		]
		html = lines_to_boq_html(lines)
		self.assertIn("THERMAL PROTECTION", html)
		self.assertIn("1-", html)
		self.assertIn("A.", html)
		self.assertIn("1,000.00", html)

	def test_print_context_two_level_parent_sub_only(self):
		doc = frappe._dict(
			{
				"name": "QTN-TEST-0002",
				"company": self.company,
				"transaction_date": today(),
				"currency": "AED",
				"custom_boq_html": "",
				"custom_boq_lines": [
					frappe._dict(
						idx=1,
						line_type="Parent",
						parent_no="1",
						description="Waterproofing membrane",
					),
					frappe._dict(
						idx=2,
						line_type="Sub",
						parent_no="1",
						sub_no="A",
						description="Horizontal",
						uom="m2",
						qty=10,
						rate=50,
						amount=500,
						display_mode="Normal",
					),
					frappe._dict(
						idx=3,
						line_type="Parent",
						parent_no="2",
						description="Bituminous coating",
					),
					frappe._dict(
						idx=4,
						line_type="Sub",
						parent_no="2",
						sub_no="A",
						description="Vertical",
						uom="m2",
						qty=20,
						rate=30,
						amount=600,
						display_mode="Normal",
					),
				],
				"terms": "",
			}
		)
		ctx = build_boq_quotation_print_context(doc)
		self.assertEqual(ctx["hierarchy_mode"], "2 Level (Parent + Sub)")
		self.assertEqual(len(ctx["sections"]), 1)
		self.assertEqual(len(ctx["sections"][0]["parents"]), 2)
		self.assertEqual(ctx["totals"]["total_excl_vat"], 1100)
		self.assertIn("Waterproofing membrane", ctx["boq_html"])
		self.assertIn("1,100.00", ctx["boq_html"])

	def test_sub_attaches_by_parent_no_not_row_order(self):
		lines = [
			frappe._dict(idx=1, line_type="Parent", parent_no="1", description="Parent One"),
			frappe._dict(idx=2, line_type="Parent", parent_no="2", description="Parent Two"),
			frappe._dict(
				idx=3,
				line_type="Sub",
				parent_no="1",
				sub_no="A",
				description="Belongs to one",
				uom="m2",
				qty=5,
				rate=10,
				amount=50,
				display_mode="Normal",
			),
		]
		ctx = build_boq_quotation_print_context(
			frappe._dict(
				name="QTN-TEST",
				company=self.company,
				transaction_date=today(),
				currency="AED",
				custom_boq_lines=lines,
				terms="",
			)
		)
		parent_one = ctx["sections"][0]["parents"][0]
		parent_two = ctx["sections"][0]["parents"][1]
		self.assertEqual(parent_one["description"], "Parent One")
		self.assertEqual(len(parent_one["subs"]), 1)
		self.assertEqual(parent_one["subs"][0]["description"], "Belongs to one")
		self.assertEqual(len(parent_two["subs"]), 0)

	def test_print_context_falls_back_to_lines(self):
		doc = frappe._dict(
			{
				"name": "QTN-TEST-0001",
				"company": self.company,
				"transaction_date": today(),
				"currency": "AED",
				"custom_boq_html": "",
				"custom_boq_lines": [
					frappe._dict(
						idx=1,
						line_type="Parent",
						parent_no="1",
						description="Waterproofing",
					),
					frappe._dict(
						idx=2,
						line_type="Sub",
						sub_no="A",
						description="Horizontal",
						uom="m2",
						qty=10,
						rate=50,
						amount=500,
						display_mode="Normal",
					),
				],
				"terms": "",
			}
		)
		ctx = build_boq_quotation_print_context(doc)
		self.assertIn("Waterproofing", ctx["boq_html"])
		self.assertIn("Horizontal", ctx["boq_html"])

	def test_import_returns_child_table_rows(self):
		if not frappe.db.exists("DocType", "Project Estimation"):
			self.skipTest("project_estimation app not installed")

		estimation = frappe.get_doc(
			{
				"doctype": "Project Estimation",
				"customer": self._ensure_customer(),
				"company": self.company,
				"items": [
					{
						"task": "Section A",
						"activity_type": self._ensure_activity_type(),
						"item": self._ensure_item(),
						"quantity": 10,
						"rate": 100,
						"amount": 1000,
					},
				],
			}
		)
		estimation.insert(ignore_permissions=True)

		lines = import_boq_lines_from_estimation(estimation.name)
		self.assertTrue(isinstance(lines, list))
		self.assertEqual(lines[0]["line_type"], "Section")
		self.assertEqual(lines[1]["line_type"], "Parent")

		estimation.delete(ignore_permissions=True)

	def _ensure_customer(self):
		name = "_Test BOQ Quotation Customer"
		if not frappe.db.exists("Customer", name):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": name,
					"customer_type": "Company",
					"customer_group": "All Customer Groups",
					"territory": "All Territories",
				}
			).insert(ignore_permissions=True)
		return name

	def _ensure_item(self):
		name = "_Test BOQ Quotation Item"
		if not frappe.db.exists("Item", name):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": name,
					"item_name": name,
					"item_group": "All Item Groups",
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)
		return name

	def _ensure_activity_type(self):
		name = "_Test BOQ Activity"
		if not frappe.db.exists("Activity Type", name):
			frappe.get_doc({"doctype": "Activity Type", "activity_type": name}).insert(
				ignore_permissions=True
			)
		return name
