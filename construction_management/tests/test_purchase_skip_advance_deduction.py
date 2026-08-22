# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe.tests import UnitTestCase
from unittest.mock import patch

from construction_management.api.purchase_receipt_utils import (
	get_purchase_advance_billable_for_form,
	get_purchase_billable_amounts,
)


class TestPurchaseSkipAdvanceDeduction(UnitTestCase):
	def _make_doc(self, items, skip_doc_advance=0):
		return frappe._dict(
			{
				"items": [frappe._dict(row) for row in items],
				"custom_skip_advance_deduction": skip_doc_advance,
			}
		)

	@patch("construction_management.api.boq_invoice.get_boq_items_skip_advance")
	def test_item_row_skip_excludes_amount_without_boq_item(self, mock_skip):
		mock_skip.return_value = set()
		doc = self._make_doc(
			[
				{"item_code": "LAB-001", "amount": 1000, "custom_skip_advance_deduction": 0},
				{"item_code": "LAB-002", "amount": 500, "custom_skip_advance_deduction": 1},
			]
		)

		total_billable, advance_billable = get_purchase_billable_amounts(doc)

		self.assertEqual(total_billable, 1500)
		self.assertEqual(advance_billable, 1000)

	@patch("construction_management.api.boq_invoice.get_boq_items_skip_advance")
	def test_item_skip_excludes_amount_from_advance_base_only(self, mock_skip):
		mock_skip.return_value = {"BOQ-SKIP"}
		doc = self._make_doc(
			[
				{"item_code": "LAB-001", "amount": 1000, "boq_item": "BOQ-NORMAL"},
				{"item_code": "LAB-002", "amount": 500, "boq_item": "BOQ-SKIP"},
			]
		)

		total_billable, advance_billable = get_purchase_billable_amounts(doc)

		self.assertEqual(total_billable, 1500)
		self.assertEqual(advance_billable, 1000)

	def test_doc_skip_zeros_advance_base(self):
		doc = self._make_doc(
			[{"item_code": "LAB-001", "amount": 1000, "boq_item": "BOQ-NORMAL"}],
			skip_doc_advance=1,
		)

		total_billable, advance_billable = get_purchase_billable_amounts(doc)

		self.assertEqual(total_billable, 1000)
		self.assertEqual(advance_billable, 0)

	@patch("construction_management.api.boq_invoice.get_boq_items_skip_advance")
	def test_form_api_matches_helper(self, mock_skip):
		mock_skip.return_value = {"BOQ-SKIP"}
		items = [
			{"item_code": "LAB-001", "amount": 800, "boq_item": "BOQ-NORMAL"},
			{"item_code": "RETENTION-DEDUCTION", "amount": -80},
			{"item_code": "LAB-002", "amount": 200, "boq_item": "BOQ-SKIP"},
		]

		result = get_purchase_advance_billable_for_form(items, skip_doc_advance=0)

		self.assertEqual(result["total_billable"], 1000)
		self.assertEqual(result["advance_billable"], 800)
		self.assertEqual(set(result["skip_boq_items"]), {"BOQ-SKIP"})

	def test_deduction_items_excluded_from_both_bases(self):
		doc = self._make_doc(
			[
				{"item_code": "LAB-001", "amount": 1000, "boq_item": "BOQ-NORMAL"},
				{"item_code": "RETENTION-DEDUCTION", "amount": -100},
				{"item_code": "ADVANCE-DEDUCTION", "amount": -50},
				{"item_code": "PURCHASE-ADVANCE", "amount": 200},
			]
		)

		total_billable, advance_billable = get_purchase_billable_amounts(doc)

		self.assertEqual(total_billable, 1000)
		self.assertEqual(advance_billable, 1000)

	@patch("construction_management.api.boq_invoice.get_boq_items_skip_advance")
	def test_retention_uses_full_base_advance_uses_reduced(self, mock_skip):
		mock_skip.return_value = {"BOQ-SKIP"}
		doc = self._make_doc(
			[
				{"item_code": "LAB-001", "amount": 1000, "boq_item": "BOQ-NORMAL"},
				{"item_code": "LAB-002", "amount": 500, "boq_item": "BOQ-SKIP"},
			]
		)

		total_billable, advance_billable = get_purchase_billable_amounts(doc)
		retention_pct = 10
		advance_pct = 10

		self.assertEqual(total_billable * retention_pct / 100, 150)
		self.assertEqual(advance_billable * advance_pct / 100, 100)
