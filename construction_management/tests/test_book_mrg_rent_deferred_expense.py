# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase
from frappe.utils import add_days, getdate, today

from construction_management.patches.book_mrg_rent_deferred_expense import (
	INVOICES,
	execute,
)


class TestBookMRGRentDeferredExpense(UnitTestCase):
	@patch("erpnext.accounts.deferred_revenue.book_deferred_income_or_expense")
	@patch(
		"construction_management.patches.book_mrg_rent_deferred_expense._load_invoice"
	)
	def test_books_only_submitted_deferred_invoices_through_yesterday(self, load_invoice, book):
		cutoff = getdate(add_days(today(), -1))
		loaded = {
			INVOICES[0]: frappe._dict(name=INVOICES[0]),
			INVOICES[1]: frappe._dict(name=INVOICES[1]),
		}

		def _load(name, passed_cutoff):
			self.assertEqual(passed_cutoff, cutoff)
			return loaded.get(name)

		load_invoice.side_effect = _load

		execute()

		self.assertEqual(book.call_count, 2)
		booked_names = [call.args[0].name for call in book.call_args_list]
		self.assertEqual(booked_names, [INVOICES[0], INVOICES[1]])
		for call in book.call_args_list:
			self.assertIsNone(call.args[1])
			self.assertEqual(call.args[2], cutoff)

	@patch("erpnext.accounts.deferred_revenue.book_deferred_income_or_expense")
	@patch(
		"construction_management.patches.book_mrg_rent_deferred_expense.frappe.db.exists",
		return_value=False,
	)
	def test_skips_invoices_missing_on_this_site(self, _exists, book):
		execute()
		book.assert_not_called()

	@patch(
		"construction_management.patches.book_mrg_rent_deferred_expense.frappe.get_doc"
	)
	@patch(
		"construction_management.patches.book_mrg_rent_deferred_expense.frappe.db.exists",
		return_value=True,
	)
	def test_load_invoice_skips_draft(self, _exists, get_doc):
		from construction_management.patches.book_mrg_rent_deferred_expense import _load_invoice

		get_doc.return_value = frappe._dict(
			name=INVOICES[0],
			docstatus=0,
			items=[],
		)
		self.assertIsNone(_load_invoice(INVOICES[0], getdate("2026-09-23")))
