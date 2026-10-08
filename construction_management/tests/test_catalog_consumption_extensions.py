from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.api import consumable_receipt
from construction_management.construction_management.report.outstanding_po_items_missing_from_catalog import (
	outstanding_po_items_missing_from_catalog as outstanding_report,
)


class TestCatalogConsumptionExtensions(UnitTestCase):
	@patch("construction_management.api.consumable_receipt._auto_consumption_enabled", return_value=True)
	@patch("construction_management.api.consumable_receipt._create_source_issue")
	def test_transfer_consumes_from_destination(self, create_issue, _enabled):
		transfer = frappe._dict(stock_entry_type="Material Transfer", is_return=0)
		consumable_receipt.on_transfer_submit(transfer)
		create_issue.assert_called_once_with(
			transfer,
			"Stock Entry",
			"custom_source_material_transfer",
			"t_warehouse",
			"qty",
		)

	@patch("construction_management.api.consumable_receipt._skip_auto_consumption_warehouses", return_value={"Hold - MRG"})
	@patch("construction_management.api.consumable_receipt._controlled_item_types", return_value={"CONSUMABLE": "Consumable"})
	def test_eligible_rows_skip_opted_out_warehouse(self, _item_types, _skip_warehouses):
		doc = MagicMock(name="MAT-STE-1", company="MRG", posting_date="2026-10-07")
		doc.items = [
			frappe._dict(name="ROW-1", idx=1, item_code="CONSUMABLE", qty=2, t_warehouse="Use - MRG"),
			frappe._dict(name="ROW-2", idx=2, item_code="CONSUMABLE", qty=3, t_warehouse="Hold - MRG"),
		]
		doc.get.side_effect = lambda field: "P-1" if field == "project" else None
		rows = consumable_receipt._eligible_rows(doc, "Stock Entry", "t_warehouse", "qty")
		self.assertEqual([(row["source_line_name"], row["warehouse"], row["qty"]) for row in rows], [("ROW-1", "Use - MRG", 2)])

	@patch("construction_management.api.consumable_receipt.frappe.db.exists", return_value=True)
	@patch("construction_management.api.consumable_receipt._eligible_rows")
	def test_existing_source_issue_is_not_duplicated(self, eligible_rows, _exists):
		consumable_receipt._create_source_issue(
			frappe._dict(name="MAT-STE-1"), "Stock Entry", "custom_source_material_transfer", "t_warehouse", "qty"
		)
		eligible_rows.assert_not_called()

	def test_report_normalizes_case_and_whitespace(self):
		self.assertEqual(
			outstanding_report._normalize("  AWAZEL   PU  4040  "),
			outstanding_report._normalize("awazel pu 4040"),
		)
