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

	@patch.object(catalog, "_catalog_ceo", return_value=False)
	@patch.object(catalog, "_has_explicit_role", return_value=False)
	def test_purchase_manager_cannot_request_disable(self, role, ceo):
		with self.assertRaises(frappe.PermissionError):
			catalog.create_catalog_disable_request("ITEM-1", "Duplicate")

	@patch.object(catalog, "_queue_catalog_notices")
	@patch.object(catalog, "_append_catalog_log")
	@patch.object(catalog, "_catalog_disable_row", return_value={"item_code": "ITEM-1"})
	@patch.object(catalog, "_allowed_companies", return_value=["MRG"])
	@patch.object(catalog, "_catalog_ceo", return_value=False)
	@patch.object(catalog, "_has_explicit_role", return_value=True)
	@patch.object(catalog.frappe, "get_doc")
	def test_accounts_manager_disable_waits_for_ceo(self, get_doc, role, ceo, companies, row, log, notify):
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
	@patch.object(catalog, "_catalog_request_row", return_value={"supplier": "SUP-1"})
	@patch.object(catalog, "_allowed_companies", return_value=["MRG"])
	@patch.object(catalog, "_roles", return_value={"Purchase Manager"})
	@patch.object(catalog, "_require")
	@patch.object(catalog.frappe, "get_doc")
	def test_resubmission_preserves_saved_accounts_origin(
		self, get_doc, require, roles, companies, validate, log, notify,
	):
		row = SimpleNamespace(action="Update", supplier="SUP-1", as_dict=lambda: {"supplier": "SUP-1"})
		doc = MagicMock()
		doc.status = "Needs Correction"
		doc.requested_by = "buyer@example.com"
		doc.company = "MRG"
		doc.request_origin = "Accounts"
		doc.items = [row]
		get_doc.return_value = doc
		with patch.dict(frappe.__dict__, {"db": MagicMock()}), patch.object(catalog.frappe, "session", frappe._dict(user="buyer@example.com")):
			result = catalog.resubmit_catalog_request("CCR-1")
		self.assertEqual(result["status"], "Pending CEO")
		self.assertEqual(doc.request_origin, "Accounts")

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

	@patch.object(catalog_email, "outgoing_sender", return_value="purchase@mrggroup.ae")
	@patch.object(catalog_email, "catalog_approval_recipients", return_value=["manager@example.com"])
	@patch.object(catalog_email.frappe, "sendmail", return_value=SimpleNamespace(name="QUEUE-1"))
	@patch.object(catalog_email.frappe, "get_doc")
	def test_approval_email_creates_traceable_queue(self, get_doc, sendmail, recipients, sender):
		doc = MagicMock()
		doc.status = "Pending Accounts"
		doc.approval_email_queue = ""
		doc.company = "MRG"
		doc.requested_by = "buyer@example.com"
		doc.name = "CCR-1"
		doc.doctype = "Controlled Catalog Request"
		get_doc.return_value = doc
		db = MagicMock()
		db.get_value.return_value = "manager@example.com"
		with patch.dict(frappe.__dict__, {"db": db}), patch.object(catalog_email.frappe.utils, "get_url", return_value="https://example.com/approvals"):
			catalog_email.deliver_approval_email("CCR-1", "Pending Accounts")
		self.assertEqual(doc.approval_email_queue, "QUEUE-1")
		self.assertEqual(sendmail.call_args.kwargs["sender"], "purchase@mrggroup.ae")
		doc.save.assert_called_once_with(ignore_permissions=True)

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
