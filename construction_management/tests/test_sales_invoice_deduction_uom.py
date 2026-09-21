# Copyright (c) 2026, Construction Management
# License: MIT

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
