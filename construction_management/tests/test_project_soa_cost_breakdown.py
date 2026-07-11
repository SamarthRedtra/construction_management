# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt
from unittest.mock import patch

from construction_management.api.boq_tree import get_project_cost_breakdown
from construction_management.api.project_soa_cost_detail import (
	_build_labor_atoms,
	_build_material_atoms,
	_build_tree_from_atoms,
	categorize_project_cost_entry,
	get_soa_expense_breakdown,
	summarize_project_cost_breakdown,
)
from construction_management.construction_management.page.project_soa.project_soa import (
	_build_expenses,
	get_soa_expense_breakdown as soa_get_expense_breakdown,
)
from construction_management.tests.test_utils import create_test_project


class TestProjectSOACostBreakdown(FrappeTestCase):
	def test_categorize_material_entry(self):
		category = categorize_project_cost_entry(
			{"account_type": "Cost of Goods Sold", "voucher_type": "Stock Entry", "account": "COGS - TC"},
			[],
		)
		self.assertEqual(category, "material")

	def test_categorize_subcontractor_pi(self):
		category = categorize_project_cost_entry(
			{"account_type": "Expense Account", "voucher_type": "Purchase Invoice", "account": "Expenses"},
			[],
		)
		self.assertEqual(category, "subcontractor")

	def test_categorize_skips_commission_accounts(self):
		category = categorize_project_cost_entry(
			{"account_type": "Expense Account", "voucher_type": "Journal Entry", "account": "Comm-Acc"},
			["Comm-Acc"],
		)
		self.assertIsNone(category)

	def test_build_tree_three_levels(self):
		atoms = [
			{
				"group_key": "Steel",
				"group_label": "Steel",
				"line_key": "ITEM-1",
				"line_label": "Rebar 12mm",
				"qty": 10,
				"uom": "Kg",
				"rate": 5,
				"amount": 50,
				"source_doctype": "Daily Progress Record",
				"source_document": "DPR-TEST-001",
				"date": "2026-01-10",
				"remarks": "BOQ-1",
				"link": "/app/daily-progress-record/DPR-TEST-001",
			}
		]
		groups = _build_tree_from_atoms(atoms)
		self.assertEqual(len(groups), 1)
		self.assertEqual(groups[0]["label"], "Steel")
		self.assertEqual(flt(groups[0]["amount"]), 50)
		self.assertEqual(len(groups[0]["lines"]), 1)
		self.assertEqual(groups[0]["lines"][0]["label"], "Rebar 12mm")
		self.assertEqual(len(groups[0]["lines"][0]["sources"]), 1)
		self.assertEqual(groups[0]["lines"][0]["sources"][0]["document"], "DPR-TEST-001")

	def test_build_expenses_has_category_keys(self):
		project = create_test_project("TEST-SOA-COST-KEYS")
		expenses = _build_expenses(project)
		non_total = [row for row in expenses if not row.get("is_total")]
		self.assertEqual(len(non_total), 5)
		for row in non_total:
			self.assertIn("category_key", row)
			self.assertIn("expandable", row)
			self.assertIn(row["category_key"], ("material", "labor", "subcontractor", "commission", "other"))

	def test_summarize_matches_get_project_cost_breakdown(self):
		project = create_test_project("TEST-SOA-COST-SUM")
		summary = summarize_project_cost_breakdown(project)
		breakdown = get_project_cost_breakdown(project)
		for key in ("material", "labor", "subcontractor", "commission", "other", "unallocated", "total"):
			self.assertEqual(flt(summary.get(key)), flt(breakdown.get(key)), key)

	def test_get_soa_expense_breakdown_empty_category(self):
		project = create_test_project("TEST-SOA-COST-EMPTY")
		result = get_soa_expense_breakdown(project, "material")
		self.assertEqual(result["category"], "material")
		self.assertEqual(result["total"], 0)
		self.assertEqual(result["groups"], [])

	def test_get_soa_expense_breakdown_invalid_category(self):
		project = create_test_project("TEST-SOA-COST-INVALID")
		with self.assertRaises(frappe.ValidationError):
			get_soa_expense_breakdown(project, "invalid")

	@patch("construction_management.api.project_soa_cost_detail._category_total_from_summary", return_value=150.0)
	@patch("construction_management.api.project_soa_cost_detail._build_material_atoms")
	def test_material_breakdown_tree_shape(self, mock_build_atoms, _mock_total):
		mock_build_atoms.return_value = [
			{
				"group_key": "Raw Material",
				"group_label": "Raw Material",
				"line_key": "CEMENT-01",
				"line_label": "Cement Bag",
				"qty": 3,
				"uom": "Nos",
				"rate": 50,
				"amount": 150,
				"source_doctype": "Daily Progress Record",
				"source_document": "DPR-MAT-1",
				"date": "2026-02-01",
				"remarks": "",
				"link": "/app/daily-progress-record/DPR-MAT-1",
			}
		]
		result = soa_get_expense_breakdown("TEST-PROJ", "material")
		self.assertEqual(result["total"], 150)
		self.assertEqual(len(result["groups"]), 1)
		self.assertEqual(result["groups"][0]["label"], "Raw Material")
		self.assertEqual(flt(result["groups"][0]["amount"]), 150)
		self.assertEqual(result["groups"][0]["lines"][0]["sources"][0]["doctype"], "Daily Progress Record")

	def test_unallocated_subcontractor_pi_in_other_breakdown(self):
		from construction_management.api.project_soa_cost_detail import (
			_build_other_breakdown_atoms,
			_build_tree_from_atoms,
		)

		all_atoms = [
			{
				"category": "subcontractor",
				"amount": 3700,
				"voucher_type": "Purchase Invoice",
				"voucher_no": "MRG-PI-00192",
				"account": "Stock Received But Not Billed",
				"supplier": "Reva International General Trading LLC",
				"item_code": "SIKA-TOP",
				"item_name": "SIKA TOP 550 SEAL",
				"posting_date": "2026-03-28",
				"unallocated": True,
			}
		]
		atoms = _build_other_breakdown_atoms("TEST-PROJ", all_atoms)
		groups = _build_tree_from_atoms(atoms)
		self.assertTrue(groups)
		self.assertIn("Unallocated", groups[0]["label"])
		self.assertEqual(groups[0]["lines"][0]["sources"][0]["document"], "MRG-PI-00192")

	def test_build_expenses_total_uses_summary_total(self):
		project = create_test_project("TEST-SOA-COST-TOTAL")
		with patch(
			"construction_management.construction_management.page.project_soa.project_soa.get_project_cost_breakdown",
			return_value={
				"material": 0,
				"labor": 0,
				"subcontractor": 3700,
				"commission": 0,
				"other": 0,
				"unallocated": 3700,
				"total": 3700,
			},
		):
			expenses = _build_expenses(project)
		total_row = expenses[-1]
		self.assertEqual(flt(total_row["cost"]), 3700)

	@patch("construction_management.api.project_soa_cost_detail._get_dpr_linked_stock_entries", return_value={"SE-DPR-001"})
	@patch("construction_management.api.project_soa_cost_detail.frappe.db.sql")
	def test_material_atoms_skip_dpr_linked_stock_entry(self, mock_sql, _mock_linked):
		mock_sql.return_value = [
			frappe._dict({
				"item_code": "CEMENT-01",
				"item_name": "Cement Bag",
				"qty": 2,
				"uom": "Nos",
				"rate": 50,
				"amount": 100,
				"item_group": "Raw Material",
				"dpr_name": "DPR-MAT-1",
				"date": "2026-02-01",
				"boq_item": "BOQ-1",
				"stock_entry": "SE-DPR-001",
			})
		]
		gl_atoms = [
			{
				"category": "material",
				"amount": 100,
				"voucher_type": "Stock Entry",
				"voucher_no": "SE-DPR-001",
				"account": "COGS",
				"posting_date": "2026-02-01",
			},
			{
				"category": "material",
				"amount": 25,
				"voucher_type": "Stock Entry",
				"voucher_no": "SE-OTHER",
				"account": "COGS",
				"posting_date": "2026-02-02",
			},
		]
		with patch(
			"construction_management.api.project_soa_cost_detail._expand_stock_entry_atoms",
			side_effect=lambda atom: [{
				**atom,
				"amount": atom["amount"],
				"group_key": "GL",
				"line_key": atom["voucher_no"],
				"source_doctype": "Stock Entry",
				"source_document": atom["voucher_no"],
			}],
		):
			atoms = _build_material_atoms("TEST-PROJ", gl_atoms)

		dpr_atoms = [a for a in atoms if a.get("source_doctype") == "Daily Progress Record"]
		se_atoms = [a for a in atoms if a.get("source_doctype") == "Stock Entry"]
		self.assertEqual(len(dpr_atoms), 1)
		self.assertEqual(len(se_atoms), 1)
		self.assertEqual(se_atoms[0]["source_document"], "SE-OTHER")
		self.assertIn("SE-DPR-001", dpr_atoms[0]["remarks"])
		self.assertEqual(flt(sum(a["amount"] for a in atoms)), 125)

	@patch("construction_management.api.project_soa_cost_detail._get_dpr_linked_journal_entries", return_value={"JE-DPR-001"})
	@patch("construction_management.api.project_soa_cost_detail.frappe.get_all")
	@patch("construction_management.api.project_soa_cost_detail.frappe.db.sql")
	def test_labor_atoms_skip_dpr_linked_journal_entry(self, mock_sql, mock_get_all, _mock_linked):
		mock_sql.return_value = [
			frappe._dict({
				"employee": "EMP-001",
				"employee_name": "John Doe",
				"designation": "Mason",
				"amount": 200,
				"dpr_name": "DPR-LAB-1",
				"date": "2026-02-01",
				"boq_item": "BOQ-1",
			})
		]
		mock_get_all.return_value = [frappe._dict({"name": "DPR-LAB-1", "journal_entries": "JE-DPR-001"})]
		gl_atoms = [
			{
				"category": "labor",
				"amount": 200,
				"voucher_type": "Journal Entry",
				"voucher_no": "JE-DPR-001",
				"account": "Labour Expense",
				"posting_date": "2026-02-01",
			},
			{
				"category": "labor",
				"amount": 50,
				"voucher_type": "Journal Entry",
				"voucher_no": "JE-OTHER",
				"account": "Labour Expense",
				"posting_date": "2026-02-02",
			},
		]
		atoms = _build_labor_atoms("TEST-PROJ", gl_atoms)
		dpr_atoms = [a for a in atoms if a.get("source_doctype") == "Daily Progress Record"]
		je_atoms = [a for a in atoms if a.get("source_doctype") == "Journal Entry"]
		self.assertEqual(len(dpr_atoms), 1)
		self.assertEqual(len(je_atoms), 1)
		self.assertEqual(je_atoms[0]["source_document"], "JE-OTHER")
		self.assertIn("JE-DPR-001", dpr_atoms[0]["remarks"])
		self.assertEqual(flt(sum(a["amount"] for a in atoms)), 250)
