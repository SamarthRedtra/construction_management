from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.api import catalog_email
from construction_management.api import controlled_procurement as catalog
from construction_management.construction_management.doctype.controlled_catalog_request.controlled_catalog_request import ControlledCatalogRequest


class TestCatalogApprovalWorkflow(UnitTestCase):
	def test_direct_request_write_cannot_bypass_workflow(self):
		with self.assertRaises(frappe.PermissionError):
			ControlledCatalogRequest.validate(SimpleNamespace(flags=SimpleNamespace()))
		ControlledCatalogRequest.validate(SimpleNamespace(
			flags=SimpleNamespace(controlled_catalog_request_api=True)))

	@patch.object(catalog, "_has_explicit_role", return_value=False)
	@patch.object(catalog, "_roles", return_value={"Purchase Manager", "Accounts User"})
	def test_purchase_manager_with_accounts_user_cannot_skip_accounts(self, roles, explicit):
		self.assertEqual(catalog._catalog_request_origin(), "Purchase")
		self.assertEqual(catalog._catalog_request_status("Purchase"), "Pending Accounts")
		with self.assertRaises(frappe.PermissionError):
			catalog._catalog_request_origin("Accounts")

	@patch.object(catalog, "_has_explicit_role", return_value=True)
	@patch.object(catalog, "_roles", return_value={"Purchase Manager", "Accounts Manager"})
	def test_dual_role_user_explicitly_selects_accounts_origin(self, roles, explicit):
		self.assertEqual(catalog._catalog_request_origin(), "Purchase")
		self.assertEqual(catalog._catalog_request_origin("Accounts"), "Accounts")
		self.assertEqual(catalog._catalog_request_status("Accounts"), "Pending CEO")

	@patch.object(catalog, "_has_explicit_role", return_value=True)
	def test_accounts_manager_cannot_approve_own_request(self, explicit):
		with patch.object(catalog.frappe, "session", frappe._dict(user="manager@example.com")):
			self.assertFalse(catalog._can_approve_catalog(SimpleNamespace(
				status="Pending Accounts", requested_by="manager@example.com")))
			self.assertTrue(catalog._can_approve_catalog(SimpleNamespace(
				status="Pending Accounts", requested_by="buyer@example.com")))

	@patch.object(catalog, "_has_explicit_role", return_value=True)
	def test_catalog_ceo_is_named_user_with_explicit_role(self, explicit):
		self.assertFalse(catalog._catalog_ceo("Administrator"))
		self.assertTrue(catalog._catalog_ceo("faraaz@mrggroup.ae"))
		self.assertTrue(catalog._catalog_ceo("salman@mrggroup.ae"))

	@patch.object(catalog, "_catalog_ceo", return_value=False)
	def test_materialization_requires_catalog_ceo_even_at_zero_rate(self, ceo):
		with self.assertRaises(frappe.PermissionError):
			catalog._materialize_catalog_request(SimpleNamespace(items=[SimpleNamespace(rate=0)]))

	@patch.object(catalog, "_catalog_disable_row", return_value={"target_modified": "2026-10-15 10:00:00"})
	def test_disable_rejects_stale_item(self, current):
		with self.assertRaises(frappe.ValidationError):
			catalog._validate_catalog_disable_row(SimpleNamespace(
				item_code="ITEM-1", target_modified="2026-10-14 10:00:00"))

	@patch.object(catalog, "_can_request_catalog_disable", return_value=False)
	def test_purchase_user_cannot_request_disable(self, can_disable):
		with self.assertRaises(frappe.PermissionError):
			catalog.create_catalog_disable_request("ITEM-1", "Duplicate")

	@patch.object(catalog, "_queue_catalog_notices")
	@patch.object(catalog, "_append_catalog_log")
	@patch.object(catalog, "_catalog_disable_row", return_value={"item_code": "ITEM-1"})
	@patch.object(catalog, "_allowed_companies", return_value=["MRG"])
	@patch.object(catalog, "_catalog_ceo", return_value=False)
	@patch.object(catalog, "_has_explicit_role", side_effect=lambda role, user=None: role == "Purchase Manager")
	@patch.object(catalog, "_can_request_catalog_disable", return_value=True)
	@patch.object(catalog.frappe, "get_doc")
	def test_purchase_manager_disable_waits_for_ceo(self, get_doc, can_disable, role, ceo, companies, row, log, notify):
		doc = MagicMock()
		doc.name = "CCR-1"
		doc.status = "Pending CEO"
		get_doc.return_value = doc
		result = catalog.create_catalog_disable_request("ITEM-1", "Duplicate", "MRG")
		self.assertEqual(result["status"], "Pending CEO")
		doc.insert.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(get_doc.call_args.args[0]["request_origin"], "Purchase")
		notify.assert_called_once_with(doc)

	@patch.object(catalog, "_queue_catalog_notices")
	@patch.object(catalog, "_append_catalog_log")
	@patch.object(catalog, "_catalog_disable_row", return_value={"item_code": "ITEM-1"})
	@patch.object(catalog, "_allowed_companies", return_value=["MRG"])
	@patch.object(catalog, "_catalog_ceo", return_value=False)
	@patch.object(catalog, "_has_explicit_role", return_value=True)
	@patch.object(catalog, "_can_request_catalog_disable", return_value=True)
	@patch.object(catalog.frappe, "get_doc")
	def test_accounts_manager_disable_waits_for_ceo(self, get_doc, can_disable, role, ceo, companies, row, log, notify):
		doc = MagicMock()
		doc.name = "CCR-1"
		doc.status = "Pending CEO"
		get_doc.return_value = doc
		result = catalog.create_catalog_disable_request("ITEM-1", "Duplicate", "MRG")
		self.assertEqual(result["status"], "Pending CEO")
		doc.insert.assert_called_once_with(ignore_permissions=True)
		notify.assert_called_once_with(doc)

	@patch.object(catalog, "_validate_catalog_disable_row")
	@patch.object(catalog.frappe, "get_doc")
	def test_disable_saves_item_without_deleting_history(self, get_doc, validate):
		item = MagicMock()
		item.name = "ITEM-1"
		get_doc.return_value = item
		row = SimpleNamespace(item_code="ITEM-1", result_item="")
		with patch.dict(frappe.__dict__, {"db": MagicMock()}):
			catalog._disable_catalog_item(row)
		self.assertEqual(item.disabled, 1)
		self.assertTrue(item.flags.controlled_procurement_api)
		item.save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(row.result_item, "ITEM-1")

	@patch.object(catalog, "_queue_catalog_notices")
	@patch.object(catalog, "_append_catalog_log")
	@patch.object(catalog, "_materialize_catalog_request")
	@patch.object(catalog, "_can_approve_catalog", return_value=True)
	@patch.object(catalog, "_allowed_companies", return_value=["MRG"])
	@patch.object(catalog, "_require")
	@patch.object(catalog.frappe, "get_doc")
	def test_ceo_approval_applies_change_and_marks_approved(
		self, get_doc, require, companies, can_approve, materialize, log, notify,
	):
		doc = MagicMock()
		doc.company = "MRG"
		doc.status = "Pending CEO"
		doc.name = "CCR-1"
		get_doc.return_value = doc
		with patch.dict(frappe.__dict__, {"db": MagicMock()}):
			result = catalog.approve_catalog_request("CCR-1")
		materialize.assert_called_once_with(doc)
		self.assertEqual(result["status"], "Approved")
		doc.save.assert_called_once_with(ignore_permissions=True)

	@patch.object(catalog, "_queue_catalog_notices")
	@patch.object(catalog, "_append_catalog_log")
	@patch.object(catalog, "_catalog_correction_rows", return_value=([{"supplier": "SUP-1", "action": "Update"}], "Item name corrected"))
	@patch.object(catalog, "_allowed_companies", return_value=["MRG"])
	@patch.object(catalog, "_roles", return_value={"Purchase Manager"})
	@patch.object(catalog, "_require")
	@patch.object(catalog.frappe, "get_doc")
	def test_resubmission_preserves_saved_accounts_origin(
		self, get_doc, require, roles, companies, validate, log, notify,
	):
		row = SimpleNamespace(action="Update", supplier="SUP-1", as_dict=lambda: {"supplier": "SUP-1"})
		doc = MagicMock()
		doc.modified = "2026-10-16 12:00:00"
		doc.status = "Needs Correction"
		doc.requested_by = "buyer@example.com"
		doc.company = "MRG"
		doc.request_origin = "Accounts"
		doc.items = [row]
		get_doc.return_value = doc
		with patch.dict(frappe.__dict__, {"db": MagicMock()}), patch.object(catalog.frappe, "session", frappe._dict(user="buyer@example.com")):
			result = catalog.resubmit_catalog_request("CCR-1", {"expected_modified": doc.modified, "items": [{"name": "ROW-1"}]})
		self.assertEqual(result["status"], "Pending CEO")
		self.assertEqual(doc.request_origin, "Accounts")
		log.assert_called_once_with(doc, "Resubmitted", "Item name corrected")

	@patch.object(catalog, "_catalog_leaf_item_group")
	@patch.object(catalog, "_catalog_request_row", return_value={
		"item_code": "ITEM-1", "item_name": "Renamed Item", "item_group": "Products", "action": "Update", "result_item": "ITEM-1"})
	def test_rejected_item_edit_can_rename_without_changing_code(self, validate, group):
		original = SimpleNamespace(action="Update", item_code="ITEM-1", result_item="ITEM-1")
		request = SimpleNamespace(company="MRG", source="Item Edit")
		row = catalog._catalog_corrected_row(request, original, {
			"item_code": "ITEM-1", "item_name": "Renamed Item", "item_group": "Products"})
		self.assertEqual((row["item_code"], row["action"], row["result_item"]), ("ITEM-1", "Update", "ITEM-1"))
		self.assertTrue(validate.call_args.kwargs["allow_uom_edit"])

	@patch.object(catalog, "_catalog_leaf_item_group")
	@patch.object(catalog, "_catalog_request_row", return_value={
		"item_code": "", "item_name": "Corrected New Item", "item_group": "Products", "action": "Create", "result_item": ""})
	def test_rejected_create_can_rename_without_acquiring_existing_code(self, validate, group):
		original = SimpleNamespace(action="Create", item_code="", result_item="")
		with patch.dict(frappe.__dict__, {"db": MagicMock(exists=lambda *args, **kwargs: False)}):
			row = catalog._catalog_corrected_row(SimpleNamespace(company="MRG", source="Manual"), original,
				{"item_code": "", "item_name": "Corrected New Item", "item_group": "Products"})
		self.assertEqual((row["item_name"], row["item_code"], row["action"]), ("Corrected New Item", "", "Create"))

	@patch.object(catalog, "_catalog_leaf_item_group")
	@patch.object(catalog, "_catalog_request_row", return_value={
		"item_code": "", "item_name": "Existing Item", "action": "Update", "result_item": "ITEM-2"})
	def test_rejected_create_cannot_become_update(self, validate, group):
		original = SimpleNamespace(action="Create", item_code="", result_item="")
		with self.assertRaises(frappe.ValidationError):
			catalog._catalog_corrected_row(SimpleNamespace(company="MRG", source="Manual"), original,
				{"item_code": "", "item_name": "Existing Item", "item_group": "Products"})

	def test_correction_rejects_changed_item_code_and_action(self):
		row = MagicMock(name="ROW-1", action="Update", item_code="ITEM-1", result_item="ITEM-1")
		row.name = "ROW-1"
		row.get.side_effect = {"item_code": "ITEM-1", "action": "Update", "result_item": "ITEM-1"}.get
		request = SimpleNamespace(items=[row])
		with self.assertRaises(frappe.ValidationError):
			catalog._catalog_correction_rows(request, [{"name": "ROW-1", "item_code": "ITEM-2", "action": "Update", "result_item": "ITEM-1"}])
		with self.assertRaises(frappe.ValidationError):
			catalog._catalog_correction_rows(request, [{"name": "ROW-1", "item_code": "ITEM-1", "action": "Create", "result_item": "ITEM-1"}])

	@patch.object(catalog, "_catalog_group_change_request_row", return_value={"item_code": "ITEM-1", "item_name": "Item", "item_group": "New Group", "action": "Change Item Group", "result_item": "ITEM-1"})
	def test_group_correction_only_changes_target_group(self, group):
		original = SimpleNamespace(action="Change Item Group", item_code="ITEM-1", result_item="ITEM-1")
		row = catalog._catalog_corrected_row(SimpleNamespace(company="MRG", source="Manual"), original,
			{"item_code": "ITEM-1", "item_group": "New Group"})
		self.assertEqual(row["item_group"], "New Group")
		self.assertEqual(row["action"], "Change Item Group")

	@patch.object(catalog, "_catalog_leaf_item_group")
	@patch.object(catalog, "_catalog_request_row", return_value={
		"item_code": "ITEM-1", "item_name": "Item", "item_group": "Products", "supplier": "SUP-2", "action": "Link Supplier", "result_item": "ITEM-1"})
	def test_supplier_link_correction_keeps_link_action(self, validate, group):
		original = SimpleNamespace(action="Link Supplier", item_code="ITEM-1", result_item="ITEM-1")
		with patch.dict(frappe.__dict__, {"db": MagicMock(exists=lambda *args, **kwargs: False)}):
			row = catalog._catalog_corrected_row(SimpleNamespace(company="MRG", source="Manual"), original,
				{"item_code": "ITEM-1", "item_group": "Products", "supplier": "SUP-2"})
		self.assertEqual((row["action"], row["result_item"]), ("Link Supplier", "ITEM-1"))

	@patch.object(catalog, "_catalog_corrected_row")
	def test_correction_records_changed_name_and_preserves_row_count(self, corrected):
		original_data = {"name": "ROW-1", "item_code": "ITEM-1", "result_item": "ITEM-1", "action": "Update",
			"item_name": "Old Name", "item_group": "Products", "item_type": "Stockable", "stock_uom": "Nos",
			"supplier": "SUP-1", "rate": 10, "asset_category": "", "expense_account": ""}
		original = MagicMock()
		original.name, original.action = "ROW-1", "Update"
		original.item_code, original.result_item, original.item_name = "ITEM-1", "ITEM-1", "Old Name"
		original.get.side_effect = original_data.get
		original.as_dict.return_value = original_data.copy()
		corrected.return_value = {**original_data, "item_name": "New Name"}
		request = SimpleNamespace(items=[original])
		edited = {**original_data, "item_name": "New Name"}

		rows, summary = catalog._catalog_correction_rows(request, [edited])

		self.assertEqual(rows[0]["item_name"], "New Name")
		self.assertIn("Old Name → New Name", summary)
		with self.assertRaises(frappe.ValidationError):
			catalog._catalog_correction_rows(request, [])

	@patch.object(catalog, "_allowed_companies", return_value=["MRG"])
	@patch.object(catalog, "_require")
	@patch.object(catalog.frappe, "get_doc")
	def test_resubmission_rejects_stale_and_other_requester(self, get_doc, require, companies):
		doc = MagicMock(status="Needs Correction", requested_by="buyer@example.com", company="MRG",
			modified="2026-10-16 12:00:00")
		get_doc.return_value = doc
		with patch.dict(frappe.__dict__, {"db": MagicMock()}), patch.object(catalog.frappe, "session", frappe._dict(user="other@example.com")):
			with self.assertRaises(frappe.PermissionError):
				catalog.resubmit_catalog_request("CCR-1", {"expected_modified": doc.modified})
		with patch.dict(frappe.__dict__, {"db": MagicMock()}), patch.object(catalog.frappe, "session", frappe._dict(user="buyer@example.com")):
			with self.assertRaises(frappe.ValidationError):
				catalog.resubmit_catalog_request("CCR-1", {"expected_modified": "2026-10-15 12:00:00"})

	@patch.object(catalog, "_queue_catalog_notices")
	@patch.object(catalog, "_append_catalog_log")
	@patch.object(catalog, "_validate_catalog_disable_row")
	@patch.object(catalog, "_has_explicit_role", return_value=True)
	@patch.object(catalog, "_allowed_companies", return_value=["MRG"])
	@patch.object(catalog, "_require")
	@patch.object(catalog.frappe, "get_doc")
	def test_disable_correction_changes_reason_only(self, get_doc, require, companies, role, validate, log, notify):
		doc = MagicMock(status="Needs Correction", requested_by="buyer@example.com", company="MRG",
			modified="2026-10-16 12:00:00", disable_reason="Old reason", request_origin="Accounts")
		doc.items = [SimpleNamespace(action="Disable")]
		get_doc.return_value = doc
		with patch.dict(frappe.__dict__, {"db": MagicMock()}), patch.object(catalog.frappe, "session", frappe._dict(user="buyer@example.com")):
			result = catalog.resubmit_catalog_request("CCR-1", {
				"expected_modified": doc.modified, "disable_reason": "Corrected reason"})
		self.assertEqual(result["status"], "Pending CEO")
		self.assertEqual(doc.disable_reason, "Corrected reason")
		log.assert_called_once_with(doc, "Resubmitted", "Disable reason: Old reason → Corrected reason")

	@patch.object(catalog, "today", return_value="2026-10-16")
	@patch.object(catalog.frappe, "get_all")
	def test_ceo_review_includes_current_item_and_buying_rate(self, get_all, current_date):
		get_all.side_effect = [
			[frappe._dict(name="ITEM-1", item_name="Old Name", item_group="Old Group",
				controlled_item_type="Stockable", stock_uom="Nos", asset_category="")],
			[frappe._dict(parent="ITEM-1", expense_account="")],
			[frappe._dict(parent="ITEM-1", supplier="SUP-1")],
			[frappe._dict(item_code="ITEM-1", supplier="SUP-1", uom="Nos", price_list_rate=12,
				valid_from=None, valid_upto=None)],
		]
		row = SimpleNamespace(name="ROW-1", action="Update", item_code="ITEM-1", result_item="ITEM-1",
			supplier="SUP-1", stock_uom="Nos")
		review = catalog._catalog_review_values(SimpleNamespace(items=[row], company="MRG"))
		self.assertEqual(review["ROW-1"]["item_name"], "Old Name")
		self.assertEqual(review["ROW-1"]["item_group"], "Old Group")
		self.assertEqual(review["ROW-1"]["suppliers"], ["SUP-1"])
		self.assertEqual(review["ROW-1"]["rate"], 12)

	@patch.object(catalog, "_catalog_review_values", return_value={"ROW-1": {"rate": 12}})
	@patch.object(catalog, "_allowed_companies", return_value=["MRG"])
	@patch.object(catalog, "_require")
	@patch.object(catalog.frappe, "get_doc")
	def test_request_detail_includes_currency_and_review(self, get_doc, require, companies, review):
		doc = MagicMock(company="MRG", approval_email_queue="")
		doc.as_dict.return_value = {"name": "CCR-1", "items": [{"name": "ROW-1"}]}
		get_doc.return_value = doc
		with patch.dict(frappe.__dict__, {"db": MagicMock(get_value=lambda *args, **kwargs: "AED")}):
			result = catalog.get_catalog_request("CCR-1")
		self.assertEqual(result["currency"], "AED")
		self.assertEqual(result["review"]["ROW-1"]["rate"], 12)

	def test_document_sender_uses_company_email_account(self):
		db = MagicMock()
		db.get_value.return_value = frappe._dict(email_id="purchase@mrggroup.ae", enable_outgoing=1)
		with patch.dict(frappe.__dict__, {"db": db, "conf": frappe._dict()}):
			self.assertEqual(catalog_email.outgoing_sender("M R G INSULATION WORKS L.L.C"), "purchase@mrggroup.ae")
		self.assertEqual(db.get_value.call_args.args[1], "MRG Purchase")

	def test_missing_company_email_account_does_not_fall_back(self):
		db = MagicMock()
		db.get_value.return_value = None
		with patch.dict(frappe.__dict__, {"db": db, "conf": frappe._dict()}):
			with self.assertRaises(frappe.OutgoingEmailError):
				catalog_email.outgoing_sender("M R G INSULATION WORKS L.L.C")

	@patch.object(catalog_email.frappe, "get_all")
	def test_ceo_email_recipients_exclude_administrator(self, get_all):
		get_all.side_effect = [["Administrator", "salman@mrggroup.ae", "faraaz@mrggroup.ae"], [], []]
		db = MagicMock()
		db.exists.return_value = True
		with patch.dict(frappe.__dict__, {"db": db}):
			self.assertEqual(catalog_email.catalog_approval_recipients("MRG", "Pending CEO"),
				["faraaz@mrggroup.ae", "salman@mrggroup.ae"])

	@patch("construction_management.api.controlled_price_requests._enqueue_catalog_notice")
	@patch("construction_management.api.catalog_email.enqueue_approval_email")
	def test_queue_catalog_notices_raven_only_for_pending_stages(self, email, raven):
		catalog._queue_catalog_notices(SimpleNamespace(name="CCR-1", status="Pending Accounts"))
		email.assert_not_called()
		raven.assert_called_once_with("CCR-1", "Pending Accounts")
		email.reset_mock()
		raven.reset_mock()
		catalog._queue_catalog_notices(SimpleNamespace(name="CCR-1", status="Pending CEO"))
		email.assert_not_called()
		raven.assert_called_once_with("CCR-1", "Pending CEO")
		email.reset_mock()
		raven.reset_mock()
		catalog._queue_catalog_notices(SimpleNamespace(name="CCR-1", status="Approved"))
		email.assert_not_called()
		raven.assert_not_called()

	@patch.object(catalog, "_queue_catalog_rejection_notice")
	@patch.object(catalog, "_append_catalog_log")
	@patch.object(catalog, "_can_approve_catalog", return_value=True)
	@patch.object(catalog, "_allowed_companies", return_value=["MRG"])
	@patch.object(catalog, "_require")
	@patch.object(catalog.frappe, "get_doc")
	def test_reject_enqueues_requester_raven_notice(
		self, get_doc, require, companies, can_approve, log, reject_notice,
	):
		doc = MagicMock()
		doc.company = "MRG"
		doc.status = "Pending Accounts"
		doc.name = "CCR-1"
		get_doc.return_value = doc
		with patch.dict(frappe.__dict__, {"db": MagicMock()}):
			result = catalog.reject_catalog_request("CCR-1", "Fix UOM")
		self.assertEqual(result["status"], "Needs Correction")
		self.assertEqual(doc.rejection_reason, "Fix UOM")
		reject_notice.assert_called_once_with(doc)

	@patch.object(catalog, "_require")
	def test_retry_catalog_approval_email_is_disabled(self, require):
		with self.assertRaisesRegex(frappe.ValidationError, "emails are disabled"):
			catalog.retry_catalog_approval_email("CCR-1")

	@patch("construction_management.api.controlled_price_requests.frappe.db.exists", return_value=True)
	@patch("construction_management.api.catalog_email.catalog_approval_recipients", return_value=["accounts@example.com"])
	def test_catalog_raven_payload_accounts_stage(self, recipients, exists):
		from construction_management.api.controlled_price_requests import _catalog_raven_payload

		users, text, _error = _catalog_raven_payload(SimpleNamespace(
			name="CCR-1", company="MRG", requested_by="buyer@example.com", rejection_reason="",
		), "Pending Accounts")
		self.assertEqual(users, ["accounts@example.com"])
		self.assertIn("Accounts approval", text)

	@patch("construction_management.api.controlled_price_requests.frappe.db.exists", return_value=True)
	def test_catalog_raven_payload_rejection_to_requester(self, exists):
		from construction_management.api.controlled_price_requests import _catalog_raven_payload

		users, text, _error = _catalog_raven_payload(SimpleNamespace(
			name="CCR-1", company="MRG", requested_by="buyer@example.com", rejection_reason="Fix UOM",
		), "Needs Correction")
		self.assertEqual(users, ["buyer@example.com"])
		self.assertIn("Fix UOM", text)

	def test_document_activity_does_not_label_queued_mail_sent(self):
		communication = SimpleNamespace(sent_or_received="Sent", delivery_status="")
		queue = SimpleNamespace(status="Not Sent")
		self.assertEqual(catalog._email_delivery_status(communication, queue), "Queued")
		queue.status = "Error"
		self.assertEqual(catalog._email_delivery_status(communication, queue), "Error")
		queue.status = "Sent"
		self.assertEqual(catalog._email_delivery_status(communication, queue), "Sent")

	@patch("frappe.core.doctype.communication.email.make", return_value={"name": "COMM-1", "emails_not_sent_to": ""})
	@patch.object(catalog_email, "outgoing_sender", return_value="purchase@mrggroup.ae")
	@patch.object(catalog.frappe, "has_permission", return_value=True)
	@patch.object(catalog, "_controlled_doc", return_value=SimpleNamespace(company="MRG"))
	def test_document_email_queues_from_company_sender(self, controlled_doc, permission, sender, make):
		result = catalog.send_document_email("Purchase Order", "PO-1", "supplier@example.com", "Order")
		self.assertEqual(result["status"], "Queued")
		self.assertEqual(make.call_args.kwargs["sender"], "purchase@mrggroup.ae")
