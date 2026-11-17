# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from construction_management.api.boq_invoice import (
	create_sales_order_from_selected_items,
	recalculate_sales_order_boq_deductions,
)
from construction_management.patches.add_sales_invoice_skip_retention_field import (
	execute as add_skip_retention_field,
)
from construction_management.patches.add_sales_order_skip_retention_field import (
	execute as add_so_skip_retention_field,
)


class TestSalesSkipRetentionDeduction(IntegrationTestCase):
	def setUp(self):
		add_skip_retention_field()
		add_so_skip_retention_field()
		frappe.set_user("Administrator")
		self.company = frappe.db.get_value("Company", {}, "name")
		self._ensure_company_accounts()
		self.customer = self._create_customer()
		self.item = self._ensure_item()
		self.project = self._create_project()
		self._ensure_boq_line()

	def _ensure_company_accounts(self):
		if not frappe.db.get_value("Company", self.company, "default_income_account"):
			income = frappe.db.get_value(
				"Account",
				{"company": self.company, "root_type": "Income", "is_group": 0},
				"name",
			)
			frappe.db.set_value("Company", self.company, "default_income_account", income)

	def _create_customer(self):
		name = f"Skip Ret Cust {frappe.generate_hash(length=6)}"
		return frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_type": "Company",
				"customer_group": frappe.db.get_value(
					"Customer Group", {"is_group": 0}, "name"
				),
				"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
			}
		).insert(ignore_permissions=True).name

	def _ensure_item(self):
		code = "SKIP-RET-ITEM"
		if not frappe.db.exists("Item", code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": code,
					"item_group": "All Item Groups",
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)
		return code

	def _create_project(self):
		return frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"SKIP-RET-{frappe.generate_hash(length=6)}",
				"status": "Open",
				"company": self.company,
				"customer": self.customer,
				"enable_progressive_boq": 1,
				"retention_percentage": 10,
			}
		).insert(ignore_permissions=True).name

	def _ensure_boq_line(self):
		project_boq = frappe.get_doc(
			{
				"doctype": "Project BOQ",
				"project": self.project,
				"boq_name": f"Skip Ret BOQ {frappe.generate_hash(length=4)}",
				"status": "Draft",
			}
		).insert(ignore_permissions=True)
		bill_no = f"BILL-{frappe.generate_hash(length=5)}"
		bill = frappe.get_doc(
			{
				"doctype": "BOQ Bill",
				"bill_no": bill_no,
				"label": "Skip retention test bill",
				"project": self.project,
				"project_boq": project_boq.name,
			}
		).insert(ignore_permissions=True)
		boq_item = frappe.get_doc(
			{
				"doctype": "BOQ Item",
				"item_code": self.item,
				"project": self.project,
				"project_boq": project_boq.name,
				"parent_bill": bill.name,
				"description": "Skip retention test line",
				"unit": "Nos",
				"total_qty": 1,
				"rate": 10000,
				"amount": 10000,
			}
		).insert(ignore_permissions=True)
		self.boq_item = boq_item.name

	def _new_progress_invoice(self, *, skip_retention: bool):
		inv = frappe.new_doc("Sales Invoice")
		inv.customer = self.customer
		inv.project = self.project
		inv.company = self.company
		inv.posting_date = today()
		inv.custom_skip_retention_deduction = 1 if skip_retention else 0
		inv.custom_skip_advance_deduction = 1
		inv.append(
			"items",
			{
				"item_code": self.item,
				"qty": 1,
				"rate": 10000,
				"amount": 10000,
				"boq_item": self.boq_item,
			},
		)
		return inv

	def test_without_skip_applies_retention(self):
		inv = self._new_progress_invoice(skip_retention=False)
		inv.insert(ignore_permissions=True)
		retention_rows = [row for row in inv.items if row.item_code == "RETENTION-DEDUCTION"]
		self.assertTrue(retention_rows)
		self.assertEqual(flt(retention_rows[0].amount), -1000.0)

	def test_skip_retention_omits_retention_rows(self):
		inv = self._new_progress_invoice(skip_retention=True)
		inv.insert(ignore_permissions=True)
		self.assertFalse(any(row.item_code == "RETENTION-DEDUCTION" for row in inv.items))

	def _create_draft_sales_order(self, *, skip_retention: bool):
		result = create_sales_order_from_selected_items(
			project=self.project,
			items=[{"boq_item": self.boq_item, "qty": 1}],
			auto_submit=0,
		)
		self.assertEqual(result.get("status"), "success")
		so = frappe.get_doc("Sales Order", result["name"])
		so.custom_skip_retention_deduction = 1 if skip_retention else 0
		so.custom_skip_advance_deduction = 1
		so.save(ignore_permissions=True)
		recalculate_sales_order_boq_deductions(so.name)
		return frappe.get_doc("Sales Order", so.name)

	def test_sales_order_without_skip_applies_retention(self):
		so = self._create_draft_sales_order(skip_retention=False)
		retention_rows = [row for row in so.items if row.item_code == "RETENTION-DEDUCTION"]
		self.assertTrue(retention_rows)
		self.assertEqual(flt(retention_rows[0].amount), -1000.0)

	def test_sales_order_skip_retention_omits_rows(self):
		so = self._create_draft_sales_order(skip_retention=True)
		self.assertFalse(any(row.item_code == "RETENTION-DEDUCTION" for row in so.items))
		self.assertEqual(flt(so.custom_retention_amount), 0)