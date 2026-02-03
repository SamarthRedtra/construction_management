# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today
from construction_management.api.boq_invoice import create_sales_order_from_selected_items


class TestSalesOrderTaxes(FrappeTestCase):
	def setUp(self):
		self.project = self.create_test_project("TAX-TEST-PROJECT")
		self.customer = frappe.db.get_value("Project", self.project, "customer")
		self.company = frappe.db.get_value("Project", self.project, "company")
		
		# Create a tax template if it doesn't exist
		self.tax_template = self.create_test_tax_template()
		
		# Create BOQ Item
		self.boq_item = self.create_test_boq_item()

	def create_test_project(self, name):
		if frappe.db.exists("Project", name):
			return name
		
		# Ensure a test customer exists
		if not frappe.db.exists("Customer", "Test Customer"):
			customer = frappe.new_doc("Customer")
			customer.customer_name = "Test Customer"
			customer.insert(ignore_permissions=True)
		
		project = frappe.new_doc("Project")
		project.project_name = name
		project.customer = "Test Customer"
		project.company = frappe.defaults.get_user_default("Company") or "Test Company"
		project.insert(ignore_permissions=True)
		return project.name

	def create_test_tax_template(self):
		template_name = "Test Sales Tax Template"
		if frappe.db.exists("Sales Taxes and Charges Template", template_name):
			return template_name
		
		# Ensure tax account exists
		tax_account = frappe.db.get_value("Account", {"account_type": "Tax", "company": self.company})
		if not tax_account:
			# Fallback to any account if tax account not found (just for test)
			tax_account = frappe.db.get_value("Account", {"company": self.company, "is_group": 0})

		template = frappe.new_doc("Sales Taxes and Charges Template")
		template.title = template_name
		template.company = self.company
		template.append("taxes", {
			"charge_type": "On Net Total",
			"account_head": tax_account,
			"description": "VAT 15%",
			"rate": 15.0
		})
		template.is_default = 1
		template.insert(ignore_permissions=True)
		return template_name

	def create_test_boq_item(self):
		# Create Project BOQ and Bill first
		boq = frappe.new_doc("Project BOQ")
		boq.project = self.project
		boq.boq_name = f"BOQ-{self.project}"
		boq.insert(ignore_permissions=True)
		
		bill = frappe.new_doc("BOQ Bill")
		bill.project = self.project
		bill.project_boq = boq.name
		bill.bill_no = "BILL-001"
		bill.insert(ignore_permissions=True)
		
		item = frappe.new_doc("BOQ Item")
		item.parent_bill = bill.name
		item.project = self.project
		item.description = "Tax Test Item"
		item.rate = 1000
		item.total_qty = 10
		item.insert(ignore_permissions=True)
		return item.name

	def test_sales_order_tax_population(self):
		"""Test that taxes are populated when creating SO from BOQ"""
		items = [{"boq_item": self.boq_item, "qty": 1, "percentage": 10}]
		
		result = create_sales_order_from_selected_items(
			project=self.project,
			items=items,
			auto_submit=0
		)
		
		self.assertEqual(result.get("status"), "success")
		so_name = result.get("name")
		
		so = frappe.get_doc("Sales Order", so_name)
		
		# Check if taxes are populated
		self.assertGreater(len(so.taxes), 0, "Taxes should be populated on the Sales Order")
		self.assertEqual(so.taxes_and_charges, self.tax_template)
		
		# Check if calculation is correct
		# 1000 (rate) * 1 (qty) = 1000 net total
		# 15% tax = 150
		# Grand total = 1150
		self.assertEqual(flt(so.net_total), 1000)
		self.assertEqual(flt(so.total_taxes_and_charges), 150)
		self.assertEqual(flt(so.grand_total), 1150)
		
		# Cleanup
		so.delete()
