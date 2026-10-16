# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase
from frappe.utils import getdate

from construction_management.patches import repost_mrg_corrected_stock_to_2026_09_30 as repost


class TestRepostMRGCorrectedStockTo20260930(UnitTestCase):
	@patch.object(repost, "_create_reconciliations", return_value=[])
	@patch.object(repost.correction, "_mismatches", return_value=[])
	@patch.object(repost.correction, "preflight")
	@patch.object(repost, "_cancel_oct_12_reconciliations", return_value=[])
	@patch.object(repost.frappe, "set_user")
	def test_run_is_noop_when_nothing_to_cancel_and_balances_match(
		self, set_user, cancel, preflight, mismatches, create
	):
		preflight.return_value = {
			"errors": [],
			"source_rows": 192,
			"target_lines": 191,
			"targets": [],
		}

		result = repost.run()

		self.assertTrue(result["no_op"])
		self.assertEqual(result["cancelled"], [])
		self.assertEqual(result["stock_reconciliations"], [])
		self.assertEqual(result["posting_date"], "2026-09-30")
		create.assert_called_once_with([])

	@patch.object(repost.correction, "_allow_negative_stock_for_reconciliations")
	@patch.object(repost.frappe, "get_doc")
	@patch.object(repost.frappe, "get_all", return_value=["MAT-RECO-2026-00096"])
	def test_cancel_oct_12_cancels_submitted_docs(self, get_all, get_doc, allow_negative):
		allow_negative.return_value.__enter__ = MagicMock(return_value=None)
		allow_negative.return_value.__exit__ = MagicMock(return_value=False)
		document = MagicMock()
		get_doc.return_value = document

		cancelled = repost._cancel_oct_12_reconciliations()

		self.assertEqual(cancelled, ["MAT-RECO-2026-00096"])
		document.cancel.assert_called_once()
		get_all.assert_called_once()
		filters = get_all.call_args.kwargs["filters"]
		self.assertEqual(filters["posting_date"], "2026-10-12")
		self.assertEqual(filters["docstatus"], 1)

	@patch.object(repost.frappe, "new_doc")
	def test_create_reconciliations_uses_september_30(self, new_doc):
		document = MagicMock()
		document.items = [frappe._dict(warehouse="Stores - MRG")]
		new_doc.return_value = document

		created = repost._create_reconciliations(
			[
				{
					"item_code": "CP-ITEM",
					"warehouse": "Stores - MRG",
					"qty": 10,
					"valuation_rate": 5,
				}
			]
		)

		self.assertEqual(created, [document])
		self.assertEqual(document.posting_date, getdate("2026-09-30"))
		self.assertEqual(document.posting_time, "00:00:00")
		document.insert.assert_called_once()

	@patch.object(repost, "_create_reconciliations")
	@patch.object(repost.correction, "_mismatches")
	@patch.object(repost.correction, "preflight")
	@patch.object(repost, "_cancel_oct_12_reconciliations", return_value=["MAT-RECO-2026-00096"])
	@patch.object(repost.frappe, "set_user")
	def test_run_cancels_then_submits_september_docs(
		self, set_user, cancel, preflight, mismatches, create
	):
		preflight.return_value = {
			"errors": [],
			"source_rows": 192,
			"target_lines": 10,
			"targets": [{"item_code": "CP-ITEM"}],
		}
		mismatches.return_value = [
			{
				"item_code": "CP-ITEM",
				"warehouse": "Stores - MRG",
				"qty": 1,
				"valuation_rate": 2,
				"actual_qty": 0,
			}
		]
		document = MagicMock()
		document.name = "MAT-RECO-NEW"
		create.return_value = [document]

		with patch.object(
			repost.correction, "_allow_negative_stock_for_reconciliations"
		) as allow_negative:
			allow_negative.return_value.__enter__ = MagicMock(return_value=None)
			allow_negative.return_value.__exit__ = MagicMock(return_value=False)
			result = repost.run()

		document.submit.assert_called_once()
		self.assertEqual(result["cancelled"], ["MAT-RECO-2026-00096"])
		self.assertEqual(result["stock_reconciliations"], ["MAT-RECO-NEW"])
		self.assertEqual(result["posting_date"], "2026-09-30")
		self.assertFalse(result["no_op"])
