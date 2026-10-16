# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.api import error_items_catalog_import as importer


class TestErrorItemsCatalogImport(UnitTestCase):
	def test_prepare_skips_already_controlled_and_holds_asset_service(self):
		rows = [
			(2, ("HARDWARE ITEMS", "CONTROLLED HAMMER", "SUP-A", "Nos", 10, "Consumable")),
			(3, ("HARDWARE ITEMS", "NEW SPANNER", "SUP-A", "Nos", 12, "Consumable")),
			(4, ("TESTING & CERTIFICATION", "AIR TEST", "SUP-A", "Nos", 50, "Service")),
			(5, ("HARDWARE ITEMS", "TOTAL STATION", "SUP-A", "SET", 1000, "Asset")),
			(6, ("STEEL", "STOCK BAR", "SUP-A", "TON", 100, "Material in Stock")),
		]

		with (
			patch.object(importer, "_source_rows", return_value=rows),
			patch.object(importer, "_controlled_names", return_value={"controlled hammer"}),
			patch.object(importer, "_legacy_by_name", return_value=[]),
			patch.object(
				importer.frappe,
				"get_all",
				side_effect=[
					[frappe._dict(name="SUP-A", supplier_name="SUP-A")],
					["HARDWARE ITEMS", "STEEL"],
				],
			),
			patch.object(importer.catalog, "_catalog_uom", side_effect=lambda value: value if value != "Tonne" else "Tonne"),
			patch.object(importer, "_resolve_uom", side_effect=lambda raw: {"TON": "Tonne", "Nos": "Nos", "SET": "Set"}.get(str(raw), str(raw))),
		):
			selected, held, missing_groups = importer._prepare(importer.PACKAGE_SOURCE)

		selected_names = [row[1] for _, row in selected]
		self.assertIn("NEW SPANNER", selected_names)
		self.assertIn("STOCK BAR", selected_names)
		self.assertNotIn("CONTROLLED HAMMER", selected_names)
		held_reasons = {desc: reason for _, desc, reason in held}
		self.assertIn("AIR TEST", held_reasons)
		self.assertIn("TOTAL STATION", held_reasons)
		self.assertTrue(held_reasons["AIR TEST"].startswith("Asset/Service"))
		self.assertEqual(missing_groups, [])

	def test_prepare_holds_missing_supplier_and_uom_conflict(self):
		rows = [
			(2, ("HARDWARE ITEMS", "MISSING SUPPLIER ITEM", "NO-SUCH-SUP", "Nos", 10, "Consumable")),
			(3, ("HARDWARE ITEMS", "UOM CONFLICT ITEM", "SUP-A", "PKT", 6.5, "Consumable")),
		]

		def legacy(description):
			if description == "UOM CONFLICT ITEM":
				return [
					frappe._dict(
						name="UOM CONFLICT ITEM",
						item_name="UOM CONFLICT ITEM",
						stock_uom="Nos",
						is_stock_item=1,
					)
				]
			return []

		with (
			patch.object(importer, "_source_rows", return_value=rows),
			patch.object(importer, "_controlled_names", return_value=set()),
			patch.object(importer, "_legacy_by_name", side_effect=legacy),
			patch.object(
				importer.frappe,
				"get_all",
				side_effect=[
					[frappe._dict(name="SUP-A", supplier_name="SUP A")],
					["HARDWARE ITEMS"],
				],
			),
			patch.object(importer.catalog, "_supplier_name", return_value=""),
			patch.object(importer, "_resolve_uom", side_effect=lambda raw: str(raw)),
		):
			selected, held, _groups = importer._prepare(importer.PACKAGE_SOURCE)

		self.assertEqual(selected, [])
		reasons = {desc: reason for _, desc, reason in held}
		self.assertEqual(reasons["MISSING SUPPLIER ITEM"], "Supplier master not found")
		self.assertIn("another stock UOM", reasons["UOM CONFLICT ITEM"])

	def test_prepare_creates_new_code_for_non_stock_legacy_adopts_stock(self):
		rows = [
			(2, ("PRINTING & STATIONERY", "A4 PAPER", "SUP-A", "Box", 68, "Consumable")),
			(3, ("ELECTRICAL ITEMS", "CABLE GLAND 25MM", "SUP-A", "Nos", 11, "Consumable")),
		]

		def legacy(description):
			if description == "A4 PAPER":
				return [
					frappe._dict(
						name="A4 PAPER",
						item_name="A4 PAPER",
						stock_uom="Box",
						is_stock_item=0,
					)
				]
			if description == "CABLE GLAND 25MM":
				return [
					frappe._dict(
						name="CABLE GLAND 25MM",
						item_name="CABLE GLAND 25MM",
						stock_uom="Nos",
						is_stock_item=1,
					)
				]
			return []

		with (
			patch.object(importer, "_source_rows", return_value=rows),
			patch.object(importer, "_controlled_names", return_value=set()),
			patch.object(importer, "_legacy_by_name", side_effect=legacy),
			patch.object(
				importer.frappe,
				"get_all",
				side_effect=[
					[frappe._dict(name="SUP-A", supplier_name="SUP-A")],
					["PRINTING & STATIONERY", "ELECTRICAL ITEMS"],
				],
			),
			patch.object(importer, "_resolve_uom", side_effect=lambda raw: str(raw)),
			patch.object(
				importer.catalog, "_item_code", return_value="CP-A4_PAPER"
			) as item_code,
		):
			selected, held, _groups = importer._prepare(importer.PACKAGE_SOURCE)

		self.assertEqual(held, [])
		by_name = {row[1]: row for _, row in selected}
		self.assertEqual(by_name["A4 PAPER"][0], "CP-A4_PAPER")
		self.assertEqual(by_name["CABLE GLAND 25MM"][0], "CABLE GLAND 25MM")
		item_code.assert_called_once_with("A4 PAPER")

	@patch.object(importer, "_existing_request")
	@patch.object(importer, "_source_checksum", return_value="abc123")
	def test_submit_is_noop_when_checksum_request_exists(self, _checksum, existing):
		existing.return_value = frappe._dict(name="CCR-EXISTING", status="Approved")
		result = importer.submit(path="/tmp/unused.xlsx")
		self.assertEqual(
			result,
			{"name": "CCR-EXISTING", "status": "Approved", "already_imported": True},
		)

	@patch.object(importer.catalog, "import_catalog_workbook")
	@patch.object(importer.catalog, "preview_catalog_workbook")
	@patch.object(importer, "save_file")
	@patch.object(importer, "_prepare")
	@patch.object(importer, "_existing_request", return_value=None)
	@patch.object(importer, "_source_checksum", return_value=importer.PACKAGE_SHA256)
	@patch.object(importer, "_validate_packaged_source")
	def test_submit_creates_pending_approval_request(
		self,
		_validate,
		_checksum,
		_existing,
		prepare,
		save_file,
		preview,
		import_workbook,
	):
		prepare.return_value = (
			[(2, ["", "NEW ITEM", "HARDWARE ITEMS", "Consumable", "Nos", "", "", "SUP-A", 10])],
			[(3, "SERVICE ROW", "Asset/Service: accounting mapping required")],
			[],
		)
		preview.return_value = {
			"valid_rows": 1,
			"create": 1,
			"reuse": 0,
			"errors": [],
		}
		import_workbook.return_value = {"name": "CCR-NEW", "status": "Pending Accounts"}
		file_doc = MagicMock()
		file_doc.file_url = "/private/files/x.xlsx"
		save_file.return_value = file_doc

		request_doc = MagicMock()
		request_doc.status = "Pending Accounts"

		with (
			patch.object(importer.frappe, "set_user"),
			patch.object(importer.frappe.defaults, "set_user_default"),
			patch.object(importer.frappe, "get_doc", return_value=request_doc),
			patch.object(importer.Path, "read_bytes", return_value=b"xlsx"),
		):
			result = importer.submit(path=str(importer.PACKAGE_SOURCE))

		import_workbook.assert_called_once()
		self.assertEqual(result["name"], "CCR-NEW")
		self.assertEqual(result["status"], "Pending Accounts")
		self.assertEqual(result["held_rows"], 1)
		self.assertEqual(request_doc.full_source_checksum, importer.PACKAGE_SHA256)
