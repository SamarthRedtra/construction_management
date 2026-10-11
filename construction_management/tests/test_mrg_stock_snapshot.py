from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.api import mrg_stock_snapshot as snapshot
from construction_management.patches import stage_mrg_stock_snapshot


class TestMrgStockSnapshot(UnitTestCase):
	def _payload(self, **overrides):
		payload = {
			"item_code": "",
			"item_name": "AWAZEL GROUT EP 300  14 LT/SET",
			"item_group": "Grout and Tiles",
			"item_type": "Stockable",
			"stock_uom": "Nos",
			"supplier": "SUP-1",
			"rate": 10,
			"action": "Create",
		}
		payload.update(overrides)
		return payload

	def _unresolved_error(self, item_name):
		return {"item_name": item_name, "reason": "Canonical controlled stock item was not uniquely resolved"}

	def test_targets_ignore_report_uom_and_keep_controlled_uom(self):
		rows = [
			{"source_row": 2, "item_name": "Catalog Item", "warehouse": "Stores - MRG", "report_uom": "Kg", "qty": 2},
			{"source_row": 3, "item_name": "Catalog Item", "warehouse": "Stores - MRG", "report_uom": "M2", "qty": 3},
		]
		items = {"catalog item": [frappe._dict(name="CP-CATALOG-ITEM", item_name="Catalog Item", stock_uom="Nos")]}

		targets, held, errors = snapshot._targets(
			rows, items, {}, {"Stores - MRG"}, {"catalog item": 10}, {"catalog item": "Stockable"},
			{"catalog item": "Nos"},
		)

		self.assertEqual((held, errors), ([], []))
		self.assertEqual(targets, [{
			"item_code": "CP-CATALOG-ITEM", "item_name": "Catalog Item", "stock_uom": "Nos",
			"warehouse": "Stores - MRG", "qty": 5.0, "source_rows": [2, 3], "valuation_rate": None,
		}])

	def test_canonical_catalog_match_uses_finalized_uom_and_first_catalog_code(self):
		matches = [
			frappe._dict(name="CP-CATALOG_ITEM", stock_uom="Nos"),
			frappe._dict(name="CP-CATALOG_ITEM-2", stock_uom="Nos"),
			frappe._dict(name="CATALOG ITEM", stock_uom="PKT"),
		]

		self.assertEqual(
			snapshot._canonical_catalog_matches(matches, "Catalog Item", "Nos"),
			[matches[0]],
		)

	@patch.object(snapshot.catalog, "create_catalog_request")
	@patch.object(snapshot.catalog, "_ensure_group")
	@patch.object(snapshot.expanded_import, "_prepare")
	@patch.object(snapshot, "_catalog_items", return_value=({}, {}))
	@patch.object(snapshot, "_catalog_candidate_has_compatible_uom", return_value=False)
	@patch.object(snapshot.frappe.db, "get_value", return_value="LEGACY-AWAZEL")
	def test_uom_conflict_is_not_staged_as_catalog_request(self, get_value, compatible, catalog_items, prepare, ensure_group, create):
		payload = self._payload()
		prepare.return_value = ([payload], [], [], {})
		errors = [self._unresolved_error(payload["item_name"])]

		self.assertEqual(snapshot._create_missing_catalog_requests(snapshot.ITEM_TREE_PATH, errors), [])

		create.assert_not_called()
		ensure_group.assert_not_called()
		self.assertIn("LEGACY-AWAZEL has another stock UOM", errors[0]["reason"])

	@patch.object(snapshot.catalog, "create_catalog_request")
	@patch.object(snapshot.catalog, "_ensure_group")
	@patch.object(snapshot.expanded_import, "_prepare")
	@patch.object(snapshot, "_catalog_items")
	def test_duplicate_controlled_master_is_not_staged_again(self, catalog_items, prepare, ensure_group, create):
		payload = self._payload(item_name="PAINT ROLLER")
		prepare.return_value = ([payload], [], [], {})
		catalog_items.return_value = ({"paint roller": [frappe._dict(name="CP-PAINT-1"), frappe._dict(name="CP-PAINT-2")]}, {})

		self.assertEqual(snapshot._create_missing_catalog_requests(snapshot.ITEM_TREE_PATH, [self._unresolved_error("PAINT ROLLER")]), [])

		create.assert_not_called()
		ensure_group.assert_not_called()

	@patch.object(snapshot.catalog, "_catalog_request_row")
	@patch.object(snapshot.catalog, "_ensure_group")
	@patch.object(snapshot.expanded_import, "_prepare")
	@patch.object(snapshot, "_catalog_items", return_value=({}, {}))
	@patch.object(snapshot, "_catalog_candidate_has_compatible_uom", return_value=True)
	@patch.object(snapshot.frappe.db, "get_value", return_value=None)
	@patch.object(snapshot.frappe, "get_doc")
	@patch.object(snapshot, "now_datetime", return_value="2026-10-10 12:00:00")
	def test_unambiguous_missing_item_is_staged_once(self, now_datetime, get_doc, get_value, compatible, catalog_items, prepare, ensure_group, request_row):
		payload = self._payload(item_name="New Catalog Item")
		prepared = {**payload, "result_item": ""}
		prepare.return_value = ([payload], [], [], {})
		request_row.return_value = prepared
		get_doc.return_value.name = "CCR-NEW"

		self.assertEqual(snapshot._create_missing_catalog_requests(snapshot.ITEM_TREE_PATH, [self._unresolved_error("New Catalog Item")]), ["CCR-NEW"])

		ensure_group.assert_called_once_with("Grout and Tiles")
		request = get_doc.call_args.args[0]
		self.assertEqual(request["status"], "Pending Accounts")
		self.assertEqual(request["items"], [prepared])
		get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)

	@patch.object(snapshot, "_save_audit", return_value=frappe._dict(file_url="/private/files/preflight.csv"))
	@patch.object(snapshot, "_create_reconciliations")
	@patch.object(snapshot, "_create_missing_catalog_requests", return_value=[])
	@patch.object(snapshot, "preflight")
	@patch.object(snapshot.frappe, "set_user")
	def test_run_returns_auditable_failure_without_stock_submission(self, set_user, preflight, create_requests, create_reconciliations, save_audit):
		preflight.return_value = {
			"errors": [{"reason": "Unresolved Item"}], "targets": [], "target_lines": 0,
			"warehouses": 0, "held_rows": [],
		}

		result = snapshot.run()

		self.assertEqual(result["status"], "preflight_failed")
		self.assertEqual(result["stock_reconciliations"], [])
		self.assertEqual(result["preflight_error_count"], 1)
		self.assertEqual(result["matched_balances"], 0)
		self.assertEqual(result["reconciliation_balances"], 0)
		self.assertEqual(result["audit_file"], "/private/files/preflight.csv")
		create_reconciliations.assert_not_called()

	@patch.object(stage_mrg_stock_snapshot.mrg_stock_snapshot, "run", return_value={"status": "preflight_failed"})
	@patch.object(stage_mrg_stock_snapshot.mrg_stock_snapshot, "activate_report_warehouses", return_value=[])
	@patch.object(stage_mrg_stock_snapshot.frappe, "logger")
	@patch.object(stage_mrg_stock_snapshot.frappe.db, "exists", return_value=True)
	def test_deployment_patch_reactivates_the_report_warehouse_before_preflight(self, exists, logger, activate, run):
		stage_mrg_stock_snapshot.execute()

		exists.assert_called_once_with("Company", snapshot.COMPANY)
		activate.assert_called_once_with()
		run.assert_called_once_with()
		logger.return_value.info.assert_called_once_with({"event": "mrg_stock_snapshot", "status": "preflight_failed"})
