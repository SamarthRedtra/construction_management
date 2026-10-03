from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.api import controlled_price_requests as prices
from construction_management.api import controlled_procurement as catalog


class TestControlledPriceRequests(UnitTestCase):
	def test_price_notice_links_to_procurement_without_html_injection(self):
		message = prices.price_notice_html("ITEM-1: 10 → 12. <script>unsafe</script>", "PO/1")
		self.assertIn('href="/procurement/catalog/prices?request=PO%2F1"', message)
		self.assertIn("&lt;script&gt;unsafe&lt;/script&gt;", message)
		self.assertNotIn("<script>", message)

	@patch.object(prices, "_is_controlled", return_value=True)
	@patch.object(prices, "_is_buying", return_value=True)
	def test_direct_controlled_buying_price_insert_is_blocked(self, buying, controlled):
		doc = MagicMock()
		doc.is_new.return_value = True
		doc.get.return_value = "ITEM-1"
		with self.assertRaises(frappe.PermissionError):
			prices.guard_item_price(doc)

	@patch.object(prices, "_is_controlled", return_value=False)
	def test_non_controlled_price_is_untouched(self, controlled):
		doc = MagicMock()
		doc.is_new.return_value = True
		prices.guard_item_price(doc)

	@patch.object(prices, "_is_controlled", return_value=True)
	@patch.object(prices, "_is_buying", return_value=True)
	def test_direct_deletion_is_blocked(self, buying, controlled):
		with self.assertRaises(frappe.PermissionError):
			prices.guard_item_price_delete(MagicMock())

	@patch.object(catalog, "_roles", return_value={"System Manager"})
	@patch.object(catalog, "_explicit_ceo", return_value=False)
	def test_system_manager_cannot_self_approve_catalog_price(self, explicit, roles):
		self.assertEqual(catalog._catalog_request_status([{"rate": 10}]), "Pending CEO")
		self.assertFalse(catalog._can_approve_catalog(SimpleNamespace(
			status="Pending CEO", items=[SimpleNamespace(rate=10)],
		)))

	@patch.object(catalog, "_roles", return_value={"CEO"})
	@patch.object(catalog, "_explicit_ceo", return_value=True)
	def test_ceo_can_approve_catalog_price(self, explicit, roles):
		self.assertEqual(catalog._catalog_request_status([{"rate": 10}]), "Approved")
		self.assertTrue(catalog._can_approve_catalog(SimpleNamespace(
			status="Pending CEO", items=[SimpleNamespace(rate=10)],
		)))

	@patch.object(prices, "_require_company")
	@patch.object(prices, "has_explicit_ceo_role", return_value=False)
	def test_system_manager_cannot_approve_price_only_request(self, explicit, company):
		with self.assertRaises(frappe.PermissionError):
			prices._approval_access(SimpleNamespace(company="MRG"))

	@patch.object(prices.frappe.db, "exists", return_value=None)
	def test_administrator_effective_roles_do_not_count_as_ceo(self, exists):
		self.assertFalse(prices.has_explicit_ceo_role("Administrator"))
		exists.assert_called_once_with("Has Role", {
			"parent": "Administrator", "parenttype": "User", "role": "CEO",
		})

	@patch.object(prices, "_price", return_value=frappe._dict(name="IP-1", price_list_rate=10, modified="2026-10-01 00:00:00"))
	@patch.object(prices, "_save_request")
	@patch.object(prices, "now_datetime", return_value="2026-10-02 00:00:00")
	def test_stale_price_needs_correction_without_overwrite(self, clock, save, current):
		doc = frappe._dict(status="Pending CEO", item_code="ITEM-1", supplier="SUP-1",
			price_list="Standard Buying", uom="Nos", target_item_price="IP-1",
			target_modified="2026-09-30 00:00:00", old_rate=10)
		with patch.object(prices.frappe.db, "sql"):
			prices._approve(doc)
		self.assertEqual(doc.status, "Needs Correction")
		save.assert_called_once_with(doc)

	@patch.object(prices, "_ceo_users", return_value=["ceo@example.com"])
	@patch.object(prices, "_save_request")
	@patch.object(prices.frappe, "get_doc")
	def test_raven_retry_skips_successful_recipient(self, get_doc, save, users):
		doc = frappe._dict(company="MRG", requested_by="buyer@example.com", status="Pending CEO",
			notified_users='["ceo@example.com"]', item_code="ITEM-1", supplier="",
			old_rate=10, proposed_rate=20, reason="Cost increase", doctype="Controlled Buying Price Request", name="CBPR-1")
		doc.reload = lambda: None
		get_doc.return_value = doc
		prices.deliver_price_notice("CBPR-1")
		self.assertEqual(doc.notification_status, "Delivered")
		get_doc.assert_called_once_with("Controlled Buying Price Request", "CBPR-1")

	@patch.object(prices, "_price", return_value=None)
	@patch.object(prices, "_save_request")
	@patch.object(prices.frappe, "get_doc")
	@patch.object(prices, "now_datetime", return_value="2026-10-02 00:00:00")
	def test_first_general_price_is_inserted_only_on_approval(self, clock, get_doc, save, current):
		price = MagicMock()
		price.name = "IP-NEW"
		get_doc.return_value = price
		doc = frappe._dict(name="CBPR-1", status="Pending CEO", item_code="ITEM-1", supplier="",
			price_list="Standard Buying", uom="Nos", target_item_price="", target_modified=None,
			old_rate=0, proposed_rate=25)
		with patch.object(prices.frappe.db, "sql"):
			prices._approve(doc)
		self.assertEqual(doc.status, "Approved")
		self.assertEqual(doc.result_item_price, "IP-NEW")
		self.assertIsNone(doc.active_identity)
		self.assertEqual(get_doc.call_args.args[0]["supplier"], None)
		price.insert.assert_called_once_with(ignore_permissions=True)

	@patch.object(prices, "_price", return_value=frappe._dict(name="IP-1", price_list_rate=10, modified="2026-10-01 00:00:00"))
	@patch.object(prices, "_save_request")
	@patch.object(prices.frappe, "get_doc")
	@patch.object(prices, "now_datetime", return_value="2026-10-02 00:00:00")
	def test_supplier_price_update_is_linked_to_approval(self, clock, get_doc, save, current):
		price = MagicMock()
		price.name = "IP-1"
		get_doc.return_value = price
		doc = frappe._dict(name="CBPR-2", status="Pending CEO", item_code="ITEM-1", supplier="SUP-1",
			price_list="Standard Buying", uom="Nos", target_item_price="IP-1",
			target_modified="2026-10-01 00:00:00", old_rate=10, proposed_rate=12)
		with patch.object(prices.frappe.db, "sql"):
			prices._approve(doc)
		self.assertEqual(doc.status, "Approved")
		self.assertEqual(price.price_list_rate, 12)
		self.assertEqual(price.custom_controlled_price_request, "CBPR-2")
		price.save.assert_called_once_with(ignore_permissions=True)
