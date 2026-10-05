from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.api import controlled_procurement


class TestControlledProcurement(UnitTestCase):
	@patch("construction_management.api.controlled_procurement.frappe.db.sql", side_effect=[[], [[0]]])
	@patch("construction_management.api.controlled_procurement._document_company", return_value="MRG")
	@patch("construction_management.api.controlled_procurement._require")
	def test_consumable_catalog_filter_and_stock_status(self, _require, _company, sql):
		controlled_procurement.get_catalog(item_type="Consumable", stock_status="in_stock")
		self.assertIn("item.controlled_item_type = %(item_type)s", sql.call_args_list[0].args[0])
		self.assertIn("item.controlled_item_type IN ('Stockable', 'Consumable')", sql.call_args_list[0].args[0])
		self.assertEqual(sql.call_args_list[0].args[1]["item_type"], "Consumable")

	@patch("construction_management.api.controlled_procurement._item_code", return_value="CP-CONSUMABLE")
	@patch("construction_management.api.controlled_procurement.frappe.new_doc")
	def test_approved_consumable_is_created_as_stock_item(self, new_doc, _item_code):
		item = new_doc.return_value
		item.is_new.return_value = True
		item.name = "CP-CONSUMABLE"
		row = SimpleNamespace(result_item="", item_code="", item_name="Consumable", item_group="Products",
			item_type="Consumable", asset_category="", expense_account="", supplier="", rate=0)
		doc = SimpleNamespace(items=[row], source="Manual Request", company="MRG", name="CCR-1")

		controlled_procurement._materialize_catalog_request_items(doc)

		self.assertTrue(any(call.args[0].get("is_stock_item") == 1 for call in item.update.call_args_list))
		self.assertEqual(row.result_item, "CP-CONSUMABLE")

	@patch("construction_management.api.controlled_procurement.frappe.get_all", return_value=[])
	@patch("construction_management.api.controlled_procurement.frappe.db.exists", return_value=True)
	@patch("construction_management.api.controlled_procurement._catalog_item",
		return_value=SimpleNamespace(controlled_item_type="Consumable", is_stock_item=1))
	@patch("construction_management.api.controlled_procurement._document_company", return_value="MRG")
	@patch("construction_management.api.controlled_procurement._require")
	def test_consumable_transfer_stock_preview(self, _require, _company, _item, _exists, _bins):
		result = controlled_procurement.get_transfer_stock_preview("Stores - MRG", ["CP-CONSUMABLE"])
		self.assertEqual(result["balances"], {"CP-CONSUMABLE": 0.0})

	@patch("construction_management.api.controlled_procurement.frappe.new_doc")
	@patch("construction_management.api.controlled_procurement._validate_company_links")
	@patch("construction_management.api.controlled_procurement._catalog_item",
		return_value=SimpleNamespace(name="CP-CONSUMABLE", controlled_item_type="Consumable", is_stock_item=1))
	@patch("construction_management.api.controlled_procurement._allowed_companies", return_value={"MRG"})
	@patch("construction_management.api.controlled_procurement._require")
	def test_consumable_opening_stock(self, _require, _companies, _item, _links, new_doc):
		new_doc.return_value.doctype = "Stock Reconciliation"
		new_doc.return_value.name = "MAT-RECO-1"
		result = controlled_procurement.record_opening_stock({"company": "MRG", "posting_date": "2026-10-04",
			"items": [{"item_code": "CP-CONSUMABLE", "warehouse": "Stores - MRG", "qty": 5, "valuation_rate": 10}]})
		self.assertEqual(result["name"], "MAT-RECO-1")
		new_doc.return_value.submit.assert_called_once()

	@patch("construction_management.api.controlled_procurement.frappe.get_list")
	@patch("construction_management.api.controlled_procurement.frappe.get_all", return_value=["SUP-2", "SUP-1"])
	@patch("construction_management.api.controlled_procurement.frappe.db.get_value", side_effect=[0, 1])
	@patch("construction_management.api.controlled_procurement._catalog_item")
	@patch("construction_management.api.controlled_procurement._document_company", return_value="MRG")
	@patch("construction_management.api.controlled_procurement._require")
	def test_item_first_supplier_choices_are_permission_filtered(self, require, company, item, get_value, get_all, get_list):
		get_list.return_value = [{"name": "SUP-1", "supplier_name": "Awazel"}]
		result = controlled_procurement.get_catalog_item_suppliers("ITEM-1", "MRG")
		self.assertEqual(result, get_list.return_value)
		self.assertEqual(get_list.call_args.kwargs["filters"], {"name": ["in", ["SUP-1", "SUP-2"]], "disabled": 0})
		company.assert_called_once_with("MRG")

	@patch("construction_management.api.controlled_procurement.frappe.get_list")
	@patch("construction_management.api.controlled_procurement.frappe.get_all", return_value=[])
	@patch("construction_management.api.controlled_procurement.frappe.db.get_value", side_effect=[0, 1])
	@patch("construction_management.api.controlled_procurement._catalog_item")
	@patch("construction_management.api.controlled_procurement._document_company", return_value="MRG")
	@patch("construction_management.api.controlled_procurement._require")
	def test_item_without_supplier_returns_no_choice(self, require, company, item, get_value, get_all, get_list):
		self.assertEqual(controlled_procurement.get_catalog_item_suppliers("ITEM-1"), [])
		get_list.assert_not_called()

	@patch("construction_management.api.controlled_procurement.frappe.get_list")
	@patch("construction_management.api.controlled_procurement._document_company", return_value="MRG")
	@patch("construction_management.api.controlled_procurement._require")
	def test_project_choices_search_name_and_number_in_company(self, require, company, get_list):
		get_list.return_value = [{"name": "100", "project_name": "Awazel Works"}]
		result = controlled_procurement.get_procurement_projects(search="Awazel", company="MRG")
		self.assertEqual(result[0]["name"], "100")
		self.assertEqual(result[0]["project_name"], "Awazel Works")
		self.assertEqual(get_list.call_args.kwargs["filters"], {"company": "MRG"})
		self.assertIn(["project_name", "like", "%Awazel%"], get_list.call_args.kwargs["or_filters"])

	@patch("construction_management.api.controlled_procurement.frappe.get_list")
	@patch("construction_management.api.controlled_procurement._document_company", return_value="MRG")
	@patch("construction_management.api.controlled_procurement._require")
	def test_saved_project_label_loads_exact_project(self, require, company, get_list):
		controlled_procurement.get_procurement_projects(selected="100", company="MRG")
		self.assertEqual(get_list.call_args.kwargs["filters"], {"company": "MRG", "name": "100"})
		self.assertEqual(get_list.call_args.kwargs["limit_page_length"], 1)

	@patch("construction_management.api.controlled_procurement.frappe.db.sql", side_effect=[[], [[0]]])
	@patch("construction_management.api.controlled_procurement._document_company", return_value="MRG")
	@patch("construction_management.api.controlled_procurement._require")
	def test_catalog_supplier_filter_applies_before_pagination(self, require, company, sql):
		result = controlled_procurement.get_catalog(supplier="SUP-1")
		self.assertEqual(result["total_count"], 0)
		for query in sql.call_args_list:
			self.assertIn("EXISTS (SELECT 1 FROM `tabItem Supplier`", query.args[0])
			self.assertEqual(query.args[1]["supplier"], "SUP-1")

	@patch("construction_management.api.controlled_procurement._item_has_supplier", return_value=True)
	def test_new_standard_order_accepts_multiple_supplier_linked_items(self, has_supplier):
		controlled_procurement._validate_order_supplier_items(
			{"lpo_type": "Standard", "supplier": "SUP-1"},
			[{"item_code": "ITEM-1"}, {"item_code": "ITEM-2"}],
		)
		self.assertEqual(has_supplier.call_count, 2)

	@patch("construction_management.api.controlled_procurement._item_has_supplier", return_value=False)
	def test_open_order_rejects_item_from_another_supplier(self, has_supplier):
		with self.assertRaisesRegex(frappe.ValidationError, "not linked to supplier"):
			controlled_procurement._validate_order_supplier_items(
				{"lpo_type": "Open", "supplier": "SUP-1"}, [{"item_code": "ITEM-1"}],
			)
		has_supplier.assert_called_once_with("ITEM-1", "SUP-1")

	@patch("construction_management.api.controlled_procurement._item_has_supplier", return_value=True)
	def test_supplier_link_allows_standard_order(self, has_supplier):
		controlled_procurement._validate_order_supplier_items(
			{"lpo_type": "Standard", "supplier": "SUP-1"}, [{"item_code": "ITEM-1"}],
		)

	@patch("construction_management.api.controlled_procurement._item_has_supplier", return_value=False)
	def test_existing_unlinked_line_can_be_kept_but_new_line_needs_supplier_link(self, has_supplier):
		existing = SimpleNamespace(supplier="SUP-1", items=[SimpleNamespace(item_code="ITEM-1")], get=lambda key: "Standard" if key == "custom_lpo_type" else None)
		controlled_procurement._validate_order_supplier_items(
			{"lpo_type": "Standard", "supplier": "SUP-1"}, [{"item_code": "ITEM-1"}], existing,
		)
		has_supplier.assert_not_called()
		with self.assertRaisesRegex(frappe.ValidationError, "not linked to supplier"):
			controlled_procurement._validate_order_supplier_items(
				{"lpo_type": "Standard", "supplier": "SUP-1"},
				[{"item_code": "ITEM-1"}, {"item_code": "ITEM-2"}], existing,
			)
		has_supplier.assert_called_once_with("ITEM-2", "SUP-1")

	def test_split_receipt_quantity_is_checked_across_rows(self):
		po = SimpleNamespace(items=[SimpleNamespace(name="PO-ROW", item_code="ITEM-1", item_name="Item 1",
			qty=10, received_qty=4, uom="Nos", get=lambda field: 0)])
		lines = [{"purchase_order_item": "PO-ROW", "item_code": "ITEM-1", "qty": 4},
			{"purchase_order_item": "PO-ROW", "item_code": "ITEM-1", "qty": 3}]
		with self.assertRaisesRegex(frappe.ValidationError, "across all rows"):
			controlled_procurement._receipt_items_by_po_line(po, lines, False)
		self.assertEqual(len(controlled_procurement._receipt_items_by_po_line(po, lines, True)["PO-ROW"]), 2)
		lines[1]["qty"] = 2
		self.assertEqual(len(controlled_procurement._receipt_items_by_po_line(po, lines, False)["PO-ROW"]), 2)

	def test_split_receipt_rejects_unrelated_po_line(self):
		po = SimpleNamespace(items=[SimpleNamespace(name="PO-ROW", item_code="ITEM-1", item_name="Item 1",
			qty=10, received_qty=0, uom="Nos", get=lambda field: 0)])
		with self.assertRaisesRegex(frappe.ValidationError, "selected Purchase Order"):
			controlled_procurement._receipt_items_by_po_line(po,
				[{"purchase_order_item": "OTHER", "item_code": "ITEM-1", "qty": 1}], False)

	@patch("construction_management.api.controlled_procurement._item_has_supplier", return_value=False)
	def test_changing_existing_order_supplier_requires_link(self, has_supplier):
		existing = SimpleNamespace(supplier="SUP-1", items=[SimpleNamespace(item_code="ITEM-1")], get=lambda key: "Open" if key == "custom_lpo_type" else None)
		with self.assertRaisesRegex(frappe.ValidationError, "not linked to supplier"):
			controlled_procurement._validate_order_supplier_items(
				{"lpo_type": "Open", "supplier": "SUP-2"}, [{"item_code": "ITEM-1"}], existing,
			)

	@patch("construction_management.api.controlled_procurement.frappe.db.get_value", return_value=frappe._dict(controlled_asset_category=None, controlled_service_expense_account=None))
	@patch("construction_management.api.controlled_procurement.frappe.db.exists", return_value=True)
	def test_catalog_request_requires_supplier(self, exists, get_value):
		with self.assertRaisesRegex(frappe.ValidationError, "Supplier is required"):
			controlled_procurement._catalog_request_row(
				{"item_name": "Test", "item_group": "Products", "item_type": "Stockable", "supplier": "  "}, "MRG",
			)

	@patch("construction_management.api.controlled_procurement.frappe.db.exists", return_value=True)
	@patch("construction_management.api.controlled_procurement._active_company", return_value="MRG")
	@patch("construction_management.api.controlled_procurement._workbook_rows")
	@patch("construction_management.api.controlled_procurement._uploaded_file_path", return_value=Path("catalog.xlsx"))
	@patch("construction_management.api.controlled_procurement._require")
	def test_workbook_preview_reports_missing_supplier(self, require, path, workbook_rows, company, exists):
		workbook_rows.return_value = ([{"row": 2, "item_name": "Test", "item_group": "Products", "item_type": "Stockable", "supplier": ""}], [])
		preview = controlled_procurement.preview_catalog_workbook("/private/files/catalog.xlsx")
		self.assertEqual(preview["valid_rows"], 0)
		self.assertIn("Supplier is required", preview["errors"][0]["reason"])

	@patch("construction_management.api.controlled_procurement._catalog_request_row")
	@patch("construction_management.api.controlled_procurement._allowed_companies", return_value=["MRG"])
	@patch("construction_management.api.controlled_procurement._roles", return_value={"Purchase User"})
	@patch("construction_management.api.controlled_procurement.frappe.get_doc")
	@patch("construction_management.api.controlled_procurement._require")
	def test_resubmit_revalidates_existing_catalog_rows(self, require, get_doc, roles, companies, validate_row):
		row = MagicMock()
		row.as_dict.return_value = {"item_name": "Test", "supplier": ""}
		get_doc.return_value = SimpleNamespace(status="Needs Correction", requested_by="buyer@example.com", company="MRG", items=[row])
		validate_row.side_effect = frappe.ValidationError("Supplier is required")
		with patch("construction_management.api.controlled_procurement.frappe.session", frappe._dict(user="buyer@example.com")):
			with self.assertRaisesRegex(frappe.ValidationError, "Supplier is required"):
				controlled_procurement.resubmit_catalog_request("REQUEST-1")
		validate_row.assert_called_once()

	@patch("construction_management.api.controlled_procurement.frappe.get_all", return_value=["M R G INSULATION WORKS L.L.C"])
	def test_allowed_companies_prefers_company_user_permissions(self, get_all):
		self.assertEqual(controlled_procurement._allowed_companies(), ["M R G INSULATION WORKS L.L.C"])

	@patch("construction_management.api.controlled_procurement._allowed_companies", return_value=["M R G INSULATION WORKS L.L.C"])
	@patch("construction_management.api.controlled_procurement.frappe.defaults.get_user_default", return_value="SKADA CONSTRUCTION L.L.C")
	def test_active_company_uses_only_permitted_mrg_company(self, get_default, allowed_companies):
		self.assertEqual(controlled_procurement._active_company(), "M R G INSULATION WORKS L.L.C")

	def test_mrg_requires_project(self):
		with patch("construction_management.api.controlled_procurement.frappe.db.get_value", return_value="MRG"):
			with self.assertRaisesRegex(frappe.ValidationError, "Project is required"):
				controlled_procurement._validate_allocation({"project": "", "bill_no": "", "boq_item": ""}, "MRG")

	def test_blank_browser_allocation_values_are_normalized(self):
		self.assertEqual(
			controlled_procurement._normalized_allocation({"project": " null ", "bill_no": "undefined", "boq_item": None}),
			{"project": "", "bill_no": "", "boq_item": ""},
		)

	@patch("construction_management.api.controlled_procurement.frappe.has_permission", return_value=True)
	@patch("construction_management.api.controlled_procurement.frappe.get_doc")
	def test_mrg_allows_project_without_bill_and_boq_item(self, get_doc, has_permission):
		get_doc.return_value = frappe._dict(name="PROJECT-1")
		with patch("construction_management.api.controlled_procurement.frappe.db.get_value", return_value="MRG"):
			controlled_procurement._validate_allocation({"project": "PROJECT-1", "bill_no": "", "boq_item": ""}, "MRG")

	def test_mrg_rejects_boq_item_without_bill(self):
		with patch("construction_management.api.controlled_procurement.frappe.db.get_value", return_value="MRG"):
			with self.assertRaisesRegex(frappe.ValidationError, "Select the Bill No"):
				controlled_procurement._validate_allocation({"project": "PROJECT-1", "bill_no": "", "boq_item": "BOQ-1"}, "MRG")

	def test_skada_requires_bill_and_boq_item_with_project(self):
		with patch("construction_management.api.controlled_procurement.frappe.db.get_value", return_value="SC"):
			with self.assertRaisesRegex(frappe.ValidationError, "Project, Bill No, and BOQ Item are required"):
				controlled_procurement._validate_allocation({"project": "PROJECT-1", "bill_no": "", "boq_item": ""}, "SKADA CONSTRUCTION L.L.C")

	@patch("construction_management.api.controlled_procurement._allowed_companies", return_value=["M R G INSULATION WORKS L.L.C"])
	@patch("construction_management.api.controlled_procurement._active_company", return_value="M R G INSULATION WORKS L.L.C")
	def test_document_company_uses_active_workspace_company_when_request_omits_it(self, active_company, allowed_companies):
		self.assertEqual(controlled_procurement._document_company(""), "M R G INSULATION WORKS L.L.C")

	def test_skada_requires_complete_allocation(self):
		with self.assertRaises(frappe.ValidationError):
			controlled_procurement._validate_allocation({"project": "", "bill_no": "", "boq_item": ""}, "SKADA")

	def test_allocation_requires_project_bill_and_boq_item(self):
		with self.assertRaises(frappe.ValidationError):
			controlled_procurement._validate_allocation({"project": "PROJECT-1", "bill_no": "", "boq_item": "BOQ-1"})

	@patch("construction_management.api.controlled_procurement.frappe.has_permission", return_value=True)
	@patch("construction_management.api.controlled_procurement.frappe.get_doc")
	@patch("construction_management.api.controlled_procurement.frappe.db.get_value")
	def test_allocation_rejects_item_from_another_bill(self, get_value, get_doc, has_permission):
		get_doc.return_value = frappe._dict(name="PROJECT-1")
		get_value.side_effect = [frappe._dict(project="PROJECT-1"), frappe._dict(project="PROJECT-1", parent_bill="BILL-2")]
		with self.assertRaises(frappe.ValidationError):
			controlled_procurement._validate_allocation({"project": "PROJECT-1", "bill_no": "BILL-1", "boq_item": "BOQ-1"})

	@patch("construction_management.api.controlled_procurement.frappe.has_permission", return_value=True)
	@patch("construction_management.api.controlled_procurement.frappe.get_doc")
	@patch("construction_management.api.controlled_procurement.frappe.db.get_value")
	def test_allocation_accepts_matching_project_bill_and_boq_item(self, get_value, get_doc, has_permission):
		get_doc.return_value = frappe._dict(name="PROJECT-1")
		get_value.side_effect = [frappe._dict(project="PROJECT-1"), frappe._dict(project="PROJECT-1", parent_bill="BILL-1")]
		controlled_procurement._validate_allocation({"project": "PROJECT-1", "bill_no": "BILL-1", "boq_item": "BOQ-1"})

	@patch("construction_management.api.controlled_procurement._require")
	@patch("construction_management.api.controlled_procurement._set_supplier_naming_series")
	@patch("construction_management.api.controlled_procurement.frappe.new_doc")
	@patch("construction_management.api.controlled_procurement.frappe.db.exists", side_effect=[False, True])
	def test_create_supplier_uses_workspace_fields(self, exists, new_doc, set_series, require):
		supplier = new_doc.return_value
		supplier.name = "SUP-0001"
		supplier.supplier_name = "Acme Trading"

		result = controlled_procurement.create_supplier({
			"supplier_name": "Acme Trading",
			"supplier_group": "Local Suppliers",
			"supplier_type": "Company",
			"tax_id": "TRN-123",
		})

		supplier.update.assert_called_once_with({
			"supplier_name": "Acme Trading",
			"supplier_group": "Local Suppliers",
			"supplier_type": "Company",
			"tax_id": "TRN-123",
			"payment_terms": None,
		})
		supplier.insert.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(result, {"name": "SUP-0001", "supplier_name": "Acme Trading", "payment_terms": supplier.payment_terms or ""})
