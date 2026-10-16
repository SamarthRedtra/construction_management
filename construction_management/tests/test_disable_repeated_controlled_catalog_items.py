# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.patches.disable_repeated_controlled_catalog_items import (
	_apply_group,
	_pick_survivor,
	run,
)


class TestDisableRepeatedControlledCatalogItems(UnitTestCase):
	def test_pick_survivor_prefers_non_dash_two(self):
		members = [
			{"name": "CP-FOO-2", "disabled": 0},
			{"name": "CP-FOO", "disabled": 0},
		]
		self.assertEqual(_pick_survivor(members), "CP-FOO")

	@patch(
		"construction_management.patches.disable_repeated_controlled_catalog_items.frappe.db.set_value"
	)
	def test_stocked_kept_zero_stock_duplicate_disabled(self, set_value):
		members = [
			frappe._dict(name="CP-MIX_GROUT_NS_(_25KG/BAG)", disabled=0),
			frappe._dict(name="CP-MIX_GROUT_NS_(_25KG/BAG)-2", disabled=0),
		]
		qty = {
			"CP-MIX_GROUT_NS_(_25KG/BAG)": 44.0,
			"CP-MIX_GROUT_NS_(_25KG/BAG)-2": 0.0,
		}

		result = _apply_group(members, qty)

		self.assertEqual(result["kept_with_stock"], ["CP-MIX_GROUT_NS_(_25KG/BAG)"])
		self.assertEqual(result["disabled"], ["CP-MIX_GROUT_NS_(_25KG/BAG)-2"])
		self.assertEqual(result["kept_as_survivor"], [])
		set_value.assert_called_once_with(
			"Item", "CP-MIX_GROUT_NS_(_25KG/BAG)-2", "disabled", 1, update_modified=False
		)

	@patch(
		"construction_management.patches.disable_repeated_controlled_catalog_items.frappe.db.set_value"
	)
	def test_both_zero_keeps_base_disables_dash_two(self, set_value):
		base = "CP-BONDCRETE_RAK_FIX_012_(_50KG_/_BAG_)"
		dup = "CP-BONDCRETE_RAK_FIX_012_(_50KG_/_BAG_)-2"
		members = [
			frappe._dict(name=base, disabled=0),
			frappe._dict(name=dup, disabled=0),
		]

		result = _apply_group(members, {base: 0.0, dup: 0.0})

		self.assertEqual(result["kept_as_survivor"], [base])
		self.assertEqual(result["disabled"], [dup])
		self.assertEqual(result["kept_with_stock"], [])
		set_value.assert_called_once_with("Item", dup, "disabled", 1, update_modified=False)

	@patch(
		"construction_management.patches.disable_repeated_controlled_catalog_items.frappe.db.set_value"
	)
	def test_already_disabled_zero_stock_is_skipped(self, set_value):
		members = [
			frappe._dict(name="CP-WING_NUT_HD", disabled=0),
			frappe._dict(name="CP-WING_NUT_HD-2", disabled=1),
		]
		qty = {"CP-WING_NUT_HD": 1.0, "CP-WING_NUT_HD-2": 0.0}

		result = _apply_group(members, qty)

		self.assertEqual(result["skipped"], ["CP-WING_NUT_HD-2"])
		self.assertEqual(result["disabled"], [])
		set_value.assert_not_called()

	@patch(
		"construction_management.patches.disable_repeated_controlled_catalog_items._bin_qty_by_item"
	)
	@patch(
		"construction_management.patches.disable_repeated_controlled_catalog_items._load_items"
	)
	@patch(
		"construction_management.patches.disable_repeated_controlled_catalog_items.frappe.db.set_value"
	)
	def test_run_disables_ms60_when_ms_60_has_stock(self, set_value, load_items, bin_qty):
		main = "CP-MS_60_6MM_PROTECTION_BOARD_(1M*2M_)"
		alt = "CP-MS60_PROTECTION_BOARD_6MM__(1M*2M_)"
		load_items.return_value = {
			main: frappe._dict(name=main, disabled=0, item_name="MS 60"),
			alt: frappe._dict(name=alt, disabled=0, item_name="MS60"),
		}
		bin_qty.return_value = {main: 452.0, alt: 0.0}

		result = run()

		self.assertIn(main, result["kept_with_stock_codes"])
		self.assertIn(alt, result["disabled_codes"])
		set_value.assert_called_once_with("Item", alt, "disabled", 1, update_modified=False)
