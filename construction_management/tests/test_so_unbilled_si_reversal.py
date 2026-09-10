# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from construction_management.overrides.unearned_revenue import (
	get_remaining_so_unbilled_balance,
	get_so_unbilled_jv_amount,
)


class TestSOUnbilledInvoiceReversal(IntegrationTestCase):
	"""SI must fully reverse remaining SO unbilled JV; sales = invoice gross minus that reversal."""

	SO = "SAL-ORD-2026-00318-2"
	SI = "ACC-SINV-2026-00252"
	UNBILLED = "Unbilled Receivables - MRG"

	def setUp(self):
		if not frappe.db.exists("Sales Invoice", self.SI):
			self.skipTest(f"{self.SI} not on site")

	def test_so_unbilled_jv_amount_matches_ca(self):
		amount = get_so_unbilled_jv_amount(self.SO)
		self.assertAlmostEqual(amount, 217271.88, places=2)

	def test_remaining_unbilled_before_repost_excludes_current_si(self):
		remaining = get_remaining_so_unbilled_balance(
			self.SO, self.UNBILLED, exclude_si=self.SI
		)
		self.assertAlmostEqual(remaining, 217271.88, places=2)

	@patch("construction_management.overrides.sales_invoice.find_journal_entry_by_so")
	def test_invoice_gl_sales_is_gross_minus_full_unbilled(self, mock_find_je):
		from construction_management.overrides.sales_invoice import SalesInvoiceOverride

		mock_find_je.return_value = "ACC-JV-2026-03034"
		si = frappe.get_doc("Sales Invoice", self.SI)

		discount = flt(si.base_discount_amount) or flt(si.discount_amount)
		gross_line = sum(
			flt(row.base_amount) or flt(row.amount)
			for row in si.items
			if flt(row.amount) > 0 and row.item_code not in ("RETENTION-DEDUCTION", "ADVANCE-DEDUCTION")
		)
		gross_line = flt(gross_line) - discount
		expected_unbilled = get_so_unbilled_jv_amount(self.SO)
		expected_sales = flt(gross_line - expected_unbilled, 2)

		orig = frappe.db.get_single_value

		def patched(dt, fn, *a, **k):
			if dt == "Accounts Settings" and fn == "book_stock_expense_gl_entries":
				return 0
			return orig(dt, fn, *a, **k)

		frappe.db.get_single_value = patched
		try:
			# Rebuild budget as for a draft (do not exclude this SI)
			from construction_management.overrides.unearned_revenue import get_remaining_so_unbilled_balance

			remaining = get_remaining_so_unbilled_balance(self.SO, self.UNBILLED, exclude_si=None)
			# Already posted SI consumed 184763.99 — simulate fresh post with full budget
			with patch(
				"construction_management.overrides.sales_invoice.get_remaining_so_unbilled_balance",
				return_value=expected_unbilled,
			):
				gl = SalesInvoiceOverride.get_gl_entries(si) or []
		finally:
			frappe.db.get_single_value = orig

		sales_cr = sum(flt(e.get("credit")) for e in gl if e.get("account") == "Sales - MRG")
		unbilled_cr = sum(flt(e.get("credit")) for e in gl if e.get("account") == self.UNBILLED)

		self.assertAlmostEqual(unbilled_cr, expected_unbilled, places=2)
		self.assertAlmostEqual(sales_cr, expected_sales, places=2)
		if not discount:
			self.assertAlmostEqual(sales_cr, 46876.68, places=0)


class TestSOUnbilledLeftoverOnUnlinkedLine(IntegrationTestCase):
	"""Unlinked Sales lines must still consume leftover SO unearned (ACC-SINV-2026-00268)."""

	SO = "SAL-ORD-2026-00261-2"
	SI = "ACC-SINV-2026-00268"
	UNBILLED = "Unbilled Receivables - MRG"
	SALES = "Sales - MRG"
	RETENTION = "Project Retention - MRG"
	EXPECTED_UNBILLED = 635663.30
	EXPECTED_SALES = 2605.57
	EXPECTED_RETENTION = 78650.89

	def setUp(self):
		if not frappe.db.exists("Sales Invoice", self.SI):
			self.skipTest(f"{self.SI} not on site")

	@patch("construction_management.overrides.sales_invoice.get_remaining_so_unbilled_balance")
	@patch("construction_management.overrides.sales_invoice.find_journal_entry_by_so")
	def test_unlinked_line_consumes_leftover_unearned(self, mock_find_je, mock_remaining):
		from construction_management.overrides.sales_invoice import SalesInvoiceOverride

		mock_find_je.return_value = "ACC-JV-2026-03933"
		mock_remaining.return_value = self.EXPECTED_UNBILLED
		si = frappe.get_doc("Sales Invoice", self.SI)

		orig = frappe.db.get_single_value

		def patched(dt, fn, *a, **k):
			if dt == "Accounts Settings" and fn == "book_stock_expense_gl_entries":
				return 0
			return orig(dt, fn, *a, **k)

		frappe.db.get_single_value = patched
		try:
			gl = SalesInvoiceOverride.get_gl_entries(si) or []
		finally:
			frappe.db.get_single_value = orig

		sales_cr = sum(flt(e.get("credit")) for e in gl if e.get("account") == self.SALES)
		unbilled_cr = sum(flt(e.get("credit")) for e in gl if e.get("account") == self.UNBILLED)
		retention_dr = sum(flt(e.get("debit")) for e in gl if e.get("account") == self.RETENTION)
		total_debit = sum(flt(e.get("debit")) for e in gl)
		total_credit = sum(flt(e.get("credit")) for e in gl)

		self.assertAlmostEqual(unbilled_cr, self.EXPECTED_UNBILLED, places=2)
		self.assertAlmostEqual(sales_cr, self.EXPECTED_SALES, places=2)
		self.assertAlmostEqual(retention_dr, self.EXPECTED_RETENTION, places=2)
		self.assertAlmostEqual(total_debit, total_credit, places=2)


