# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from construction_management.api.boq_tree import update_boq_item_base
from construction_management.tests.test_property_boq_ui import (
	create_test_boq_structure,
	create_test_project,
)


class TestBOQLumpSumEntry(IntegrationTestCase):
	"""Lump Sum Total → derived unit rate for BOQ items."""

	def setUp(self):
		self._rate_patcher = patch(
			"construction_management.construction_management.doctype.boq_item.boq_item.check_rate_history_table"
		)
		self._rate_patcher.start()
		frappe.set_user("Administrator")
		self.project = create_test_project(f"LUMP-SUM-{frappe.generate_hash(length=8)}")
		self.project_boq, self.bill, self.boq_item = create_test_boq_structure(
			self.project, total_qty=10, rate=100
		)

	def tearDown(self):
		self._rate_patcher.stop()
		frappe.db.rollback()

	def _create_lump_sum_item(self, total_qty=10, lump_sum_total=5000):
		item = frappe.new_doc("BOQ Item")
		item.parent_bill = self.bill
		item.project_boq = self.project_boq
		item.project = self.project
		item.description = f"Lump Sum Item {frappe.generate_hash(length=6)}"
		item.unit = "Nos"
		item.pricing_entry_mode = "Lump Sum Total"
		item.lump_sum_total = flt(lump_sum_total)
		item.total_qty = flt(total_qty)
		item.insert(ignore_permissions=True)
		item.reload()
		return item

	def test_new_item_derives_rate_from_lump_sum(self):
		item = self._create_lump_sum_item(total_qty=10, lump_sum_total=5000)
		self.assertEqual(flt(item.rate), 500)
		self.assertEqual(flt(item.total_amount), 5000)

	def test_qty_change_recalculates_lump_sum_rate(self):
		item = self._create_lump_sum_item(total_qty=10, lump_sum_total=5000)
		update_boq_item_base(item.name, total_qty=5)
		item.reload()
		self.assertEqual(flt(item.rate), 1000)
		self.assertEqual(flt(item.total_amount), 5000)

	def test_partially_billed_item_derives_remaining_tier_rate(self):
		item = self._create_lump_sum_item(total_qty=10, lump_sum_total=5000)
		self._add_billing_ledger(item.name, current_qty=4, current_amount=2000)

		item.total_qty = 10
		item.lump_sum_total = 5000
		item.save(ignore_permissions=True)
		item.reload()

		self.assertEqual(flt(item.rate), 500)
		self.assertEqual(flt(item.total_amount), 5000)

	def test_update_lump_sum_total_via_api(self):
		item = self._create_lump_sum_item(total_qty=10, lump_sum_total=5000)
		result = update_boq_item_base(item.name, lump_sum_total=8000, pricing_entry_mode="Lump Sum Total")
		item.reload()

		self.assertEqual(flt(item.rate), 800)
		self.assertEqual(flt(item.total_amount), 8000)
		self.assertEqual(flt(result["amount"]["rate"]), 800)
		self.assertEqual(flt(result["amount"]["total"]), 8000)

	def _add_billing_ledger(self, boq_item, current_qty, current_amount):
		bill_no = frappe.db.get_value("BOQ Item", boq_item, "parent_bill")
		ledger = frappe.new_doc("BOQ Progress Ledger")
		ledger.project = self.project
		ledger.project_boq = self.project_boq
		ledger.bill_no = bill_no
		ledger.boq_item = boq_item
		ledger.posting_date = today()
		ledger.source = "Invoice"
		ledger.entry_type = "Billing"
		ledger.prev_qty = 0
		ledger.prev_amount = 0
		ledger.current_qty = flt(current_qty)
		ledger.current_amount = flt(current_amount)
		ledger.qty = flt(current_qty)
		ledger.amount = flt(current_amount)
		ledger.accumulated_qty = flt(current_qty)
		ledger.accumulated_amount = flt(current_amount)
		ledger.insert(ignore_permissions=True)
