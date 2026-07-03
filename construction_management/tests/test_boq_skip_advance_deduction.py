# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from construction_management.api.boq_invoice import (
	boq_item_skips_advance,
	create_invoice_from_boq_item,
	create_sales_order_from_selected_items,
	get_deduction_details,
)
from construction_management.tests.test_property_boq_ui import (
	create_test_boq_structure,
	create_test_customer,
	create_test_project,
)


class TestBOQSkipAdvanceDeduction(IntegrationTestCase):
	def setUp(self):
		self._rate_patcher = patch(
			"construction_management.construction_management.doctype.boq_item.boq_item.check_rate_history_table"
		)
		self._rate_patcher.start()
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=8)
		self.customer = create_test_customer(f"Skip Advance Customer {suffix}")
		self.project = create_test_project(f"SKIP-ADV-{suffix}")
		frappe.db.set_value("Project", self.project, {
			"customer": self.customer,
			"enable_progressive_boq": 1,
			"retention_percentage": 10,
			"advance_deduction": 10,
		})

		self.project_boq, self.bill, self.boq_item_normal = create_test_boq_structure(
			self.project, total_qty=10, rate=1000
		)
		self.boq_item_skip = self._create_flagged_boq_item()
		self._ensure_advance_pool(5000)

	def tearDown(self):
		self._rate_patcher.stop()
		frappe.db.rollback()

	def _create_flagged_boq_item(self):
		item = frappe.new_doc("BOQ Item")
		item.parent_bill = self.bill
		item.project_boq = self.project_boq
		item.project = self.project
		item.description = "Skip Advance Item"
		item.unit = "Nos"
		item.total_qty = 10
		item.rate = 1000
		item.skip_advance_deduction = 1
		item.insert(ignore_permissions=True)
		return item.name

	def _ensure_advance_pool(self, amount):
		adv = frappe.new_doc("BOQ Advance Payment")
		adv.project = self.project
		adv.amount = amount
		adv.date = today()
		adv.insert(ignore_permissions=True)
		adv.submit()

	def test_boq_item_skips_advance_helper(self):
		self.assertTrue(boq_item_skips_advance(self.boq_item_skip))
		self.assertFalse(boq_item_skips_advance(self.boq_item_normal))

	def test_sales_order_skips_advance_for_flagged_item(self):
		result = create_sales_order_from_selected_items(
			project=self.project,
			items=[{"boq_item": self.boq_item_skip, "qty": 1}],
			auto_submit=0,
		)
		self.assertEqual(result.get("status"), "success")
		so = frappe.get_doc("Sales Order", result["name"])
		advance_rows = [
			row for row in so.items if row.item_code == "ADVANCE-DEDUCTION" and row.boq_item == self.boq_item_skip
		]
		self.assertEqual(len(advance_rows), 0)

	def test_sales_order_advance_only_on_eligible_items(self):
		result = create_sales_order_from_selected_items(
			project=self.project,
			items=[
				{"boq_item": self.boq_item_skip, "qty": 1},
				{"boq_item": self.boq_item_normal, "qty": 1},
			],
			auto_submit=0,
		)
		self.assertEqual(result.get("status"), "success")
		so = frappe.get_doc("Sales Order", result["name"])
		skip_rows = [row for row in so.items if row.item_code == "ADVANCE-DEDUCTION" and row.boq_item == self.boq_item_skip]
		normal_rows = [row for row in so.items if row.item_code == "ADVANCE-DEDUCTION" and row.boq_item == self.boq_item_normal]
		self.assertEqual(len(skip_rows), 0)
		self.assertEqual(len(normal_rows), 1)
		self.assertEqual(flt(normal_rows[0].amount), -100.0)

	def test_get_deduction_details_excludes_skipped_boq_items(self):
		items = [
			{"boq_item": self.boq_item_skip, "amount": 5000, "item_code": "ITEM-A"},
			{"boq_item": self.boq_item_normal, "amount": 3000, "item_code": "ITEM-B"},
		]
		details = get_deduction_details(self.project, items)
		self.assertIn(self.boq_item_skip, details.get("skip_advance_boq_items", []))
		self.assertEqual(flt(details["suggested_advance"]), 300.0)

	def test_direct_invoice_ignores_advance_for_flagged_item(self):
		frappe.db.set_value("BOQ Item", self.boq_item_skip, "current_qty", 1)
		result = create_invoice_from_boq_item(
			project=self.project,
			boq_item=self.boq_item_skip,
			current_qty=1,
			apply_retention=0,
			advance_deduction=500,
			is_proforma=0,
		)
		self.assertIn("invoice", result)
		inv = frappe.get_doc("Sales Invoice", result["invoice"])
		advance_rows = [row for row in inv.items if row.item_code == "ADVANCE-DEDUCTION"]
		self.assertEqual(len(advance_rows), 0)
		self.assertEqual(flt(result.get("advance_deduction")), 0)
