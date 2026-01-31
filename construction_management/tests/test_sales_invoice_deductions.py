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
        # Ensure variance item and account exist to satisfy mandatory fields
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
        else:
            settings_doc = frappe.get_doc("BOQ Settings", self.company)
            settings_doc.varience_item = "VARIANCE-ITEM"
            settings_doc.varience_account_debit = self.dummy_variance_account
            
            # Defensive: If any existing account is a group, try to pick a child to satisfy GL validation
            for field in ["retention_account", "advance_account", "advance_deduction_item", "default_advance_item"]:
                val = settings_doc.get(field)
                if val:
                    if "account" in field:
                        if frappe.db.get_value("Account", val, "is_group"):
                            child = frappe.db.get_value("Account", {"parent_account": val, "is_group": 0}, "name")
                            if child:
                                settings_doc.set(field, child)
            
            settings_doc.save(ignore_permissions=True)

    def _get_test_company(self):
        company = frappe.db.get_value("Company", {}, "name")
        if not company:
            doc = frappe.get_doc({
                "doctype": "Company",
                "company_name": "Test Company",
                "default_currency": "USD"
            }).insert(ignore_permissions=True)
            company = doc.name
        
        # Ensure Cost Center exists
        if not frappe.db.exists("Cost Center", {"company": company}):
             cc = frappe.get_doc({
                 "doctype": "Cost Center",
                 "cost_center_name": "Main",
                 "company": company,
                 "is_group": 0
             }).insert(ignore_permissions=True)
             frappe.db.set_value("Company", company, "cost_center", cc.name)
        elif not frappe.db.get_value("Company", company, "cost_center"):
             cc = frappe.db.get_value("Cost Center", {"company": company}, "name")
             frappe.db.set_value("Company", company, "cost_center", cc)
             
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
        project_name = "Test Deduction Project"
        existing = frappe.db.get_value("Project", {"project_name": project_name}, "name")
        if existing:
            return existing
            
        project = frappe.get_doc({
            "doctype": "Project",
            "project_name": project_name,
            "status": "Open",
            "retention_percentage": 10.0,
            "customer": self.customer
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

    def test_gl_entries_for_deductions(self):
        # Create unique accounts for test
        # Ensure we get a group account for the parent
        parent_asset = frappe.db.get_value("Account", {"account_type": "Receivable", "company": self.company, "is_group": 1, "account_name": ["not like", "Loans and Advances%"]})
        if not parent_asset:
             parent_asset = frappe.db.get_value("Account", {"root_type": "Asset", "company": self.company, "is_group": 1, "account_name": ["not like", "Loans and Advances%"]}) or \
                            frappe.db.get_value("Account", {"root_type": "Asset", "company": self.company, "is_group": 1})
        
        parent_liability = frappe.db.get_value("Account", {"account_type": "Payable", "company": self.company, "is_group": 1})
        if not parent_liability:
            parent_liability = frappe.db.get_value("Account", {"root_type": "Liability", "company": self.company, "is_group": 1})

        retention_account_name = f"Test Retention {frappe.generate_hash(length=5)}"
        retention_account = frappe.get_doc({
            "doctype": "Account",
            "account_name": retention_account_name,
            "parent_account": parent_asset,
            "company": self.company,
            "account_type": "Receivable",
            "is_group": 0
        }).insert(ignore_permissions=True).name
        
        advance_account_name = f"Test Advance {frappe.generate_hash(length=5)}"
        advance_account = frappe.get_doc({
            "doctype": "Account",
            "account_name": advance_account_name,
            "parent_account": parent_liability,
            "company": self.company,
            "account_type": "Payable",
            "is_group": 0
        }).insert(ignore_permissions=True).name
        
        # Configure BOQ Settings
        if not frappe.db.exists("BOQ Settings", self.company):
            frappe.get_doc({
                "doctype": "BOQ Settings",
                "name": self.company,
                "company": self.company,
                "retention_account": retention_account,
                "advance_account": advance_account
            }).insert(ignore_permissions=True)
        else:
            settings_doc = frappe.get_doc("BOQ Settings", self.company)
            settings_doc.retention_account = retention_account
            settings_doc.advance_account = advance_account
            settings_doc.save(ignore_permissions=True)
            
        # Create advance payment
        self._create_advance_payment(2000)
        
        # Create invoice
        inv = frappe.new_doc("Sales Invoice")
        inv.customer = self.customer
        inv.project = self.project
        inv.company = self.company
        inv.posting_date = frappe.utils.today()
        # Item 10000
        inv.append("items", {
            "item_code": self.item,
            "qty": 1,
            "rate": 10000,
            "amount": 10000
        })
        # Retention 10% (1000)
        inv.append("items", {
            "item_code": "RETENTION-DEDUCTION",
            "qty": 1,
            "rate": -1000,
            "amount": -1000
        })
        # Advance deduction (500)
        inv.append("items", {
            "item_code": "ADVANCE-DEDUCTION",
            "qty": 1,
            "rate": -500,
            "amount": -500
        })
        
        inv.insert(ignore_permissions=True)
        inv.submit()
        
        # Check GL Entries
        gl_entries = frappe.get_all("GL Entry", filters={"voucher_no": inv.name}, fields=["account", "debit", "credit"])
        
        retention_gl = next((e for e in gl_entries if e.account == retention_account), None)
        advance_gl = next((e for e in gl_entries if e.account == advance_account), None)
        
        self.assertIsNotNone(retention_gl, "Retention GL entry not found")
        self.assertEqual(flt(retention_gl.debit), 1000.0)
        
        self.assertIsNotNone(advance_gl, "Advance GL entry not found")
        self.assertEqual(flt(advance_gl.debit), 500.0)
        
        # Ensure Sales Credit is still full? 
        # Actually ERPNext usually splits it based on income accounts.
        # But for our deduction items, they should be in retention/advance accounts.

    def test_pc_to_si_with_variance_and_gross_amount(self):
        # 1. Setup Variance Item and Account
        if not frappe.db.exists("Item", "VARIANCE-ITEM"):
            frappe.get_doc({
                "doctype": "Item",
                "item_code": "VARIANCE-ITEM",
                "item_name": "Variance Item",
                "item_group": "All Item Groups",
                "stock_uom": "Nos",
                "is_stock_item": 0
            }).insert(ignore_permissions=True)
        
        parent_expense = frappe.db.get_value("Account", {"root_type": "Expense", "company": self.company, "is_group": 1})
        variance_acc_name = f"Test Variance {frappe.generate_hash(length=5)}"
        variance_account = frappe.get_doc({
            "doctype": "Account",
            "account_name": variance_acc_name,
            "parent_account": parent_expense,
            "company": self.company,
            "account_type": "Expense Account",
            "is_group": 0
        }).insert(ignore_permissions=True).name

        # Update BOQ Settings
        frappe.db.set_value("BOQ Settings", self.company, {
            "varience_account_debit": variance_account,
            "varience_item": "VARIANCE-ITEM"
        })

        # 2. Create Payment Certificate
        # We need a real BOQ Item hierarchy to avoid DB fetch errors
        pboq = frappe.get_doc({
            "doctype": "Project BOQ",
            "boq_name": "Test BOQ Name",
            "project": self.project,
            "company": self.company,
            "status": "Draft"
        }).insert(ignore_permissions=True)

        bill = frappe.get_doc({
            "doctype": "BOQ Bill",
            "bill_no": "B001",
            "project": self.project,
            "project_boq": pboq.name,
            "company": self.company
        }).insert(ignore_permissions=True)

        boq_item = frappe.get_doc({
            "doctype": "BOQ Item",
            "item_code": self.item,
            "description": "Test BOQ Item",
            "total_qty": 100,
            "rate": 100,
            "unit": "Nos",
            "parent_bill": bill.name,
            "project": self.project,
            "project_boq": pboq.name
        }).insert(ignore_permissions=True)

        pc = frappe.new_doc("Payment Certificate")
        pc.type = "Sales"
        pc.project = self.project
        pc.customer = self.customer
        pc.company = self.company
        pc.posting_date = frappe.utils.today()
        pc.proforma_amount = 1000
        pc.accepted_amount = 800
        pc.variance = 200
        
        pc.append("items", {
            "boq_item": boq_item.name,
            "item_code": self.item,
            "item_name": "Test Item",
            "description": "Test Item Description",
            "qty": 10,
            "rate": 100,
            "proforma_amount": 1000,
            "accepted_amount": 800,
            "bill_no": bill.name
        })
        
        pc.insert(ignore_permissions=True)
        pc.submit()

        # 3. Create Tax Invoice from PC
        si_name = pc.create_tax_invoice()
        inv = frappe.get_doc("Sales Invoice", si_name)

        # 4. Verify Invoice Items
        # Should have 3 items: ITEM-1 (Gross 1000), VARIANCE-ITEM (-200), RETENTION-DEDUCTION (-100)
        self.assertEqual(len(inv.items), 3)
        
        boq_row = next((i for i in inv.items if i.item_code == self.item), None)
        var_row = next((i for i in inv.items if i.item_code == "VARIANCE-ITEM"), None)
        ret_row = next((i for i in inv.items if i.item_code == "RETENTION-DEDUCTION"), None)
        
        self.assertIsNotNone(boq_row)
        self.assertEqual(flt(boq_row.amount), 1000.0)
        
        self.assertIsNotNone(var_row)
        self.assertEqual(flt(var_row.amount), -200.0)

        self.assertIsNotNone(ret_row)
        self.assertIsNotNone(ret_row)
        self.assertEqual(flt(ret_row.amount), -100.0)

        # 5. Verify GL Entries
        gl_entries = frappe.get_all("GL Entry", filters={"voucher_no": inv.name}, fields=["account", "debit", "credit"])
        
        # Sales Credit should be 1000 (Gross)
        income_account = frappe.db.get_value("Company", self.company, "default_income_account")
        sales_gl = next((e for e in gl_entries if e.account == income_account), None)
        self.assertIsNotNone(sales_gl)
        self.assertEqual(flt(sales_gl.credit), 1000.0)
        
        # Variance Debit should be 200
        var_gl = next((e for e in gl_entries if e.account == variance_account), None)
        self.assertIsNotNone(var_gl)
        self.assertEqual(flt(var_gl.debit), 200.0)

        # Retention Debit should be 100
        ret_account = frappe.db.get_value("BOQ Settings", self.company, "retention_account")
        ret_gl = next((e for e in gl_entries if e.account == ret_account), None)
        self.assertIsNotNone(ret_gl)
        self.assertEqual(flt(ret_gl.debit), 100.0)

        # Debtors Debit should be 700 (1000 - 200 - 100)
        debtors_account = frappe.db.get_value("Account", {"account_type": "Receivable", "company": self.company, "is_group": 0})
        debtors_gl = next((e for e in gl_entries if e.account == debtors_account), None)
        self.assertIsNotNone(debtors_gl)
        self.assertEqual(flt(debtors_gl.debit), 700.0)

    def test_deduction_on_net_amount(self):
        """
        Test that advance deduction is calculated on (Gross - Variance) i.e. Net Amount.
        If Gross = 1000, Variance = -200, Advance % = 10%
        Advance Deduction should be (1000 - 200) * 0.10 = 80.
        """
        # 1. Setup Project with 10% Advance Deduction
        # 1. Setup Project with 10% Advance Deduction
        p = frappe.get_doc("Project", self.project)
        p.advance_deduction = 10.0
        p.save(ignore_permissions=True)
        
        # Explicitly create advance to ensure balance exists (setup seems flaky here?)
        self._create_advance_payment(2000)
        
        # 2. Create PC with variance
        pc = self._create_payment_certificate(1000.0, 800.0)
        
        # 3. Pull items from PC (mocking the button click logic in server script)
        # Manually construct items list for get_deduction_details as if they were in SI
        # Gross Item
        items = [{
            "item_code": self.item,
            "amount": 1000.0,
            "qty": 10,
            "rate": 100.0
        }]
        
        # Variance Item
        items.append({
            "item_code": "VARIANCE-ITEM",
            "amount": -200.0,
            "qty": 1,
            "rate": -200.0
        })
        
        # 4. Call API
        from construction_management.api.boq_invoice import get_deduction_details
        details = get_deduction_details(self.project, items=items)
        
        # 5. Verify Suggested Advance
        # Net = 1000 - 200 = 800
        # Advance = 10% of 800 = 80
        # Note: get_deduction_details returns suggested_advance based on balance too.
        # We need to ensure balance is sufficient.
        # We created 2000 advance in setUp, so 80 is well within limit.
        self.assertEqual(flt(details.get("suggested_advance")), 80.0)

    def _create_payment_certificate(self, proforma_amount, accepted_amount):
        """Helper to create a submitted PC"""
        # Create BOQ structure
        pboq = frappe.get_doc({
            "doctype": "Project BOQ",
            "boq_name": f"Test BOQ {frappe.generate_hash(length=5)}",
            "project": self.project,
            "company": self.company,
            "status": "Draft"
        }).insert(ignore_permissions=True)

        bill = frappe.get_doc({
            "doctype": "BOQ Bill",
            "bill_no": f"B{frappe.generate_hash(length=3)}",
            "project": self.project,
            "project_boq": pboq.name,
            "company": self.company
        }).insert(ignore_permissions=True)

        boq_item = frappe.get_doc({
            "doctype": "BOQ Item",
            "item_code": self.item,
            "description": "Test BOQ Item",
            "total_size": 100, # total_qty field name might be total_qty
            "total_qty": 100,
            "rate": proforma_amount / 10, # Assuming qty 10
            "unit": "Nos",
            "parent_bill": bill.name,
            "project": self.project,
            "project_boq": pboq.name
        }).insert(ignore_permissions=True)

        pc = frappe.new_doc("Payment Certificate")
        pc.type = "Sales"
        pc.project = self.project
        pc.customer = self.customer
        pc.company = self.company
        pc.posting_date = frappe.utils.today()
        pc.proforma_amount = proforma_amount
        pc.accepted_amount = accepted_amount
        pc.variance = proforma_amount - accepted_amount
        
        pc.append("items", {
            "boq_item": boq_item.name,
            "item_code": self.item,
            "item_name": "Test Item",
            "description": "Test Item Description",
            "qty": 10,
            "rate": proforma_amount / 10,
            "proforma_amount": proforma_amount,
            "accepted_amount": accepted_amount,
            "bill_no": bill.name
        })
        
        pc.insert(ignore_permissions=True)
        pc.submit()
        return pc.name

    def test_ledger_entry_multiple_items_distribution(self):
        """
        Test distribution of global deductions (Retention, Advance, Variance) 
        across multiple BOQ items in the ledger.
        """
        # 1. Setup BOQ Items (Mocking simple items for test)
        # Create Items first
        if not frappe.db.exists("Item", "ITEM-A"):
            frappe.new_doc("Item", item_code="ITEM-A", item_name="Item A", item_group="All Item Groups").insert(ignore_permissions=True)
        if not frappe.db.exists("Item", "ITEM-B"):
            frappe.new_doc("Item", item_code="ITEM-B", item_name="Item B", item_group="All Item Groups").insert(ignore_permissions=True)

        # 2. Setup Project & Advance
        self._create_advance_payment(2000)
        
        # Ensure proper Cost Center
        cc_name = "Test-CC-Main"
        if not frappe.db.exists("Cost Center", {"company": self.company, "cost_center_name": "Main"}):
             # Try to find any CC or create one
             cc = frappe.get_doc({
                 "doctype": "Cost Center",
                 "cost_center_name": "Test-CC-Main",
                 "company": self.company,
                 "is_group": 0
             }).insert(ignore_permissions=True)
             cc_name = cc.name
        else:
             cc_name = frappe.db.get_value("Cost Center", {"company": self.company, "cost_center_name": "Main"}, "name") or \
                       frappe.db.get_value("Cost Center", {"company": self.company, "is_group": 0}, "name")

        # 3. Create Invoice
        inv = frappe.new_doc("Sales Invoice")
        inv.customer = self.customer
        inv.project = self.project
        inv.company = self.company
        inv.cost_center = cc_name
        inv.posting_date = frappe.utils.today()
        
        # BOQ Item A: 1000
        inv.append("items", {
            "item_code": "ITEM-A",
            "qty": 1,
            "rate": 1000,
            "amount": 1000,
            "boq_item": "BOQ-A-MOCK" # We need a boq_item name for ledger
        })
        
        # BOQ Item B: 2000
        inv.append("items", {
            "item_code": "ITEM-B",
            "qty": 1,
            "rate": 2000,
            "amount": 2000,
            "boq_item": "BOQ-B-MOCK"
        })
        
        # Deductions: Total -750
        # Retention: -300
        inv.append("items", {
            "item_code": "RETENTION-DEDUCTION",
            "qty": 1,
            "rate": -300,
            "amount": -300
        })
        # Advance: -300
        inv.append("items", {
            "item_code": "ADVANCE-DEDUCTION",
            "qty": 1,
            "rate": -300,
            "amount": -300
        })
        # Variance: -150
        inv.append("items", {
            "item_code": "VARIANCE-ITEM",
            "qty": 1,
            "rate": -150,
            "amount": -150
        })

        # Create a dummy BOQ Bill first
        if not frappe.db.exists("BOQ Bill", "BILL-MOCK"):
             pboq = frappe.get_doc({
                "doctype": "Project BOQ",
                "boq_name": "MOCK-BOQ-ROOT",
                "project": self.project,
                "company": self.company
             }).insert(ignore_permissions=True)
             
             bill_doc = frappe.get_doc({
                 "doctype": "BOQ Bill",
                 "bill_no": "BILL-MOCK",
                 "project": self.project,
                 "company": self.company,
                 "project_boq": pboq.name
             }).insert(ignore_permissions=True)
             bill_name = bill_doc.name
        else:
             bill_name = frappe.db.get_value("BOQ Bill", {"bill_no": "BILL-MOCK"})

        if not frappe.db.exists("BOQ Item", "BOQ-A-MOCK"):
             boq_a = frappe.get_doc({
                "doctype": "BOQ Item",
                "item_code": "ITEM-A",
                "boq_item_name": "BOQ-A-MOCK", # ID
                "rate": 1000,
                "total_qty": 10,
                "project": self.project,
                "parent_bill": bill_name,
                "description": "Mock Item A",
                "unit": "Nos"
             }).insert(ignore_permissions=True)
             boq_a_name = boq_a.name
        else:
             boq_a_name = frappe.db.get_value("BOQ Item", {"boq_item_name": "BOQ-A-MOCK"})

        if not frappe.db.exists("BOQ Item", "BOQ-B-MOCK"):
             boq_b = frappe.get_doc({
                "doctype": "BOQ Item",
                "item_code": "ITEM-B",
                "boq_item_name": "BOQ-B-MOCK",
                "rate": 2000,
                "total_qty": 10,
                "project": self.project,
                "parent_bill": bill_name,
                "description": "Mock Item B",
                "unit": "Nos"
             }).insert(ignore_permissions=True)
             boq_b_name = boq_b.name
        else:
             boq_b_name = frappe.db.get_value("BOQ Item", {"boq_item_name": "BOQ-B-MOCK"})

        # Update invoice items with correct BOQ Item names
        # Note: We appended items before creating BOQ Items in the previous code block order,
        # which was also wrong because items list is processed on insert. 
        # But actually I see I appended items *before* creating them in validation? 
        # No, 'inv.insert' is called *after* append. But I need to update the already appended items or append them now.
        # Let's re-append or just update the dicts. 
        # Easier to clear items and append again with correct names.
        inv.items = []
        
        # BOQ Item A: 1000
        inv.append("items", {
            "item_code": "ITEM-A",
            "qty": 1,
            "rate": 1000,
            "amount": 1000,
            "boq_item": boq_a_name
        })
        
        # BOQ Item B: 2000
        inv.append("items", {
            "item_code": "ITEM-B",
            "qty": 1,
            "rate": 2000,
            "amount": 2000,
            "boq_item": boq_b_name
        })
        
        # Deductions
        inv.append("items", {
            "item_code": "RETENTION-DEDUCTION",
            "qty": 1,
            "rate": -300,
            "amount": -300
        })
        inv.append("items", {
            "item_code": "ADVANCE-DEDUCTION",
            "qty": 1,
            "rate": -300,
            "amount": -300
        })
        inv.append("items", {
            "item_code": "VARIANCE-ITEM",
            "qty": 1,
            "rate": -150,
            "amount": -150,
            "cost_center": cc_name
        })

        inv.insert(ignore_permissions=True)
        inv.submit()

        # 4. Verify Ledger Entries
        # Previously: Item A: 1000 (33.33% of 3000) -> Share of 750 deduction = 250. Net = 750.
        # Now: Share of 150 variance = 50. Net = 950.
        entry_a = frappe.db.get_value("BOQ Progress Ledger", 
                                      {"tax_invoice": inv.name, "boq_item": boq_a_name}, 
                                      ["amount", "tax_invoice_amount"], as_dict=True)
        self.assertIsNotNone(entry_a)
        self.assertEqual(flt(entry_a.amount), 950.0)
        
        # Previously: Item B: 2000 (66.67% of 3000) -> Share of 750 deduction = 500. Net = 1500.
        # Now: Share of 150 variance = 100. Net = 1900.
        entry_b = frappe.db.get_value("BOQ Progress Ledger", 
                                      {"tax_invoice": inv.name, "boq_item": boq_b_name}, 
                                      ["amount", "tax_invoice_amount"], as_dict=True)
        self.assertIsNotNone(entry_b)
        self.assertEqual(flt(entry_b.amount), 1900.0)

def run_tests():
    unittest.main()
