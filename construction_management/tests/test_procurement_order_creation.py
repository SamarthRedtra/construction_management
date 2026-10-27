from datetime import date
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.api import controlled_procurement
from construction_management.overrides.purchase_receipt import validate_supplier_delivery_note


class TestProcurementOrderCreation(UnitTestCase):
	@patch("construction_management.api.controlled_procurement.frappe.new_doc")
	@patch("construction_management.api.controlled_procurement._purchase_order_for_request")
	@patch("construction_management.api.controlled_procurement._document_company", return_value="MRG")
	@patch("construction_management.api.controlled_procurement._require")
	def test_repeated_request_returns_original_order(self, require, company, existing, new_doc):
		existing.return_value = {"doctype": "Purchase Order", "name": "PO-1"}
		result = controlled_procurement.create_purchase_order({
			"company": "MRG", "creation_request_id": "c0f2d9b3-8408-40e1-a720-e2c9f527e521",
		})
		self.assertEqual(result["name"], "PO-1")
		new_doc.assert_not_called()

	@patch("construction_management.api.controlled_procurement.frappe.session", frappe._dict(user="buyer@example.com"))
	@patch("construction_management.api.controlled_procurement.frappe.db.sql")
	def test_creation_request_is_scoped_to_owner_and_company(self, sql):
		sql.return_value = [frappe._dict(name="PO-1", company="MRG", owner="other@example.com",
			controlled_procurement=1, is_subcontracted=0)]
		with self.assertRaises(frappe.PermissionError):
			controlled_procurement._purchase_order_for_request("request-id", "MRG")

	def test_supplier_do_number_rejects_whitespace(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Supplier DO No"):
			validate_supplier_delivery_note(frappe._dict(supplier_delivery_note="  ", docstatus=0))

	@patch("construction_management.overrides.purchase_receipt.frappe.db.get_value", return_value=None)
	def test_supplier_do_number_is_trimmed(self, get_value):
		doc = frappe._dict(supplier_delivery_note="  DO-123  ", docstatus=0, name="GRN-NEW")
		validate_supplier_delivery_note(doc)
		self.assertEqual(doc.supplier_delivery_note, "DO-123")

	@patch("construction_management.overrides.purchase_receipt.frappe.db.get_value", return_value="GRN-OTHER")
	def test_supplier_do_number_rejects_active_duplicate(self, get_value):
		with self.assertRaisesRegex(frappe.ValidationError, "already used on Receive Note GRN-OTHER"):
			validate_supplier_delivery_note(frappe._dict(supplier_delivery_note="DO-123", docstatus=0, name="GRN-NEW"))

	@patch("construction_management.api.controlled_procurement.frappe.get_all")
	def test_receive_note_discovers_source_and_direct_documents(self, get_all):
		get_all.side_effect = [["PI-1"], ["GRN-RETURN-1"]]
		doc = MagicMock()
		doc.name = "GRN-1"
		doc.company = "MRG"
		doc.custom_purchase_order = "PO-1"
		doc.items = [frappe._dict(purchase_order="PO-1")]
		links = controlled_procurement._receipt_direct_connections(doc)
		self.assertEqual(links[0][1:], ("Purchase Order", ["PO-1"]))
		self.assertEqual(links[1][2], ["PI-1"])
		self.assertEqual(links[2][2], ["GRN-RETURN-1"])

	@patch("construction_management.api.controlled_procurement.frappe.get_list")
	@patch("construction_management.api.controlled_procurement.frappe.get_meta")
	def test_connected_documents_are_company_scoped(self, get_meta, get_list):
		get_meta.return_value = frappe._dict(is_submittable=1, has_field=lambda field: field == "company")
		controlled_procurement._connection_rows("Purchase Order", ["PO-1"], "MRG")
		self.assertEqual(get_list.call_args.kwargs["filters"]["company"], "MRG")

	@patch("construction_management.api.controlled_procurement._apply_taxes")
	@patch("construction_management.api.controlled_procurement._set_row_type")
	@patch("construction_management.api.controlled_procurement._apply_allocation")
	@patch("construction_management.api.controlled_procurement.get_warehouse_project", return_value="")
	@patch("construction_management.api.controlled_procurement._catalog_item", return_value={})
	@patch("construction_management.api.controlled_procurement._validate_company_links")
	@patch("construction_management.api.controlled_procurement._validate_allocation")
	@patch("construction_management.api.controlled_procurement._receipt_items_by_po_line")
	@patch("construction_management.api.controlled_procurement._validate_line_data")
	@patch("construction_management.api.controlled_procurement._validate_receivable_po")
	@patch("construction_management.api.controlled_procurement._is_open_lpo", return_value=False)
	@patch("construction_management.api.controlled_procurement._controlled_doc")
	@patch("construction_management.api.controlled_procurement._require")
	@patch("construction_management.api.controlled_procurement.frappe.new_doc")
	def test_controlled_receipt_create_sets_posting_time(
		self, new_doc, require, controlled_doc, open_lpo, receivable, line_data, by_po,
		allocation, company_links, catalog, warehouse_project, apply_alloc, set_type, taxes,
	):
		po_row = MagicMock()
		po_row.name = "POI-1"
		po_row.item_code = "ITEM-1"
		po_row.uom = "Nos"
		po_row.stock_uom = "Nos"
		po_row.conversion_factor = 1
		po_row.rate = 10
		po_row.item_tax_template = None

		po = MagicMock()
		po.name = "PO-1"
		po.company = "MRG"
		po.supplier = "SUP-1"
		po.controlled_procurement = 1
		po.taxes_and_charges = None
		po.items = [po_row]
		po.get = MagicMock(side_effect=lambda key, default=None: {
			"project": "PRJ-1", "bill_no": None, "boq_item": None,
		}.get(key, default))
		controlled_doc.return_value = po

		doc = MagicMock()
		doc.doctype = "Purchase Receipt"
		doc.name = "GRN-1"
		doc.flags = frappe._dict()
		captured = {}
		doc.update.side_effect = lambda values: captured.update(values)
		new_doc.return_value = doc

		result = controlled_procurement.create_purchase_receipt({
			"purchase_order": "PO-1",
			"supplier_delivery_note": "DO-99",
			"received_on": "2026-09-15",
			"project": "PRJ-1",
			"items": [{"purchase_order_item": "POI-1", "qty": 1, "warehouse": "Stores - MRG"}],
		})

		self.assertEqual(captured["posting_date"], "2026-09-15")
		self.assertEqual(captured["set_posting_time"], 1)
		doc.insert.assert_called_once()
		self.assertEqual(result["name"], "GRN-1")

	@patch("construction_management.api.controlled_procurement._apply_taxes")
	@patch("construction_management.api.controlled_procurement._map_invoice")
	@patch("construction_management.api.controlled_procurement._require")
	@patch("construction_management.api.controlled_procurement.frappe.has_permission")
	def test_invoice_create_sets_posting_time_and_date(self, has_permission, require, map_invoice, taxes):
		row = MagicMock()
		row.qty = 2
		row.item_name = "Item"
		row.item_code = "ITEM-1"
		row.meta.has_field.return_value = False
		row.get = MagicMock(side_effect=lambda field, default=None: "PRI-1" if field == "pr_detail" else None)
		invoice = MagicMock()
		invoice.doctype = "Purchase Invoice"
		invoice.name = "PINV-1"
		invoice.posting_date = "2026-01-01"
		invoice.items = [row]
		map_invoice.return_value = (MagicMock(), invoice)

		result = controlled_procurement.create_purchase_invoice({
			"source_doctype": "Purchase Receipt",
			"source_name": "GRN-1",
			"supplier_invoice_no": "INV-1",
			"supplier_invoice_date": "2026-09-10",
			"posting_date": "2026-09-12",
			"items": [{"key": "PRI-1", "qty": 2}],
		})

		self.assertEqual(invoice.set_posting_time, 1)
		self.assertEqual(invoice.posting_date, date(2026, 9, 12))
		self.assertEqual(invoice.bill_date, "2026-09-10")
		invoice.insert.assert_called_once()
		self.assertEqual(result["name"], "PINV-1")
