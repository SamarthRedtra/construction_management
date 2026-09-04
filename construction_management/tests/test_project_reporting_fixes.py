# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.api.project_collection_data import (
	_collection_filter_date,
	_get_standard_sales_order_links,
)
from construction_management.api.project_revenue import get_project_billed_revenue
from construction_management.construction_management.page.project_soa.project_soa import (
	_payment_rows_for_reference,
)


class TestProjectReportingFixes(UnitTestCase):
	def test_collection_filter_prefers_proforma_date(self):
		row = {"pi_date": "2026-01-10", "ti_date": "2026-02-15"}
		self.assertEqual(_collection_filter_date(row), "2026-01-10")

	@patch("construction_management.api.project_collection_data.frappe.get_all")
	def test_standard_sales_order_link_is_used(self, get_all):
		get_all.return_value = [
			frappe._dict(parent="SINV-1", sales_order="SO-1"),
			frappe._dict(parent="SINV-1", sales_order="SO-2"),
		]

		links = _get_standard_sales_order_links(["SINV-1"])

		self.assertEqual(links, {"SINV-1": "SO-1"})

	@patch(
		"construction_management.construction_management.page.project_soa.project_soa.frappe.db.sql"
	)
	def test_multiple_payments_share_one_invoice_row(self, sql):
		sql.return_value = [
			frappe._dict(reference_no="CHQ-1", posting_date="2026-01-10", allocated_amount=400),
			frappe._dict(reference_no="CHQ-2", posting_date="2026-01-20", allocated_amount=600),
		]

		rows = _payment_rows_for_reference(
			project="PROJECT-1",
			reference_doctype="Sales Invoice",
			reference_name="SINV-1",
			proforma_date="2026-01-01",
			tax_invoice_date="2026-01-05",
			invoice_no="SINV-1",
			invoice_type="Tax Invoice",
			amount=1000,
		)

		self.assertEqual(len(rows), 1)
		self.assertEqual(len(rows[0]["payments"]), 2)
		self.assertEqual(rows[0]["cheque_amount"], 1000)
		self.assertEqual(rows[0]["cheque_no"], "CHQ-1, CHQ-2")

	@patch("construction_management.api.project_revenue.frappe.db.sql")
	@patch("construction_management.api.project_revenue.frappe.db.has_column")
	def test_revenue_excludes_advances_and_deductions(self, has_column, sql):
		has_column.return_value = True
		sql.return_value = [(66340.62,)]

		revenue = get_project_billed_revenue("PROJECT-1")

		self.assertEqual(revenue, 66340.62)
		query = sql.call_args.args[0]
		self.assertIn("custom_is_advanced", query)
		self.assertIn("RETENTION-DEDUCTION", query)
		self.assertIn("ADVANCE-DEDUCTION", query)
