# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
import unittest
from frappe.utils import flt

class TestPurchaseReceiptExtraEntries(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = self._get_test_company()
		self.supplier = self._get_test_supplier()
		self.cost_center = frappe.db.get_value("Company", self.company, "cost_center")
		self.expense_account, self.liability_account = self._create_test_accounts()

	def test_extra_entry_party_propagates_to_gl_dict(self):
		doc = self._make_pr_with_extra_entries()
		gl_entries = doc._append_extra_accounting_entries([])

		self.assertEqual(len(gl_entries), 2)

		debit_entry = next(e for e in gl_entries if flt(e.debit) > 0)
		credit_entry = next(e for e in gl_entries if flt(e.credit) > 0)

		for entry in (debit_entry, credit_entry):
			self.assertEqual(entry.party_type, "Supplier")
			self.assertEqual(entry.party, self.supplier)
			self.assertEqual(entry.against, self.supplier)
			self.assertTrue((entry.remarks or "").startswith("Extra entry from Purchase Receipt"))

	def test_gl_entry_override_allows_party_on_expense_extra_entry(self):
		doc = self._make_pr_with_extra_entries()
		gl_entries = doc._append_extra_accounting_entries([])
		debit_entry = next(e for e in gl_entries if flt(e.debit) > 0)

		gle = frappe.get_doc({"doctype": "GL Entry", **debit_entry})
		gle.validate_party()

		self.assertEqual(gle.party_type, "Supplier")
		self.assertEqual(gle.party, self.supplier)

	def _make_pr_with_extra_entries(self):
		doc = frappe.get_doc(
			{
				"doctype": "Purchase Receipt",
				"company": self.company,
				"supplier": self.supplier,
				"posting_date": frappe.utils.today(),
				"cost_center": self.cost_center,
				"currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"conversion_rate": 1,
				"name": "TEST-PR-EXTRA-ENTRY",
				"custom_extra_accounting_entries": [
					{
						"account": self.expense_account,
						"debit": 100,
						"credit": 0,
						"party_type": "Supplier",
						"party": self.supplier,
					},
					{
						"account": self.liability_account,
						"debit": 0,
						"credit": 100,
						"party_type": "Supplier",
						"party": self.supplier,
					},
				],
			}
		)
		return doc

	def _get_test_company(self):
		company = frappe.db.get_value("Company", {}, "name")
		if not company:
			company = frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": "Test PR Extra Entry Co",
					"abbr": "TPEC",
					"default_currency": "USD",
					"country": "United States",
				}
			).insert(ignore_permissions=True).name

		if not frappe.db.get_value("Company", company, "cost_center"):
			cc = frappe.get_doc(
				{
					"doctype": "Cost Center",
					"cost_center_name": "Main",
					"company": company,
					"is_group": 0,
				}
			).insert(ignore_permissions=True)
			frappe.db.set_value("Company", company, "cost_center", cc.name)

		return company

	def _get_test_supplier(self):
		supplier = frappe.db.get_value("Supplier", {"disabled": 0}, "name")
		if supplier:
			return supplier

		return frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": "Test PR Extra Entry Supplier",
				"supplier_group": frappe.db.get_value("Supplier Group", {}, "name") or "All Supplier Groups",
			}
		).insert(ignore_permissions=True).name

	def _create_test_accounts(self):
		suffix = frappe.generate_hash(length=6)
		expense_parent = frappe.db.get_value(
			"Account", {"root_type": "Expense", "company": self.company, "is_group": 1}, "name"
		)
		liability_parent = frappe.db.get_value(
			"Account", {"root_type": "Liability", "company": self.company, "is_group": 1}, "name"
		)

		expense_account = frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": f"Test Subcon Expense {suffix}",
				"parent_account": expense_parent,
				"company": self.company,
				"account_type": "Direct Expense",
				"is_group": 0,
			}
		).insert(ignore_permissions=True).name

		liability_account = frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": f"Test Accrued Subcon {suffix}",
				"parent_account": liability_parent,
				"company": self.company,
				"is_group": 0,
			}
		).insert(ignore_permissions=True).name

		return expense_account, liability_account
