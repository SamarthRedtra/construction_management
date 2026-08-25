# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from construction_management.api.advance_release import prepare_advance_release_sales_invoice
from construction_management.api.boq_invoice import get_advance_balance
from construction_management.patches.add_advance_release_sales_invoice_field import execute as add_release_field


class TestAdvanceReleaseSalesInvoice(IntegrationTestCase):
	def setUp(self):
		add_release_field()
		frappe.set_user("Administrator")
		if not frappe.db.exists("Item Group", "Services"):
			parent = frappe.db.get_value("Item Group", {"is_group": 1}, "name") or "All Item Groups"
			frappe.get_doc(
				{"doctype": "Item Group", "item_group_name": "Services", "parent_item_group": parent}
			).insert(ignore_permissions=True)
		self.company = frappe.db.get_value("Company", {}, "name")
		self._ensure_company_accounts()
		self.customer = self._create_customer()
		self.project = self._create_project()
		self.pool_amount = 1800
		self._ensure_advance_pool(self.pool_amount)

	def _ensure_company_accounts(self):
		if not frappe.db.get_value("Company", self.company, "default_income_account"):
			income = frappe.db.get_value(
				"Account",
				{"company": self.company, "root_type": "Income", "is_group": 0},
				"name",
			)
			frappe.db.set_value("Company", self.company, "default_income_account", income)
		if not frappe.db.get_value("Company", self.company, "cost_center"):
			cc = frappe.db.get_value("Cost Center", {"company": self.company, "is_group": 0}, "name")
			frappe.db.set_value("Company", self.company, "cost_center", cc)

		parent_liability = frappe.db.get_value(
			"Account", {"company": self.company, "root_type": "Liability", "is_group": 1}, "name"
		)
		advance_account = frappe.db.get_value("BOQ Settings", self.company, "advance_account")
		if not advance_account:
			advance_account = frappe.get_doc(
				{
					"doctype": "Account",
					"account_name": f"Test Adv Rel {frappe.generate_hash(length=5)}",
					"parent_account": parent_liability,
					"company": self.company,
					"is_group": 0,
				}
			).insert(ignore_permissions=True).name
			if frappe.db.exists("BOQ Settings", self.company):
				frappe.db.set_value("BOQ Settings", self.company, "advance_account", advance_account)
			else:
				frappe.get_doc(
					{
						"doctype": "BOQ Settings",
						"company": self.company,
						"advance_account": advance_account,
					}
				).insert(ignore_permissions=True)
		self.advance_account = frappe.db.get_value("BOQ Settings", self.company, "advance_account")
		self.income_account = frappe.db.get_value("Company", self.company, "default_income_account")

	def _create_customer(self):
		customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
		name = f"Adv Rel Cust {frappe.generate_hash(length=6)}"
		return frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_type": "Company",
				"customer_group": customer_group,
				"territory": territory,
			}
		).insert(ignore_permissions=True).name

	def _create_project(self):
		return frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"ADV-REL-{frappe.generate_hash(length=6)}",
				"status": "Open",
				"company": self.company,
				"customer": self.customer,
				"enable_progressive_boq": 1,
			}
		).insert(ignore_permissions=True).name

	def _ensure_advance_pool(self, amount):
		adv = frappe.new_doc("BOQ Advance Payment")
		adv.project = self.project
		adv.amount = amount
		adv.date = today()
		adv.insert(ignore_permissions=True)
		adv.submit()

	def _create_item(self):
		if not frappe.db.exists("Item", "ITEM-1"):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": "ITEM-1",
					"item_name": "Test Item",
					"item_group": "All Item Groups",
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)
		return "ITEM-1"

	def test_skip_deduction_progress_invoice_leaves_pool(self):
		self.assertEqual(flt(get_advance_balance(self.project)), flt(self.pool_amount))
		inv = frappe.new_doc("Sales Invoice")
		inv.customer = self.customer
		inv.project = self.project
		inv.company = self.company
		inv.posting_date = today()
		inv.custom_skip_advance_deduction = 1
		inv.append(
			"items",
			{"item_code": self._create_item(), "qty": 1, "rate": 500, "amount": 500},
		)
		inv.insert(ignore_permissions=True)
		inv.submit()
		self.assertFalse(any(row.item_code == "ADVANCE-DEDUCTION" for row in inv.items))
		self.assertEqual(flt(get_advance_balance(self.project)), flt(self.pool_amount))

	def test_release_invoice_clears_pool_and_posts_gl(self):
		self.assertEqual(flt(get_advance_balance(self.project)), flt(self.pool_amount))
		result = prepare_advance_release_sales_invoice(self.project)
		self.assertTrue(result.get("invoice_name"))
		self.assertEqual(flt(result.get("amount")), flt(self.pool_amount))

		inv = frappe.get_doc("Sales Invoice", result["invoice_name"])
		self.assertTrue(inv.custom_is_advance_release)
		self.assertFalse(inv.custom_is_advanced)
		inv.submit()

		self.assertEqual(flt(inv.outstanding_amount), 0)
		self.assertEqual(flt(get_advance_balance(self.project)), 0)

		gl_entries = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": inv.name, "is_cancelled": 0},
			fields=["account", "debit", "credit"],
		)
		advance_debit = sum(flt(row.debit) for row in gl_entries if row.account == self.advance_account)
		income_credit = sum(flt(row.credit) for row in gl_entries if row.account == self.income_account)
		self.assertEqual(flt(advance_debit), flt(self.pool_amount))
		self.assertEqual(flt(income_credit), flt(self.pool_amount))

	def test_cannot_combine_advance_and_release_flags(self):
		inv = frappe.new_doc("Sales Invoice")
		inv.customer = self.customer
		inv.project = self.project
		inv.company = self.company
		inv.custom_is_advanced = 1
		inv.custom_is_advance_release = 1
		inv.append(
			"items",
			{"item_code": self._create_item(), "qty": 1, "rate": 100, "amount": 100},
		)
		self.assertRaises(frappe.ValidationError, inv.insert)
