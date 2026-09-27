from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from construction_management.api.project_collection_data import get_collection_expected_payments


NO_LOOKUPS = {"cheque_dates": {}, "follow_up_dates": {}, "invoice_sales_orders": {}, "sales_order_dates": {}}
LOOKUPS = "construction_management.api.project_collection_data._expected_payment_lookups"


def invoice(name, due_date, amount, **extra):
	return frappe._dict({
		"customer": "CUST-001", "customer_name": "Customer One", "invoice": name,
		"project": "PROJ-001", "project_name": "Project One", "due_date": due_date,
		"posting_date": due_date, "outstanding_amount": amount, "overdue_basis": "Tax Invoice",
		"overdue_days": 0, **extra,
	})


class TestCollectionExpectedPayments(FrappeTestCase):
	def setUp(self):
		# frappe.db.sql is stubbed per test, so answer column checks directly
		patcher = patch("construction_management.api.project_collection_data.frappe.db.has_column", return_value=True)
		patcher.start()
		self.addCleanup(patcher.stop)

	@patch(LOOKUPS, return_value=NO_LOOKUPS)
	@patch("construction_management.api.project_collection_data.frappe.db.sql")
	@patch("construction_management.api.project_collection_data.today", return_value="2026-09-26")
	def test_overdue_invoices_roll_into_forecast_start_month(self, _today, mock_sql, _lookups):
		mock_sql.return_value = [
			frappe._dict({
				"customer": "CUST-001",
				"customer_name": "Customer One",
				"invoice": "SINV-AUG",
				"project": "PROJ-001",
				"project_name": "Project One",
				"due_date": "2026-08-15",
				"outstanding_amount": 100,
			}),
			frappe._dict({
				"customer": "CUST-001",
				"customer_name": "Customer One",
				"invoice": "SINV-SEP",
				"project": "PROJ-001",
				"project_name": "Project One",
				"due_date": "2026-09-30",
				"outstanding_amount": 200,
			}),
			frappe._dict({
				"customer": "CUST-001",
				"customer_name": "Customer One",
				"invoice": "SINV-OCT",
				"project": "PROJ-002",
				"project_name": "Project Two",
				"due_date": "2026-10-01",
				"outstanding_amount": 300,
			}),
		]

		result = get_collection_expected_payments("Test Company", {"from_date": "2026-08-01"})

		self.assertEqual([month["key"] for month in result["months"]], ["2026-09-01", "2026-10-01", "2026-11-01"])
		row = result["rows"][0]
		self.assertEqual(row["amounts"]["2026-09-01"], 300)
		self.assertEqual(row["amounts"]["2026-10-01"], 300)
		self.assertNotIn("2026-08-01", row["amounts"])
		self.assertTrue(row["details"]["2026-09-01"][0]["carried_forward"])
		self.assertFalse(row["details"]["2026-09-01"][1]["carried_forward"])

	@patch(LOOKUPS, return_value=NO_LOOKUPS)
	@patch("construction_management.api.project_collection_data.frappe.db.sql")
	@patch("construction_management.api.project_collection_data.today", return_value="2026-09-26")
	def test_customer_filter_is_passed_to_invoice_query(self, _today, mock_sql, _lookups):
		mock_sql.return_value = []

		get_collection_expected_payments("Test Company", {"customer": "CUST-001"})

		query, values = mock_sql.call_args.args[:2]
		self.assertIn("si.customer = %(customer)s", query)
		self.assertEqual(values["customer"], "CUST-001")

	@patch("construction_management.api.project_collection_data.frappe.db.sql")
	@patch("construction_management.api.project_collection_data.today", return_value="2026-09-26")
	def test_expected_date_prefers_cheque_then_follow_up_then_project_terms(self, _today, mock_sql):
		mock_sql.return_value = [
			# all four are overdue by invoice due date; the other sources move them forward
			invoice("SINV-PDC", "2026-08-10", 100),
			invoice("SINV-FU", "2026-08-10", 200),
			invoice("SINV-TERMS", "2026-08-10", 300, overdue_days=90),
			invoice("SINV-PLAIN", "2026-08-10", 400),
			invoice("SINV-LATER", "2027-02-01", 500),  # beyond the three-month window
		]
		lookups = {
			"cheque_dates": {"SINV-PDC": "2026-10-15"},
			"follow_up_dates": {"SO-FU": "2026-11-05"},
			"invoice_sales_orders": {"SINV-FU": ["SO-FU"]},
			"sales_order_dates": {},
		}
		with patch(LOOKUPS, return_value=lookups):
			result = get_collection_expected_payments("Test Company", {})

		row = result["rows"][0]
		self.assertEqual(row["amounts"], {"2026-09-01": 400, "2026-10-01": 100, "2026-11-01": 500})
		details = {d["invoice"]: d for month in row["details"].values() for d in month}
		self.assertEqual(details["SINV-PDC"]["basis"], "Cheque")
		self.assertEqual(details["SINV-FU"]["basis"], "Follow-up")
		self.assertEqual(details["SINV-TERMS"]["basis"], "Project terms")
		self.assertEqual(str(details["SINV-TERMS"]["expected_date"]), "2026-11-08")
		self.assertTrue(details["SINV-PLAIN"]["carried_forward"])
		self.assertNotIn("SINV-LATER", details)

	@patch("construction_management.api.project_collection_data.frappe.db.sql")
	@patch("construction_management.api.project_collection_data.today", return_value="2026-09-26")
	def test_proforma_basis_counts_days_from_sales_order_date(self, _today, mock_sql):
		mock_sql.return_value = [invoice("SINV-PF", "2026-08-01", 250, overdue_basis="Proforma Invoice", overdue_days=60)]
		lookups = {"cheque_dates": {}, "follow_up_dates": {}, "invoice_sales_orders": {"SINV-PF": ["SO-1"]}, "sales_order_dates": {"SO-1": "2026-09-01"}}
		with patch(LOOKUPS, return_value=lookups):
			result = get_collection_expected_payments("Test Company", {})

		self.assertEqual(result["rows"][0]["amounts"], {"2026-10-01": 250})
