# Copyright (c) 2026, Construction Management and Contributors
# See license.txt

# import frappe
from frappe.tests import IntegrationTestCase


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]



class IntegrationTestPaymentCertificate(IntegrationTestCase):
	"""
	Integration tests for PaymentCertificate.
	Use this class for testing interactions between multiple components.
	"""

	def setUp(self):
		self.company = "_Test Company"
		self.cost_center = "_Test Cost Center - _TC"
		self.project = "_Test Project"
		self.customer = "_Test Customer"
		self.item_code = "_Test Item"

		from frappe.test_runner import make_test_objects
		make_test_objects("Item", [{"item_code": self.item_code}])
		make_test_objects("Customer", [{"customer_name": self.customer}])
		
		# Ensure BOQ Settings exists
		if not frappe.db.exists("BOQ Settings", self.company):
			settings = frappe.new_doc("BOQ Settings")
			settings.company = self.company
			settings.default_retention_percentage = 10
			settings.retention_account = "Retention Account - _TC"
			settings.default_income_account = "Sales - _TC"
			settings.varience_item = self.item_code
			settings.insert()
			
		# Ensure Project exists
		if not frappe.db.exists("Project", self.project):
			p = frappe.new_doc("Project")
			p.project_name = self.project
			p.company = self.company
			p.customer = self.customer
			p.insert()
			
	def test_pc_submission(self):
		"""
		Test Payment Certificate submission workflow.
		Verifies fix for AttributeError: 'PaymentCertificate' object has no attribute 'company'
		"""
		# 1. Create Sales Order
		so = frappe.new_doc("Sales Order")
		so.company = self.company
		so.customer = self.customer
		so.project = self.project
		so.mock_append("items", {
			"item_code": self.item_code,
			"qty": 10,
			"rate": 1000,
			"boq_item": "Test BOQ Item", # Mock
			"bill_no": "Test Bill No"    # Mock
		})
		so.insert()
		so.submit()
		
		# 2. Create Payment Certificate
		pc = frappe.new_doc("Payment Certificate")
		pc.type = "Sales"
		pc.project = self.project
		pc.customer = self.customer
		pc.sales_order = so.name
		pc.append("items", {
			"boq_item": "Test BOQ Item",
			"bill_no": "Test Bill No",
			"description": "Test Item Description",
			"qty": 5,
			"rate": 1000,
			"amount": 5000,
			"accepted_amount": 5000,
			"sales_order_item": so.items[0].name
		})
		pc.insert()
		
		# 3. Submit Payment Certificate (This triggered the error)
		pc.submit()
		
		# 4. Verify Tax Invoice created
		self.assertEqual(pc.status, "Invoiced")
		self.assertTrue(pc.tax_invoice)
		
		ti = frappe.get_doc("Sales Invoice", pc.tax_invoice)
		self.assertEqual(ti.docstatus, 1)
		self.assertEqual(flt(ti.grand_total), 5000)
		self.assertEqual(ti.company, self.company)
		self.assertEqual(ti.project, self.project)

