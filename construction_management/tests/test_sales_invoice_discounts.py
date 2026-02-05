# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
import unittest
from frappe.utils import flt
from construction_management.overrides.sales_invoice import SalesInvoiceOverride

class TestSalesInvoiceDiscounts(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.company = self._get_test_company()
        self.customer = self._create_test_customer()
        self.item = self._create_test_item()
        self.project = self._create_test_project()
        
        # Ensure variance item and account exist
        if not frappe.db.exists("Item", "VARIANCE-ITEM"):
            frappe.get_doc({
                "doctype": "Item",
                "item_code": "VARIANCE-ITEM",
                "item_name": "Variance Item",
                "item_group": "Services",
                "stock_uom": "Nos",
                "is_stock_item": 0
            }).insert(ignore_permissions=True)
        
        parent_expense = frappe.db.get_value("Account", {"root_type": "Expense", "company": self.company, "is_group": 1})
        self.dummy_variance_account = frappe.get_doc({
            "doctype": "Account",
            "account_name": f"Dummy Variance {frappe.generate_hash(length=5)}",
            "parent_account": parent_expense,
            "company": self.company,
            "account_type": "Expense Account",
            "is_group": 0
        }).insert(ignore_permissions=True).name

        if not frappe.db.exists("BOQ Settings", self.company):
            frappe.get_doc({
                "doctype": "BOQ Settings",
                "name": self.company,
                "company": self.company,
                "varience_item": "VARIANCE-ITEM",
                "varience_account_debit": self.dummy_variance_account
            }).insert(ignore_permissions=True)

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
        customer_name = "Test Discount Customer"
        if not frappe.db.exists("Customer", customer_name):
            frappe.get_doc({
                "doctype": "Customer",
                "customer_name": customer_name,
                "customer_group": "All Customer Groups",
                "customer_type": "Company",
                "territory": "All Territories"
            }).insert(ignore_permissions=True)
        return customer_name

    def _create_test_project(self):
        project_name = "Test Discount Project"
        existing = frappe.db.get_value("Project", {"project_name": project_name}, "name")
        if existing:
            return existing
            
        project = frappe.get_doc({
            "doctype": "Project",
            "project_name": project_name,
            "status": "Open",
            "retention_percentage": 0,
            "customer": self.customer
        })
        project.insert(ignore_permissions=True)
        return project.name

    def test_discount_on_net_total(self):
        # Create BOQ structure
        pboq = frappe.get_doc({
            "doctype": "Project BOQ",
            "boq_name": "Test Discount BOQ",
            "project": self.project,
            "company": self.company
        }).insert(ignore_permissions=True)

        bill = frappe.get_doc({
            "doctype": "BOQ Bill",
            "bill_no": "BD-001",
            "project": self.project,
            "project_boq": pboq.name,
            "company": self.company
        }).insert(ignore_permissions=True)

        boq_item = frappe.get_doc({
            "doctype": "BOQ Item",
            "item_code": self.item,
            "boq_item_name": "BOQ-D-1",
            "rate": 1000,
            "total_qty": 10,
            "project": self.project,
            "parent_bill": bill.name,
            "unit": "Nos",
            "description": "Test Discount Item Description"
        }).insert(ignore_permissions=True)

        # Create Invoice
        inv = frappe.new_doc("Sales Invoice")
        inv.customer = self.customer
        inv.project = self.project
        inv.company = self.company
        inv.posting_date = frappe.utils.today()
        inv.apply_discount_on = "Net Total"
        inv.discount_amount = 100
        
        inv.append("items", {
            "item_code": self.item,
            "qty": 1,
            "rate": 1000,
            "amount": 1000,
            "boq_item": boq_item.name
        })

        inv.insert(ignore_permissions=True)
        inv.submit()

        # Verify Ledger Entry
        # Gross 1000, Discount 100, Net 900
        entry = frappe.db.get_value("BOQ Progress Ledger", 
                                      {"tax_invoice": inv.name, "boq_item": boq_item.name}, 
                                      ["amount"], as_dict=True)
        self.assertIsNotNone(entry)
        self.assertEqual(flt(entry.amount), 900.0)

    def test_discount_on_grand_total(self):
        # Create BOQ structure
        pboq = frappe.get_doc({
            "doctype": "Project BOQ",
            "boq_name": "Test Discount GT BOQ",
            "project": self.project,
            "company": self.company
        }).insert(ignore_permissions=True)

        bill = frappe.get_doc({
            "doctype": "BOQ Bill",
            "bill_no": "BD-002",
            "project": self.project,
            "project_boq": pboq.name,
            "company": self.company
        }).insert(ignore_permissions=True)

        boq_item = frappe.get_doc({
            "doctype": "BOQ Item",
            "item_code": self.item,
            "boq_item_name": "BOQ-D-2",
            "rate": 1000,
            "total_qty": 10,
            "project": self.project,
            "parent_bill": bill.name,
            "unit": "Nos",
            "description": "Test Discount Item Description GT"
        }).insert(ignore_permissions=True)

        # Create Invoice
        inv = frappe.new_doc("Sales Invoice")
        inv.customer = self.customer
        inv.project = self.project
        inv.company = self.company
        inv.posting_date = frappe.utils.today()
        inv.apply_discount_on = "Grand Total"
        inv.discount_amount = 50
        
        inv.append("items", {
            "item_code": self.item,
            "qty": 1,
            "rate": 1000,
            "amount": 1000,
            "boq_item": boq_item.name
        })

        inv.insert(ignore_permissions=True)
        inv.submit()

        # Verify Ledger Entry
        # Gross 1000, No tax in this test, Discount 50, Grand Net 950
        entry = frappe.db.get_value("BOQ Progress Ledger", 
                                      {"tax_invoice": inv.name, "boq_item": boq_item.name}, 
                                      ["amount"], as_dict=True)
        self.assertIsNotNone(entry)
        self.assertEqual(flt(entry.amount), 950.0)

    def tearDown(self):
        frappe.db.rollback()
