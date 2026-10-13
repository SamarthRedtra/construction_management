from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.api import controlled_procurement
from construction_management.api import item_tree_part_2_expanded_import as expanded_import


class TestControlledProcurement(UnitTestCase):
	@patch("construction_management.api.controlled_procurement.frappe.db.exists", return_value=True)
	def test_workbook_uom_aliases(self, exists):
		self.assertEqual(controlled_procurement._catalog_uom("Nos."), "Nos")
		self.assertEqual(controlled_procurement._catalog_uom("TON"), "Tonne")
		self.assertEqual(controlled_procurement._catalog_uom("HRS"), "Hour")
		self.assertEqual(controlled_procurement._catalog_uom("Monthly"), "Months")
		self.assertEqual(controlled_procurement._catalog_uom("ROLL"), "ROLL")
		self.assertEqual([call.args for call in exists.call_args_list],
			[("UOM", "Nos"), ("UOM", "Tonne"), ("UOM", "Hour"), ("UOM", "Months"), ("UOM", "ROLL")])

	def test_expanded_import_adopts_only_an_exact_uom_match(self):
		row = {"item_name": "Binder Clip", "item_type": "Consumable", "stock_uom": "PKT"}
		entry = {"source_row": 1, "item_name": "Binder Clip"}
		legacy = SimpleNamespace(name="BINDER-CLIP-PKT", controlled_procurement_catalog=0, stock_uom="PKT")

		action, result_item = expanded_import._item_action([legacy], row, [], [entry])
		self.assertEqual((action, result_item), ("Adopt", "BINDER-CLIP-PKT"))

		action, result_item = expanded_import._item_action([], row, [], [entry])
		self.assertEqual((action, result_item), ("Create", ""))

	def test_expanded_import_keeps_distinct_supplier_prices(self):
		entries = [
			{"supplier": "SUP-1", "rate": 10, "item_group": "Products", "asset_category": "", "expense_account": "", "source_row": 1, "item_name": "Paper"},
			{"supplier": "SUP-2", "rate": 12, "item_group": "Products", "asset_category": "", "expense_account": "", "source_row": 2, "item_name": "Paper"},
		]
		held = []

		self.assertEqual(expanded_import._deduplicate_identity(entries, held), entries)
		self.assertEqual(held, [])

		entries[1]["supplier"] = "SUP-1"
		self.assertEqual(expanded_import._deduplicate_identity(entries, held), [])
		self.assertEqual(len(held), 2)

	def test_unique_catalog_rows_prefers_original_item_code(self):
		rows = [
			frappe._dict(name="CP-GR-118665-2", item_name="Lubricant Grease", item_group="Tools", stock_uom="Nos", controlled_item_type="Consumable"),
			frappe._dict(name="CP-OTHER", item_name="Other Item", item_group="Tools", stock_uom="Nos", controlled_item_type="Consumable"),
			frappe._dict(name="CP-GR-118665", item_name="Lubricant Grease", item_group="Tools", stock_uom="Nos", controlled_item_type="Consumable"),
		]

		result = controlled_procurement._unique_catalog_rows(rows)

		self.assertEqual([row.name for row in result], ["CP-OTHER", "CP-GR-118665"])

	@patch("construction_management.api.controlled_procurement.frappe.db.sql")
	@patch("construction_management.api.controlled_procurement._document_company", return_value="MRG")
	@patch("construction_management.api.controlled_procurement._require")
	def test_unique_catalog_picker_counts_and_paginates_unique_items(self, _require, _company, sql):
		sql.return_value = [
			frappe._dict(name="CP-GR-118665", item_name="Lubricant Grease", item_group="Tools", stock_uom="Nos", controlled_item_type="Consumable"),
			frappe._dict(name="CP-GR-118665-2", item_name="Lubricant Grease", item_group="Tools", stock_uom="Nos", controlled_item_type="Consumable"),
			frappe._dict(name="CP-SPRING", item_name="Spring", item_group="Tools", stock_uom="Nos", controlled_item_type="Consumable"),
		]

		result = controlled_procurement.get_catalog(unique_items=1, page_length=1)

		self.assertEqual(result["total_count"], 2)
		self.assertEqual([row.name for row in result["rows"]], ["CP-GR-118665"])
		sql.assert_called_once()

	@patch("construction_management.api.controlled_procurement.frappe.get_doc")
	@patch("construction_management.api.controlled_procurement.frappe.get_all", return_value=["CP-GR-118665-2", "CP-GR-118665"])
	def test_existing_catalog_item_prefers_original_item_code(self, get_all, get_doc):
		row = SimpleNamespace(item_name="Lubricant Grease", item_group="Tools", stock_uom="Nos", item_type="Consumable")

		controlled_procurement._existing_catalog_item(row)

		self.assertEqual(get_doc.call_args.args, ("Item", "CP-GR-118665"))
		self.assertEqual(get_all.call_args.kwargs["filters"]["controlled_procurement_catalog"], 1)

	def test_expanded_import_uses_the_agreed_accounting_mappings(self):
		self.assertEqual(
			expanded_import._accounting_mapping("Asset", "SCAFFOLDING & FORMWORK"),
			("Scaffolding Item", ""),
		)
		self.assertEqual(
			expanded_import._accounting_mapping("Service", "TESTING & CERTIFICATION"),
			("", "Professional Charges - MRG"),
		)

	@patch("construction_management.api.controlled_procurement._existing_catalog_item", return_value=None)
	@patch("construction_management.api.controlled_procurement._add_supplier_and_price", return_value="")
	@patch("construction_management.api.controlled_procurement.frappe.new_doc")
	def test_multiple_supplier_prices_create_one_catalog_item(self, new_doc, add_supplier, _existing):
		item = new_doc.return_value
		item.name = "CP-PAPER"
		item.is_new.return_value = True
		rows = [
			SimpleNamespace(action="Create", result_item="", item_code="", item_name="Paper", item_group="Products",
				item_type="Consumable", stock_uom="PKT", asset_category="", expense_account="", supplier="SUP-1", rate=10),
			SimpleNamespace(action="Create", result_item="", item_code="", item_name="Paper", item_group="Products",
				item_type="Consumable", stock_uom="PKT", asset_category="", expense_account="", supplier="SUP-2", rate=12),
		]

		controlled_procurement._materialize_catalog_request_items(
			SimpleNamespace(items=rows, source="Workbook Import", company="MRG", name="CCR-EXPANDED"),
		)

		new_doc.assert_called_once_with("Item")
		self.assertEqual(add_supplier.call_count, 2)
		self.assertEqual([row.result_item for row in rows], ["CP-PAPER", "CP-PAPER"])

	@patch("construction_management.api.controlled_procurement._add_supplier_and_price", return_value="")
	@patch("construction_management.api.controlled_procurement._existing_catalog_item")
	@patch("construction_management.api.controlled_procurement.frappe.new_doc")
	def test_new_catalog_request_reuses_matching_catalog_item(self, new_doc, existing, add_supplier):
		item = MagicMock(name="CP-PAPER", stock_uom="PKT")
		item.name = "CP-PAPER"
		item.is_new.return_value = False
		existing.return_value = item
		row = SimpleNamespace(action="Create", result_item="", item_code="", item_name="Paper", item_group="Products",
			item_type="Consumable", stock_uom="PKT", asset_category="", expense_account="", supplier="SUP-1", rate=10)

		controlled_procurement._materialize_catalog_request_items(
			SimpleNamespace(items=[row], source="Workbook Import", company="MRG", name="CCR-NEW")
		)

		new_doc.assert_not_called()
		self.assertEqual(row.result_item, "CP-PAPER")
		add_supplier.assert_called_once()

	@patch("construction_management.api.controlled_procurement._add_supplier_and_price", return_value="")
	@patch("construction_management.api.controlled_procurement.frappe.get_doc")
	def test_catalog_request_updates_supplier_for_explicit_legacy_item(self, get_doc, add_supplier):
		item = MagicMock(name="LEGACY-PAPER", stock_uom="PKT")
		item.name = "LEGACY-PAPER"
		item.is_new.return_value = False
		get_doc.return_value = item
		row = SimpleNamespace(action="Update", result_item="LEGACY-PAPER", item_code="LEGACY-PAPER",
			item_name="Paper", item_group="Products", item_type="Consumable", stock_uom="PKT",
			asset_category="", expense_account="", supplier="SUP-1", rate=10)

		controlled_procurement._materialize_catalog_request_items(
			SimpleNamespace(items=[row], source="Workbook Import", company="MRG", name="CCR-LEGACY")
		)

		get_doc.assert_called_once_with("Item", "LEGACY-PAPER")
		add_supplier.assert_called_once_with(item, "SUP-1", 10)
		self.assertEqual(row.result_item, "LEGACY-PAPER")

	@patch("construction_management.api.controlled_procurement.create_catalog_request")
	@patch("construction_management.api.controlled_procurement.frappe.get_all")
	@patch("construction_management.api.controlled_procurement._selected_catalog_items")
	@patch("construction_management.api.controlled_procurement._document_company", return_value="MRG")
	@patch("construction_management.api.controlled_procurement._require")
	@patch("construction_management.api.controlled_procurement.frappe.db.exists", return_value=True)
	def test_batch_supplier_link_request_uses_existing_catalog_items(
		self, exists, require, company, selected_items, get_all, create_request
	):
		selected_items.return_value = [
			frappe._dict(name="ITEM-1", item_name="Item One", item_group="Products", stock_uom="Nos",
				controlled_item_type="Stockable", asset_category=""),
			frappe._dict(name="ITEM-2", item_name="Item Two", item_group="Tools", stock_uom="PKT",
				controlled_item_type="Consumable", asset_category=""),
		]
		get_all.return_value = ["ITEM-1"]
		create_request.return_value = {"name": "CCR-NEW", "status": "Pending Accounts"}

		result = controlled_procurement.create_catalog_supplier_link_request(
			{"company": "MRG", "supplier": "SUP-1", "item_codes": ["ITEM-1", "ITEM-2", "ITEM-2"]}
		)

		self.assertEqual(result, {"name": "CCR-NEW", "status": "Pending Accounts", "requested": 1, "already_linked": 1})
		selected_items.assert_called_once_with(["ITEM-1", "ITEM-2"])
		create_request.assert_called_once_with(
			{
				"company": "MRG",
				"source": "Manual",
				"supplier_link_only": 1,
				"items": [
					{
						"item_code": "ITEM-2", "item_name": "Item Two", "item_group": "Tools",
						"item_type": "Consumable", "stock_uom": "PKT", "asset_category": "",
						"supplier": "SUP-1", "rate": 0,
					}
				],
			}
		)

	@patch("construction_management.api.controlled_procurement.frappe.get_all")
	@patch("construction_management.api.controlled_procurement._selected_catalog_items")
	@patch("construction_management.api.controlled_procurement._document_company", return_value="MRG")
	@patch("construction_management.api.controlled_procurement._require")
	@patch("construction_management.api.controlled_procurement.frappe.db.exists", return_value=True)
	def test_batch_supplier_link_request_returns_no_op_when_already_linked(
		self, exists, require, company, selected_items, get_all
	):
		selected_items.return_value = [
			frappe._dict(name="ITEM-1", item_name="Item One", item_group="Products", stock_uom="Nos",
				controlled_item_type="Stockable", asset_category=""),
		]
		get_all.return_value = ["ITEM-1"]

		result = controlled_procurement.create_catalog_supplier_link_request(
			{"company": "MRG", "supplier": "SUP-1", "item_codes": ["ITEM-1"]}
		)

		self.assertEqual(result, {"name": "", "status": "", "requested": 0, "already_linked": 1})

	@patch("construction_management.api.controlled_procurement.frappe.get_doc")
	@patch("construction_management.api.controlled_procurement._append_catalog_log")
	@patch("construction_management.api.controlled_procurement._catalog_request_status", return_value="Pending Accounts")
	@patch("construction_management.api.controlled_procurement._catalog_request_row")
	@patch("construction_management.api.controlled_procurement._allowed_companies", return_value=["MRG"])
	@patch("construction_management.api.controlled_procurement._require")
	def test_supplier_link_request_marks_rows_link_only(
		self, require, companies, catalog_row, request_status, append_log, get_doc
	):
		catalog_row.return_value = {
			"item_code": "ITEM-1", "item_name": "Item One", "supplier": "SUP-1", "rate": 0,
		}
		doc = MagicMock(name="CCR-LINK", status="Pending Accounts")
		doc.name = "CCR-LINK"
		get_doc.return_value = doc

		controlled_procurement.create_catalog_request({
			"company": "MRG",
			"supplier_link_only": 1,
			"items": [{"item_code": "ITEM-1"}],
		})

		catalog_row.assert_called_once_with(
			{"item_code": "ITEM-1"}, "MRG", supplier_link_only=True
		)

	@patch("construction_management.api.controlled_procurement._apply_catalog_supplier_mapping")
	@patch("construction_management.api.controlled_procurement.frappe.get_doc")
	def test_supplier_link_action_does_not_update_item_master(self, get_doc, apply_mapping):
		item = MagicMock(name="LEGACY-PAPER", stock_uom="PKT")
		get_doc.return_value = item
		row = SimpleNamespace(action="Link Supplier", result_item="LEGACY-PAPER", item_name="Paper",
			supplier="SUP-1", rate=0)

		controlled_procurement._materialize_catalog_request_items(
			SimpleNamespace(items=[row], source="Manual", company="MRG", name="CCR-LINK")
		)

		get_doc.assert_called_once_with("Item", "LEGACY-PAPER")
		apply_mapping.assert_called_once_with(item, "SUP-1", 0, "Paper")
		item.update.assert_not_called()

	@patch("construction_management.api.controlled_procurement._materialize_catalog_request_items")
	@patch("construction_management.api.controlled_procurement.frappe.db.sql")
	@patch("construction_management.api.controlled_procurement._explicit_ceo", return_value=True)
	def test_catalog_materialization_locks_company_before_reuse(self, _ceo, sql, materialize):
		doc = SimpleNamespace(name="CCR-NEW", company="MRG", items=[SimpleNamespace(rate=0)])

		controlled_procurement._materialize_catalog_request(doc)

		sql.assert_called_once_with("select name from `tabCompany` where name = %s for update", "MRG")
		materialize.assert_called_once_with(doc)

	@patch("construction_management.api.controlled_procurement.frappe.get_doc")
	def test_adoption_preserves_existing_item_master_fields(self, get_doc):
		item = MagicMock(name="LEGACY-PKT", stock_uom="PKT")
		get_doc.return_value = item
		row = SimpleNamespace(action="Adopt", result_item="LEGACY-PKT", item_name="Binder Clip",
			item_group="Products", item_type="Consumable", stock_uom="PKT")
		doc = SimpleNamespace(source="Workbook Import", name="CCR-EXPANDED")

		controlled_procurement._adopt_catalog_item(doc, row)

		update = item.update.call_args.args[0]
		self.assertEqual(update["controlled_procurement_catalog"], 1)
		self.assertNotIn("stock_uom", update)
		self.assertEqual(update["item_group"], "Products")
		self.assertNotIn("is_stock_item", update)
		item.save.assert_called_once_with(ignore_permissions=True)

	@patch("construction_management.api.controlled_procurement._apply_allocation")
	@patch("construction_management.api.controlled_procurement._catalog_item",
		return_value=SimpleNamespace(name="CP-ROLL", stock_uom="ROLL", controlled_item_type="Stockable"))
	def test_po_line_preserves_catalog_uom(self, _item, _allocation):
		doc = MagicMock(doctype="Purchase Order", company="MRG", set_warehouse="Stores - MRG")
		controlled_procurement._append_item(doc, {"item_code": "CP-ROLL", "qty": 2, "rate": 10}, {}, False)
		line = doc.append.call_args.args[1]
		self.assertEqual((line["uom"], line["stock_uom"], line["conversion_factor"]), ("ROLL", "ROLL", 1))

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
			item_type="Consumable", stock_uom="Box", asset_category="", expense_account="", supplier="", rate=0)
		doc = SimpleNamespace(items=[row], source="Manual Request", company="MRG", name="CCR-1")

		controlled_procurement._materialize_catalog_request_items(doc)

		self.assertTrue(any(call.args[0].get("is_stock_item") == 1 for call in item.update.call_args_list))
		self.assertTrue(any(call.args[0].get("stock_uom") == "Box" for call in item.update.call_args_list))
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

	@patch("construction_management.api.mrg_stock_snapshot.run", return_value={"status": "completed"})
	@patch("construction_management.api.controlled_procurement._allowed_companies", return_value={"M R G INSULATION WORKS L.L.C"})
	@patch("construction_management.api.controlled_procurement._require")
	def test_mrg_opening_stock_snapshot_uses_the_guarded_runner(self, require, companies, run):
		result = controlled_procurement.run_mrg_opening_stock_snapshot("M R G INSULATION WORKS L.L.C")

		self.assertEqual(result, {"status": "completed"})
		run.assert_called_once_with()

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
