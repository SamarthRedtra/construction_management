from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.api import po_price_approvals as approvals


class TestPOPriceApprovals(UnitTestCase):
	@patch.object(approvals.frappe.db, "commit")
	@patch.object(approvals.frappe.db, "set_value")
	@patch.object(approvals.prices, "_ceo_users", return_value=["ceo@example.com"])
	@patch.object(approvals.frappe, "get_doc")
	def test_raven_price_link_opens_procurement_not_desk_po(self, get_doc, users, set_value, commit):
		doc = frappe._dict(name="PO-1", company="MRG", supplier="SUP-1", currency="AED",
			owner="buyer@example.com", custom_po_price_status="Pending CEO",
			custom_po_price_proposal='{"requested_by":"buyer@example.com","changes":[{"item_code":"ITEM-1","price_list":"Standard Buying","old_active_rate":10,"old_active_supplier":"SUP-1","rate":12,"reason":"New quote"}]}',
			custom_po_price_history="[]", custom_po_price_notified_users="[]")
		bot = MagicMock()
		bot.send_direct_message.return_value = "RAVEN-1"
		get_doc.side_effect = [doc, bot]
		approvals.deliver_po_price_notice("PO-1")
		kwargs = bot.send_direct_message.call_args.kwargs
		self.assertIn('href="/procurement/catalog/prices?request=PO-1"', kwargs["text"])
		self.assertIn("AED 10 → AED 12", kwargs["text"])
		self.assertNotIn("link_doctype", kwargs)
		self.assertNotIn("link_document", kwargs)

	@patch.object(approvals, "_current", return_value={"rate": 10, "price_list": "Standard Buying"})
	def test_new_order_at_active_rate_needs_no_approval(self, current):
		rows = [{"item_code": "ITEM-1", "rate": 10, "rate_edited": False}]
		self.assertEqual(approvals.prepare_rates("MRG", "SUP-1", "2026-10-02", rows), [])
		self.assertEqual(rows[0]["rate"], 10)

	@patch.object(approvals, "_current", return_value={"rate": 10, "price_list": "Standard Buying"})
	def test_multiple_new_items_at_active_rates_need_no_approval(self, current):
		rows = [{"item_code": code, "rate": 10, "rate_edited": False} for code in ("ITEM-1", "ITEM-2")]
		self.assertEqual(approvals.prepare_rates("MRG", "SUP-1", "2026-10-02", rows), [])
		self.assertEqual(current.call_count, 2)

	@patch.object(approvals.frappe, "get_cached_value", return_value="AED")
	@patch.object(approvals.frappe.db, "get_value", return_value=frappe._dict(buying=1, enabled=1, currency="AED"))
	@patch.object(approvals, "_current", return_value={"rate": 10, "price_list": "Standard Buying"})
	def test_new_order_changed_rate_is_held_at_active_rate(self, current, get_value, currency):
		rows = [{"item_code": "ITEM-1", "rate": 12, "rate_edited": True, "price_change_reason": "Supplier revision"}]
		changes = approvals.prepare_rates("MRG", "SUP-1", "2026-10-02", rows)
		self.assertEqual(rows[0]["rate"], 10)
		self.assertEqual(changes[0]["rate"], 12)
		self.assertEqual(changes[0]["reason"], "Supplier revision")

	@patch.object(approvals, "_current", return_value={"rate": 15, "price_list": "Standard Buying"})
	def test_stale_auto_fetched_rate_must_be_refreshed(self, current):
		rows = [{"item_code": "ITEM-1", "rate": 10, "rate_edited": False}]
		with self.assertRaises(frappe.ValidationError):
			approvals.prepare_rates("MRG", "SUP-1", "2026-10-02", rows)

	@patch.object(approvals, "_current")
	def test_unchanged_historical_rate_does_not_reprice(self, current):
		previous = SimpleNamespace(supplier="SUP-1", docstatus=0,
			items=[SimpleNamespace(name="ROW-1", item_code="ITEM-1", rate=7)])
		rows = [{"docname": "ROW-1", "item_code": "ITEM-1", "rate": 7}]
		self.assertEqual(approvals.prepare_rates("MRG", "SUP-1", "2026-10-02", rows, previous), [])
		current.assert_not_called()

	@patch.object(approvals, "_current", return_value={"rate": 10, "price_list": "Standard Buying"})
	def test_changed_rate_requires_reason(self, current):
		rows = [{"item_code": "ITEM-1", "rate": 12, "rate_edited": True, "price_change_reason": "  "}]
		with self.assertRaises(frappe.ValidationError):
			approvals.prepare_rates("MRG", "SUP-1", "2026-10-02", rows)

	def test_zero_rate_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			approvals.prepare_rates("MRG", "SUP-1", "2026-10-02", [{"item_code": "ITEM-1", "rate": 0}])

	def test_pending_draft_cannot_be_submitted(self):
		doc = frappe._dict(controlled_procurement=1, custom_po_price_status="Pending CEO",
			items=[frappe._dict(rate=10)])
		with self.assertRaises(frappe.PermissionError):
			approvals.before_submit_purchase_order(doc)

	@patch.object(approvals.prices, "_require_company")
	@patch.object(approvals.prices, "has_explicit_ceo_role", return_value=False)
	@patch.object(approvals.frappe, "get_doc")
	def test_administrator_without_explicit_ceo_cannot_approve(self, get_doc, explicit, company):
		get_doc.return_value = frappe._dict(company="MRG", name="PO-1", custom_po_price_status="Pending CEO")
		with self.assertRaises(frappe.PermissionError):
			approvals.approve_po_price("PO-1")

	@patch.object(approvals, "_finish")
	@patch.object(approvals.prices, "_require_company")
	@patch.object(approvals.prices, "has_explicit_ceo_role", return_value=True)
	@patch.object(approvals.frappe, "get_doc")
	def test_changed_po_never_applies_prices(self, get_doc, explicit, company, finish):
		get_doc.return_value = frappe._dict(company="MRG", name="PO-1", modified="later",
			custom_po_price_status="Pending CEO", custom_lpo_type="Standard",
			custom_po_price_proposal='{"po_modified":"earlier","requests":[],"changes":[]}')
		self.assertEqual(approvals.approve_po_price("PO-1")["status"], "Needs Correction")
		finish.assert_called_once()
