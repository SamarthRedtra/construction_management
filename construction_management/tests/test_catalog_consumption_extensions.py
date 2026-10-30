from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.api import consumable_receipt
from construction_management.construction_management.report.outstanding_po_items_missing_from_catalog import (
	outstanding_po_items_missing_from_catalog as outstanding_report,
)

MRG = "M R G INSULATION WORKS L.L.C"
SKADA = "SKADA CONSTRUCTION L.L.C"
SITE_PROJECTS = {"1171 - Site - MRG": "1171", "Use - MRG": "P-1"}


def _site_project(warehouse, company=None):
	return SITE_PROJECTS.get(warehouse)


def _transfer(*rows, company=MRG):
	doc = MagicMock(name="MAT-STE-1", company=company, posting_date="2026-10-07")
	doc.items = [frappe._dict(row) for row in rows]
	doc.get.return_value = None
	return doc


@patch("construction_management.api.consumable_receipt.get_warehouse_project", side_effect=_site_project)
@patch("construction_management.api.consumable_receipt._controlled_item_types", return_value={"CONSUMABLE": "Consumable"})
class TestCatalogConsumptionExtensions(UnitTestCase):
	@patch("construction_management.api.consumable_receipt._auto_consumption_enabled", return_value=True)
	@patch("construction_management.api.consumable_receipt._create_source_issue")
	def test_transfer_consumes_from_destination(self, create_issue, _enabled, *_):
		transfer = frappe._dict(stock_entry_type="Material Transfer", is_return=0, company=MRG)
		consumable_receipt.on_transfer_submit(transfer)
		create_issue.assert_called_once_with(
			transfer,
			"Stock Entry",
			"custom_source_material_transfer",
			"t_warehouse",
			"qty",
		)

	@patch("construction_management.api.consumable_receipt._create_source_issue")
	@patch("construction_management.api.consumable_receipt.frappe.db.get_value", return_value=0)
	def test_skada_transfer_is_not_consumed(self, _setting, create_issue, *_):
		consumable_receipt.on_transfer_submit(
			frappe._dict(stock_entry_type="Material Transfer", is_return=0, company=SKADA)
		)
		create_issue.assert_not_called()

	@patch("construction_management.api.consumable_receipt._skip_auto_consumption_warehouses", return_value=set())
	def test_site_transfer_issues_to_site_project(self, *_):
		doc = _transfer(dict(name="ROW-1", idx=1, item_code="CONSUMABLE", qty=4, t_warehouse="1171 - Site - MRG"))
		rows = consumable_receipt._eligible_rows(doc, "Stock Entry", "t_warehouse", "qty")
		self.assertEqual([(row["warehouse"], row["qty"], row["project"]) for row in rows], [("1171 - Site - MRG", 4, "1171")])

	@patch("construction_management.api.consumable_receipt._skip_auto_consumption_warehouses", return_value={"Stores - MRG"})
	def test_eligible_rows_skip_store_and_opted_out_warehouse(self, *_):
		doc = _transfer(
			dict(name="ROW-1", idx=1, item_code="CONSUMABLE", qty=2, t_warehouse="Use - MRG"),
			dict(name="ROW-2", idx=2, item_code="CONSUMABLE", qty=3, t_warehouse="Stores - MRG"),
		)
		rows = consumable_receipt._eligible_rows(doc, "Stock Entry", "t_warehouse", "qty")
		self.assertEqual([(row["source_line_name"], row["warehouse"], row["qty"]) for row in rows], [("ROW-1", "Use - MRG", 2)])

	@patch("construction_management.api.consumable_receipt._skip_auto_consumption_warehouses", return_value=set())
	def test_site_without_project_is_blocked(self, *_):
		doc = _transfer(dict(name="ROW-1", idx=1, item_code="CONSUMABLE", qty=1, t_warehouse="1172 - No Project - MRG"))
		with self.assertRaises(frappe.ValidationError):
			consumable_receipt._eligible_rows(doc, "Stock Entry", "t_warehouse", "qty")

	@patch("construction_management.api.consumable_receipt._skip_auto_consumption_warehouses", return_value=set())
	def test_receipt_directly_at_site_is_consumed(self, *_):
		doc = _transfer(dict(name="PRI-1", idx=1, item_code="CONSUMABLE", stock_qty=5, warehouse="1171 - Site - MRG"))
		rows = consumable_receipt._eligible_rows(doc, "Purchase Receipt", "warehouse", "stock_qty")
		self.assertEqual([(row["source_doctype"], row["qty"], row["project"]) for row in rows], [("Purchase Receipt", 5, "1171")])

	@patch("construction_management.api.consumable_receipt.frappe.db.exists", return_value=True)
	@patch("construction_management.api.consumable_receipt._eligible_rows")
	def test_existing_source_issue_is_not_duplicated(self, eligible_rows, *_):
		consumable_receipt._create_source_issue(
			frappe._dict(name="MAT-STE-1"), "Stock Entry", "custom_source_material_transfer", "t_warehouse", "qty"
		)
		eligible_rows.assert_not_called()

	def test_report_normalizes_case_and_whitespace(self, *_):
		self.assertEqual(
			outstanding_report._normalize("  AWAZEL   PU  4040  "),
			outstanding_report._normalize("awazel pu 4040"),
		)
