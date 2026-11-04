# Copyright (c) 2026, Construction Management
# License: MIT

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.scripts import enable_consumable_stock_from_grn as job


class TestEnableConsumableStockFromGrn(UnitTestCase):
	def test_load_item_codes_from_csv(self):
		path = Path(frappe.get_app_path("construction_management", "data", job.CSV_NAME))
		codes = job.load_item_codes(path)
		self.assertEqual(len(codes), 125)
		self.assertIn('1" PPR GATE VALVE', codes)
		self.assertEqual(len(codes), len(set(codes)))

	def test_service_charge_exclusions(self):
		self.assertTrue(job.is_service_charge("CONCRETE MOBILE PUMP CHARGES UP TO 45 MTR"))
		self.assertTrue(job.is_service_charge("CONCRETE -TECHNICIAN CHARGES FOR QTY LESS THAN 30 CUM"))
		self.assertTrue(job.is_service_charge("CONCRETE MOBILIZATION CHARGES FOR  PUMP ABOVE 56 MTR"))
		self.assertTrue(job.is_service_charge("CONCRETE - EXCESS CONCRETE CHARGES ( FULL LOAD )"))
		self.assertTrue(job.is_service_charge("BUSINESS CARD PRINTING"))
		self.assertFalse(job.is_service_charge("CONCRETE C50/20 ( 236KG OPC + 144KG GGBS + 20 KG MS"))
		self.assertFalse(job.is_service_charge("CONCRETE SPACER 25MM"))
		self.assertFalse(job.is_service_charge("TILE SPACER 1.5MM"))

	def test_aggregate_nets_returns_and_rates(self):
		rows = job.aggregate_stock_rows(
			[
				{
					"item_code": "TILE SPACER 1.5MM",
					"company": "SKADA",
					"warehouse": "SKD-46 - SC",
					"purchase_receipt": "GRN-1",
					"is_return": 0,
					"qty": 100,
					"amount": 60,
				},
				{
					"item_code": "TILE SPACER 1.5MM",
					"company": "SKADA",
					"warehouse": "SKD-46 - SC",
					"purchase_receipt": "GRN-2",
					"is_return": 1,
					"qty": 20,
					"amount": 12,
				},
			]
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["qty"], 80)
		self.assertAlmostEqual(rows[0]["valuation_rate"], 0.6)
		self.assertEqual(rows[0]["receipt_count"], 2)

	@patch.object(job, "submit_stock_reconciliations")
	@patch.object(job.frappe.db, "commit")
	@patch.object(job.frappe.db, "set_value")
	@patch.object(job.frappe.db, "get_value")
	@patch.object(job, "fetch_grn_lines")
	@patch.object(job.frappe, "get_all")
	@patch.object(job, "load_item_codes", return_value=["TILE SPACER 1.5MM", "CONCRETE MOBILE PUMP CHARGES UP TO 45 MTR"])
	def test_dry_run_does_not_write(
		self, _codes, get_all, fetch, get_value, set_value, commit, submit,
	):
		get_all.return_value = [
			SimpleNamespace(
				name="TILE SPACER 1.5MM",
				item_name="TILE SPACER 1.5MM",
				is_stock_item=0,
				controlled_item_type="Consumable",
				disabled=0,
				stock_uom="Nos",
			),
			SimpleNamespace(
				name="CONCRETE MOBILE PUMP CHARGES UP TO 45 MTR",
				item_name="CONCRETE MOBILE PUMP CHARGES UP TO 45 MTR",
				is_stock_item=0,
				controlled_item_type="Consumable",
				disabled=0,
				stock_uom="Nos",
			),
		]
		fetch.return_value = [
			{
				"item_code": "TILE SPACER 1.5MM",
				"company": "SKADA CONSTRUCTION L.L.C",
				"warehouse": "SKD-46 - SC",
				"purchase_receipt": "GRN-1",
				"posting_date": "2026-09-10",
				"is_return": 0,
				"qty": 10,
				"amount": 6,
			},
			{
				"item_code": "CONCRETE MOBILE PUMP CHARGES UP TO 45 MTR",
				"company": "SKADA CONSTRUCTION L.L.C",
				"warehouse": "SKD-50 - SC",
				"purchase_receipt": "GRN-2",
				"posting_date": "2026-09-10",
				"is_return": 0,
				"qty": 5,
				"amount": 125,
			},
		]
		get_value.return_value = SimpleNamespace(
			company="SKADA CONSTRUCTION L.L.C", is_group=0, disabled=0
		)

		result = job.run(dry_run=1)

		self.assertEqual(result["status"], "preview")
		self.assertEqual(result["enabled_count"], 2)
		self.assertEqual(result["excluded_service_line_count"], 1)
		self.assertEqual(result["bookable_aggregate_count"], 1)
		set_value.assert_not_called()
		submit.assert_not_called()
		commit.assert_not_called()

	@patch.object(job, "submit_stock_reconciliations", return_value=[{"name": "MAT-RECO-1"}])
	@patch.object(job.frappe.db, "commit")
	@patch.object(job.frappe.db, "set_value")
	@patch.object(job.frappe.db, "get_value")
	@patch.object(job, "fetch_grn_lines")
	@patch.object(job.frappe, "get_all")
	@patch.object(job, "load_item_codes", return_value=["TILE SPACER 1.5MM"])
	def test_apply_enables_and_submits(
		self, _codes, get_all, fetch, get_value, set_value, commit, submit,
	):
		get_all.return_value = [
			SimpleNamespace(
				name="TILE SPACER 1.5MM",
				item_name="TILE SPACER 1.5MM",
				is_stock_item=0,
				controlled_item_type="Consumable",
				disabled=0,
				stock_uom="Nos",
			)
		]
		fetch.return_value = [
			{
				"item_code": "TILE SPACER 1.5MM",
				"company": "SKADA CONSTRUCTION L.L.C",
				"warehouse": "SKD-46 - SC",
				"purchase_receipt": "GRN-1",
				"posting_date": "2026-09-10",
				"is_return": 0,
				"qty": 10,
				"amount": 6,
			}
		]
		get_value.return_value = SimpleNamespace(
			company="SKADA CONSTRUCTION L.L.C", is_group=0, disabled=0
		)

		result = job.run(dry_run=0)

		self.assertEqual(result["status"], "applied")
		set_value.assert_called_once_with(
			"Item", "TILE SPACER 1.5MM", "is_stock_item", 1, update_modified=False
		)
		submit.assert_called_once()
		commit.assert_called_once()
		self.assertEqual(result["documents"][0]["name"], "MAT-RECO-1")
