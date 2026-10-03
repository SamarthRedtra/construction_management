from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.api import controlled_price_history as history
from construction_management.api import po_price_approvals as approvals


class TestControlledPriceHistory(UnitTestCase):
	@patch.object(history.prices, "_require_company")
	@patch.object(history.prices, "_price", return_value=None)
	@patch.object(history.frappe, "get_all", return_value=[])
	@patch.object(history.frappe, "get_cached_value", return_value="AED")
	@patch.object(history.frappe.db, "get_value", return_value=frappe._dict(buying=1, enabled=1, currency="AED"))
	def test_history_uses_exact_identity_and_only_approved_changes(self, value, currency, get_all, price, permitted):
		with patch.object(history.prices, "_procurement") as procurement:
			procurement.return_value._active_company.return_value = "MRG"
			procurement.return_value._item_has_supplier.return_value = True
			result = history.get_price_history("ITEM-1", "SUP-1", "Standard Buying", "Nos")
		self.assertEqual(result["rows"], [])
		self.assertEqual(get_all.call_args.kwargs["filters"], {
			"item_code": "ITEM-1", "supplier": "SUP-1", "price_list": "Standard Buying",
			"uom": "Nos", "status": "Approved",
		})
		permitted.assert_called_once_with("MRG")

	@patch.object(history.prices, "_require_company")
	@patch.object(history.frappe, "get_all")
	@patch.object(history.frappe, "get_cached_value", return_value="AED")
	@patch.object(history.frappe.db, "get_value", return_value=frappe._dict(buying=1, enabled=1, currency="AED"))
	def test_unlinked_supplier_cannot_read_history(self, value, currency, get_all, permitted):
		with patch.object(history.prices, "_procurement") as procurement:
			procurement.return_value._active_company.return_value = "MRG"
			procurement.return_value._item_has_supplier.return_value = False
			with self.assertRaises(frappe.PermissionError):
				history.get_price_history("ITEM-1", "SUP-2")
		get_all.assert_not_called()

	def test_po_notice_includes_each_rate_and_general_fallback(self):
		message = approvals._notice_lines([
			{"item_code": "ITEM-1", "price_list": "Standard Buying", "old_active_rate": 10,
				"old_active_supplier": "SUP-1", "old_active_item_price": "IP-1", "rate": 12, "reason": "Increase"},
			{"item_code": "ITEM-2", "price_list": "Standard Buying", "old_active_rate": 8,
				"old_active_supplier": "", "old_active_item_price": "IP-2", "rate": 9, "reason": "New quote"},
		], "SUP-1", "AED")
		self.assertIn("ITEM-1 · SUP-1 · Standard Buying: AED 10 → AED 12", message)
		self.assertIn("New supplier price (general fallback AED 8) → AED 9", message)
		self.assertIn("ITEM-2", message)

	@patch.object(history.frappe, "get_all")
	def test_po_history_fallback_matches_request_identity_not_line_order(self, get_all):
		get_all.return_value = [frappe._dict(name="PO-1", custom_po_price_history='''[{
			"action":"Approved", "requests":["PRICE-B", "PRICE-A"],
			"changes":[
				{"item_code":"ITEM-A", "price_list":"Standard Buying", "old_active_supplier":"SUP-1"},
				{"item_code":"ITEM-B", "price_list":"Standard Buying", "old_active_supplier":"",
				 "old_active_item_price":"GENERAL-B", "old_active_rate":8}
			]}]''')]
		rows = [frappe._dict(name="PRICE-A", item_code="ITEM-A", price_list="Standard Buying", purchase_order="PO-1"),
			frappe._dict(name="PRICE-B", item_code="ITEM-B", price_list="Standard Buying", purchase_order="PO-1")]
		self.assertEqual(history._po_change_snapshots(rows), {"PRICE-B": {"general_fallback_rate": 8}})
