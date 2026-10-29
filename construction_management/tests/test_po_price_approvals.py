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

	@patch.object(approvals, "_po_only", return_value=False)
	@patch.object(approvals.frappe, "get_cached_value", return_value="AED")
	@patch.object(approvals.frappe.db, "get_value", return_value=frappe._dict(buying=1, enabled=1, currency="AED"))
	@patch.object(approvals, "_current", return_value={"rate": 10, "price_list": "Standard Buying"})
	def test_new_order_changed_rate_stays_on_po_row(self, current, get_value, currency, po_only):
		rows = [{"item_code": "ITEM-1", "rate": 12, "rate_edited": True, "price_change_reason": "Supplier revision"}]
		changes = approvals.prepare_rates("MRG", "SUP-1", "2026-10-02", rows)
		self.assertEqual(rows[0]["rate"], 12)
		self.assertEqual(changes[0]["rate"], 12)
		self.assertEqual(changes[0]["old_po_rate"], 10)
		self.assertEqual(changes[0]["reason"], "Supplier revision")

	@patch.object(approvals, "_current", return_value={"rate": 15, "price_list": "Standard Buying"})
	def test_stale_auto_fetched_rate_must_be_refreshed(self, current):
		rows = [{"item_code": "ITEM-1", "rate": 10, "rate_edited": False}]
		with self.assertRaises(frappe.ValidationError):
			approvals.prepare_rates("MRG", "SUP-1", "2026-10-02", rows)

	@patch.object(approvals, "_current")
	def test_unchanged_historical_rate_does_not_reprice(self, current):
		previous = SimpleNamespace(supplier="SUP-1", docstatus=0, get=lambda key, default=None: None,
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

	def test_validate_blocks_submit_even_with_api_flag(self):
		doc = frappe._dict(
			controlled_procurement=1,
			custom_po_price_status="Pending CEO",
			_action="submit",
			flags=SimpleNamespace(controlled_procurement_api=True),
		)
		with self.assertRaisesRegex(frappe.PermissionError, "cannot be submitted"):
			approvals.validate_purchase_order(doc)

	@patch("construction_management.api.controlled_procurement._controlled_doc")
	@patch("construction_management.api.controlled_procurement.frappe.db.get_value", return_value="Pending CEO")
	def test_submit_document_blocks_pending_price_po(self, get_value, controlled_doc):
		from construction_management.api import controlled_procurement as procurement

		doc = MagicMock()
		doc.docstatus = 0
		doc.controlled_procurement = 1
		doc.get = MagicMock(side_effect=lambda key, default=None: {
			"controlled_procurement": 1, "custom_lpo_type": "Standard",
		}.get(key, default))
		controlled_doc.return_value = doc
		with patch("construction_management.api.lpo_workflow.lpo_type", return_value="Standard"):
			with self.assertRaisesRegex(frappe.PermissionError, "cannot be submitted"):
				procurement.submit_document("Purchase Order", "PO-1")
		doc.submit.assert_not_called()

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

	@patch.object(approvals.frappe, "get_doc")
	def test_restore_draft_po_rates_on_reject(self, get_doc):
		row = SimpleNamespace(item_code="ITEM-1", rate=12)
		po = MagicMock()
		po.docstatus = 0
		po.items = [row]
		po.flags = SimpleNamespace()
		get_doc.return_value = po
		approvals._restore_draft_po_rates(
			frappe._dict(name="PO-1", docstatus=0),
			{"changes": [{"index": 0, "item_code": "ITEM-1", "rate": 12, "old_po_rate": 10}]},
		)
		self.assertEqual(row.rate, 10)
		po.save.assert_called_once_with(ignore_permissions=True)

	@patch.object(approvals, "_po_only", return_value=True)
	@patch.object(approvals, "_current")
	def test_draft_save_defers_consumable_service_rates(self, current, po_only):
		rows = [{"item_code": "CONS-1", "rate": 99, "rate_edited": True}]
		self.assertEqual(approvals.prepare_rates("MRG", "SUP-1", "2026-10-02", rows, defer_po_only=True), [])
		current.assert_not_called()

	@patch.object(approvals, "_enqueue_notice")
	@patch.object(approvals.prices, "has_explicit_ceo_role", return_value=False)
	@patch.object(approvals.prices, "_save_request")
	@patch.object(approvals.frappe.db, "set_value")
	def test_po_only_change_creates_no_catalog_request(self, set_value, save_request, explicit, notice):
		import json

		doc = frappe._dict(name="PO-1", docstatus=0, modified="m1", supplier="SUP-1", custom_lpo_type="Standard")
		change = {"index": 0, "item_code": "CONS-1", "rate": 99, "reason": "Quote", "po_only": True, "price_list": "Standard Buying"}
		approvals.stage(doc, [change], submit_on_approval=True)
		save_request.assert_not_called()
		values = set_value.call_args.args[2]
		proposal = json.loads(values["custom_po_price_proposal"])
		self.assertEqual(values["custom_po_price_status"], "Pending CEO")
		self.assertEqual(proposal["requests"], [])
		self.assertTrue(proposal["submit_on_approval"])

	@patch.object(approvals, "_history", return_value="[]")
	@patch.object(approvals.frappe.db, "set_value")
	@patch.object(approvals.frappe.db, "savepoint")
	@patch.object(approvals.frappe.db, "sql")
	@patch.object(approvals.prices, "_require_company")
	@patch.object(approvals.prices, "has_explicit_ceo_role", return_value=True)
	@patch.object(approvals.frappe, "get_doc")
	def test_approval_submits_po_when_requested(self, get_doc, explicit, company, sql, savepoint, set_value, history):
		doc = MagicMock()
		doc.name, doc.company, doc.modified, doc.docstatus = "PO-1", "MRG", "m1", 0
		doc.custom_po_price_status = "Pending CEO"
		doc.custom_po_price_proposal = ('{"po_modified":"m1","requests":[],"submit_on_approval":true,'
			'"changes":[{"index":0,"item_code":"CONS-1","rate":99,"po_only":true}]}')
		doc.get = MagicMock(side_effect=lambda key, default=None: {"custom_lpo_type": "Standard"}.get(key, default))
		doc.items = [SimpleNamespace(item_code="CONS-1", rate=99)]
		doc.flags = SimpleNamespace()
		get_doc.return_value = doc
		self.assertEqual(approvals.approve_po_price("PO-1")["status"], "Approved")
		doc.submit.assert_called_once()

	@patch.object(approvals.frappe, "get_doc")
	def test_rejected_po_only_rate_stays_on_draft(self, get_doc):
		row = SimpleNamespace(item_code="CONS-1", rate=99)
		po = MagicMock()
		po.items = [row]
		get_doc.return_value = po
		approvals._restore_draft_po_rates(
			frappe._dict(name="PO-1", docstatus=0),
			{"changes": [{"index": 0, "item_code": "CONS-1", "rate": 99, "old_po_rate": 10, "po_only": True}]},
		)
		self.assertEqual(row.rate, 99)
		po.save.assert_not_called()

	@patch.object(approvals, "prepare_rates")
	@patch.object(approvals, "_po_only", return_value=True)
	def test_approved_po_only_line_is_not_reapproved(self, po_only, prepare):
		doc = frappe._dict(controlled_procurement=1, custom_lpo_type="Standard", company="MRG", supplier="SUP-1",
			transaction_date="2026-10-02", items=[frappe._dict(item_code="CONS-1", rate=99)],
			custom_po_price_history='[{"action":"Approved","changes":[{"index":0,"item_code":"CONS-1","rate":99}]}]')
		self.assertEqual(approvals.pending_po_only_changes(doc), [])
		prepare.assert_not_called()

	@patch.object(approvals, "_po_only", return_value=True)
	@patch.object(approvals, "prepare_rates", return_value=[{"index": 0, "item_code": "CONS-1", "rate": 99, "po_only": True}])
	def test_unapproved_po_only_line_maps_back_to_po_row(self, prepare, po_only):
		doc = frappe._dict(controlled_procurement=1, custom_lpo_type="Standard", company="MRG", supplier="SUP-1",
			transaction_date="2026-10-02", custom_po_price_history="[]",
			items=[frappe._dict(item_code="ITEM-1", rate=10), frappe._dict(item_code="CONS-1", rate=99, custom_price_change_reason="Quote")])
		po_only.side_effect = lambda code, kind: code == "CONS-1"
		changes = approvals.pending_po_only_changes(doc)
		self.assertEqual(changes[0]["index"], 1)
		self.assertEqual(prepare.call_args.args[3][0]["price_change_reason"], "Quote")

	def test_print_blocked_until_approved_and_submitted(self):
		for docstatus, status in ((0, None), (1, "Pending CEO"), (1, "Pending Accounts")):
			with self.assertRaises(frappe.PermissionError):
				approvals.before_print_purchase_order(frappe._dict(name="PO-1", controlled_procurement=1, docstatus=docstatus, custom_po_price_status=status))
		approvals.before_print_purchase_order(frappe._dict(name="PO-1", controlled_procurement=1, docstatus=1, custom_po_price_status="Approved"))
		approvals.before_print_purchase_order(frappe._dict(name="PO-1", controlled_procurement=0, docstatus=0))
