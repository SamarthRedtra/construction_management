"""Collection Register batching and invoice-type classification checks."""

from unittest.mock import patch

from frappe.tests import UnitTestCase

from construction_management.api.collection_register import _finish_rows, _orders


class TestCollectionRegister(UnitTestCase):
	@patch("construction_management.api.collection_register.frappe.get_all", return_value=["SINV-1"])
	def test_retention_release_applies_to_linked_sales_order(self, get_all):
		rows = [
			{"reference_doctype": "Sales Order", "reference_name": "SO-1", "invoice_no": "SO-1",
				"pi_date": "2026-09-01", "tax_invoices": [{"name": "SINV-1"}]},
			{"reference_doctype": "Sales Invoice", "reference_name": "SINV-2", "invoice_no": "SINV-2",
				"ti_date": "2026-09-02", "is_advance": 1},
		]

		result = _finish_rows(rows)
		by_name = {row["reference_name"]: row for row in result}

		self.assertTrue(by_name["SO-1"]["is_retention_release"])
		self.assertFalse(by_name["SINV-2"]["is_retention_release"])
		self.assertEqual(get_all.call_args.kwargs["filters"]["item_code"], "RETENTION-RELEASE")

	@patch("construction_management.api.collection_register.frappe.db.has_column", return_value=False)
	@patch("construction_management.api.collection_register.frappe.get_all", return_value=[])
	def test_order_date_filter_is_applied_before_related_loading(self, get_all, _has_column):
		_orders("MRG", ["PROJ-1"], {"from_date": "2026-09-01", "to_date": "2026-09-30"})

		self.assertEqual(get_all.call_args.kwargs["filters"]["transaction_date"],
			("between", ["2026-09-01", "2026-09-30"]))
