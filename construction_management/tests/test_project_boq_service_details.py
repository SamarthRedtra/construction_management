from unittest.mock import patch

from frappe.tests import UnitTestCase

from construction_management.api.boq_invoice import get_project_boq_service_details


class TestProjectBoqServiceDetails(UnitTestCase):
	@patch("construction_management.api.boq_invoice._open_sales_order_line")
	@patch("construction_management.api.boq_invoice._open_sales_order_lines")
	@patch("construction_management.api.boq_ledger.get_to_date_qty", return_value=0)
	@patch("construction_management.api.boq_invoice.frappe.get_doc")
	@patch("construction_management.api.boq_invoice.frappe.db.get_value")
	@patch("construction_management.api.boq_invoice.frappe.db.exists", return_value=True)
	def test_link_sales_order_returns_so_fields(
		self, _exists, get_value, get_doc, _to_date, open_lines, open_line
	):
		get_value.return_value = 0
		get_doc.return_value = type(
			"BOQ",
			(),
			{
				"name": "BOQI-1",
				"project": "PRJ-1",
				"linked_item": "ITEM-1",
				"description": "Work",
				"label": None,
				"unit": "M2",
				"rate": 10,
				"parent_bill": "BILL-1",
				"total_qty": 100,
				"project_boq": None,
			},
		)()
		open_lines.return_value = [{"sales_order": "SO-1"}]
		open_line.return_value = {"sales_order": "SO-1", "so_detail": "SOD-1"}

		result = get_project_boq_service_details("PRJ-1", "BOQI-1", link_sales_order=1)

		self.assertEqual(result["sales_order"], "SO-1")
		self.assertEqual(result["so_detail"], "SOD-1")
		self.assertTrue(result["has_open_sales_order"])

	@patch("construction_management.api.boq_invoice._open_sales_order_line")
	@patch("construction_management.api.boq_invoice._open_sales_order_lines")
	@patch("construction_management.api.boq_ledger.get_to_date_qty", return_value=0)
	@patch("construction_management.api.boq_invoice.frappe.get_doc")
	@patch("construction_management.api.boq_invoice.frappe.db.get_value")
	@patch("construction_management.api.boq_invoice.frappe.db.exists", return_value=True)
	def test_direct_mode_skips_so_link(
		self, _exists, get_value, get_doc, _to_date, open_lines, open_line
	):
		get_value.return_value = 0
		get_doc.return_value = type(
			"BOQ",
			(),
			{
				"name": "BOQI-1",
				"project": "PRJ-1",
				"linked_item": "ITEM-1",
				"description": "Work",
				"label": None,
				"unit": "M2",
				"rate": 10,
				"parent_bill": "BILL-1",
				"total_qty": 100,
				"project_boq": None,
			},
		)()
		open_lines.return_value = [{"sales_order": "SO-1"}]

		result = get_project_boq_service_details("PRJ-1", "BOQI-1", link_sales_order=0)

		open_line.assert_not_called()
		self.assertIsNone(result["sales_order"])
		self.assertIsNone(result["so_detail"])
		self.assertEqual(result["open_sales_orders"], ["SO-1"])
		self.assertTrue(result["has_open_sales_order"])