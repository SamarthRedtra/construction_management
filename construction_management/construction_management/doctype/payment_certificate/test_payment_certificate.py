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
			
	def test_pc_with_discounts(self):
		"""
		Test Payment Certificate with discounts and net certified amount.
		"""
		# 1. Create Sales Order
		so = frappe.new_doc("Sales Order")
		so.company = self.company
		so.customer = self.customer
		so.project = self.project
		so.append("items", {
			"item_code": self.item_code,
			"qty": 10,
			"rate": 1000,
			"boq_item": "Test BOQ Item",
			"bill_no": "Test Bill No",
			"warehouse": "_Test Warehouse - _TC"
		})
		so.insert()
		so.submit()
		
		# 2. Create Payment Certificate
		pc = frappe.new_doc("Payment Certificate")
		pc.type = "Sales"
		pc.project = self.project
		pc.customer = self.customer
		pc.sales_order = so.name
		pc.retention_percentage = 10
		pc.apply_discount_on = "Net Total"
		pc.discount_amount = 500
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
		
		# 3. Verify calculations
		# Total Accepted = 5000
		# Discount = 500
		# Net Total = 4500
		# Retention = 10% of 5000 = 500
		# Net Certified Amount (item) = 5000 - 500 = 4500
		
		self.assertEqual(flt(pc.proforma_amount), 5000)
		self.assertEqual(flt(pc.accepted_amount), 4500)
		self.assertEqual(flt(pc.retention_amount), 500)
		self.assertEqual(flt(pc.items[0].net_certified_amount), 4500)
		
		# 4. Submit and verify Sales Invoice
		pc.submit()
		
		ti = frappe.get_doc("Sales Invoice", pc.tax_invoice)
		self.assertEqual(ti.apply_discount_on, "Net Total")
		self.assertEqual(flt(ti.discount_amount), 500)
		# TI items: 1 gross, 1 variance (if any), 1 retention deduction
		# Since accepted_amount = 5000 (before extra discount), variance is 0
		# Total items should be: BOQ Item (5000), Retention Deduction (-500)
		# Total net amount before extra discount = 4500
		# After extra discount (500 on Net Total) = 4000? 
		# Wait, ERPNext's Sales Invoice apply_discount_on "Net Total" reduces total amount further.
		
		# Check if TI grand total matches or follows the logic
		# Accepted Amount in PC (4500) + Taxes - Extra Discount (already included in accepted_amount?)
		# Actually in my PC logic, accepted_amount is ALREADY discounted.
		# But in Sales Invoice, the discount is a separate field.
		# If I map it, it might double deduct if not careful.
		
		# Let's see: My PC .py says:
		# if self.apply_discount_on == "Net Total": self.accepted_amount = total_accepted - discount
		# Then I map to Sales Invoice.
		
		# If the Sales Invoice ALREADY has the discounted accepted_amount in its items, 
		# AND I set the discount fields, it will indeed double deduct.
		
		# WAIT, my create_tax_invoice uses pc_item.amount and pc_item.rate for the items, NOT the discounted rate.
		# So it should be fine.
		
		self.assertEqual(flt(ti.total), 4500) # (5000 item - 500 retention)


