import csv
from io import BytesIO, StringIO
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase
from openpyxl import load_workbook

from construction_management.api import controlled_procurement as catalog


class TestControlledCatalogExport(UnitTestCase):
	def _row(self, **overrides):
		row = frappe._dict({
			"name": "CP-001",
			"item_name": "Injection Packer",
			"item_group": "Injection Items",
			"controlled_item_type": "Stockable",
			"stock_uom": "Nos",
			"actual_qty": 50,
			"controlled_catalog_source": "Workbook Import",
		})
		row.update(overrides)
		return row

	def test_csv_export_has_required_columns_and_safe_values(self):
		content = catalog._catalog_export_content([self._row(item_name="=formula")], "csv")
		rows = list(csv.reader(StringIO(content.decode("utf-8-sig"))))

		self.assertEqual(rows[0], list(catalog.CATALOG_EXPORT_HEADERS))
		self.assertEqual(rows[1], ["CP-001", "'=formula", "Injection Items", "Stockable", "Nos", "50.0", "Workbook Import"])

	def test_xlsx_export_has_required_columns_and_rows(self):
		content = catalog._catalog_export_content([self._row()], "xlsx")
		sheet = load_workbook(BytesIO(content), data_only=True).active

		self.assertEqual([cell.value for cell in sheet[1]], list(catalog.CATALOG_EXPORT_HEADERS))
		self.assertEqual([cell.value for cell in sheet[2]], ["CP-001", "Injection Packer", "Injection Items", "Stockable", "Nos", 50, "Workbook Import"])

	@patch.object(catalog, "save_file", return_value=SimpleNamespace(file_url="/private/files/catalog.csv"))
	@patch.object(catalog.frappe.db, "sql")
	@patch.object(catalog, "_document_company", return_value="MRG Insulation Works L.L.C")
	@patch.object(catalog, "_require")
	@patch.object(catalog, "today", return_value="2026-10-10")
	def test_download_export_uses_catalog_filters_without_pagination(self, today, require, company, sql, save):
		sql.return_value = [self._row()]

		result = catalog.download_catalog_export(
			file_format="csv", search="Packer", item_type="Stockable", item_group="Injection Items",
			source="Workbook Import", stock_status="in_stock", sort_by="actual_qty", sort_order="desc",
		)

		self.assertEqual(result, {"file_url": "/private/files/catalog.csv", "filename": result["filename"], "rows": 1})
		query, params = sql.call_args.args
		self.assertNotIn("LIMIT", query)
		self.assertIn("item.item_name LIKE %(search)s", query)
		self.assertIn("COALESCE(stock.actual_qty, 0) > 0", query)
		self.assertIn("ORDER BY COALESCE(stock.actual_qty, 0) DESC, item.name ASC", query)
		self.assertEqual(params["search"], "%Packer%")
		self.assertEqual(params["item_group"], "Injection Items")
		save.assert_called_once()
		self.assertTrue(save.call_args.args[0].endswith(".csv"))
		self.assertEqual(save.call_args.kwargs["is_private"], 1)

	@patch.object(catalog, "_roles", return_value=set())
	def test_export_requires_catalog_permission(self, roles):
		with self.assertRaises(frappe.PermissionError):
			catalog.download_catalog_export()
