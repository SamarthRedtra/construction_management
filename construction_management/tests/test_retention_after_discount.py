# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase
from frappe.utils import flt

from construction_management.api.boq_invoice import (
	allocate_discount_by_share,
	allocate_retention_after_discount,
	get_retention_base_amount,
	normalize_retention_discount,
)


class TestRetentionAfterDiscount(UnitTestCase):
	def test_retention_base_unchanged_when_flag_off(self):
		self.assertEqual(
			get_retention_base_amount(10000, after_discount=False, discount_amount=2000),
			10000,
		)

	def test_retention_base_subtracts_discount_when_flag_on(self):
		self.assertEqual(
			get_retention_base_amount(10000, after_discount=True, discount_amount=2000),
			8000,
		)

	def test_retention_base_never_negative(self):
		self.assertEqual(
			get_retention_base_amount(500, after_discount=True, discount_amount=900),
			0,
		)

	def test_retention_base_reads_doc_discount(self):
		doc = frappe._dict(base_discount_amount=1500, discount_amount=100)
		self.assertEqual(get_retention_base_amount(10000, doc=doc, after_discount=True), 8500)

	def test_allocate_discount_by_share_proportional(self):
		shares = allocate_discount_by_share({"A": 7000, "B": 3000}, 1000)
		self.assertEqual(flt(shares["A"], 2), 700.0)
		self.assertEqual(flt(shares["B"], 2), 300.0)

	@patch("construction_management.api.boq_invoice.get_advance_balance", return_value=0)
	@patch("construction_management.api.boq_invoice.get_boq_kpi", return_value={})
	@patch("construction_management.api.boq_invoice.get_or_create_advance_item")
	@patch("construction_management.api.boq_invoice.get_or_create_retention_item")
	@patch("construction_management.api.boq_invoice.frappe.get_doc")
	@patch("construction_management.api.boq_invoice.frappe.get_cached_doc")
	def test_get_deduction_details_after_discount(
		self, get_cached_doc, get_doc, _ret, _adv, _kpi, _bal
	):
		from construction_management.api.boq_invoice import get_deduction_details

		get_doc.return_value = frappe._dict(
			retention_percentage=10,
			advance_deduction=0,
			enable_progressive_boq=1,
			company="Test Co",
		)
		get_cached_doc.return_value = frappe._dict(varience_item=None)

		items = [{"item_code": "WORK", "amount": 10000}]
		plain = get_deduction_details("PROJ", items, after_discount=0, discount_amount=2000)
		after = get_deduction_details("PROJ", items, after_discount=1, discount_amount=2000)

		self.assertEqual(flt(plain["suggested_retention"], 2), 1000.0)
		self.assertEqual(flt(after["suggested_retention"], 2), 800.0)
		self.assertEqual(flt(after["retention_base_amount"], 2), 8000.0)

	def test_per_boq_retention_uses_discount_share(self):
		amounts = {"BOQ-A": 7000.0, "BOQ-B": 3000.0}
		shares = allocate_discount_by_share(amounts, 1000)
		retention_a = flt(max(0.0, amounts["BOQ-A"] - shares["BOQ-A"]) * 10 / 100, 2)
		retention_b = flt(max(0.0, amounts["BOQ-B"] - shares["BOQ-B"]) * 10 / 100, 2)
		# A: (7000-700)*10% = 630; B: (3000-300)*10% = 270
		self.assertEqual(retention_a, 630.0)
		self.assertEqual(retention_b, 270.0)
		self.assertEqual(flt(retention_a + retention_b, 2), 900.0)

	def test_tinv_1177_gross_minus_raw_discount(self):
		# total work 82164.16 − discount 41485 = 40679.16 → 10% = 4067.92
		work = 82164.16
		discount = 41485.0
		base = get_retention_base_amount(work, after_discount=True, discount_amount=discount)
		self.assertEqual(flt(base, 2), 40679.16)
		self.assertEqual(flt(base * 10 / 100, 2), 4067.92)

		amounts = {"BOQ-A": 76828.16, "BOQ-B": 5336.0}
		by_boq = allocate_retention_after_discount(amounts, 10, discount)
		self.assertEqual(flt(by_boq["BOQ-A"] + by_boq["BOQ-B"], 2), 4067.92)

	def test_grand_total_discount_is_not_converted_ex_vat(self):
		# Retention uses header discount as entered, including Grand Total.
		self.assertEqual(normalize_retention_discount(41485, "Grand Total", 0.05), 41485)
		self.assertEqual(normalize_retention_discount(41485, "Net Total", 0.05), 41485)
