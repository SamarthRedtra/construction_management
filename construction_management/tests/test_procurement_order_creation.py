from unittest.mock import patch

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
			validate_supplier_delivery_note(frappe._dict(supplier_delivery_note="  "))

	def test_supplier_do_number_is_trimmed(self):
		doc = frappe._dict(supplier_delivery_note="  DO-123  ")
		validate_supplier_delivery_note(doc)
		self.assertEqual(doc.supplier_delivery_note, "DO-123")

	@patch("construction_management.api.controlled_procurement.frappe.get_all")
	def test_receive_note_discovers_source_and_direct_documents(self, get_all):
		get_all.side_effect = [["PI-1"], ["GRN-RETURN-1"]]
		doc = frappe._dict(
			name="GRN-1", company="MRG", custom_purchase_order="PO-1",
			items=[frappe._dict(purchase_order="PO-1")],
		)
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
