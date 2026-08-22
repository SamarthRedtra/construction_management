# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from construction_management.api.purchase_receipt_utils import get_purchase_billable_amounts
from construction_management.overrides.purchase_invoice import (
	PurchaseInvoiceOverride,
	apply_purchase_deductions,
)

COMPANY = "SKADA CONSTRUCTION L.L.C"
PROJECT = "SKD-46"
PO_WITH_ADVANCE = "SKD-LPO-00220"
RETENTION_ACCOUNT = "Retention Payables - SC"
ADVANCE_ACCOUNT = "Advance to subcontractor - SC"


def _patch_accounts_settings_get_single(original):
	def _wrapper(doctype, fieldname, *args, **kwargs):
		if doctype == "Accounts Settings" and fieldname == "book_stock_expense_gl_entries":
			return 0
		return original(doctype, fieldname, *args, **kwargs)

	return _wrapper


class TestPurchaseInvoiceGLDeductions(IntegrationTestCase):
	"""GL posting for subcontractor PI retention/advance deductions (incl. skip-advance)."""

	def setUp(self):
		if not frappe.db.exists("BOQ Settings", COMPANY):
			self.skipTest("BOQ Settings missing for smoke company")
		settings = frappe.db.get_value(
			"BOQ Settings",
			COMPANY,
			["purchase_retention_account", "purchase_advance_account"],
			as_dict=True,
		)
		if not settings.get("purchase_retention_account") or not settings.get("purchase_advance_account"):
			self.skipTest("Purchase retention/advance accounts not configured")

	@patch("construction_management.overrides.purchase_invoice._check_pr_deductions", return_value=(False, False))
	@patch("construction_management.overrides.purchase_invoice._get_linked_purchase_order")
	def test_skip_advance_reduces_advance_row_only(self, mock_po_link, _mock_pr_deductions):
		mock_po_link.return_value = PO_WITH_ADVANCE
		doc = self._make_billable_doc(skip_line=True)
		apply_purchase_deductions(doc)

		retention_rows = [row for row in doc.items if row.item_code == "RETENTION-DEDUCTION"]
		advance_rows = [row for row in doc.items if row.item_code == "ADVANCE-DEDUCTION"]

		self.assertEqual(len(retention_rows), 1)
		self.assertEqual(flt(retention_rows[0].amount), -10000.0)
		self.assertEqual(len(advance_rows), 0)

	@patch("construction_management.overrides.purchase_invoice._check_pr_deductions", return_value=(False, False))
	@patch("construction_management.overrides.purchase_invoice._get_linked_purchase_order")
	def test_baseline_has_retention_and_advance_rows(self, mock_po_link, _mock_pr_deductions):
		mock_po_link.return_value = PO_WITH_ADVANCE
		doc = self._make_billable_doc(skip_line=False)
		apply_purchase_deductions(doc)

		retention_rows = [row for row in doc.items if row.item_code == "RETENTION-DEDUCTION"]
		advance_rows = [row for row in doc.items if row.item_code == "ADVANCE-DEDUCTION"]

		self.assertEqual(len(retention_rows), 1)
		self.assertEqual(flt(retention_rows[0].amount), -10000.0)
		self.assertEqual(len(advance_rows), 1)
		self.assertEqual(flt(advance_rows[0].amount), -10000.0)

	def test_billable_amounts_match_skip_advance_rules(self):
		baseline = self._make_billable_doc(skip_line=False)
		skipped = self._make_billable_doc(skip_line=True)

		base_total, base_advance = get_purchase_billable_amounts(baseline)
		skip_total, skip_advance = get_purchase_billable_amounts(skipped)

		self.assertEqual(base_total, 100000.0)
		self.assertEqual(base_advance, 100000.0)
		self.assertEqual(skip_total, 100000.0)
		self.assertEqual(skip_advance, 0.0)

	@patch("construction_management.overrides.purchase_invoice._check_pr_deductions", return_value=(False, False))
	@patch("construction_management.overrides.purchase_invoice._get_linked_purchase_order")
	def test_get_gl_entries_credits_boq_deduction_accounts(self, mock_po_link, _mock_pr_deductions):
		pi = self._load_smoke_draft("ACC-PINV-2026-00012")
		if not pi:
			self.skipTest("Smoke baseline draft ACC-PINV-2026-00012 not on site")

		gl = self._get_gl_entries(pi)
		retention_credit = sum(flt(e.get("credit")) for e in gl if e.get("account") == RETENTION_ACCOUNT)
		advance_credit = sum(flt(e.get("credit")) for e in gl if e.get("account") == ADVANCE_ACCOUNT)
		total_debit = sum(flt(e.get("debit")) for e in gl)
		total_credit = sum(flt(e.get("credit")) for e in gl)

		self.assertEqual(retention_credit, 10000.0)
		self.assertEqual(advance_credit, 10000.0)
		self.assertAlmostEqual(total_debit, total_credit, places=2)

	@patch("construction_management.overrides.purchase_invoice._check_pr_deductions", return_value=(False, False))
	@patch("construction_management.overrides.purchase_invoice._get_linked_purchase_order")
	def test_get_gl_entries_skip_advance_has_retention_not_advance(self, mock_po_link, _mock_pr_deductions):
		pi = self._load_smoke_draft("ACC-PINV-2026-00013")
		if not pi:
			self.skipTest("Smoke skip draft ACC-PINV-2026-00013 not on site")

		gl = self._get_gl_entries(pi)
		retention_credit = sum(flt(e.get("credit")) for e in gl if e.get("account") == RETENTION_ACCOUNT)
		advance_credit = sum(flt(e.get("credit")) for e in gl if e.get("account") == ADVANCE_ACCOUNT)

		self.assertEqual(retention_credit, 10000.0)
		self.assertEqual(advance_credit, 0.0)

	def _load_smoke_draft(self, name):
		if not frappe.db.exists("Purchase Invoice", name):
			return None
		return frappe.get_doc("Purchase Invoice", name)

	def _get_gl_entries(self, pi):
		original_get_single = frappe.db.get_single_value
		frappe.db.get_single_value = _patch_accounts_settings_get_single(original_get_single)
		try:
			return PurchaseInvoiceOverride.get_gl_entries(pi) or []
		finally:
			frappe.db.get_single_value = original_get_single

	def _make_billable_doc(self, skip_line=False):
		expense_account = frappe.db.get_value("Company", COMPANY, "default_expense_account")
		supplier = frappe.db.get_value("Purchase Order", PO_WITH_ADVANCE, "supplier")
		cost_center = frappe.db.get_value("Purchase Order", PO_WITH_ADVANCE, "cost_center")

		pi = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": COMPANY,
				"supplier": supplier,
				"project": PROJECT,
				"cost_center": cost_center,
				"currency": "AED",
				"conversion_rate": 1,
				"posting_date": frappe.utils.today(),
				"bill_date": frappe.utils.today(),
				"custom_suppliersubcontractor": "Subcontractor",
				"items": [
					{
						"item_code": "PLUNGE POOL WORKS 4 NO'S PLUNGE POOL WORKS AT 1ST FLOOR",
						"item_name": "PLUNGE POOL WORKS",
						"qty": 1,
						"rate": 100000,
						"amount": 100000,
						"net_amount": 100000,
						"base_amount": 100000,
						"base_net_amount": 100000,
						"expense_account": expense_account,
						"project": PROJECT,
						"cost_center": cost_center,
						"purchase_order": PO_WITH_ADVANCE,
						"uom": "LS",
						"conversion_factor": 1,
						"custom_skip_advance_deduction": 1 if skip_line else 0,
					}
				],
			}
		)
		return pi
