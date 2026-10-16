from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.patches import repair_controlled_catalog_item_groups_2026_10_13 as group_repair


class TestRepairControlledCatalogItemGroups(UnitTestCase):
	@patch("construction_management.patches.repair_controlled_catalog_item_groups_2026_10_13.frappe.get_all")
	@patch("construction_management.patches.repair_controlled_catalog_item_groups_2026_10_13._item_groups")
	@patch("construction_management.patches.repair_controlled_catalog_item_groups_2026_10_13._source_entries")
	def test_preflight_returns_workbook_backed_group_correction(self, source_entries, item_groups, get_all):
		source_entries.return_value = {
			"netoproof 600 (20ltr)": {"source_row": 144, "item_name": "Netoproof 600 (20LTR)",
				"item_group": "PU COATING", "item_type": "Stockable", "stock_uom": "Nos"},
		}
		item_groups.return_value = {"pu coating": "PU COATING"}
		get_all.return_value = [SimpleNamespace(name="NETOPROOF", item_name="Netoproof 600 (20LTR)",
			item_group="Products", stock_uom="Nos", controlled_item_type="Stockable", is_purchase_item=1, disabled=0)]

		targets = group_repair.preflight()

		self.assertEqual(targets, [{
			"item_code": "NETOPROOF", "item_name": "Netoproof 600 (20LTR)", "current_group": "Products",
			"target_group": "PU COATING", "source_row": 144,
		}])

	@patch("construction_management.patches.repair_controlled_catalog_item_groups_2026_10_13.frappe.get_all")
	@patch("construction_management.patches.repair_controlled_catalog_item_groups_2026_10_13._item_groups", return_value={"pu coating": "PU COATING"})
	@patch("construction_management.patches.repair_controlled_catalog_item_groups_2026_10_13._source_entries")
	def test_preflight_rejects_ambiguous_mismatched_description(self, source_entries, item_groups, get_all):
		source_entries.return_value = {
			"netoproof 600 (20ltr)": {"source_row": 144, "item_name": "Netoproof 600 (20LTR)",
				"item_group": "PU COATING", "item_type": "Stockable", "stock_uom": "Nos"},
		}
		get_all.return_value = [
			SimpleNamespace(name="NET-1", item_name="Netoproof 600 (20LTR)", item_group="Products",
				stock_uom="Nos", controlled_item_type="Stockable", is_purchase_item=1, disabled=0),
			SimpleNamespace(name="NET-2", item_name="Netoproof 600 (20LTR)", item_group="Products",
				stock_uom="Nos", controlled_item_type="Stockable", is_purchase_item=1, disabled=0),
		]

		with self.assertRaisesRegex(frappe.ValidationError, "ambiguous controlled Items"):
			group_repair.preflight()

	@patch("construction_management.patches.repair_controlled_catalog_item_groups_2026_10_13.frappe.get_all")
	@patch("construction_management.patches.repair_controlled_catalog_item_groups_2026_10_13._item_groups", return_value={"pu coating": "PU COATING"})
	@patch("construction_management.patches.repair_controlled_catalog_item_groups_2026_10_13._source_entries")
	def test_preflight_rejects_disabled_matching_item(self, source_entries, item_groups, get_all):
		source_entries.return_value = {
			"netoproof 600 (20ltr)": {"source_row": 144, "item_name": "Netoproof 600 (20LTR)",
				"item_group": "PU COATING", "item_type": "Stockable", "stock_uom": "Nos"},
		}
		get_all.return_value = [SimpleNamespace(name="NETOPROOF", item_name="Netoproof 600 (20LTR)",
			item_group="Products", stock_uom="Nos", controlled_item_type="Stockable", is_purchase_item=1, disabled=1)]

		with self.assertRaisesRegex(frappe.ValidationError, "no active controlled Item"):
			group_repair.preflight()

	@patch("construction_management.patches.repair_controlled_catalog_item_groups_2026_10_13._item_groups", return_value={})
	@patch("construction_management.patches.repair_controlled_catalog_item_groups_2026_10_13._source_entries")
	def test_preflight_rejects_missing_item_group(self, source_entries, item_groups):
		source_entries.return_value = {
			"netoproof 600 (20ltr)": {"source_row": 144, "item_name": "Netoproof 600 (20LTR)",
				"item_group": "PU COATING", "item_type": "Stockable", "stock_uom": "Nos"},
		}

		with self.assertRaisesRegex(frappe.ValidationError, "missing Item Groups"):
			group_repair.preflight()

	@patch("construction_management.patches.repair_controlled_catalog_item_groups_2026_10_13.frappe.get_doc")
	def test_apply_target_updates_only_group(self, get_doc):
		item = MagicMock(name="NETOPROOF", item_group="Products", disabled=0, is_purchase_item=1,
			controlled_procurement_catalog=1)
		get_doc.return_value = item
		target = {"item_code": "NETOPROOF", "target_group": "PU COATING"}

		outcome = group_repair._apply_target(target)

		self.assertTrue(outcome["updated"])
		self.assertEqual(item.item_group, "PU COATING")
		item.save.assert_called_once_with(ignore_permissions=True)

	@patch("construction_management.patches.repair_controlled_catalog_item_groups_2026_10_13._save_audit", return_value=[])
	@patch("construction_management.patches.repair_controlled_catalog_item_groups_2026_10_13.preflight", return_value=[])
	def test_run_is_no_op_after_groups_match(self, preflight, save_audit):
		result = group_repair.run()

		self.assertTrue(result["no_op"])
		self.assertEqual(result["updated"], 0)
