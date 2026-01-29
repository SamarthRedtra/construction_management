# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
import unittest
from frappe.utils import flt
from construction_management.api.boq_invoice import get_deduction_details, get_or_create_retention_item, get_or_create_advance_item, get_advance_balance

class TestSalesInvoiceDeductions(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.company = self._get_test_company()
        self.customer = self._create_test_customer()
        self.item = self._create_test_item()
        self.project = self._create_test_project()
        # Create deduction items
        get_or_create_retention_item()
        get_or_create_advance_item()

    def _get_test_company(self):
        company = frappe.db.get_value("Company", {}, "name")
        if not company:
            doc = frappe.get_doc({
                "doctype": "Company",
                "company_name": "Test Company",
                "default_currency": "USD"
            }).insert(ignore_permissions=True)
            company = doc.name
        return company

    def tearDown(self):
        frappe.db.rollback()

    def _create_test_item(self):
        if not frappe.db.exists("Item", "ITEM-1"):
            item = frappe.new_doc("Item")
            item.item_code = "ITEM-1"
            item.item_name = "Test Item"
            item.item_group = "All Item Groups"
            item.stock_uom = "Nos"
            item.is_stock_item = 0
            item.insert(ignore_permissions=True)
        return "ITEM-1"

    def _create_test_customer(self):
        customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": "Test Customer",
            "customer_group": "All Customer Groups",
            "customer_type": "Company",
            "territory": "All Territories"
        })
        if not frappe.db.exists("Customer", "Test Customer"):
            customer.insert(ignore_permissions=True)
        return "Test Customer"

    def _create_test_project(self):
        project = frappe.get_doc({
            "doctype": "Project",
            "project_name": "Test Deduction Project",
            "status": "Open",
            "retention_percentage": 10.0
        })
        project.insert(ignore_permissions=True)
        return project.name

    def _create_advance_payment(self, amount):
        adv = frappe.new_doc("BOQ Advance Payment")
        adv.project = self.project
        adv.amount = amount
        adv.date = frappe.utils.today()
        adv.insert(ignore_permissions=True)
        adv.submit()
        return adv.name

    def test_get_deduction_details(self):
        # Create advance of 1000
        self._create_advance_payment(1000)
        
        items = [
            {"amount": 5000, "item_code": "ITEM-1"},
            {"amount": 3000, "item_code": "ITEM-2"}
        ]
        
        details = get_deduction_details(self.project, items)
        
        self.assertEqual(details["retention_percentage"], 10.0)
        self.assertEqual(details["available_advance"], 1000.0)
        self.assertEqual(details["total_billable_amount"], 8000.0)
        self.assertEqual(details["suggested_retention"], 800.0)
        self.assertTrue("enable_progressive_boq" in details)

    def test_advance_balance_after_deduction(self):
        self._create_advance_payment(1000)
        
        # Create a submitted invoice with deduction and a positive item
        inv = frappe.new_doc("Sales Invoice")
        inv.customer = self.customer
        inv.project = self.project
        inv.company = self.company
        inv.posting_date = frappe.utils.today()
        inv.append("items", {
            "item_code": "ITEM-1",
            "qty": 1,
            "rate": 1000,
            "amount": 1000
        })
        inv.append("items", {
            "item_code": "ADVANCE-DEDUCTION",
            "qty": 1,
            "rate": -400,
            "amount": -400
        })
        inv.insert(ignore_permissions=True)
        inv.submit()
        
        # Check available advance
        details = get_deduction_details(self.project, [])
        self.assertEqual(details["available_advance"], 600.0)

    def test_server_side_automatic_deductions(self):
        # Enable progressive boq for project and set cap
        frappe.db.set_value("Project", self.project, {
            "enable_progressive_boq": 1,
            "retention_percentage": 10.0,
            "advance_deduction": 5.0  # 5% cap
        })
        
        # Create advance of 2000
        self._create_advance_payment(2000)
        
        # Create invoice with 10000
        inv = frappe.new_doc("Sales Invoice")
        inv.customer = self.customer
        inv.project = self.project
        inv.company = self.company
        inv.posting_date = frappe.utils.today()
        inv.append("items", {
            "item_code": self.item,
            "qty": 1,
            "rate": 10000,
            "amount": 10000
        })
        
        # This should trigger 'apply_automatic_deductions' via 'validate' hook
        inv.insert(ignore_permissions=True)
        
        # Verify retention deduction (10% of 10000 = 1000)
        retention_row = next((i for i in inv.items if i.item_code == "RETENTION-DEDUCTION"), None)
        self.assertIsNotNone(retention_row)
        self.assertEqual(flt(retention_row.amount), -1000.0)
        
        # Verify advance deduction (capped at 5% of 10000 = 500)
        advance_row = next((i for i in inv.items if i.item_code == "ADVANCE-DEDUCTION"), None)
        self.assertIsNotNone(advance_row)
        self.assertEqual(flt(advance_row.amount), -500.0)

    def test_advance_balance_with_drafts(self):
        # Create advance of 1000
        self._create_advance_payment(1000)
        
        # Draft 1: Total 1000, Deduct 400
        inv1 = frappe.new_doc("Sales Invoice")
        inv1.customer = self.customer
        inv1.project = self.project
        inv1.company = self.company
        inv1.append("items", {
            "item_code": self.item,
            "qty": 1,
            "rate": 1000,
            "amount": 1000
        })
        inv1.append("items", {
            "item_code": "ADVANCE-DEDUCTION",
            "qty": 1,
            "rate": -400,
            "amount": -400
        })
        inv1.insert(ignore_permissions=True)
        
        # Balance should be 600 even if Draft
        self.assertEqual(get_advance_balance(self.project), 600.0)
        
        # When creating Draft 2, it should exclude Draft 1 only if it's the current doc (not relevant here yet)
        # But get_deduction_details for inv1 should show 1000 available (excluding itself)
        details = get_deduction_details(self.project, [], invoice_name=inv1.name)
        self.assertEqual(details["available_advance"], 1000.0)

def run_tests():
    unittest.main()