class TestSOUnbilledDecreaseDebitsSales(IntegrationTestCase):
	"""Invoice work below SO unbilled (discount) must reverse the full JV and debit Sales.

	Suhana example SAL-ORD-2026-00292 / ACC-SINV-2026-00266-2:
	Unbilled Cr 83655.38, Sales Dr 17032.28, discount stays in the sales pot.
	"""

	SO = "SAL-ORD-2026-00292"
	SI = "ACC-SINV-2026-00266-2"
	UNBILLED = "Unbilled Receivables - MRG"
	SALES = "Sales - MRG"
	RETENTION = "Project Retention - MRG"
	ADVANCE = "Advance from customer - MRG"
	DEBTORS = "Debtors - MRG"
	VAT = "VAT 5% - MRG"
	EXPECTED_UNBILLED = 83655.38
	EXPECTED_SALES_DR = 17032.28
	EXPECTED_RETENTION = 10632.81
	EXPECTED_ADVANCE = 2658.20

	def setUp(self):
		if not frappe.db.exists("Sales Invoice", self.SI):
			self.skipTest(f"{self.SI} not on site")

	@patch("construction_management.overrides.sales_invoice.get_remaining_so_unbilled_balance")
	@patch("construction_management.overrides.sales_invoice.find_journal_entry_by_so")
	def test_shortfall_reverses_full_unbilled_and_debits_sales(self, mock_find_je, mock_remaining):
		from construction_management.overrides.sales_invoice import SalesInvoiceOverride

		mock_find_je.return_value = "ACC-JV-2026-02056"
		mock_remaining.return_value = self.EXPECTED_UNBILLED
		si = frappe.get_doc("Sales Invoice", self.SI)

		orig = frappe.db.get_single_value

		def patched(dt, fn, *a, **k):
			if dt == "Accounts Settings" and fn == "book_stock_expense_gl_entries":
				return 0
			return orig(dt, fn, *a, **k)

		frappe.db.get_single_value = patched
		try:
			gl = SalesInvoiceOverride.get_gl_entries(si) or []
		finally:
			frappe.db.get_single_value = orig

		sales_cr = sum(flt(e.get("credit")) for e in gl if e.get("account") == self.SALES)
		sales_dr = sum(flt(e.get("debit")) for e in gl if e.get("account") == self.SALES)
		unbilled_cr = sum(flt(e.get("credit")) for e in gl if e.get("account") == self.UNBILLED)
		retention_dr = sum(flt(e.get("debit")) for e in gl if e.get("account") == self.RETENTION)
		advance_dr = sum(flt(e.get("debit")) for e in gl if e.get("account") == self.ADVANCE)
		debtors_dr = sum(flt(e.get("debit")) for e in gl if e.get("account") == self.DEBTORS)
		vat_cr = sum(flt(e.get("credit")) for e in gl if e.get("account") == self.VAT)
		total_debit = sum(flt(e.get("debit")) for e in gl)
		total_credit = sum(flt(e.get("credit")) for e in gl)

		self.assertAlmostEqual(unbilled_cr, self.EXPECTED_UNBILLED, places=2)
		self.assertAlmostEqual(sales_dr - sales_cr, self.EXPECTED_SALES_DR, places=2)
		self.assertAlmostEqual(retention_dr, self.EXPECTED_RETENTION, places=2)
		self.assertAlmostEqual(advance_dr, self.EXPECTED_ADVANCE, places=2)
		self.assertAlmostEqual(debtors_dr, 55998.69, places=2)
		self.assertAlmostEqual(vat_cr, 2666.60, places=2)
		self.assertAlmostEqual(total_debit, total_credit, places=2)
