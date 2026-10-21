# Copyright (c) 2026, Construction Management
# License: MIT

from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.patches import apply_item_trail_list_migration as patch_mod


class TestApplyItemTrailListMigration(UnitTestCase):
	def test_load_mapping_skips_blank_rows(self):
		with NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as handle:
			handle.write("old_item_code,new_item_code,new_item_name,action\n")
			handle.write(",,,\n")
			handle.write("OLD-1,,New Name,name_only\n")
			path = handle.name
		try:
			rows = patch_mod.load_mapping_rows(path)
		finally:
			Path(path).unlink(missing_ok=True)
		self.assertEqual(rows, [{
			"old_item_code": "OLD-1",
			"new_item_code": "",
			"new_item_name": "New Name",
			"action": "name_only",
			"current_uom": "",
			"trail_uom": "",
			"uom_flag": "",
		}])

	def test_load_mapping_accepts_optional_uom_columns(self):
		with NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as handle:
			handle.write(
				"old_item_code,new_item_code,new_item_name,action,current_uom,trail_uom,uom_flag\n"
			)
			handle.write("OLD-1,NEW-1,Pipe,rename_code,Nos,LM,yes\n")
			path = handle.name
		try:
			rows = patch_mod.load_mapping_rows(path)
		finally:
			Path(path).unlink(missing_ok=True)
		self.assertEqual(rows[0]["current_uom"], "Nos")
		self.assertEqual(rows[0]["trail_uom"], "LM")
		self.assertEqual(rows[0]["uom_flag"], "yes")
		self.assertEqual(rows[0]["action"], "rename_code")

	@patch.object(patch_mod.frappe.db, "get_value", return_value="Nos")
	@patch.object(patch_mod.frappe.db, "exists", return_value=True)
	def test_collect_uom_review_rows_flags_mismatch_and_merge(self, exists, get_value):
		rows = [
			{
				"old_item_code": "OLD-1",
				"new_item_code": "NEW-1",
				"new_item_name": "Pipe",
				"action": "rename_code",
				"current_uom": "Nos",
				"trail_uom": "LM",
				"uom_flag": "yes",
			},
			{
				"old_item_code": "OLD-2",
				"new_item_code": "KEEP-2",
				"new_item_name": "",
				"action": "merge",
				"current_uom": "Nos",
				"trail_uom": "BAGS",
				"uom_flag": "",
			},
			{
				"old_item_code": "OLD-3",
				"new_item_code": "",
				"new_item_name": "Same",
				"action": "name_only",
				"current_uom": "Nos",
				"trail_uom": "Nos",
				"uom_flag": "",
			},
		]
		flagged = patch_mod.collect_uom_review_rows(rows)
		self.assertEqual(len(flagged), 2)
		self.assertEqual(flagged[0]["old_item_code"], "OLD-1")
		self.assertIn("uom_flag=yes", flagged[0]["reason"])
		self.assertEqual(flagged[1]["old_item_code"], "OLD-2")
		self.assertIn("merge not allowed", flagged[1]["reason"])

	def test_validate_row_requires_name_for_name_only(self):
		with self.assertRaises(frappe.ValidationError):
			patch_mod.validate_row({
				"old_item_code": "OLD-1", "new_item_code": "", "new_item_name": "", "action": "name_only",
			}, 2)

	def test_validate_row_requires_new_code_for_rename(self):
		with self.assertRaises(frappe.ValidationError):
			patch_mod.validate_row({
				"old_item_code": "OLD-1", "new_item_code": "", "new_item_name": "X", "action": "rename_code",
			}, 3)

	@patch.object(patch_mod, "_set_item_name")
	@patch.object(patch_mod.frappe.db, "get_value", return_value="Old Name")
	@patch.object(patch_mod.frappe.db, "exists", return_value=True)
	def test_name_only_updates_item_name(self, exists, get_value, set_name):
		outcome = patch_mod.apply_row({
			"old_item_code": "OLD-1", "new_item_code": "", "new_item_name": "Trail Name", "action": "name_only",
		})
		self.assertEqual(outcome["status"], "applied")
		set_name.assert_called_once_with("OLD-1", "Trail Name")

	@patch.object(patch_mod.frappe.db, "get_value", return_value="Trail Name")
	@patch.object(patch_mod.frappe.db, "exists", return_value=True)
	def test_name_only_skips_when_already_set(self, exists, get_value):
		outcome = patch_mod.apply_row({
			"old_item_code": "OLD-1", "new_item_code": "", "new_item_name": "Trail Name", "action": "name_only",
		})
		self.assertEqual(outcome["status"], "skipped")

	@patch("frappe.model.rename_doc.rename_doc")
	@patch.object(patch_mod.frappe.db, "exists", side_effect=lambda dt, name: name == "OLD-1")
	def test_rename_code_calls_rename_doc(self, exists, rename_doc):
		outcome = patch_mod.apply_row({
			"old_item_code": "OLD-1", "new_item_code": "NEW-1", "new_item_name": "", "action": "rename_code",
		})
		self.assertEqual(outcome["status"], "applied")
		rename_doc.assert_called_once()
		self.assertEqual(rename_doc.call_args.kwargs["merge"], False)
		self.assertEqual(rename_doc.call_args.kwargs["doctype"], "Item")
		self.assertEqual(rename_doc.call_args.kwargs["old"], "OLD-1")
		self.assertEqual(rename_doc.call_args.kwargs["new"], "NEW-1")

	@patch.object(patch_mod.frappe.db, "exists", side_effect=lambda dt, name: name == "NEW-1")
	def test_rename_code_skips_when_already_migrated(self, exists):
		outcome = patch_mod.apply_row({
			"old_item_code": "OLD-1", "new_item_code": "NEW-1", "new_item_name": "", "action": "rename_code",
		})
		self.assertEqual(outcome["status"], "skipped")

	@patch.object(patch_mod.frappe.db, "exists", return_value=True)
	def test_rename_code_fails_when_both_exist(self, exists):
		with self.assertRaisesRegex(frappe.ValidationError, "target already exists"):
			patch_mod.apply_row({
				"old_item_code": "OLD-1", "new_item_code": "NEW-1", "new_item_name": "", "action": "rename_code",
			})

	@patch.object(patch_mod, "merge_blocker", return_value=None)
	@patch("frappe.model.rename_doc.rename_doc")
	@patch.object(patch_mod.frappe.db, "exists", return_value=True)
	def test_merge_calls_rename_doc_with_merge(self, exists, rename_doc, merge_blocker):
		outcome = patch_mod.apply_row({
			"old_item_code": "OLD-1", "new_item_code": "NEW-1", "new_item_name": "", "action": "merge",
		})
		self.assertEqual(outcome["status"], "applied")
		self.assertTrue(rename_doc.call_args.kwargs["merge"])
		merge_blocker.assert_called_once_with("OLD-1", "NEW-1")

	@patch.object(patch_mod, "merge_blocker", return_value="stock_uom differs")
	@patch.object(patch_mod.frappe.db, "exists", return_value=True)
	def test_merge_fails_on_blocker(self, exists, merge_blocker):
		with self.assertRaisesRegex(frappe.ValidationError, "stock_uom differs"):
			patch_mod.apply_row({
				"old_item_code": "OLD-1", "new_item_code": "NEW-1", "new_item_name": "", "action": "merge",
			})

	@patch.object(patch_mod.frappe.db, "sql", return_value=[])
	@patch.object(patch_mod.frappe.db, "get_value")
	def test_merge_blocker_detects_property_mismatch(self, get_value, sql):
		get_value.side_effect = [
			frappe._dict(stock_uom="Nos", is_stock_item=1, has_serial_no=0, has_batch_no=0),
			frappe._dict(stock_uom="LM", is_stock_item=1, has_serial_no=0, has_batch_no=0),
		]
		self.assertIn("stock_uom differs", patch_mod.merge_blocker("OLD-1", "NEW-1"))

	@patch.object(patch_mod, "apply_row")
	@patch.object(patch_mod.frappe.db, "commit")
	@patch.object(patch_mod.frappe.db, "rollback")
	def test_run_orders_actions_and_throws_on_failures(self, rollback, commit, apply_row):
		apply_row.side_effect = [
			{"status": "applied", "detail": "name ok", "row": {}},
			frappe.ValidationError("merge blocked"),
		]
		rows = [
			{"old_item_code": "B", "new_item_code": "B2", "new_item_name": "", "action": "merge"},
			{"old_item_code": "A", "new_item_code": "", "new_item_name": "Name A", "action": "name_only"},
		]
		with self.assertRaises(frappe.ValidationError):
			patch_mod.run(rows)
		self.assertEqual(
			[call.args[0]["action"] for call in apply_row.call_args_list],
			["name_only", "merge"],
		)
		commit.assert_called_once()
		rollback.assert_called_once()

	@patch.object(patch_mod, "run")
	@patch.object(patch_mod, "load_mapping_rows", return_value=[])
	def test_execute_noop_when_csv_empty(self, load_rows, run):
		patch_mod.execute()
		run.assert_not_called()
