# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.construction_management.page.bulk_dpr_entry import bulk_dpr_entry
from construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_fetch import (
	get_boq_items_with_balance,
	get_existing_dprs,
)


class TestBulkDPRFetch(UnitTestCase):
	@patch("construction_management.api.boq_tree.get_item_ledger_values")
	@patch(
		"construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_fetch.frappe.db.sql"
	)
	@patch(
		"construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_fetch.frappe.get_all"
	)
	def test_boq_balance_uses_batched_ledger_query(self, get_all, sql, get_item_ledger_values):
		get_all.return_value = [
			frappe._dict(name="BOQI-1", item_code="SVC", description="Roof", unit="M2", total_qty=100)
		]
		sql.return_value = [frappe._dict(boq_item="BOQI-1", accumulated_qty=40)]

		items = get_boq_items_with_balance("1037")

		get_item_ledger_values.assert_not_called()
		sql.assert_called_once()
		self.assertEqual(items[0]["balance"], 60)

	@patch(
		"construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_fetch.frappe.get_doc"
	)
	@patch(
		"construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_fetch.frappe.db.get_value"
	)
	@patch(
		"construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_fetch.frappe.db.count",
		return_value=1,
	)
	@patch(
		"construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_fetch.frappe.get_all"
	)
	def test_existing_dprs_do_not_call_get_doc(self, get_all, _count, get_value, get_doc):
		get_value.return_value = "MRG"
		headers = [
			frappe._dict(
				name="DPR-1",
				boq_item="BOQI-1",
				site="SITE-1",
				remarks="",
				warehouse="WH",
				docstatus=0,
				area_covered=10,
				asset_cost=0,
				labour_cost=100,
				material_cost=0,
				overhead_cost=0,
				expense_cost=0,
				total_cost=100,
			)
		]

		def _get_all(doctype, **kwargs):
			if doctype == "Daily Progress Record":
				return headers
			if doctype == "DPR Employee":
				return [
					frappe._dict(
						parent="DPR-1",
						employee="EMP-1",
						employee_name="Ali",
						hours=8,
						rate_per_day=100,
						amount=100,
					)
				]
			return []

		get_all.side_effect = _get_all

		result = get_existing_dprs("1037", "2026-09-22")

		get_doc.assert_not_called()
		self.assertEqual(result["total"], 1)
		self.assertEqual(result["dprs"][0]["employees"][0]["employee_name"], "Ali")

	def test_master_payload_uses_project_summary(self):
		project_row = frappe._dict(name="1037", company="MRG", site_location="Stores - MRG")
		with patch.object(bulk_dpr_entry, "get_project_summary", return_value=project_row), patch.object(
			bulk_dpr_entry, "project_company_mismatch", return_value=False
		), patch.object(bulk_dpr_entry, "get_boq_items_with_balance", return_value=[]), patch.object(
			bulk_dpr_entry, "get_project_sites", return_value=[]
		), patch.object(
			bulk_dpr_entry, "get_employees_with_rates", return_value=[]
		), patch.object(
			bulk_dpr_entry, "get_materials", return_value=[]
		), patch.object(
			bulk_dpr_entry, "load_project_assets", return_value=[]
		), patch.object(
			bulk_dpr_entry, "get_overhead_accounts", return_value=[]
		), patch(
			"construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_entry.frappe.db.get_value",
			return_value="",
		), patch(
			"construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_entry.frappe.get_doc"
		) as get_doc:
			payload = bulk_dpr_entry.get_master_data("1037", "MRG", "2026-09-22")

		get_doc.assert_not_called()
		self.assertEqual(payload["project"].name, "1037")
		self.assertNotIn("items", payload["project"])
