from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.patches import apply_mrg_corrected_stock_2026_10_12 as correction


class TestMrgCorrectedStock20261012(UnitTestCase):
	def test_source_rows_preserve_zero_and_negative_balances(self):
		rows = correction._source_rows()

		self.assertEqual(len(rows), 192)
		self.assertEqual(sum(row["qty"] == 0 for row in rows), 15)
		self.assertEqual(sum(row["qty"] < 0 for row in rows), 4)

	def test_targets_ignore_report_uom_and_sum_duplicate_rows(self):
		rows = [
			{"source_row": 2, "item_name": "Catalog Item", "warehouse": "Stores - MRG", "report_uom": "Kg", "qty": 0.92},
			{"source_row": 3, "item_name": "Catalog Item", "warehouse": "Stores - MRG", "report_uom": "M2", "qty": 8.435},
		]
		items = {"catalog item": [frappe._dict(name="CP-CATALOG-ITEM", item_name="Catalog Item", stock_uom="Nos")]}

		targets, errors = correction._targets(rows, items, {"Stores - MRG"})

		self.assertEqual(errors, [])
		self.assertEqual(targets[0]["stock_uom"], "Nos")
		self.assertEqual(targets[0]["qty"], 9.355)
		self.assertEqual(targets[0]["source_rows"], [2, 3])

	def test_targets_reject_missing_or_ambiguous_catalog_items(self):
		rows = [{"source_row": 2, "item_name": "Unknown", "warehouse": "Stores - MRG", "qty": 1}]

		targets, errors = correction._targets(rows, {}, {"Stores - MRG"})

		self.assertEqual(targets, [])
		self.assertEqual(errors[0]["reason"], "Controlled stock item was not uniquely resolved by item name")

	def test_negative_stock_override_is_scoped_to_the_context(self):
		class FakeStockReconciliation:
			def update_stock_ledger(self, allow_negative_stock=False):
				return allow_negative_stock

			def validate_data(self):
				self.validation_messages = ["Row #1: Negative Quantity is not allowed"]
				raise frappe.ValidationError(self.validation_messages)

		with patch.object(correction, "StockReconciliation", FakeStockReconciliation):
			with correction._allow_negative_stock_for_reconciliations():
				self.assertTrue(FakeStockReconciliation().update_stock_ledger())
				FakeStockReconciliation().validate_data()
			self.assertFalse(FakeStockReconciliation().update_stock_ledger())
			with self.assertRaises(frappe.ValidationError):
				FakeStockReconciliation().validate_data()

	@patch.object(correction, "_save_source_workbook")
	@patch.object(correction, "_save_audit", return_value=frappe._dict(file_url="/private/files/audit.csv"))
	@patch.object(correction, "_create_reconciliations", return_value=[])
	@patch.object(correction, "_mismatches", return_value=[])
	@patch.object(correction, "preflight")
	@patch.object(correction.frappe, "set_user")
	def test_run_is_a_no_op_when_every_balance_matches(
		self, set_user, preflight, mismatches, create_reconciliations, save_audit, save_source
	):
		preflight.return_value = {"errors": [], "source_rows": 192, "target_lines": 191, "targets": []}

		result = correction.run()

		self.assertTrue(result["no_op"])
		self.assertEqual(result["matched_balances"], 191)
		create_reconciliations.assert_called_once_with([])
