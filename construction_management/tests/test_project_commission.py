# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today
from unittest.mock import patch

from construction_management.api.project_commission_data import (
	ROW_TYPE_JV,
	ROW_TYPE_SI,
	_get_commission_payout_resolution,
	build_commission_ledger,
	build_summary,
)
from construction_management.construction_management.page.project_commission.project_commission import (
	get_project_commission_data,
)
from construction_management.tests.test_utils import create_test_project


class TestProjectCommission(FrappeTestCase):
	def test_summary_commission_totals(self):
		ledger = [
			{
				"row_type": ROW_TYPE_SI,
				"invoice_no": "SI-TEST-001",
				"amount": 1000,
				"sales_person": "SP-1",
				"commission_amount": 100,
				"cheque_amount": 500,
			},
			{
				"row_type": ROW_TYPE_SI,
				"invoice_no": "SI-TEST-001",
				"amount": 1000,
				"sales_person": "SP-1",
				"commission_amount": 100,
				"cheque_amount": 300,
			},
			{
				"row_type": ROW_TYPE_JV,
				"commission_amount": 80,
				"commission_received": 80,
			},
		]
		summary = build_summary("TEST-PROJ", ledger)
		self.assertEqual(summary["total_invoice_amount"], 1000)
		self.assertEqual(summary["total_received_amount"], 800)
		self.assertEqual(summary["commission_total"], 100)
		self.assertEqual(summary["commission_received_total"], 80)
		self.assertEqual(summary["commission_balance"], 20)

	@patch("construction_management.api.project_commission_data._build_journal_commission_rows")
	@patch("construction_management.api.project_commission_data._build_sales_invoice_commission_rows")
	def test_combined_ledger_si_and_jv_rows(self, mock_si, mock_jv):
		project = create_test_project("TEST-COMBINED-COMM")
		company = frappe.db.get_value("Company", {}, "name")
		if company:
			frappe.db.set_value("Project", project, "company", company)

		mock_si.return_value = [
			{
				"row_type": ROW_TYPE_SI,
				"sort_date": "2026-01-10",
				"invoice_date": "2026-01-10",
				"invoice_no": "SI-COMM-001",
				"invoice_type": "Tax Invoice",
				"amount": 5000,
				"commission_pct": 1,
				"commission_amount": 50,
				"commission_received": 0,
				"remarks": "",
				"cheque_amount": 0,
			}
		]
		mock_jv.return_value = [
			{
				"row_type": ROW_TYPE_JV,
				"sort_date": "2026-02-01",
				"invoice_date": "",
				"invoice_no": "",
				"invoice_type": "",
				"amount": 0,
				"commission_amount": 50,
				"commission_received": 50,
				"remarks": "Commission payout for Jan",
				"source_name": "JV-COMM-001",
				"cheque_amount": 0,
			}
		]

		rows, _meta = build_commission_ledger(project)
		self.assertEqual(len(rows), 2)

		si_row = next(r for r in rows if r["row_type"] == ROW_TYPE_SI)
		jv_row = next(r for r in rows if r["row_type"] == ROW_TYPE_JV)

		self.assertEqual(si_row["invoice_no"], "SI-COMM-001")
		self.assertEqual(si_row["commission_amount"], 50)
		self.assertEqual(si_row["commission_received"], 0)

		self.assertEqual(jv_row["invoice_no"], "")
		self.assertEqual(jv_row["remarks"], "Commission payout for Jan")
		self.assertEqual(jv_row["commission_received"], 50)

	def test_get_project_commission_data_structure(self):
		project = create_test_project("TEST-COMMISSION-PAGE")
		frappe.db.set_value("Project", project, {"status": "Open", "is_active": "Yes"})

		result = get_project_commission_data(project)
		self.assertIn("services", result)
		self.assertIn("ledger", result)
		self.assertIn("summary", result)
		self.assertIn("total_project_value", result)
		self.assertIn("commission_total", result["summary"])

	def test_jv_row_builder_shape(self):
		company = frappe.db.get_value("Company", {}, "name")
		if not company:
			self.skipTest("No company configured")

		from construction_management.api.project_commission_data import _build_journal_commission_rows

		with patch("construction_management.api.project_commission_data._redtra_available", return_value=True):
			with patch(
				"redtra_customisation.redtra_customisation.report.sales_person_commission_payment_summary.sales_person_commission_payment_summary.get_journal_entries"
			) as mock_get_jv:
				mock_get_jv.return_value = [
					{
						"source_name": "JV-TEST-99",
						"posting_date": today(),
						"commission_amount": 250,
						"user_remark": "Sales person commission",
						"employee_name": "Test Employee",
					}
				]
				rows = _build_journal_commission_rows("TEST-PROJ", company)
				self.assertEqual(len(rows), 1)
				self.assertEqual(rows[0]["invoice_no"], "")
				self.assertEqual(rows[0]["remarks"], "Sales person commission")
				self.assertEqual(rows[0]["commission_received"], 250)

	@patch("construction_management.api.project_commission_data._pe_has_commission_payout_flag", return_value=True)
	@patch("construction_management.api.project_commission_data.frappe.db.sql")
	def test_legacy_payment_is_matched_only_to_one_exact_commission(self, mock_sql, _mock_has_flag):
		mock_sql.return_value = [
			frappe._dict({
				"name": "PE-COMM-001",
				"docstatus": 1,
				"employee": "EMP-001",
				"paid_amount": 100.004,
				"remarks": "",
				"is_commission_payout": 0,
			})
		]

		resolution = _get_commission_payout_resolution(
			"PROJ-001",
			"Test Company",
			[
				{
					"source_name": "SI-COMM-001",
					"employee": "EMP-001",
					"commission_amount": 100.0,
				}
			],
		)

		self.assertEqual(resolution["invoice_by_payment"], {"PE-COMM-001": "SI-COMM-001"})
