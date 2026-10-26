"""Database-free regression tests for the MRG duplicate-stock repair guards."""

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.scripts.mrg_stock_duplicate_repair import planner, runner
from construction_management.scripts.mrg_stock_duplicate_repair.revaluation import select_jobs


class TestMRGStockDuplicateRepair(UnitTestCase):
	def setUp(self):
		old = frappe._dict(name="OLD", item_name="FOAM (250KG) DRUM", stock_uom="Kg",
			is_stock_item=1, has_serial_no=0, has_batch_no=0, disabled=0, is_customer_provided_item=0)
		new = frappe._dict(old, name="CP-NEW", item_name="FOAM (250KG DRUM)", stock_uom="Nos")
		old_balance = frappe._dict(qty_after_transaction=875, stock_value=10325,
			valuation_rate=11.8, name="old-sle")
		new_balance = frappe._dict(qty_after_transaction=3.5, stock_value=10325,
			name="new-sle", voucher_no="snapshot", voucher_type="Stock Reconciliation",
			posting_datetime="2026-09-30 00:00:00")
		self.source = {"new_code": new.name, "warehouse": "Stores - MRG", "source_qty": 875,
			"source_uoms": ["Kg"], "source_rows": [2]}
		self.evidence = SimpleNamespace(items={old.name: old, new.name: new},
			mapping={new.name: {old.name}}, future={}, reserved={},
			mapping_rows={(new.name, old.name): [2]}, uoms={old.name: {"kg": 1, "nos": 250}},
			balances={(old.name, "Stores - MRG"): old_balance, (new.name, "Stores - MRG"): new_balance})

	def test_source_quantity_and_explicit_mapping_select_legacy_carrying_value(self):
		rows, reason = planner.classify(self.source, self.evidence)
		self.assertFalse(reason)
		self.assertEqual(rows[0]["old_qty"], 875)
		self.assertEqual(rows[0]["old_value"], 10325)
		self.assertEqual(rows[0]["new_qty"], 3.5)

	def test_name_similarity_never_authorizes_a_write(self):
		self.evidence.mapping.clear()
		self.assert_reason("missing_explicit_mapping")

	def test_future_legacy_activity_is_held_even_if_current_quantity_matches(self):
		self.evidence.future["OLD", "Stores - MRG"] = {"count": 2}
		self.assert_reason("legacy_transactions_after_cutoff")

	def test_original_snapshot_must_match_historical_legacy_quantity(self):
		self.source["source_qty"] = 1000
		self.assert_reason("legacy_quantity_differs_from_source")

	def test_different_package_capacity_is_held(self):
		self.evidence.items["CP-NEW"].item_name = "FOAM (220KG DRUM)"
		self.assert_reason("conflicting_package_sizes")

	def test_batch_items_are_not_silently_retired(self):
		self.evidence.items["OLD"].has_batch_no = 1
		self.assert_reason("unsupported_item_properties")

	def test_reserved_stock_is_held(self):
		self.evidence.reserved["OLD", "Stores - MRG"] = 1
		self.assert_reason("legacy_stock_reserved")

	def test_new_stock_requires_reconciliation_provenance(self):
		self.evidence.balances["CP-NEW", "Stores - MRG"].voucher_type = "Purchase Receipt"
		self.assert_reason("new_stock_not_from_reconciliation_at_cutoff")

	def test_zero_or_negative_legacy_stock_value_is_held(self):
		self.evidence.balances["OLD", "Stores - MRG"].stock_value = -1
		self.assert_reason("nonpositive_legacy_value")

	def test_stored_package_factor_is_used_without_guessing_from_name(self):
		old, new = self.evidence.items["OLD"], self.evidence.items["CP-NEW"]
		self.assertEqual(planner.source_factor("Nos", old, new, {"nos": 250}), 250)
		self.assertIsNone(planner.source_factor("Nos", old, new, {}))

	def test_equivalent_package_labels_require_matching_capacity(self):
		old, new = self.evidence.items["OLD"], self.evidence.items["CP-NEW"]
		old.stock_uom = "DRUM"
		self.assertEqual(planner.source_factor("Nos", old, new, {}), 1)
		new.item_name = "FOAM (220KG DRUM)"
		self.assertIsNone(planner.source_factor("Nos", old, new, {}))

	def test_duplicate_claims_on_one_legacy_balance_are_all_held(self):
		rows = [{"old_code": "OLD", "new_code": code, "warehouse": "W"} for code in ["CP-A", "CP-B"]]
		eligible, held = planner.remove_overlapping_legacy_rows(rows)
		self.assertFalse(eligible)
		self.assertEqual(len(held), 2)

	def test_preview_fingerprint_detects_value_changes(self):
		plan = self.sample_plan()
		before = planner.plan_hash(plan)
		changed = deepcopy(plan)
		changed["eligible"][0]["old_value"] = 11000
		self.assertNotEqual(before, planner.plan_hash(changed))

	def test_site_must_be_explicit_and_exact(self):
		with self.assertRaises(ValueError):
			runner.validate_apply_site("skada.local", None, False)
		with self.assertRaises(ValueError):
			runner.validate_apply_site("production.com", "skada.local", True)

	def test_production_requires_a_separate_explicit_flag(self):
		with self.assertRaises(ValueError):
			runner.validate_apply_site("production.com", "production.com", False)
		runner.validate_apply_site("skada.local", "skada.local", False)

	@patch.object(runner, "capture_balances", return_value={})
	@patch.object(runner, "build_plan")
	@patch.object(runner.frappe, "get_all", return_value=[])
	@patch.object(runner.frappe, "db", new=MagicMock())
	def test_mid_batch_failure_rolls_back_without_committing(self, get_all, build, balances):
		database = runner.frappe.db
		plan = self.sample_plan()
		build.return_value = plan
		with patch.object(runner, "protected_balances", return_value={}), \
			patch.object(runner, "apply_documents", side_effect=ValueError("second voucher failed")):
			with self.assertRaisesRegex(ValueError, "second voucher failed"):
				runner.execute_run(False, plan["plan_hash"], None)
		database.rollback.assert_called_once_with(save_point="mrg_duplicate_repair")
		database.commit.assert_not_called()

	@patch.object(runner, "capture_balances", return_value={})
	@patch.object(runner, "build_plan")
	@patch.object(runner.frappe, "get_all", return_value=[])
	def test_stale_preview_never_starts_posting(self, get_all, build, balances):
		build.return_value = self.sample_plan()
		with patch.object(runner, "apply_documents") as apply:
			with self.assertRaisesRegex(ValueError, "Plan changed"):
				runner.execute_run(False, "0" * 64, None)
			apply.assert_not_called()

	@patch.object(runner, "verify_documents", return_value=[])
	@patch.object(runner, "capture_balances", return_value={})
	@patch.object(runner.frappe, "get_all", return_value=["manifest-file"])
	@patch.object(runner.frappe, "get_doc")
	def test_idempotency_accepts_content_hashed_manifest_filename(self, get_doc, get_all, balances, verify):
		plan = self.sample_plan()
		original = {"documents": ["MRG-DUP-20260930-test"], "status": "applied"}
		get_doc.return_value.get_content.return_value = json.dumps({"plan": plan, "result": original})
		existing = [frappe._dict(name=original["documents"][0], docstatus=1)]
		result = runner.existing_result(existing, plan["plan_hash"], None)
		self.assertEqual(result["status"], "already_applied")
		self.assertEqual(get_all.call_args.kwargs["filters"]["file_name"],
			["like", "mrg_duplicate_repair_manifest%.json"])

	def test_revaluation_cannot_process_jobs_outside_the_captured_batch(self):
		plan = {"pending_revaluations": [{"name": "captured"}]}
		with self.assertRaisesRegex(ValueError, "not captured"):
			select_jobs(plan, ["unrelated"], 0)
		self.assertEqual(select_jobs(plan, ["captured", "captured"], 0), ["captured"])

	def test_revaluation_limit_does_not_expand_scope(self):
		plan = {"pending_revaluations": [{"name": "first"}, {"name": "second"}]}
		self.assertEqual(select_jobs(plan, None, 1), ["first"])
		with self.assertRaises(ValueError):
			select_jobs(plan, None, -1)

	def assert_reason(self, expected):
		rows, reason = planner.classify(self.source, self.evidence)
		self.assertEqual(reason, expected)
		self.assertFalse(rows)

	def sample_plan(self):
		plan = {"version": 1, "company": "MRG", "cutoff": "2026-09-30 00:00:01", "sources": {},
			"eligible": [{"old_code": "OLD", "warehouse": "W", "old_value": 10325}],
			"exceptions": [], "pending_revaluations": [], "summary": {}}
		plan["plan_hash"] = planner.plan_hash(plan)
		return plan
