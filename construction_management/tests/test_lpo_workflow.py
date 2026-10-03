from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.api import controlled_procurement, lpo_workflow
from redtra_customisation.override import provisional_purchase_order


class TestLpoWorkflow(UnitTestCase):
	def test_open_lpo_can_be_received_after_full_receipt(self):
		po = frappe._dict(docstatus=1, status="Completed", per_received=100)
		controlled_procurement._validate_receivable_po(po, True)
		with self.assertRaisesRegex(frappe.ValidationError, "no quantity left"):
			controlled_procurement._validate_receivable_po(po, False)

	def test_closed_open_lpo_cannot_be_received(self):
		po = frappe._dict(docstatus=1, status="Closed", per_received=100)
		with self.assertRaises(frappe.ValidationError):
			controlled_procurement._validate_receivable_po(po, True)

	@patch("redtra_customisation.override.provisional_purchase_order.get_provisional_settings", return_value={"enabled": False})
	@patch("redtra_customisation.override.provisional_purchase_order.frappe.db.get_value")
	@patch("redtra_customisation.override.provisional_purchase_order.frappe.get_meta")
	def test_controlled_open_lpo_syncs_without_global_setting(self, get_meta, get_value, settings):
		get_meta.return_value.has_field.return_value = True
		get_value.return_value = frappe._dict(custom_is_provisional_po=1, controlled_procurement=1, custom_lpo_type="Open")
		self.assertTrue(provisional_purchase_order.is_provisional_po("PO-1"))
		settings.assert_not_called()
		get_value.return_value.custom_lpo_type = "Standard"
		self.assertFalse(provisional_purchase_order.is_provisional_po("PO-1"))

	@patch("redtra_customisation.override.provisional_purchase_order._apply_po_item_updates")
	@patch("redtra_customisation.override.provisional_purchase_order.is_provisional_po", return_value=True)
	@patch("redtra_customisation.override.provisional_purchase_order.frappe.db.get_value")
	def test_open_lpo_receipt_bumps_po_qty_on_submit(self, get_value, is_provisional, apply_updates):
		get_value.return_value = frappe._dict(qty=11, received_qty=0, rate=10, item_code="ITEM-1",
			uom="Nos", schedule_date="2026-10-02", description="Item", conversion_factor=1)
		receipt = frappe._dict(items=[frappe._dict(purchase_order="PO-1", purchase_order_item="ROW-1", qty=2000)])
		provisional_purchase_order.bump_provisional_po_qty_before_receipt(receipt)
		self.assertEqual(apply_updates.call_args.args[1][0]["qty"], 2000)

	@patch("construction_management.api.controlled_procurement._require")
	@patch("construction_management.api.controlled_procurement._document_company", return_value="MRG")
	@patch("construction_management.api.controlled_procurement._has_open_po_field", return_value=True)
	@patch("construction_management.api.controlled_procurement.frappe.get_list", return_value=["PO-1"])
	@patch("construction_management.api.controlled_procurement.frappe.db.sql", return_value=[])
	def test_open_lpo_search_includes_fully_received_orders(self, sql, get_list, field, company, require):
		controlled_procurement.get_open_lpos(open_po_only=1)
		query = sql.call_args.args[0]
		self.assertIn("po.custom_is_provisional_po = 1", query)
		self.assertIn("pending_qty > 0 or is_open_po = 1", query)
		self.assertNotIn('"per_received": ["<", 100]', str(get_list.call_args))

	@patch("construction_management.api.controlled_procurement._require")
	@patch("construction_management.api.controlled_procurement._controlled_doc")
	@patch("construction_management.api.controlled_procurement._is_open_lpo", return_value=True)
	@patch("construction_management.api.controlled_procurement._vat_choice", return_value="standard")
	def test_fully_received_open_lpo_returns_item_line(self, vat, is_open, controlled_doc, require):
		row = frappe._dict(name="ROW-1", item_code="ITEM-1", item_name="Item", qty=11, received_qty=11,
			rate=10, project="P-1", bill_no="", boq_item="", controlled_item_type="Asset",
			item_tax_template="", uom="Nos", warehouse="Stores", closed=0, delivered_by_supplier=0)
		po = frappe._dict(docstatus=1, status="Completed", per_received=100, company="MRG",
			taxes_and_charges="", controlled_procurement=1, items=[row])
		controlled_doc.return_value = po
		result = controlled_procurement.get_purchase_order_items("PO-1")
		self.assertEqual(result[0]["remaining_qty"], 0)
		self.assertTrue(result[0]["is_open_lpo"])

	def test_legacy_open_lpo_is_classified_from_existing_flag(self):
		doc = frappe._dict(custom_lpo_type="", custom_is_provisional_po=1)
		self.assertEqual(lpo_workflow.lpo_type(doc), "Open")

	def test_manual_lpo_cannot_submit_outside_ceo_action(self):
		doc = MagicMock()
		doc.get.side_effect = {"controlled_procurement": 1, "custom_lpo_type": "Manual"}.get
		doc.custom_lpo_approval_status = "Approved"
		doc.flags.lpo_ceo_submit = False
		with self.assertRaises(frappe.PermissionError):
			lpo_workflow.before_submit_purchase_order(doc)

	def test_manual_lpo_requires_approved_state_even_with_transition_flag(self):
		doc = MagicMock()
		doc.get.side_effect = {"controlled_procurement": 1, "custom_lpo_type": "Manual"}.get
		doc.custom_lpo_approval_status = "Pending CEO"
		doc.flags.lpo_ceo_submit = True
		with self.assertRaises(frappe.PermissionError):
			lpo_workflow.before_submit_purchase_order(doc)

	@patch("construction_management.api.controlled_procurement._controlled_doc")
	def test_generic_submit_rejects_manual_lpo(self, controlled_doc):
		doc = controlled_doc.return_value
		doc.docstatus = 0
		doc.get.side_effect = {"controlled_procurement": 1, "custom_lpo_type": "Manual"}.get
		with self.assertRaises(frappe.ValidationError):
			controlled_procurement.submit_document("Purchase Order", "PO-1")
		doc.submit.assert_not_called()

	@patch("construction_management.api.lpo_workflow.get_manual_lpo")
	@patch("construction_management.api.lpo_workflow.frappe.get_roles", return_value=["Accounts User"])
	@patch("construction_management.api.lpo_workflow.transition")
	def test_accounts_stage_goes_to_ceo_without_submitting(self, transition, roles, manual_lpo):
		doc = manual_lpo.return_value
		doc.docstatus = 0
		doc.custom_lpo_approval_status = "Pending Accounts"
		lpo_workflow.approve("PO-1")
		transition.assert_called_once_with(doc, "Pending CEO", "Accounts approved")
		doc.submit.assert_not_called()
