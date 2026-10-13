from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.patches import repair_approved_catalog_supplier_mappings_2026_10_13 as supplier_repair


class TestRepairApprovedCatalogSupplierMappings(UnitTestCase):
	@patch("construction_management.patches.repair_approved_catalog_supplier_mappings_2026_10_13.frappe.db.sql")
	def test_approved_targets_deduplicates_identical_item_supplier_rows(self, sql):
		sql.return_value = [
			frappe._dict(request="CCR-1", company="MRG", item_code="ITEM-1", item_name="Item One", supplier="SUP-1", rate=12),
			frappe._dict(request="CCR-1", company="MRG", item_code="ITEM-1", item_name="Item One", supplier="SUP-1", rate=12),
		]

		targets = supplier_repair._approved_targets()

		self.assertEqual(len(targets), 1)
		self.assertEqual(targets[0]["requests"], ["CCR-1"])
		self.assertEqual(targets[0]["rate"], 12)

	@patch("construction_management.patches.repair_approved_catalog_supplier_mappings_2026_10_13.frappe.db.sql")
	def test_approved_targets_rejects_conflicting_approved_rates(self, sql):
		sql.return_value = [
			frappe._dict(request="CCR-1", company="MRG", item_code="ITEM-1", item_name="Item One", supplier="SUP-1", rate=12),
			frappe._dict(request="CCR-2", company="MRG", item_code="ITEM-1", item_name="Item One", supplier="SUP-1", rate=15),
		]

		with self.assertRaisesRegex(frappe.ValidationError, "disagree on the buying price"):
			supplier_repair._approved_targets()

	@patch("construction_management.patches.repair_approved_catalog_supplier_mappings_2026_10_13._price")
	@patch("construction_management.patches.repair_approved_catalog_supplier_mappings_2026_10_13._existing_supplier_links", return_value=set())
	@patch("construction_management.patches.repair_approved_catalog_supplier_mappings_2026_10_13._suppliers_by_name")
	@patch("construction_management.patches.repair_approved_catalog_supplier_mappings_2026_10_13._items_by_name")
	@patch("construction_management.patches.repair_approved_catalog_supplier_mappings_2026_10_13._approved_targets")
	def test_preflight_rejects_conflicting_price(self, targets, items, suppliers, links, price):
		targets.return_value = [{"request": "CCR-1", "item_code": "ITEM-1", "supplier": "SUP-1", "rate": 12}]
		items.return_value = {
			"ITEM-1": SimpleNamespace(name="ITEM-1", disabled=0, is_purchase_item=1,
				controlled_procurement_catalog=1, stock_uom="Nos"),
		}
		suppliers.return_value = {"SUP-1": SimpleNamespace(name="SUP-1", disabled=0)}
		price.return_value = SimpleNamespace(price_list_rate=15)

		with self.assertRaisesRegex(frappe.ValidationError, "conflicting buying price"):
			supplier_repair.preflight()

	@patch("construction_management.patches.repair_approved_catalog_supplier_mappings_2026_10_13.controlled_procurement._apply_catalog_supplier_mapping")
	@patch("construction_management.patches.repair_approved_catalog_supplier_mappings_2026_10_13.frappe.get_doc")
	def test_repair_target_adds_only_missing_supplier_link_and_price(self, get_doc, apply_mapping):
		target = {
			"request": "CCR-1", "item_code": "ITEM-1", "item_name": "Item One", "supplier": "SUP-1",
			"rate": 12, "supplier_link_exists": False, "price_exists": False,
		}

		outcome = supplier_repair._repair_target(target)

		get_doc.assert_called_once_with("Item", "ITEM-1")
		apply_mapping.assert_called_once_with(get_doc.return_value, "SUP-1", 12, "Item One")
		self.assertTrue(outcome["supplier_link_added"])
		self.assertTrue(outcome["price_added"])
