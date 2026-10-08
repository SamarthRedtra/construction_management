from frappe.tests import UnitTestCase

from construction_management.purchase_order_dashboard import get_dashboard_data


class TestPurchaseOrderDashboard(UnitTestCase):
	def test_adds_post_dated_cheques_to_payment_connections(self):
		data = {
			"non_standard_fieldnames": {"Payment Entry": "reference_name"},
			"transactions": [{"label": "Payment", "items": ["Payment Entry", "Journal Entry"]}],
		}

		dashboard = get_dashboard_data(data)

		self.assertEqual(dashboard["non_standard_fieldnames"]["Post Dated Cheques"], "custom_purchase_order")
		self.assertEqual(
			dashboard["transactions"][0]["items"],
			["Payment Entry", "Journal Entry", "Post Dated Cheques"],
		)
		self.assertNotIn("Post Dated Cheques", data["transactions"][0]["items"])
