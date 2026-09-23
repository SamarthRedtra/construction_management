# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase
from frappe.utils import cint, flt

from construction_management.overrides.sales_invoice import SalesInvoiceOverride


class _InvoiceStub:
	def __init__(self, items):
		self.items = [frappe._dict(row) for row in items]
		self.project = "1037"
		self.cost_center = "Main - MRG"

	def append(self, field, values):
		row = frappe._dict(values)
		getattr(self, field).append(row)
		return row


class TestSalesInvoiceDeductionUom(UnitTestCase):
	def test_appended_boq_deduction_sets_conversion_factor(self):
		invoice = _InvoiceStub([])
		parent = frappe._dict(
			uom="M2",
			project="1037",
			boq_item="BOQI-218",
			bill_no="BILL-1",
			income_account="Sales - MRG",
			cost_center="Main - MRG",
		)

		SalesInvoiceOverride._append_boq_deduction_row(
			invoice, "ADVANCE-DEDUCTION", 9421.92, "Advance deduction (10%)", parent
		)

		row = invoice.items[0]
		self.assertEqual(row.uom, "Nos")
		self.assertEqual(row.stock_uom, "Nos")
		self.assertEqual(row.conversion_factor, 1.0)
		self.assertEqual(row.stock_qty, 1)
		self.assertEqual(row.boq_item, "BOQI-218")

	def test_duplicate_advance_boq_is_reassigned_instead_of_appending(self):
		invoice = _InvoiceStub(
			[
				{"item_code": "SVC-A", "boq_item": "BOQI-219", "amount": 511431.54},
				{"item_code": "SVC-B", "boq_item": "BOQI-218", "amount": 94219.23},
				{
					"item_code": "ADVANCE-DEDUCTION",
					"boq_item": "BOQI-219",
					"amount": -51143.15,
					"custom_service_deduction": 0,
				},
				{
					"item_code": "ADVANCE-DEDUCTION",
					"boq_item": "BOQI-219",
					"amount": -9421.92,
					"custom_service_deduction": 0,
				},
			]
		)

		SalesInvoiceOverride._reassign_duplicate_boq_deductions(
			invoice, {"BOQI-219": 511431.54, "BOQI-218": 94219.23}
		)
		SalesInvoiceOverride._normalize_deduction_uoms(invoice)

		advances = [row for row in invoice.items if row.item_code == "ADVANCE-DEDUCTION"]
		self.assertEqual({row.boq_item for row in advances}, {"BOQI-219", "BOQI-218"})
		self.assertTrue(all(flt(row.conversion_factor) == 1 for row in advances))
		self.assertFalse(any(cint(row.get("conversion_factor")) == 0 for row in advances))

	@patch(
		"construction_management.overrides.sales_invoice.frappe.get_all",
		return_value=[frappe._dict(name="soi-ret-1", uom="M2")],
	)
	def test_normalize_keeps_sales_order_uom_for_mapped_deduction(self, _get_all):
		invoice = _InvoiceStub(
			[
				{
					"item_code": "RETENTION-DEDUCTION",
					"boq_item": "BOQI-219",
					"so_detail": "soi-ret-1",
					"uom": "Nos",
					"stock_uom": "Nos",
					"conversion_factor": 0,
					"qty": 1,
				}
			]
		)

		SalesInvoiceOverride._normalize_deduction_uoms(invoice)

		row = invoice.items[0]
		self.assertEqual(row.uom, "M2")
		self.assertEqual(row.conversion_factor, 1.0)
		self.assertEqual(row.stock_qty, 1)

	@patch.object(SalesInvoiceOverride, "apply_automatic_deductions")
	@patch.object(SalesInvoiceOverride, "_normalize_deduction_uoms")
	@patch("erpnext.accounts.doctype.sales_invoice.sales_invoice.SalesInvoice.validate")
	def test_validate_normalizes_uom_before_erpnext_validate(
		self, erpnext_validate, normalize, apply_deductions
	):
		call_order = []
		normalize.side_effect = lambda: call_order.append("normalize")
		erpnext_validate.side_effect = lambda: call_order.append("erpnext")

		invoice = SalesInvoiceOverride({"doctype": "Sales Invoice"})
		invoice.flags = frappe._dict()
		invoice.project = None
		invoice.custom_is_advanced = 0

		SalesInvoiceOverride.validate(invoice)

		self.assertEqual(call_order, ["normalize", "erpnext"])
		apply_deductions.assert_not_called()
