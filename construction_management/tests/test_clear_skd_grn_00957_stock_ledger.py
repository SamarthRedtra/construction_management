# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from construction_management.patches.clear_skd_grn_00957_stock_ledger import (
	WAREHOUSE,
	_rebuild_bins,
)


class TestClearSKDGRN00957StockLedger(UnitTestCase):
	@patch("erpnext.stock.stock_ledger.update_entries_after")
	@patch("construction_management.patches.clear_skd_grn_00957_stock_ledger.frappe.get_doc")
	@patch("construction_management.patches.clear_skd_grn_00957_stock_ledger.frappe.db.set_value")
	@patch("construction_management.patches.clear_skd_grn_00957_stock_ledger.frappe.db.get_value")
	def test_rebuild_bins_zeroes_qty_when_ledger_is_empty(
		self, get_value, set_value, get_doc, update_entries_after
	):
		item_code = 'ANGLE GRINDER 4.5" DEWALT 730W'
		get_value.return_value = "BIN-GRINDER"
		bin_doc = MagicMock()
		bin_doc.projected_qty = 0.0
		get_doc.return_value = bin_doc

		_rebuild_bins({item_code})

		update_entries_after.assert_called_once()
		set_value.assert_called_once_with(
			"Bin",
			"BIN-GRINDER",
			{"actual_qty": 0.0, "stock_value": 0.0, "valuation_rate": 0.0},
			update_modified=False,
		)
		get_doc.assert_called_once_with("Bin", "BIN-GRINDER")
		bin_doc.set_projected_qty.assert_called_once()
		bin_doc.db_set.assert_called_once_with("projected_qty", 0.0, update_modified=False)
		get_value.assert_called_once_with("Bin", {"item_code": item_code, "warehouse": WAREHOUSE})
