from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.api.repair_combined_si_sales_orders import _plan_splits, _row_over_billed


class TestRepairCombinedSI(UnitTestCase):
	def test_row_over_billed_detects_aggregate(self):
		row = frappe._dict(qty=100, amount=5000, so_detail="SOD-1")
		with patch(
			"construction_management.api.repair_combined_si_sales_orders.frappe.db.get_value",
			return_value={"qty": 10, "amount": 500},
		):
			self.assertTrue(_row_over_billed(row))

	def test_plan_splits_one_row_three_orders(self):
		si = frappe._dict(
			name="SI-1",
			project="PRJ",
			items=[
				frappe._dict(
					name="SII-1",
					idx=1,
					item_code="WORK",
					boq_item="BOQ-1",
					uom="M2",
					qty=300,
					amount=3000,
					sales_order="SO-C",
					so_detail="SOD-C",
					description="Work",
					income_account="Income",
					cost_center="CC",
					bill_no="B1",
					project="PRJ",
				),
			],
		)
		sources = ["SO-A", "SO-B", "SO-C"]

		def fake_so_lines(sources_arg, boq_item, item_code, uom):
			self.assertEqual(sources_arg, sources)
			return [
				frappe._dict(
					name=f"SOD-{label}",
					parent=label,
					qty=100,
					rate=10,
					amount=1000,
					uom="M2",
					stock_uom="M2",
					conversion_factor=1,
					description="Work",
					bill_no="B1",
				)
				for label in ("SO-A", "SO-B", "SO-C")
			]

		with patch(
			"construction_management.api.repair_combined_si_sales_orders._source_so_lines",
			side_effect=fake_so_lines,
		):
			plans = _plan_splits(si, sources)
		self.assertEqual(len(plans), 3)
		self.assertEqual({plan["sales_order"] for plan in plans}, set(sources))