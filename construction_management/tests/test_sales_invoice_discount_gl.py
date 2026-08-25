# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from construction_management.api.boq_invoice import get_or_create_retention_item
from construction_management.overrides.sales_invoice import SalesInvoiceOverride


class TestSalesInvoiceDiscountGL(IntegrationTestCase):
	"""Additional discount must settle to Sales and keep debit == credit after BOQ remap."""

	DISCOUNT = 200

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Selling Settings", "enable_discount_accounting", 0)
		if not frappe.db.exists("Item Group", "Services"):
			parent = frappe.db.get_value("Item Group", {"is_group": 1}, "name") or "All Item Groups"
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": "Services",
					"parent_item_group": parent,
				}
			).insert(ignore_permissions=True)
		self.company = frappe.db.get_value("Company", {}, "name")
		self._ensure_company_accounts()
		self.income_account = frappe.db.get_value("Company", self.company, "default_income_account")
		self.cost_center = frappe.db.get_value("Company", self.company, "cost_center")
		self.customer = self._create_customer()
		self.project = self._create_project()
		self.item = self._ensure_item()
		self.retention_item = get_or_create_retention_item()
		self.boq_item = self._create_boq_item()
		self.retention_account = self._ensure_retention_account()
		self.unbilled_account = self._ensure_unbilled_accounts()

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
		if not frappe.db.get_value("Company", self.company, "default_receivable_account"):
			recv = frappe.db.get_value(
				"Account",
				{"company": self.company, "account_type": "Receivable", "is_group": 0},
				"name",
			)
			if recv:
				frappe.db.set_value("Company", self.company, "default_receivable_account", recv)

	def _leaf_account(self, root_type, account_name):
		existing = frappe.db.get_value(
			"Account",
			{"account_name": account_name, "company": self.company, "is_group": 0},
			"name",
		)
		if existing:
			return existing
		parent = frappe.db.get_value(
			"Account",
			{"company": self.company, "root_type": root_type, "is_group": 1},
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

	def _ensure_retention_account(self):
		account = self._leaf_account("Asset", f"Test Disc Ret {frappe.generate_hash(length=5)}")
		if not frappe.db.exists("BOQ Settings", self.company):
			frappe.get_doc(
				{
					"doctype": "BOQ Settings",
					"company": self.company,
					"retention_account": account,
				}
			).insert(ignore_permissions=True)
		else:
			frappe.db.set_value("BOQ Settings", self.company, "retention_account", account)
		return account

	def _ensure_unbilled_accounts(self):
		debit = self._leaf_account("Asset", f"Test Unbilled Dr {frappe.generate_hash(length=5)}")
		credit = self._leaf_account("Liability", f"Test Unbilled Cr {frappe.generate_hash(length=5)}")
		frappe.db.set_value(
			"BOQ Settings",
			self.company,
			{
				"enable_so_unearned_revenue_jv": 1,
				"so_unearned_revenue_debit_account": debit,
				"so_unearned_revenue_credit_account": credit,
			},
		)
		return debit

	def _create_customer(self):
		customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
		name = f"Disc GL Cust {frappe.generate_hash(length=6)}"
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
				"project_name": f"Disc GL Proj {frappe.generate_hash(length=6)}",
				"status": "Open",
				"company": self.company,
				"customer": self.customer,
				"retention_percentage": 0,
			}
		).insert(ignore_permissions=True).name

	def _ensure_item(self):
		code = "ITEM-DISC-GL"
		if not frappe.db.exists("Item", code):
			group = "Services" if frappe.db.exists("Item Group", "Services") else "All Item Groups"
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": "Discount GL Item",
					"item_group": group,
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"is_sales_item": 1,
				}
			).insert(ignore_permissions=True)
		return code

	def _create_boq_item(self):
		pboq = frappe.get_doc(
			{
				"doctype": "Project BOQ",
				"boq_name": f"Disc GL BOQ {frappe.generate_hash(length=4)}",
				"project": self.project,
			}
		).insert(ignore_permissions=True)
		bill = frappe.get_doc(
			{
				"doctype": "BOQ Bill",
				"bill_no": f"BD-{frappe.generate_hash(length=4)}",
				"project": self.project,
				"project_boq": pboq.name,
			}
		).insert(ignore_permissions=True)
		boq_item = frappe.get_doc(
			{
				"doctype": "BOQ Item",
				"item_code": self.item,
				"boq_item_name": "BOQ-DISC-GL",
				"rate": 10000,
				"total_qty": 10,
				"project": self.project,
				"parent_bill": bill.name,
				"unit": "Nos",
				"description": "Discount GL BOQ item",
			}
		).insert(ignore_permissions=True)
		return boq_item.name

	def _make_invoice(self, discount=0, sales_order=None):
		inv = frappe.new_doc("Sales Invoice")
		inv.customer = self.customer
		inv.project = self.project
		inv.company = self.company
		inv.posting_date = today()
		inv.debit_to = frappe.db.get_value("Company", self.company, "default_receivable_account")
		inv.apply_discount_on = "Net Total"
		if discount:
			inv.discount_amount = discount
		inv.append(
			"items",
			{
				"item_code": self.item,
				"qty": 1,
				"rate": 10000,
				"amount": 10000,
				"boq_item": self.boq_item,
				"income_account": self.income_account,
				"cost_center": self.cost_center,
				"project": self.project,
			},
		)
		inv.append(
			"items",
			{
				"item_code": self.retention_item,
				"qty": 1,
				"rate": -1000,
				"amount": -1000,
				"boq_item": self.boq_item,
				"income_account": self.income_account,
				"cost_center": self.cost_center,
				"project": self.project,
			},
		)
		inv.flags.ignore_deduction_recalc = 1
		inv.insert(ignore_permissions=True)
		if sales_order:
			for row in inv.items:
				frappe.db.set_value(
					"Sales Invoice Item",
					row.name,
					"sales_order",
					sales_order,
					update_modified=False,
				)
			inv.reload()
		return inv

	def _gl(self, inv):
		orig = frappe.db.get_single_value

		def patched(dt, fn, *a, **k):
			if dt == "Accounts Settings" and fn == "book_stock_expense_gl_entries":
				return 0
			return orig(dt, fn, *a, **k)

		frappe.db.get_single_value = patched
		try:
			return SalesInvoiceOverride.get_gl_entries(inv) or []
		finally:
			frappe.db.get_single_value = orig

	def _assert_balanced(self, gl):
		debit = sum(flt(e.get("debit")) for e in gl)
		credit = sum(flt(e.get("credit")) for e in gl)
		self.assertAlmostEqual(debit, credit, places=2)

	def _net_sales(self, gl):
		credit = sum(flt(e.get("credit")) for e in gl if e.get("account") == self.income_account)
		debit = sum(flt(e.get("debit")) for e in gl if e.get("account") == self.income_account)
		return flt(credit - debit, 2)

	def test_discount_with_retention_balances_and_reduces_sales(self):
		plain = self._make_invoice(discount=0)
		discounted = self._make_invoice(discount=self.DISCOUNT)

		plain_gl = self._gl(plain)
		disc_gl = self._gl(discounted)

		self._assert_balanced(plain_gl)
		self._assert_balanced(disc_gl)
		self.assertAlmostEqual(
			self._net_sales(disc_gl),
			flt(self._net_sales(plain_gl) - self.DISCOUNT, 2),
			places=2,
		)

	@patch("construction_management.overrides.sales_invoice.find_journal_entry_by_so", return_value="JV-DISC-GL")
	@patch(
		"construction_management.overrides.sales_invoice.get_remaining_so_unbilled_balance",
		return_value=5000,
	)
	def test_discount_with_unearned_balances_and_reduces_sales(self, _mock_remaining, _mock_je):
		so_name = f"SAL-ORD-DISC-{frappe.generate_hash(length=4)}"
		plain = self._make_invoice(discount=0, sales_order=so_name)
		discounted = self._make_invoice(discount=self.DISCOUNT, sales_order=so_name)

		plain_gl = self._gl(plain)
		disc_gl = self._gl(discounted)

		self._assert_balanced(plain_gl)
		self._assert_balanced(disc_gl)
		self.assertAlmostEqual(
			self._net_sales(disc_gl),
			flt(self._net_sales(plain_gl) - self.DISCOUNT, 2),
			places=2,
		)
		unbilled = sum(
			flt(e.get("credit")) for e in disc_gl if e.get("account") == self.unbilled_account
		)
		self.assertGreater(unbilled, 0)
