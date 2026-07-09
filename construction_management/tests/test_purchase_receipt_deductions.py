# Copyright (c) 2026, Construction Management
# License: MIT

from frappe.tests import UnitTestCase

from construction_management.api.purchase_receipt_utils import get_purchase_deduction_percentages


class TestPurchaseReceiptDeductions(UnitTestCase):
	def test_po_zero_percentages_do_not_use_project_fallback(self):
		doc = {"project": "1148"}
		po_doc = {
			"custom_retention_": 0,
			"custom_advance_": 0,
			"project": "1148",
		}

		retention_pct, advance_pct = get_purchase_deduction_percentages(doc, po_doc)

		self.assertEqual(retention_pct, 0)
		self.assertEqual(advance_pct, 0)

	def test_po_percentages_are_used_when_set(self):
		doc = {"project": "1148"}
		po_doc = {
			"custom_retention_": 5,
			"custom_advance_": 2,
			"project": "1148",
		}

		retention_pct, advance_pct = get_purchase_deduction_percentages(doc, po_doc)

		self.assertEqual(retention_pct, 5)
		self.assertEqual(advance_pct, 2)
