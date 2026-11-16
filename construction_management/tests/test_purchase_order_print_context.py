# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from construction_management.purchase_order_print_context import (
	build_lpo_print_context,
	get_po_item_line_notes,
	get_po_item_print_block,
)


class TestPurchaseOrderPrintContext(IntegrationTestCase):
	def test_standard_lpo_type(self):
		doc = frappe._dict(custom_lpo_type="Standard", company="Test Co", supplier=None, owner="Administrator")
		ctx = build_lpo_print_context(doc)
		self.assertEqual(ctx["lpo_type"], "Standard")
		self.assertEqual(ctx["lpo_type_label"], "Standard LPO")

	def test_open_from_provisional_flag(self):
		doc = frappe._dict(custom_is_provisional_po=1, company="Test Co", supplier=None, owner="Administrator")
		ctx = build_lpo_print_context(doc)
		self.assertEqual(ctx["lpo_type"], "Open")
		self.assertTrue(ctx["is_open_lpo"])

	def test_manual_lpo_type(self):
		doc = frappe._dict(
			custom_lpo_type="Manual",
			custom_lpo_reference="REF-1",
			custom_lpo_approval_status="Approved",
			company="Test Co",
			supplier=None,
			owner="Administrator",
		)
		ctx = build_lpo_print_context(doc)
		self.assertEqual(ctx["lpo_type"], "Manual")
		self.assertEqual(ctx["lpo_reference"], "REF-1")
		self.assertEqual(ctx["approval_status"], "Approved")

	def test_skada_hides_mrg_delivery_contact(self):
		doc = frappe._dict(company="SKADA CONSTRUCTION L.L.C", owner="Administrator")
		ctx = build_lpo_print_context(doc)
		self.assertFalse(ctx["show_mrg_delivery_contact"])

	def test_mrg_shows_delivery_contact(self):
		doc = frappe._dict(company="MRG WATERPROOFING LLC", owner="Administrator")
		ctx = build_lpo_print_context(doc)
		self.assertTrue(ctx["show_mrg_delivery_contact"])

	def test_logo_url_from_company(self):
		doc = frappe._dict(company="MRG CO", owner="Administrator")
		with patch(
			"construction_management.purchase_order_print_context.frappe.db.get_value",
			return_value=frappe._dict(company_name="MRG CO", company_logo="/files/logo.png"),
		), patch(
			"construction_management.purchase_order_print_context.get_url",
			return_value="https://example.test/files/logo.png",
		):
			ctx = build_lpo_print_context(doc)
		self.assertEqual(ctx["logo_url"], "https://example.test/files/logo.png")
		self.assertEqual(ctx["company_name"], "MRG CO")

	def test_get_po_item_line_notes(self):
		item = frappe._dict(
			item_code="ITEM-1",
			item_name="Widget",
			description="Deliver to site gate B",
		)
		with patch(
			"construction_management.purchase_order_print_context.frappe.db.get_value",
			return_value="Catalog spec",
		):
			self.assertEqual(get_po_item_line_notes(item), "Deliver to site gate B")

		with patch(
			"construction_management.purchase_order_print_context.frappe.db.get_value",
			return_value="",
		):
			self.assertEqual(get_po_item_line_notes(item), "")

		item["description"] = "Widget"
		with patch(
			"construction_management.purchase_order_print_context.frappe.db.get_value",
			return_value="",
		):
			self.assertEqual(get_po_item_line_notes(item), "")

		item["description"] = ""
		self.assertEqual(get_po_item_line_notes(item), "")

	def test_get_po_item_print_block_description_and_notes(self):
		item = frappe._dict(
			item_code="ITEM-1",
			item_name="Widget",
			description="Deliver to site gate B",
		)
		with patch(
			"construction_management.purchase_order_print_context.frappe.db.get_value",
			return_value="Standard widget specification",
		):
			blk = get_po_item_print_block(item)
		self.assertEqual(blk["description"], "Standard widget specification")
		self.assertEqual(blk["notes"], "Deliver to site gate B")

		with patch(
			"construction_management.purchase_order_print_context.frappe.db.get_value",
			return_value="",
		):
			blk = get_po_item_print_block(item)
		self.assertEqual(blk["description"], "Deliver to site gate B")
		self.assertEqual(blk["notes"], "")

	def test_get_print_options_lists_lpo_formats(self):
		if not frappe.db.exists("Print Format", "LPO MRG Skada"):
			self.skipTest("LPO MRG Skada print format not installed")
		from construction_management.api.controlled_procurement import get_print_options

		po_name = frappe.db.get_value("Purchase Order", {}, "name")
		if not po_name:
			self.skipTest("No Purchase Order on site")
		options = get_print_options("Purchase Order", po_name)
		self.assertIn("LPO MRG Skada", options["print_formats"])
		if frappe.db.exists("Print Format", "LPO PF"):
			self.assertIn("LPO PF", options["print_formats"])