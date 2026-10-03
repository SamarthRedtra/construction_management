"""Focused checks for warehouse-only transfers and procurement audit summaries."""

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.api import controlled_procurement as procurement
from construction_management.api import procurement_insights


class TestProcurementRevisions(UnitTestCase):
	@patch("construction_management.api.controlled_procurement._require")
	@patch("construction_management.api.controlled_procurement._document_company", return_value="MRG")
	@patch("construction_management.api.controlled_procurement.frappe.db.exists", return_value=True)
	@patch("construction_management.api.controlled_procurement._catalog_item")
	@patch("construction_management.api.controlled_procurement.frappe.get_all", return_value=[])
	def test_transfer_stock_preview_uses_zero_for_missing_bin(self, get_all, catalog_item, exists, company, require):
		catalog_item.return_value = frappe._dict(controlled_item_type="Stockable", is_stock_item=1)
		result = procurement.get_transfer_stock_preview("Stores - MRG", ["ITEM-1", "ITEM-1"])
		self.assertEqual(result["balances"], {"ITEM-1": 0.0})
		require.assert_called_once_with(procurement.STOCK_ROLES)
		get_all.assert_called_once()
		self.assertEqual(get_all.call_args.kwargs["filters"]["item_code"], ["in", ["ITEM-1"]])

	@patch("construction_management.api.controlled_procurement._require")
	@patch("construction_management.api.controlled_procurement._document_company", return_value="MRG")
	@patch("construction_management.api.controlled_procurement.frappe.db.exists", return_value=False)
	def test_transfer_stock_preview_rejects_other_company_warehouse(self, exists, company, require):
		with self.assertRaises(frappe.PermissionError):
			procurement.get_transfer_stock_preview("Other company warehouse", ["ITEM-1"])
		self.assertEqual(exists.call_args.args[0], "Warehouse")
		self.assertEqual(exists.call_args.args[1]["company"], "MRG")

	@patch("construction_management.api.controlled_procurement._require")
	@patch("construction_management.api.controlled_procurement._document_company", return_value="MRG")
	@patch("construction_management.api.controlled_procurement.frappe.db.exists", return_value=True)
	@patch("construction_management.api.controlled_procurement._catalog_item")
	def test_transfer_stock_preview_rejects_nonstock_item(self, catalog_item, exists, company, require):
		catalog_item.return_value = frappe._dict(controlled_item_type="Service", is_stock_item=0)
		with self.assertRaisesRegex(frappe.ValidationError, "Stockable"):
			procurement.get_transfer_stock_preview("Stores - MRG", ["SERVICE-1"])

	def test_insights_include_every_procurement_workspace_role(self):
		self.assertEqual(procurement_insights.INSIGHT_ROLES, procurement.CATALOG_ROLES)
		self.assertIn("Purchase User", procurement_insights.INSIGHT_ROLES)
		self.assertIn("Stock User", procurement_insights.INSIGHT_ROLES)
		self.assertIn("Accounts User", procurement_insights.INSIGHT_ROLES)

	@patch("construction_management.api.procurement_insights._require")
	@patch("construction_management.api.procurement_insights._company", return_value="MRG")
	def test_unrestricted_ledger_keeps_separate_permission(self, company, require):
		procurement_insights._ledger_scope("", "", "", "", "", "")
		require.assert_called_once_with(procurement_insights.LEDGER_ROLES)
		self.assertNotIn("Purchase User", procurement_insights.LEDGER_ROLES)

	@patch("construction_management.api.controlled_procurement._require")
	def test_document_sort_rejects_unapproved_sql_field(self, require):
		with self.assertRaisesRegex(frappe.ValidationError, "Invalid document sort"):
			procurement.get_controlled_documents("Purchase Order", sort_by="name; drop table")

	def test_ledger_export_escapes_spreadsheet_formulas(self):
		self.assertEqual(procurement_insights._csv_text("=1+1"), "'=1+1")
		self.assertEqual(procurement_insights._csv_text("ITEM-1"), "ITEM-1")

	def test_ledger_filter_options_reject_unapproved_field(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Invalid stock-ledger filter"):
			procurement_insights.get_stock_ledger_options("voucher_no")

	@patch("construction_management.api.controlled_procurement.frappe.db.exists", return_value=False)
	def test_tagging_excludes_users_without_enabled_raven(self, exists):
		doc = frappe._dict(doctype="Purchase Order", company="MRG")
		self.assertFalse(procurement._eligible_tag_user(doc, "disabled@example.com"))

	@patch("construction_management.api.controlled_procurement._validate_allocation")
	@patch("construction_management.api.controlled_procurement._validate_transfer_warehouses")
	@patch("construction_management.api.controlled_procurement._catalog_item")
	def test_transfer_validation_does_not_require_boq(self, catalog_item, validate_warehouses, validate_allocation):
		catalog_item.return_value = frappe._dict(controlled_item_type="Stockable", is_stock_item=1)
		row = frappe._dict(item_code="ITEM-1", uom="Nos", s_warehouse="From", t_warehouse="To")
		doc = MagicMock()
		doc.doctype = "Stock Entry"
		doc.purpose = "Material Transfer"
		doc.company = "MRG"
		doc.from_warehouse = "From"
		doc.to_warehouse = "To"
		doc.flags.controlled_procurement_api = True
		doc.get.side_effect = lambda field: {"controlled_procurement": 1, "items": [row]}.get(field)
		doc.is_new.return_value = False
		procurement.validate_transaction(doc)
		validate_warehouses.assert_called_once_with("MRG", "From", "To")
		validate_allocation.assert_not_called()

	@patch("construction_management.api.controlled_procurement.frappe.db.exists", return_value=True)
	def test_transfer_warehouses_need_no_project(self, exists):
		procurement._validate_transfer_warehouses("MRG", "Stores - MRG", "Site - MRG")
		self.assertEqual(exists.call_count, 2)

	def test_transfer_rejects_same_warehouse(self):
		with self.assertRaisesRegex(frappe.ValidationError, "different From and To"):
			procurement._validate_transfer_warehouses("MRG", "Stores - MRG", "Stores - MRG")

	@patch("construction_management.api.controlled_procurement.frappe.get_meta")
	def test_version_summary_includes_field_and_item_edits(self, get_meta):
		get_meta.return_value.get_label.side_effect = lambda name: name.replace("_", " ").title()
		changes = procurement._version_changes("Purchase Receipt", json.dumps({
			"changed": [["supplier_delivery_note", "DN-1", "DN-2"], ["grand_total", 100, 200]],
			"added": [["items", {"item_code": "ITEM-2", "qty": 3}]],
			"removed": [["items", {"item_code": "ITEM-1"}]],
			"row_changed": [["items", "ROW-1", 1, [["qty", 1, 2]]]],
		}))
		self.assertIn("Supplier Delivery Note: DN-1 → DN-2", changes)
		self.assertIn("Added item ITEM-2 (qty 3)", changes)
		self.assertIn("Removed item ITEM-1", changes)
		self.assertIn("Item ROW-1: Qty 1 → 2", changes)
		self.assertEqual(len(changes), 4)

	@patch("construction_management.api.controlled_procurement.frappe.copy_doc")
	@patch("construction_management.api.controlled_procurement._controlled_doc")
	def test_amendment_links_native_predecessor(self, controlled_doc, copy_doc):
		original = MagicMock(name="GRN-1")
		original.name = "GRN-1"
		original.docstatus = 2
		controlled_doc.return_value = original
		amended = MagicMock()
		amended.name = "GRN-1-1"
		amended.docstatus = 0
		copy_doc.return_value = amended
		result = procurement._cancel_and_amend("Purchase Receipt", "GRN-1", True)
		self.assertEqual(amended.amended_from, "GRN-1")
		amended.insert.assert_called_once()
		self.assertEqual(result["name"], "GRN-1-1")

	@patch("construction_management.api.controlled_procurement._controlled_doc")
	def test_cancellation_restrictions_are_not_bypassed(self, controlled_doc):
		doc = controlled_doc.return_value
		doc.docstatus = 1
		doc.cancel.side_effect = frappe.ValidationError("Linked invoice prevents cancellation")
		with self.assertRaisesRegex(frappe.ValidationError, "Linked invoice"):
			procurement._cancel_and_amend("Purchase Receipt", "GRN-1", False)
