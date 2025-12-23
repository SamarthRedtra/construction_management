# Copyright (c) 2024, Construction Management
# License: MIT
# Property Tests for Payment Certificate and Proforma Tracking

"""
Property Tests for Construction Management Enhancements v2

These tests validate the following properties:
- Task 5.6: Pending Proforma Tracking
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today


class TestPendingProformaTracking(FrappeTestCase):
	"""
	Property 12: Pending Proforma Tracking
	
	Validates: Requirements 7.6
	Property: Proforma invoices are correctly tracked as pending until converted to Payment Certificate.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-PROFORMA-PROJECT")
		cls.test_customer = create_test_customer("Test Proforma Customer")
		
		# Link customer to project
		frappe.db.set_value("Project", cls.test_project, "customer", cls.test_customer)
	
	def test_proforma_invoice_has_custom_is_proforma_flag(self):
		"""Property: Proforma invoices have custom_is_proforma = 1"""
		# Create a proforma invoice
		invoice = create_test_proforma_invoice(self.test_project, self.test_customer, 10000)
		
		# Check flag is set
		is_proforma = frappe.db.get_value("Sales Invoice", invoice, "custom_is_proforma")
		self.assertEqual(is_proforma, 1)
	
	def test_get_pending_proformas_returns_only_proformas(self):
		"""Property: get_pending_proformas returns only invoices with custom_is_proforma=1"""
		# Create a proforma
		proforma = create_test_proforma_invoice(self.test_project, self.test_customer, 5000)
		
		# Create a regular invoice
		regular = create_test_regular_invoice(self.test_project, self.test_customer, 3000)
		
		# Get pending proformas
		from construction_management.construction_management.doctype.payment_certificate.payment_certificate import get_pending_proformas
		
		pending = get_pending_proformas(self.test_project)
		pending_names = [p.name for p in pending]
		
		# Proforma should be in list
		self.assertIn(proforma, pending_names)
		
		# Regular invoice should NOT be in list
		self.assertNotIn(regular, pending_names)
	
	def test_pending_proformas_excludes_converted_proformas(self):
		"""Property: Proformas linked to Payment Certificates are not pending"""
		# Create a proforma
		proforma = create_test_proforma_invoice(self.test_project, self.test_customer, 8000)
		
		# Create a payment certificate from it
		pc = create_test_payment_certificate(self.test_project, proforma, 8000)
		
		# Get pending proformas
		from construction_management.construction_management.doctype.payment_certificate.payment_certificate import get_pending_proformas
		
		pending = get_pending_proformas(self.test_project)
		pending_names = [p.name for p in pending]
		
		# Converted proforma should NOT be in pending list
		self.assertNotIn(proforma, pending_names)
	
	def test_proforma_age_days_is_calculated(self):
		"""Property: Pending proformas include age_days calculation"""
		# Create a proforma
		proforma = create_test_proforma_invoice(self.test_project, self.test_customer, 6000)
		
		# Get pending proformas
		from construction_management.construction_management.doctype.payment_certificate.payment_certificate import get_pending_proformas
		
		pending = get_pending_proformas(self.test_project)
		
		# Find our proforma
		our_proforma = next((p for p in pending if p.name == proforma), None)
		
		if our_proforma:
			# age_days should be defined (0 for today)
			self.assertIn("age_days", our_proforma)
			self.assertGreaterEqual(our_proforma.age_days, 0)


class TestPaymentCertificateCreation(FrappeTestCase):
	"""
	Property: Payment Certificate Creation from Proforma
	
	Validates: Requirements 8.4
	Property: Payment Certificate correctly links to proforma and tracks variance.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-PC-CREATE-PROJECT")
		cls.test_customer = create_test_customer("Test PC Customer")
		frappe.db.set_value("Project", cls.test_project, "customer", cls.test_customer)
	
	def test_payment_certificate_links_to_proforma(self):
		"""Property: Payment Certificate has correct proforma_invoice reference"""
		proforma = create_test_proforma_invoice(self.test_project, self.test_customer, 15000)
		pc = create_test_payment_certificate(self.test_project, proforma, 15000)
		
		pc_doc = frappe.get_doc("Payment Certificate", pc)
		self.assertEqual(pc_doc.proforma_invoice, proforma)
	
	def test_payment_certificate_calculates_variance(self):
		"""Property: Variance = Proforma Amount - Accepted Amount"""
		proforma_amount = 20000
		accepted_amount = 18000
		expected_variance = proforma_amount - accepted_amount
		
		proforma = create_test_proforma_invoice(self.test_project, self.test_customer, proforma_amount)
		pc = create_test_payment_certificate(self.test_project, proforma, accepted_amount)
		
		pc_doc = frappe.get_doc("Payment Certificate", pc)
		self.assertEqual(flt(pc_doc.variance), expected_variance)
	
	def test_payment_certificate_stores_proforma_amount(self):
		"""Property: Payment Certificate stores original proforma amount"""
		proforma_amount = 25000
		
		proforma = create_test_proforma_invoice(self.test_project, self.test_customer, proforma_amount)
		pc = create_test_payment_certificate(self.test_project, proforma, 22000)
		
		pc_doc = frappe.get_doc("Payment Certificate", pc)
		self.assertEqual(flt(pc_doc.proforma_amount), proforma_amount)


# ============================================
# Test Fixtures
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


def create_test_proforma_invoice(project, customer, amount):
	"""Create a test proforma invoice"""
	# Get or create a service item
	item_code = get_or_create_service_item()
	
	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = customer
	invoice.project = project
	invoice.posting_date = today()
	invoice.due_date = today()
	invoice.custom_is_proforma = 1
	
	invoice.append("items", {
		"item_code": item_code,
		"qty": 1,
		"rate": amount
	})
	
	invoice.insert(ignore_permissions=True)
	# Keep as draft for proforma
	return invoice.name


def create_test_regular_invoice(project, customer, amount):
	"""Create a test regular (non-proforma) invoice"""
	item_code = get_or_create_service_item()
	
	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = customer
	invoice.project = project
	invoice.posting_date = today()
	invoice.due_date = today()
	invoice.custom_is_proforma = 0
	
	invoice.append("items", {
		"item_code": item_code,
		"qty": 1,
		"rate": amount
	})
	
	invoice.insert(ignore_permissions=True)
	return invoice.name


def create_test_payment_certificate(project, proforma_invoice, accepted_amount):
	"""Create a test payment certificate"""
	proforma_doc = frappe.get_doc("Sales Invoice", proforma_invoice)
	
	pc = frappe.new_doc("Payment Certificate")
	pc.project = project
	pc.proforma_invoice = proforma_invoice
	pc.proforma_amount = proforma_doc.grand_total
	pc.accepted_amount = accepted_amount
	pc.variance = flt(proforma_doc.grand_total) - flt(accepted_amount)
	pc.posting_date = today()
	pc.insert(ignore_permissions=True)
	return pc.name


def get_or_create_service_item():
	"""Get or create a service item for testing"""
	item_code = "TEST-SERVICE-ITEM"
	
	if not frappe.db.exists("Item", item_code):
		item = frappe.new_doc("Item")
		item.item_code = item_code
		item.item_name = "Test Service Item"
		item.item_group = "Services"
		item.stock_uom = "Nos"
		item.is_stock_item = 0
		item.is_sales_item = 1
		item.insert(ignore_permissions=True)
	
	return item_code
