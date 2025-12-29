# Copyright (c) 2024, Construction Management
# License: MIT
# Tests for BOQ Management Fixes - Proforma Invoice Workflow

"""
Tests for the BOQ Management Fixes including:
- Issue #1: Action button visibility (CSS fixes - manual testing)
- Issue #2: Proforma Invoice to Payment Certificate workflow
- Issue #3: Row-level highlighting and PC creation
- Issue #4: BOQ Progress Ledger display fixes
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today


class TestProformaInvoiceWorkflow(FrappeTestCase):
	"""
	Tests for the Proforma Invoice to Payment Certificate workflow.
	Validates the new Proforma Invoice doctype integration.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-PI-WORKFLOW-PROJECT")
		cls.test_customer = create_test_customer("Test PI Workflow Customer")
		frappe.db.set_value("Project", cls.test_project, "customer", cls.test_customer)
	
	def test_payment_certificate_links_to_proforma_invoice_doctype(self):
		"""Property: PC.proforma_invoice links to Proforma Invoice doctype, not Sales Invoice"""
		# Create Proforma Invoice
		pi = create_test_proforma_invoice_doc(self.test_project, self.test_customer, 10000)
		
		# Create Payment Certificate
		pc = frappe.new_doc("Payment Certificate")
		pc.type = "Sales"
		pc.project = self.test_project
		pc.customer = self.test_customer
		pc.proforma_invoice = pi
		pc.proforma_amount = 10000
		pc.accepted_amount = 10000
		pc.posting_date = today()
		pc.insert(ignore_permissions=True)
		
		# Verify proforma_invoice links to Proforma Invoice doctype
		self.assertTrue(frappe.db.exists("Proforma Invoice", pi))
		self.assertEqual(pc.proforma_invoice, pi)
	
	def test_accepted_amount_auto_populated_from_proforma(self):
		"""Property: accepted_amount is auto-populated from proforma net_amount"""
		from construction_management.api.boq_invoice import create_payment_certificate
		
		# Create Proforma Invoice
		pi = create_test_proforma_invoice_doc(self.test_project, self.test_customer, 15000)
		
		# Create PC without specifying accepted_amount
		pc_name = create_payment_certificate(proforma_invoice=pi)
		
		pc = frappe.get_doc("Payment Certificate", pc_name)
		
		# accepted_amount should equal proforma net_amount
		proforma = frappe.get_doc("Proforma Invoice", pi)
		expected = flt(proforma.net_amount) or flt(proforma.amount)
		self.assertEqual(flt(pc.accepted_amount), expected)
	
	def test_accepted_amount_validation_exceeds_proforma(self):
		"""Property: accepted_amount cannot exceed proforma_amount"""
		from construction_management.api.boq_invoice import create_payment_certificate
		
		# Create Proforma Invoice
		pi = create_test_proforma_invoice_doc(self.test_project, self.test_customer, 10000)
		
		# Try to create PC with accepted_amount > proforma_amount
		with self.assertRaises(frappe.ValidationError) as context:
			create_payment_certificate(
				proforma_invoice=pi, 
				accepted_amount=15000  # More than proforma
			)
		
		self.assertIn("cannot exceed", str(context.exception).lower())
	
	def test_duplicate_pc_for_proforma_prevented(self):
		"""Property: Cannot create duplicate PC for same Proforma Invoice"""
		from construction_management.api.boq_invoice import create_payment_certificate
		
		# Create Proforma Invoice
		pi = create_test_proforma_invoice_doc(self.test_project, self.test_customer, 20000)
		
		# Create first PC
		pc1 = create_payment_certificate(proforma_invoice=pi)
		self.assertIsNotNone(pc1)
		
		# Try to create second PC - should fail
		with self.assertRaises(frappe.ValidationError) as context:
			create_payment_certificate(proforma_invoice=pi)
		
		self.assertIn("already exists", str(context.exception).lower())


