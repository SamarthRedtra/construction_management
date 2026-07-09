# Copyright (c) 2026, Construction Management
# License: MIT

from frappe.tests import UnitTestCase
from frappe.utils import getdate


class TestSalesOrderSubmittedDateUpdate(UnitTestCase):
	def test_sales_order_dates_changed_detects_transaction_date_change(self):
		from construction_management.overrides.sales_order import _sales_order_dates_changed

		before = {"transaction_date": "2026-06-01", "delivery_date": "2026-06-30"}
		after = {"transaction_date": "2026-06-15", "delivery_date": "2026-06-30"}

		self.assertTrue(_sales_order_dates_changed(before, after))

	def test_sales_order_dates_changed_ignores_unchanged_dates(self):
		from construction_management.overrides.sales_order import _sales_order_dates_changed

		before = {"transaction_date": "2026-06-01", "delivery_date": "2026-06-30"}
		after = {"transaction_date": "2026-06-01", "delivery_date": "2026-06-30"}

		self.assertFalse(_sales_order_dates_changed(before, after))

	def test_getdate_none_handling(self):
		from construction_management.overrides.sales_order import _sales_order_dates_changed

		before = {"transaction_date": "2026-06-01"}
		after = {"transaction_date": "2026-06-01", "delivery_date": "2026-06-30"}

		self.assertTrue(_sales_order_dates_changed(before, after))
		self.assertEqual(getdate("2026-06-30"), getdate(after["delivery_date"]))
