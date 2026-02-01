import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today
from construction_management.api.boq_ledger import create_ledger_entry, recalculate_ledger_for_item

class TestBOQLedgerReversal(IntegrationTestCase):
	def setUp(self):
		self.company = "_Test Company"
		self.project = "_Test Project Reversal"
		self.customer = "_Test Customer"
		self.item_code = "TEST-BOQ-ITEM-REV"

		# Create test data
		if not frappe.db.exists("Company", self.company):
			c = frappe.new_doc("Company")
			c.company_name = self.company
			c.default_currency = "INR"
			c.insert()

		if not frappe.db.exists("Project", self.project):
			p = frappe.new_doc("Project")
			p.project_name = self.project
			p.company = self.company
			p.customer = self.customer
			p.insert()

		# Ensure BOQ Settings exists
		if not frappe.db.exists("BOQ Settings", self.company):
			settings = frappe.new_doc("BOQ Settings")
			settings.company = self.company
			settings.varience_item = "Variance Item"
			settings.insert()

		# Create Project BOQ
		self.project_boq = frappe.new_doc("Project BOQ")
		self.project_boq.project = self.project
		self.project_boq.status = "Draft"
		self.project_boq.insert()

		# Create BOQ Bill
		self.boq_bill = frappe.new_doc("BOQ Bill")
		self.boq_bill.project = self.project
		self.boq_bill.project_boq = self.project_boq.name
		self.boq_bill.bill_no = "BILL-001"
		self.boq_bill.insert()

		# Create BOQ Item
		self.boq_item = frappe.new_doc("BOQ Item")
		self.boq_item.description = "Test Ledger Reversal Item"
		self.boq_item.project = self.project
		self.boq_item.project_boq = self.project_boq.name
		self.boq_item.parent_bill = self.boq_bill.name
		self.boq_item.total_qty = 10
		self.boq_item.rate = 1000  # Amount = 10000
		self.boq_item.insert()
		
		# Approve BOQ to lock it
		self.project_boq.status = "Approved"
		self.project_boq.save()

	def test_ledger_reversal_on_invoice_cancel(self):
		"""
		Scenario:
		1. Create Ledger Entry for BOQ Item (Amount: 5000)
		2. Linked to PC with Accepted Amount: 4500 (Variance of 500)
		3. Create Sales Invoice (Amount: 4500)
		4. Submit Sales Invoice -> Ledger 'amount' remains 4500 (accepted/net)
		5. Cancel Sales Invoice -> Ledger 'amount' should revert to 5000 (proforma_amount)
		"""
		boq_item = self.boq_item.name
		
		# 1. Create Ledger Entry (simulating Proforma/Order)
		ledger_name = create_ledger_entry(
			boq_item=boq_item,
			qty=5,
			amount=5000,
			source="Order",
			posting_date=today(),
			remarks="Initial Order",
			proforma_amount=5000
		)
		
		ledger = frappe.get_doc("BOQ Progress Ledger", ledger_name)
		self.assertEqual(flt(ledger.amount), 5000)
		self.assertEqual(flt(ledger.proforma_amount), 5000)
		
		# 2. Simulate Payment Certificate & Sales Invoice via update_boq_ledger_entry logic
		# We mimic what Payment Certificate.update_boq_progress_ledger does
		pc_name = "TEST-PC-001"
		si_name = "TEST-SI-001"
		
		# Update ledger with PC details (Accepted amount = 4500)
		frappe.db.set_value("BOQ Progress Ledger", ledger_name, {
			"payment_certificate": pc_name,
			"certified_amount": 4500,
			"tax_invoice": si_name,
			"tax_invoice_amount": 4500,
			"amount": 4500, # This is what happens today in create_boq_ledger_entry
			"source": "Invoice"
		})
		
		recalculate_ledger_for_item(boq_item)
		
		ledger.reload()
		self.assertEqual(flt(ledger.amount), 4500) # Current (accepted) value
		self.assertEqual(flt(ledger.proforma_amount), 5000) # Original value preserved
		
		# 3. Simulate Sales Invoice Cancellation
		# Mocking the Sales Invoice doc for create_boq_reversal_entry
		invoice = frappe._dict({
			"name": si_name,
			"custom_payment_certificate": pc_name,
			"items": [frappe._dict({"boq_item": boq_item, "qty": 5, "amount": 4500})]
		})
		
		from construction_management.overrides.sales_invoice import create_boq_reversal_entry
		# In actual code, it takes invoice doc. 
		# We need to make sure the function can handle it.
		create_boq_reversal_entry(invoice, invoice.items[0])
		
		# 4. Verify Reversal
		ledger.reload()
		self.assertEqual(flt(ledger.amount), 5000, "Ledger amount did not revert to original proforma amount")
		self.assertEqual(ledger.tax_invoice, None)
		self.assertEqual(flt(ledger.tax_invoice_amount), 0)
		self.assertEqual(ledger.source, "Adjustment") # Based on fallback in create_boq_reversal_entry
