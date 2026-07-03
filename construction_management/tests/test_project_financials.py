# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
import unittest
from frappe.utils import flt

from construction_management.api.boq_tree import get_advance_breakdown, get_retention_breakdown
from construction_management.api.project_financials import get_project_journal_entries
from construction_management.construction_management.doctype.boq_item.boq_item import get_rate_split_summary


class TestProjectFinancials(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = frappe.db.get_value("Company", {}, "name")
		if not self.company:
			self.skipTest("No company available")

	def tearDown(self):
		frappe.db.rollback()

	def test_project_journal_entries_api_shape(self):
		project = frappe.db.get_value("Project", {"company": self.company}, "name")
		if not project:
			self.skipTest("No project available")

		result = get_project_journal_entries(project)
		self.assertIn("summary", result)
		self.assertIn("rows", result)
		self.assertIn("journal_entries", result)
		self.assertIn("count", result["summary"])

	def test_advance_breakdown_api_shape(self):
		project = frappe.db.get_value("Project", {"company": self.company}, "name")
		if not project:
			self.skipTest("No project available")

		result = get_advance_breakdown(project)
		self.assertIn("rows", result)
		self.assertIn("total_collected", result)
		self.assertIn("balance", result)

	def test_retention_breakdown_api_shape(self):
		project = frappe.db.get_value("Project", {"company": self.company}, "name")
		if not project:
			self.skipTest("No project available")

		result = get_retention_breakdown(project)
		self.assertIn("rows", result)
		self.assertIn("retention_balance", result)
		self.assertIn("opening_retained", result)

	def test_rate_split_summary_shape(self):
		boq_item = frappe.db.get_value("BOQ Item", {}, "name")
		if not boq_item:
			self.skipTest("No BOQ item available")

		result = get_rate_split_summary(boq_item)
		for key in (
			"prev_qty",
			"prev_amount",
			"prev_effective_rate",
			"balance_qty",
			"current_rate",
			"balance_value",
			"total_amount",
			"rate_history",
		):
			self.assertIn(key, result)
		self.assertEqual(
			flt(result["total_amount"]),
			flt(result["prev_amount"]) + flt(result["balance_value"]),
		)
