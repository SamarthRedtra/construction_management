# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
import unittest
from frappe.utils import flt, today

from construction_management.api.boq_opening_balance import (
	cancel_opening_journal_entry,
	is_opening_journal_entry,
	sync_opening_journal_entry,
)
from construction_management.api.boq_tree import get_advance_summary, get_retention_summary


class TestBOQOpeningBalance(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = self._get_test_company()
		self.cost_center = frappe.db.get_value("Company", self.company, "cost_center")
		self.customer = self._create_test_customer()
		self.project = self._create_test_project()
		self.advance_account = self._create_liability_account("BOQ Test Advance")
		self.retention_account = self._create_liability_account("BOQ Test Retention")
		self.temp_opening = self._get_temporary_opening_account()
		self._configure_boq_settings()

	def tearDown(self):
		frappe.db.rollback()

	def _get_test_company(self):
		company = frappe.db.get_value("Company", {}, "name")
		if not company:
			company = frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": "Test Company",
					"default_currency": "USD",
					"country": "United States",
				}
			).insert(ignore_permissions=True).name

		if not frappe.db.exists("Cost Center", {"company": company}):
			cc = frappe.get_doc(
				{
					"doctype": "Cost Center",
					"cost_center_name": "Main",
					"company": company,
					"is_group": 0,
				}
			).insert(ignore_permissions=True)
			frappe.db.set_value("Company", company, "cost_center", cc.name)
		elif not frappe.db.get_value("Company", company, "cost_center"):
			cc = frappe.db.get_value("Cost Center", {"company": company}, "name")
			frappe.db.set_value("Company", company, "cost_center", cc)

		return company

	def _create_test_customer(self):
		customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		if not customer_group:
			customer_group = "Commercial"

		if not frappe.db.exists("Customer", "Test Opening JE Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "Test Opening JE Customer",
					"customer_group": customer_group,
					"customer_type": "Company",
					"territory": "All Territories",
				}
			).insert(ignore_permissions=True)
		return "Test Opening JE Customer"

	def _create_test_project(self):
		project_name = "Test Opening JE Project"
		existing = frappe.db.get_value("Project", {"project_name": project_name}, "name")
		if existing:
			return existing

		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": project_name,
				"status": "Open",
				"company": self.company,
				"customer": self.customer,
				"enable_progressive_boq": 1,
			}
		)
		project.insert(ignore_permissions=True)
		return project.name

	def _create_liability_account(self, account_name):
		existing = frappe.db.get_value(
			"Account", {"account_name": account_name, "company": self.company}, "name"
		)
		if existing:
			return existing

		parent = frappe.db.get_value(
			"Account",
			{"root_type": "Liability", "company": self.company, "is_group": 1},
			"name",
		)
		return frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": account_name,
				"parent_account": parent,
				"company": self.company,
				"is_group": 0,
			}
		).insert(ignore_permissions=True).name

	def _get_temporary_opening_account(self):
		account = frappe.db.get_value(
			"Account",
			{"company": self.company, "account_name": ["like", "%Temporary Opening%"], "is_group": 0},
			"name",
		)
		if account:
			return account

		parent = frappe.db.get_value(
			"Account",
			{"root_type": "Liability", "company": self.company, "is_group": 1},
			"name",
		)
		return frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": f"Temporary Opening {frappe.generate_hash(length=5)}",
				"parent_account": parent,
				"company": self.company,
				"account_type": "Temporary",
				"is_group": 0,
			}
		).insert(ignore_permissions=True).name

	def _configure_boq_settings(self):
		if not frappe.db.exists("BOQ Settings", self.company):
			settings = frappe.new_doc("BOQ Settings")
			settings.company = self.company
		else:
			settings = frappe.get_doc("BOQ Settings", self.company)

		settings.advance_account = self.advance_account
		settings.retention_account = self.retention_account
		settings.flags.ignore_permissions = True
		settings.save()

	def _create_opening_journal_entry(self, credit_account, amount, is_opening=True):
		je = frappe.new_doc("Journal Entry")
		je.company = self.company
		je.posting_date = today()
		je.is_opening = "Yes" if is_opening else "No"
		if is_opening:
			je.voucher_type = "Opening Entry"
		je.append(
			"accounts",
			{
				"account": credit_account,
				"credit_in_account_currency": amount,
				"project": self.project,
				"cost_center": self.cost_center,
			},
		)
		je.append(
			"accounts",
			{
				"account": self.temp_opening,
				"debit_in_account_currency": amount,
				"cost_center": self.cost_center,
			},
		)
		je.insert()
		je.submit()
		return je

	def test_is_opening_journal_entry(self):
		opening = frappe._dict({"voucher_type": "Opening Entry", "is_opening": "No"})
		regular = frappe._dict({"voucher_type": "Journal Entry", "is_opening": "No"})
		flagged = frappe._dict({"voucher_type": "Journal Entry", "is_opening": "Yes"})

		self.assertTrue(is_opening_journal_entry(opening))
		self.assertFalse(is_opening_journal_entry(regular))
		self.assertTrue(is_opening_journal_entry(flagged))

	def test_opening_je_advance_creates_boq_advance_payment(self):
		amount = 5000
		je = self._create_opening_journal_entry(self.advance_account, amount)

		bap = frappe.db.get_value(
			"BOQ Advance Payment",
			{"reference": f"{je.name}::{self.project}", "docstatus": 1},
			["amount", "project"],
			as_dict=True,
		)
		self.assertIsNotNone(bap)
		self.assertEqual(flt(bap.amount), amount)
		self.assertEqual(bap.project, self.project)

		summary = get_advance_summary(self.project)
		self.assertGreaterEqual(flt(summary["total_collected"]), amount)
		self.assertGreaterEqual(flt(summary["balance"]), amount)

	def test_opening_je_retention_in_summary(self):
		amount = 2500
		self._create_opening_journal_entry(self.retention_account, amount)

		summary = get_retention_summary(self.project)
		self.assertGreaterEqual(flt(summary["opening_retained"]), amount)
		self.assertGreaterEqual(flt(summary["total_retained"]), amount)
		self.assertGreaterEqual(flt(summary["retention_balance"]), amount)

	def test_boq_invoice_retention_summary_includes_opening_je(self):
		amount = 1800
		self._create_opening_journal_entry(self.retention_account, amount)

		from construction_management.api.boq_invoice import get_retention_summary as invoice_retention_summary

		summary = invoice_retention_summary(self.project)
		self.assertGreaterEqual(flt(summary["opening_retained"]), amount)
		self.assertGreaterEqual(flt(summary["retention_balance"]), amount)

	def test_non_opening_je_does_not_sync(self):
		amount = 1500
		je = self._create_opening_journal_entry(self.advance_account, amount, is_opening=False)

		exists = frappe.db.exists(
			"BOQ Advance Payment",
			{"reference": f"{je.name}::{self.project}", "docstatus": ["!=", 2]},
		)
		self.assertFalse(exists)

	def test_cancel_opening_je_cancels_boq_advance_payment(self):
		amount = 3000
		je = self._create_opening_journal_entry(self.advance_account, amount)
		reference = f"{je.name}::{self.project}"

		self.assertTrue(
			frappe.db.exists("BOQ Advance Payment", {"reference": reference, "docstatus": 1})
		)

		je.cancel()

		self.assertFalse(
			frappe.db.exists("BOQ Advance Payment", {"reference": reference, "docstatus": 1})
		)
		self.assertTrue(
			frappe.db.exists("BOQ Advance Payment", {"reference": reference, "docstatus": 2})
		)

	def test_manual_sync_is_idempotent(self):
		amount = 1200
		je = self._create_opening_journal_entry(self.advance_account, amount)

		sync_opening_journal_entry(je)
		sync_opening_journal_entry(je)

		count = frappe.db.count(
			"BOQ Advance Payment",
			{"reference": f"{je.name}::{self.project}", "docstatus": 1},
		)
		self.assertEqual(count, 1)

		cancel_opening_journal_entry(je)
		self.assertFalse(
			frappe.db.exists(
				"BOQ Advance Payment",
				{"reference": f"{je.name}::{self.project}", "docstatus": 1},
			)
		)
