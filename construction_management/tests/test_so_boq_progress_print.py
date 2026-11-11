# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, money_in_words, today

from construction_management.api.so_boq_progress_excel import (
	export_sales_invoice_boq_progress_excel,
	export_sales_order_boq_progress_excel,
)
from construction_management.so_boq_progress_print_context import build


class TestSOBOQProgressPrint(FrappeTestCase):
	def _doc(self, **kwargs):
		item = frappe._dict(
			item_code="WATERPROOFING",
			item_name="Waterproofing",
			description="Supply and apply 1 coat of Primer and 1 layer of 4mm thick membrane",
			uom="M2",
			qty=1,
			rate=165775.35,
			amount=165775.35,
			boq_item="BOQ-ITEM-1",
		)
		defaults = {
			"doctype": "Sales Order",
			"name": "SO-TEST-BOQ-PROGRESS-PRINT",
			"customer": "CUST-1",
			"customer_name": "M1 Construction LLC SOC",
			"company": "Test Company",
			"project": "PROJ-1",
			"currency": "AED",
			"transaction_date": today(),
			"total_taxes_and_charges": 8288.768,
			"discount_amount": 0,
			"grand_total": 174064.118,
			"in_words": money_in_words(174064.118, "AED"),
			"items": [item],
			"taxes": [frappe._dict(rate=5)],
			"terms": "",
		}
		defaults.update(kwargs)
		return frappe._dict(defaults)

	def _ledger(self, **kwargs):
		row = frappe._dict(
			boq_item="BOQ-ITEM-1",
			prev_amount=0,
			current_amount=165775.35,
			accumulated_amount=165775.35,
			retention_amount=16577.535,
			advance_deduction=0,
			prev_qty=0,
			percentage=0,
			tax_invoice_amount=0,
		)
		row.update(kwargs)
		return [row]

	def test_net_c_matches_print_formula_and_words_use_net_not_grand_total(self):
		doc = self._doc()
		with patch(
			"construction_management.so_boq_progress_print_context.frappe.get_all",
			return_value=self._ledger(),
		), patch(
			"construction_management.so_boq_progress_print_context.frappe.db.has_column",
			return_value=False,
		):
			ctx = build(doc)

		t = ctx["totals"]
		expected_net = t["gross_c"] - t["ret_c"] - t["adv_c"] + t["tax_c"] - t["disc_c"]
		self.assertAlmostEqual(t["gross_c"], 165775.35, places=3)
		self.assertAlmostEqual(t["ret_c"], 16577.535, places=3)
		self.assertAlmostEqual(t["net_c"], 157486.583, places=3)
		self.assertAlmostEqual(t["net_c"], expected_net, places=6)
		self.assertEqual(ctx["amount_in_words"], money_in_words(flt(t["net_c"]), "AED"))
		self.assertNotEqual(ctx["amount_in_words"], doc.in_words)

	def test_excel_export_contains_net_amount(self):
		doc = self._doc()
		with patch(
			"construction_management.so_boq_progress_print_context.frappe.get_all",
			return_value=self._ledger(),
		), patch(
			"construction_management.so_boq_progress_print_context.frappe.db.has_column",
			return_value=False,
		):
			ctx = build(doc)

		real_get_doc = frappe.get_doc

		def fake_get_doc(*args, **kwargs):
			first = args[0] if args else None
			if first == "Sales Order":
				return doc
			return real_get_doc(*args, **kwargs)

		with patch(
			"construction_management.api.so_boq_progress_excel.frappe.has_permission",
			return_value=True,
		), patch(
			"construction_management.api.so_boq_progress_excel.frappe.get_doc",
			side_effect=fake_get_doc,
		), patch(
			"construction_management.api.so_boq_progress_excel.build",
			return_value=ctx,
		):
			url = export_sales_order_boq_progress_excel(doc.name)

		self.assertTrue(url)
		self.assertIn(".xlsx", url)
		file_doc = real_get_doc("File", {"file_url": url})
		from openpyxl import load_workbook

		wb = load_workbook(file_doc.get_full_path())
		ws = wb.active
		values = []
		for row in ws.iter_rows(values_only=True):
			values.extend([str(v) for v in row if v is not None])
		joined = " ".join(values)
		self.assertIn("NET AMOUNT DUE", joined)
		self.assertIn("157486", joined.replace(",", ""))
		self.assertIn("Amount in words", joined)

	def test_sales_invoice_excel_export_uses_tax_invoice_heading(self):
		doc = self._doc(
			doctype="Sales Invoice",
			name="SINV-TEST-BOQ-PROGRESS-PRINT",
			transaction_date=None,
			posting_date=today(),
			grand_total=157486.583,
			in_words=money_in_words(157486.583, "AED"),
		)
		with patch(
			"construction_management.so_boq_progress_print_context.frappe.get_all",
			return_value=self._ledger(),
		), patch(
			"construction_management.so_boq_progress_print_context._prior_tax_invoice_totals_for_boq_items",
			return_value={},
		), patch(
			"construction_management.so_boq_progress_print_context._prior_tax_invoice_payment_total",
			return_value=0.0,
		), patch(
			"construction_management.so_boq_progress_print_context.frappe.db.has_column",
			return_value=False,
		):
			ctx = build(doc)

		real_get_doc = frappe.get_doc

		def fake_get_doc(*args, **kwargs):
			first = args[0] if args else None
			if first == "Sales Invoice":
				return doc
			return real_get_doc(*args, **kwargs)

		with patch(
			"construction_management.api.so_boq_progress_excel.frappe.has_permission",
			return_value=True,
		), patch(
			"construction_management.api.so_boq_progress_excel.frappe.get_doc",
			side_effect=fake_get_doc,
		), patch(
			"construction_management.api.so_boq_progress_excel.build",
			return_value=ctx,
		):
			url = export_sales_invoice_boq_progress_excel(doc.name)

		file_doc = real_get_doc("File", {"file_url": url})
		from openpyxl import load_workbook

		workbook = load_workbook(file_doc.get_full_path())
		self.assertEqual(workbook.active["A1"].value, "TAX INVOICE")
		self.assertIn("Sales Invoice BOQ Progress", file_doc.file_name)
		self.assertTrue(url.endswith(".xlsx"))

	def test_sales_invoice_linked_ledger_via_tax_invoice(self):
		doc = self._doc(
			doctype="Sales Invoice",
			name="TINV/LINKED/1",
			transaction_date=None,
			posting_date=today(),
			grand_total=150000,
			in_words=money_in_words(150000, "AED"),
		)
		ledger = self._ledger(
			prev_amount=50000,
			prev_qty=10,
			percentage=25,
			retention_amount=8000,
			advance_deduction=2000,
			tax_invoice_amount=165775.35,
		)
		captured = []

		def fake_get_all(doctype, filters=None, fields=None, **kwargs):
			captured.append(filters or {})
			if filters and filters.get("tax_invoice") == doc.name:
				return ledger
			return []

		prior_from_tax = {
			"BOQ-ITEM-1": {"prev_qty": 10, "prev_amount": 50000},
		}

		with patch(
			"construction_management.so_boq_progress_print_context.frappe.get_all",
			side_effect=fake_get_all,
		), patch(
			"construction_management.so_boq_progress_print_context._prior_tax_invoice_totals_for_boq_items",
			return_value=prior_from_tax,
		), patch(
			"construction_management.so_boq_progress_print_context._prior_tax_invoice_payment_total",
			return_value=98765.43,
		), patch(
			"construction_management.so_boq_progress_print_context.frappe.db.has_column",
			return_value=False,
		), patch(
			"construction_management.so_boq_progress_print_context.frappe.db.get_value",
			return_value=None,
		):
			ctx = build(doc)

		self.assertEqual(captured[0].get("tax_invoice"), doc.name)
		self.assertAlmostEqual(ctx["rows"][0]["prev_amount"], 50000, places=2)
		self.assertAlmostEqual(ctx["rows"][0]["prev_qty"], 10, places=2)
		self.assertAlmostEqual(ctx["totals"]["ret_c"], 8000, places=2)
		self.assertAlmostEqual(ctx["totals"]["adv_c"], 2000, places=2)
		self.assertAlmostEqual(ctx["totals"]["net_c"], 150000, places=2)
		self.assertAlmostEqual(ctx["totals"]["prev_paid"], 98765.43, places=2)
		self.assertEqual(ctx["amount_in_words"], doc.in_words)

	def test_sales_invoice_orphan_ledger_fallback(self):
		doc = self._doc(
			doctype="Sales Invoice",
			name="TINV/ORPHAN/1",
			transaction_date=None,
			posting_date=today(),
			grand_total=140000,
			in_words=money_in_words(140000, "AED"),
		)
		ledger = self._ledger(prev_amount=12000, retention_amount=5000)

		def fake_get_all(doctype, filters=None, fields=None, **kwargs):
			if filters and filters.get("tax_invoice"):
				return []
			if (
				filters
				and filters.get("reference_doctype") == "Sales Invoice"
				and filters.get("reference_name") == doc.name
			):
				return ledger
			return []

		with patch(
			"construction_management.so_boq_progress_print_context.frappe.get_all",
			side_effect=fake_get_all,
		), patch(
			"construction_management.so_boq_progress_print_context._prior_tax_invoice_totals_for_boq_items",
			return_value={"BOQ-ITEM-1": {"prev_qty": 5, "prev_amount": 12000}},
		), patch(
			"construction_management.so_boq_progress_print_context._prior_tax_invoice_payment_total",
			return_value=0.0,
		), patch(
			"construction_management.so_boq_progress_print_context.frappe.db.has_column",
			return_value=False,
		), patch(
			"construction_management.so_boq_progress_print_context.frappe.db.get_value",
			return_value=None,
		):
			ctx = build(doc)

		self.assertAlmostEqual(ctx["rows"][0]["prev_amount"], 12000, places=2)
		self.assertAlmostEqual(ctx["totals"]["ret_c"], 5000, places=2)
		self.assertAlmostEqual(ctx["totals"]["net_c"], doc.grand_total, places=2)

	def test_sales_invoice_prev_uses_prior_tax_invoices_not_ledger_proforma(self):
		"""Print Previous column must follow earlier tax invoices, not proforma ledger prev."""
		doc = self._doc(
			doctype="Sales Invoice",
			name="TINV/PREV/2",
			transaction_date=None,
			posting_date=today(),
			grand_total=200000,
			in_words=money_in_words(200000, "AED"),
		)
		ledger = self._ledger(
			prev_amount=999999,
			prev_qty=999,
			percentage=40,
			retention_amount=10000,
		)

		def fake_get_all(doctype, filters=None, fields=None, **kwargs):
			if filters and filters.get("tax_invoice") == doc.name:
				return ledger
			return []

		prior_from_tax = {
			"BOQ-ITEM-1": {"prev_qty": 12.5, "prev_amount": 25000},
		}

		with patch(
			"construction_management.so_boq_progress_print_context.frappe.get_all",
			side_effect=fake_get_all,
		), patch(
			"construction_management.so_boq_progress_print_context._prior_tax_invoice_totals_for_boq_items",
			return_value=prior_from_tax,
		), patch(
			"construction_management.so_boq_progress_print_context._prior_tax_invoice_payment_total",
			return_value=0.0,
		), patch(
			"construction_management.so_boq_progress_print_context.frappe.db.has_column",
			return_value=False,
		), patch(
			"construction_management.so_boq_progress_print_context.frappe.db.get_value",
			return_value=None,
		):
			ctx = build(doc)

		self.assertAlmostEqual(ctx["rows"][0]["prev_amount"], 25000, places=2)
		self.assertAlmostEqual(ctx["rows"][0]["prev_qty"], 12.5, places=2)
		self.assertAlmostEqual(ctx["totals"]["gross_p"], 25000, places=2)

	def test_sales_invoice_prev_paid_sums_prior_tax_invoice_grand_totals(self):
		doc = self._doc(
			doctype="Sales Invoice",
			name="TINV/PREV-PAID/1",
			transaction_date=None,
			posting_date=today(),
			grand_total=200000,
			in_words=money_in_words(200000, "AED"),
		)
		with patch(
			"construction_management.so_boq_progress_print_context.frappe.get_all",
			return_value=self._ledger(),
		), patch(
			"construction_management.so_boq_progress_print_context._prior_tax_invoice_totals_for_boq_items",
			return_value={},
		), patch(
			"construction_management.so_boq_progress_print_context._prior_tax_invoice_payment_total",
			return_value=125000.0,
		), patch(
			"construction_management.so_boq_progress_print_context.frappe.db.has_column",
			return_value=False,
		), patch(
			"construction_management.so_boq_progress_print_context.frappe.db.get_value",
			return_value=None,
		):
			ctx = build(doc)

		self.assertAlmostEqual(ctx["totals"]["prev_paid"], 125000.0, places=2)

	def test_sales_invoice_deduction_lines_drive_retention_and_advance(self):
		work = frappe._dict(
			item_code="WATERPROOFING",
			item_name="Waterproofing",
			description="Work",
			uom="M2",
			qty=1,
			rate=100000,
			amount=100000,
			boq_item="BOQ-ITEM-1",
		)
		ret = frappe._dict(
			item_code="RETENTION-DEDUCTION",
			item_name="Retention",
			description="Retention",
			uom="Nos",
			qty=1,
			rate=-10000,
			amount=-10000,
			boq_item=None,
		)
		adv = frappe._dict(
			item_code="ADVANCE-DEDUCTION",
			item_name="Advance",
			description="Advance",
			uom="Nos",
			qty=1,
			rate=-5000,
			amount=-5000,
			boq_item=None,
		)
		doc = self._doc(
			doctype="Sales Invoice",
			name="TINV/DED/1",
			transaction_date=None,
			posting_date=today(),
			items=[work, ret, adv],
			grand_total=89750,
			total_taxes_and_charges=4750,
			in_words=money_in_words(89750, "AED"),
		)

		with patch(
			"construction_management.so_boq_progress_print_context.frappe.get_all",
			return_value=self._ledger(retention_amount=999, advance_deduction=999),
		), patch(
			"construction_management.so_boq_progress_print_context._prior_tax_invoice_totals_for_boq_items",
			return_value={},
		), patch(
			"construction_management.so_boq_progress_print_context._prior_tax_invoice_payment_total",
			return_value=0.0,
		), patch(
			"construction_management.so_boq_progress_print_context.frappe.db.has_column",
			return_value=False,
		), patch(
			"construction_management.so_boq_progress_print_context.frappe.db.get_value",
			return_value=None,
		):
			ctx = build(doc)

		self.assertEqual(len(ctx["rows"]), 1)
		self.assertEqual(ctx["rows"][0]["description"], "Work")
		self.assertAlmostEqual(ctx["totals"]["ret_c"], 10000, places=2)
		self.assertAlmostEqual(ctx["totals"]["adv_c"], 5000, places=2)
		self.assertAlmostEqual(ctx["totals"]["net_c"], 89750, places=2)
		self.assertEqual(ctx["amount_in_words"], doc.in_words)

	def test_sales_invoice_retention_release_is_not_retained_again(self):
		release = frappe._dict(
			item_code="RETENTION-RELEASE",
			item_name="Retention Release",
			description="Retention release",
			uom="Nos",
			qty=1,
			rate=68755.05,
			amount=68755.05,
			boq_item=None,
		)
		doc = self._doc(
			doctype="Sales Invoice",
			name="TINV/1053/2026-NOV/2",
			transaction_date=None,
			posting_date=today(),
			items=[release],
			taxes=[],
			total_taxes_and_charges=0,
			discount_amount=0,
			grand_total=68755.05,
			in_words=money_in_words(68755.05, "AED"),
		)

		with patch(
			"construction_management.so_boq_progress_print_context.frappe.get_all",
			return_value=[],
		), patch(
			"construction_management.so_boq_progress_print_context._prior_tax_invoice_totals_for_boq_items",
			return_value={},
		), patch(
			"construction_management.so_boq_progress_print_context._prior_tax_invoice_payment_total",
			return_value=0.0,
		), patch(
			"construction_management.so_boq_progress_print_context.frappe.db.has_column",
			return_value=False,
		), patch(
			"construction_management.so_boq_progress_print_context.frappe.db.get_value",
			return_value=None,
		):
			ctx = build(doc)

		t = ctx["totals"]
		self.assertEqual(len(ctx["rows"]), 1)
		self.assertAlmostEqual(t["gross_c"], 68755.05, places=2)
		self.assertAlmostEqual(t["ret_c"], 0, places=2)
		self.assertAlmostEqual(t["adv_c"], 0, places=2)
		self.assertEqual(t["vat_rate"], 0)
		self.assertAlmostEqual(t["tax_c"], 0, places=2)
		self.assertAlmostEqual(t["net_c"], doc.grand_total, places=2)
		self.assertEqual(t["prev_paid"], 0)