class TestBOQLedgerDisplay(FrappeTestCase):
	"""
	Tests for BOQ Progress Ledger display fixes.
	Validates that ledger values are correctly calculated.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-LEDGER-PROJECT")
		cls.test_customer = create_test_customer("Test Ledger Customer")
		frappe.db.set_value("Project", cls.test_project, "customer", cls.test_customer)
	
	def test_get_item_ledger_values_returns_correct_structure(self):
		"""Property: get_item_ledger_values returns qty and amount with all required keys"""
		from construction_management.api.boq_tree import get_item_ledger_values
		
		# Create BOQ structure
		boq, bill, item = create_test_boq_structure(self.test_project, total_qty=100, rate=50)
		
		result = get_item_ledger_values(item)
		
		# Check structure
		self.assertIn("qty", result)
		self.assertIn("amount", result)
		
		# Check qty keys
		for key in ["total", "prev", "current", "to_date", "balance"]:
			self.assertIn(key, result["qty"])
		
		# Check amount keys
		for key in ["rate", "total", "prev", "current", "to_date", "balance"]:
			self.assertIn(key, result["amount"])
	
	def test_ledger_values_fallback_to_proforma_data(self):
		"""Property: When no ledger entries exist, values come from Proforma Invoice items"""
		from construction_management.api.boq_tree import get_item_ledger_values
		
		# Create BOQ structure
		boq, bill, item = create_test_boq_structure(self.test_project, total_qty=100, rate=50)
		
		# Create and submit a Proforma Invoice for this item
		pi = create_proforma_with_boq_item(
			self.test_project, 
			self.test_customer, 
			item, 
			qty=25, 
			rate=50
		)
		
		# Get ledger values - should fallback to proforma data
		result = get_item_ledger_values(item)
		
		# to_date_qty should reflect the proforma invoice
		self.assertEqual(flt(result["qty"]["to_date"]), 25)
		self.assertEqual(flt(result["amount"]["to_date"]), 1250)  # 25 * 50


class TestPendingProformasForItem(FrappeTestCase):
	"""
	Tests for get_pending_proformas_for_item API function.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-PENDING-PI-PROJECT")
		cls.test_customer = create_test_customer("Test Pending PI Customer")
		frappe.db.set_value("Project", cls.test_project, "customer", cls.test_customer)
	
	def test_returns_proformas_without_pc(self):
		"""Property: Returns proformas that don't have a Payment Certificate"""
		from construction_management.api.boq_invoice import get_pending_proformas_for_item
		
		# Create BOQ structure
		boq, bill, item = create_test_boq_structure(self.test_project, total_qty=100, rate=50)
		
		# Create proforma for this item
		pi = create_proforma_with_boq_item(
			self.test_project,
			self.test_customer,
			item,
			qty=20,
			rate=50
		)
		
		# Get pending proformas
		pending = get_pending_proformas_for_item(item)
		
		# Should include our proforma
		pending_names = [p.name for p in pending]
		self.assertIn(pi, pending_names)
	
	def test_excludes_proformas_with_pc(self):
		"""Property: Excludes proformas that already have a Payment Certificate"""
		from construction_management.api.boq_invoice import get_pending_proformas_for_item
		
		# Create BOQ structure
		boq, bill, item = create_test_boq_structure(self.test_project, total_qty=100, rate=50)
		
		# Create proforma for this item
		pi = create_proforma_with_boq_item(
			self.test_project,
			self.test_customer,
			item,
			qty=20,
			rate=50
		)
		
		# Create PC for this proforma
		pc = frappe.new_doc("Payment Certificate")
		pc.type = "Sales"
		pc.project = self.test_project
		pc.customer = self.test_customer
		pc.proforma_invoice = pi
		pc.proforma_amount = 1000
		pc.accepted_amount = 1000
		pc.posting_date = today()
		pc.insert(ignore_permissions=True)
		
		# Get pending proformas
		pending = get_pending_proformas_for_item(item)
		
		# Should NOT include our proforma
		pending_names = [p.name for p in pending]
		self.assertNotIn(pi, pending_names)


# ============================================
# Test Fixtures for Proforma Invoice Doctype
# ============================================

def create_test_project(name):
	"""Create a test project if it doesn't exist"""
	if frappe.db.exists("Project", name):
		return name
	
	project = frappe.new_doc("Project")
	project.project_name = name
	project.insert(ignore_permissions=True)
	return project.name


def create_test_customer(name):
	"""Create a test customer"""
	if frappe.db.exists("Customer", name):
		return name
	
	customer = frappe.new_doc("Customer")
	customer.customer_name = name
	customer.customer_type = "Company"
	customer.insert(ignore_permissions=True)
	return customer.name


def create_test_proforma_invoice_doc(project, customer, amount):
	"""Create a test Proforma Invoice using the Proforma Invoice doctype"""
	import random
	import string
	
	suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
	
	pi = frappe.new_doc("Proforma Invoice")
	pi.project = project
	pi.customer = customer
	pi.posting_date = today()
	
	# Add a dummy item
	pi.append("items", {
		"description": f"Test Item {suffix}",
		"qty": 1,
		"rate": amount,
		"amount": amount
	})
	
	pi.amount = amount
	pi.net_amount = amount
	pi.insert(ignore_permissions=True)
	pi.submit()
	
	return pi.name


def create_proforma_with_boq_item(project, customer, boq_item, qty, rate):
	"""Create a Proforma Invoice linked to a specific BOQ Item"""
	import random
	import string
	
	suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
	
	pi = frappe.new_doc("Proforma Invoice")
	pi.project = project
	pi.customer = customer
	pi.posting_date = today()
	
	# Get BOQ Item details
	item_doc = frappe.get_doc("BOQ Item", boq_item)
	
	# Add item linked to BOQ Item
	pi.append("items", {
		"description": item_doc.description or f"Test Item {suffix}",
		"boq_item": boq_item,
		"bill_no": item_doc.parent_bill,
		"qty": qty,
		"rate": rate,
		"amount": qty * rate
	})
	
	pi.amount = qty * rate
	pi.net_amount = qty * rate
	pi.insert(ignore_permissions=True)
	pi.submit()
	
	return pi.name


def create_test_boq_structure(project, total_qty=100, rate=10):
	"""Create a test BOQ structure with Project BOQ, Bill, and Item"""
	import random
	import string
	
	suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
	
	# Create Project BOQ
	boq = frappe.new_doc("Project BOQ")
	boq.project = project
	boq.boq_name = f"Test BOQ {suffix}"
	boq.status = "Draft"
	boq.insert(ignore_permissions=True)
	
	# Create BOQ Bill
	bill = frappe.new_doc("BOQ Bill")
	bill.project_boq = boq.name
	bill.project = project
	bill.bill_no = f"BILL-{suffix}"
	bill.description = f"Test Bill {suffix}"
	bill.insert(ignore_permissions=True)
	
	# Create BOQ Item
	item = frappe.new_doc("BOQ Item")
	item.parent_bill = bill.name
	item.project_boq = boq.name
	item.project = project
	item.description = f"Test Item {suffix}"
	item.unit = "Nos"
	item.total_qty = flt(total_qty)
	item.rate = flt(rate)
	item.total_amount = flt(total_qty) * flt(rate)
	item.balance_qty = flt(total_qty)
	item.balance_amount = flt(total_qty) * flt(rate)
	item.billing_status = "Not Billed"
	item.insert(ignore_permissions=True)
	
	return boq.name, bill.name, item.name
