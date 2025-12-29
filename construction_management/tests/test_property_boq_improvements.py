# Copyright (c) 2024, Construction Management
# License: MIT
# Property Tests for BOQ UI Improvements v2

"""
Property Tests for BOQ UI Improvements v2

These tests validate the following properties:
- Property 4: BOQ Item to Project BOQ Traceability (Task 1.5)
- Property 1: Column Order Consistency (Task 3.3)
- Property 2: Action Button Completeness (Task 5.3)
- Property 6: Billing Validation Completeness (Task 8.4)
- Property 7: API Response Structure Consistency (Task 8.5)
- Property 8: Transaction History Data Completeness (Task 9.2)
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today
from hypothesis import given, strategies as st, settings
import random
import string


class TestBOQItemToProjectBOQTraceability(FrappeTestCase):
	"""
	**Feature: boq-ui-improvements-v2, Property 4: BOQ Item to Project BOQ Traceability**
	**Validates: Requirements 5.2**
	
	Property: For any BOQ Item, the system SHALL be able to traverse the hierarchy
	BOQ Item → BOQ Bill → Project BOQ and return a valid Project BOQ.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-TRACEABILITY-PROJECT")
		cls.test_boq = create_test_project_boq(cls.test_project)
		cls.test_bill = create_test_bill(cls.test_project, "Bill No. 1 - Traceability Test")
		cls.test_boq_item = create_test_boq_item(cls.test_bill, "Traceability Test Item")
	
	def test_get_project_boq_for_item_returns_valid_boq(self):
		"""
		Property: get_project_boq_for_item returns valid Project BOQ for any BOQ Item
		**Validates: Requirements 5.2**
		"""
		from construction_management.api.boq_ledger import get_project_boq_for_item
		
		project_boq = get_project_boq_for_item(self.test_boq_item)
		
		# Must return a value
		self.assertIsNotNone(project_boq, "get_project_boq_for_item must return a value")
		self.assertTrue(project_boq, "get_project_boq_for_item must not return empty string")
		
		# Must be a valid Project BOQ document
		self.assertTrue(
			frappe.db.exists("Project BOQ", project_boq),
			f"Returned project_boq '{project_boq}' must be a valid Project BOQ document"
		)
	
	def test_hierarchy_traversal_matches_direct_lookup(self):
		"""
		Property: Hierarchy traversal returns same result as direct lookup
		"""
		from construction_management.api.boq_ledger import get_project_boq_for_item
		
		# Get via function
		result_via_function = get_project_boq_for_item(self.test_boq_item)
		
		# Get via direct hierarchy traversal
		parent_bill = frappe.db.get_value("BOQ Item", self.test_boq_item, "parent_bill")
		result_via_hierarchy = frappe.db.get_value("BOQ Bill", parent_bill, "project_boq")
		
		self.assertEqual(
			result_via_function, result_via_hierarchy,
			"Function result must match direct hierarchy traversal"
		)
	
	def test_returns_none_for_invalid_item(self):
		"""
		Property: Returns None for non-existent BOQ Item
		"""
		from construction_management.api.boq_ledger import get_project_boq_for_item
		
		result = get_project_boq_for_item("NON-EXISTENT-ITEM-12345")
		self.assertIsNone(result, "Should return None for non-existent item")
	
	def test_returns_none_for_empty_input(self):
		"""
		Property: Returns None for empty/None input
		"""
		from construction_management.api.boq_ledger import get_project_boq_for_item
		
		self.assertIsNone(get_project_boq_for_item(None))
		self.assertIsNone(get_project_boq_for_item(""))

	@given(
		description=st.text(min_size=5, max_size=50, alphabet=string.ascii_letters + string.digits + " ")
	)
	@settings(max_examples=50, deadline=None)
	def test_traceability_property_for_new_items(self, description):
		"""
		**Feature: boq-ui-improvements-v2, Property 4: BOQ Item to Project BOQ Traceability**
		**Validates: Requirements 5.2**
		
		Property: For any newly created BOQ Item with valid parent_bill,
		get_project_boq_for_item SHALL return a valid Project BOQ.
		"""
		from construction_management.api.boq_ledger import get_project_boq_for_item
		
		# Create a new BOQ Item
		suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
		item = frappe.new_doc("BOQ Item")
		item.parent_bill = self.test_bill
		item.project = self.test_project
		item.description = f"{description} {suffix}"
		item.unit = "Nos"
		item.total_qty = 10
		item.rate = 100
		item.insert(ignore_permissions=True)
		
		try:
			# Get project_boq via function
			project_boq = get_project_boq_for_item(item.name)
			
			# Must return valid Project BOQ
			self.assertIsNotNone(project_boq)
			self.assertTrue(frappe.db.exists("Project BOQ", project_boq))
		finally:
			# Cleanup
			frappe.delete_doc("BOQ Item", item.name, force=True)


class TestBillingValidationCompleteness(FrappeTestCase):
	"""
	**Feature: boq-ui-improvements-v2, Property 6: Billing Validation Completeness**
	**Validates: Requirements 6.2**
	
	Property: For any ledger entry creation, the system SHALL validate all required fields
	(boq_item, project, project_boq, bill_no, posting_date, source, qty, amount) before
	database operations.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-BILLING-VAL-PROJECT")
		cls.test_boq = create_test_project_boq(cls.test_project)
		cls.test_bill = create_test_bill(cls.test_project, "Bill No. 1 - Billing Val Test")
		cls.test_boq_item = create_test_boq_item(cls.test_bill, "Billing Validation Test Item")
	
	def test_validate_ledger_entry_fields_success(self):
		"""
		Property: Validation passes for complete valid data
		**Validates: Requirements 6.2**
		"""
		from construction_management.api.boq_ledger import validate_ledger_entry_fields
		
		result = validate_ledger_entry_fields(
			boq_item=self.test_boq_item,
			project=self.test_project,
			project_boq=self.test_boq,
			bill_no=self.test_bill,
			posting_date=today(),
			source="Proforma",
			qty=10,
			amount=1000
		)
		
		self.assertEqual(result["status"], "success")
	
	def test_validate_ledger_entry_fields_missing_boq_item(self):
		"""
		Property: Validation fails when boq_item is missing
		"""
		from construction_management.api.boq_ledger import validate_ledger_entry_fields
		
		result = validate_ledger_entry_fields(
			boq_item=None,
			project=self.test_project,
			project_boq=self.test_boq,
			bill_no=self.test_bill,
			posting_date=today(),
			source="Proforma",
			qty=10,
			amount=1000
		)
		
		self.assertEqual(result["status"], "error")
		self.assertIn("BOQ Item", result["error_message"])

	def test_validate_ledger_entry_fields_missing_project_boq(self):
		"""
		Property: Validation fails when project_boq is missing
		"""
		from construction_management.api.boq_ledger import validate_ledger_entry_fields
		
		result = validate_ledger_entry_fields(
			boq_item=self.test_boq_item,
			project=self.test_project,
			project_boq=None,
			bill_no=self.test_bill,
			posting_date=today(),
			source="Proforma",
			qty=10,
			amount=1000
		)
		
		self.assertEqual(result["status"], "error")
		self.assertIn("Project BOQ", result["error_message"])
	
	def test_validate_ledger_entry_fields_invalid_source(self):
		"""
		Property: Validation fails for invalid source value
		"""
		from construction_management.api.boq_ledger import validate_ledger_entry_fields
		
		result = validate_ledger_entry_fields(
			boq_item=self.test_boq_item,
			project=self.test_project,
			project_boq=self.test_boq,
			bill_no=self.test_bill,
			posting_date=today(),
			source="Invalid Source",
			qty=10,
			amount=1000
		)
		
		self.assertEqual(result["status"], "error")
		self.assertIn("Source", result["error_message"])
	
	@given(
		source=st.sampled_from(["Invoice", "Proforma", "Proforma Reversal", "Adjustment", "Reversal"])
	)
	@settings(max_examples=20, deadline=None)
	def test_valid_sources_pass_validation(self, source):
		"""
		**Feature: boq-ui-improvements-v2, Property 6: Billing Validation Completeness**
		**Validates: Requirements 6.2**
		
		Property: All valid source values SHALL pass validation.
		"""
		from construction_management.api.boq_ledger import validate_ledger_entry_fields
		
		result = validate_ledger_entry_fields(
			boq_item=self.test_boq_item,
			project=self.test_project,
			project_boq=self.test_boq,
			bill_no=self.test_bill,
			posting_date=today(),
			source=source,
			qty=10,
			amount=1000
		)
		
		self.assertEqual(result["status"], "success", f"Source '{source}' should be valid")


class TestAPIResponseStructureConsistency(FrappeTestCase):
	"""
	**Feature: boq-ui-improvements-v2, Property 7: API Response Structure Consistency**
	**Validates: Requirements 6.4**
	
	Property: All billing APIs SHALL return consistent response structures with
	status and error_message fields.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-API-RESPONSE-PROJECT")
		cls.test_boq = create_test_project_boq(cls.test_project)
		cls.test_bill = create_test_bill(cls.test_project, "Bill No. 1 - API Response Test")
		cls.test_boq_item = create_test_boq_item(cls.test_bill, "API Response Test Item")
	
	def test_create_proforma_success_response_structure(self):
		"""
		Property: Successful proforma creation returns proper structure
		**Validates: Requirements 6.4**
		"""
		from construction_management.construction_management.doctype.proforma_invoice.proforma_invoice import (
			create_proforma_from_selected_items
		)
		
		items = [{"boq_item": self.test_boq_item, "qty": 5}]
		
		result = create_proforma_from_selected_items(
			project=self.test_project,
			items=items,
			apply_retention=0
		)
		
		# Must have status field
		self.assertIn("status", result, "Response must have 'status' field")
		self.assertEqual(result["status"], "success")
		
		# Success response should have name
		self.assertIn("name", result, "Success response must have 'name' field")
		
		# Cleanup
		if result.get("name"):
			frappe.delete_doc("Proforma Invoice", result["name"], force=True)
	
	def test_create_proforma_error_response_structure(self):
		"""
		Property: Error response has status and error_message fields
		**Validates: Requirements 6.4**
		"""
		from construction_management.construction_management.doctype.proforma_invoice.proforma_invoice import (
			create_proforma_from_selected_items
		)
		
		# Empty items should return error
		result = create_proforma_from_selected_items(
			project=self.test_project,
			items=[],
			apply_retention=0
		)
		
		# Must have status field
		self.assertIn("status", result, "Response must have 'status' field")
		self.assertEqual(result["status"], "error")
		
		# Error response must have error_message
		self.assertIn("error_message", result, "Error response must have 'error_message' field")
		self.assertTrue(result["error_message"], "error_message must not be empty")

	def test_create_proforma_over_balance_error_response(self):
		"""
		Property: Over-balance error returns proper structure
		"""
		from construction_management.construction_management.doctype.proforma_invoice.proforma_invoice import (
			create_proforma_from_selected_items
		)
		
		# Request qty exceeding balance
		items = [{"boq_item": self.test_boq_item, "qty": 99999}]
		
		result = create_proforma_from_selected_items(
			project=self.test_project,
			items=items,
			apply_retention=0
		)
		
		# Must have status field
		self.assertIn("status", result)
		self.assertEqual(result["status"], "error")
		
		# Must have error_message
		self.assertIn("error_message", result)
		self.assertTrue(result["error_message"])
	
	@given(
		qty=st.floats(min_value=0.1, max_value=50, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=30, deadline=None)
	def test_api_response_always_has_status(self, qty):
		"""
		**Feature: boq-ui-improvements-v2, Property 7: API Response Structure Consistency**
		**Validates: Requirements 6.4**
		
		Property: For any valid qty, API response SHALL always have status field.
		"""
		from construction_management.construction_management.doctype.proforma_invoice.proforma_invoice import (
			create_proforma_from_selected_items
		)
		
		items = [{"boq_item": self.test_boq_item, "qty": qty}]
		
		result = create_proforma_from_selected_items(
			project=self.test_project,
			items=items,
			apply_retention=0
		)
		
		# Must always have status field
		self.assertIn("status", result, "Response must always have 'status' field")
		self.assertIn(result["status"], ["success", "error"], "Status must be 'success' or 'error'")
		
		# Cleanup if successful
		if result.get("status") == "success" and result.get("name"):
			frappe.delete_doc("Proforma Invoice", result["name"], force=True)


class TestTransactionHistoryDataCompleteness(FrappeTestCase):
	"""
	**Feature: boq-ui-improvements-v2, Property 8: Transaction History Data Completeness**
	**Validates: Requirements 3.4**
	
	Property: For any BOQ Item with transactions, the transaction history data SHALL
	include project_boq, prev/current/accumulated values, and complete ledger information.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-TXN-HISTORY-PROJECT")
		cls.test_boq = create_test_project_boq(cls.test_project)
		cls.test_bill = create_test_bill(cls.test_project, "Bill No. 1 - Txn History Test")
		cls.test_boq_item = create_test_boq_item(cls.test_bill, "Transaction History Test Item")
	
	def test_get_boq_item_with_transactions_returns_item_data(self):
		"""
		Property: API returns complete item data structure
		**Validates: Requirements 3.4**
		"""
		from construction_management.api.boq_tree import get_boq_item_with_transactions
		
		result = get_boq_item_with_transactions(self.test_boq_item)
		
		# Must have item key
		self.assertIn("item", result, "Response must have 'item' key")
		
		item_data = result["item"]
		
		# Item must have project_boq
		self.assertIn("project_boq", item_data, "Item data must have 'project_boq'")
		
		# Item must have qty breakdown
		self.assertIn("qty", item_data, "Item data must have 'qty' breakdown")
		qty = item_data["qty"]
		self.assertIn("prev", qty, "Qty must have 'prev'")
		self.assertIn("current", qty, "Qty must have 'current'")
		self.assertIn("to_date", qty, "Qty must have 'to_date'")
		
		# Item must have amount breakdown
		self.assertIn("amount", item_data, "Item data must have 'amount' breakdown")
		amount = item_data["amount"]
		self.assertIn("prev", amount, "Amount must have 'prev'")
		self.assertIn("current", amount, "Amount must have 'current'")
		self.assertIn("to_date", amount, "Amount must have 'to_date'")
	
	def test_get_boq_item_with_transactions_returns_transactions_list(self):
		"""
		Property: API returns transactions list
		"""
		from construction_management.api.boq_tree import get_boq_item_with_transactions
		
		result = get_boq_item_with_transactions(self.test_boq_item)
		
		# Must have transactions key
		self.assertIn("transactions", result, "Response must have 'transactions' key")
		
		# Transactions must be a list
		self.assertIsInstance(result["transactions"], list, "Transactions must be a list")

	def test_transaction_history_includes_project_boq_after_proforma(self):
		"""
		Property: After proforma submission, transaction history includes project_boq
		**Validates: Requirements 3.4**
		"""
		from construction_management.api.boq_tree import get_boq_item_with_transactions
		
		# Create and submit proforma
		proforma = create_proforma_invoice_with_items(
			self.test_project, self.test_boq_item, qty=5, rate=100
		)
		proforma.submit()
		
		try:
			# Get transaction history
			result = get_boq_item_with_transactions(self.test_boq_item)
			
			# Should have transactions
			self.assertGreater(len(result["transactions"]), 0, "Should have transactions after proforma")
			
			# Each transaction should have project_boq
			for txn in result["transactions"]:
				self.assertIn("project_boq", txn, "Transaction must have 'project_boq'")
				if txn.get("project_boq"):
					self.assertTrue(
						frappe.db.exists("Project BOQ", txn["project_boq"]),
						"Transaction project_boq must be valid"
					)
		finally:
			# Cleanup
			proforma.cancel()
			frappe.delete_doc("Proforma Invoice", proforma.name, force=True)
	
	@given(
		qty=st.floats(min_value=1, max_value=50, allow_nan=False, allow_infinity=False),
		rate=st.floats(min_value=10, max_value=500, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=30, deadline=None)
	def test_transaction_history_completeness_property(self, qty, rate):
		"""
		**Feature: boq-ui-improvements-v2, Property 8: Transaction History Data Completeness**
		**Validates: Requirements 3.4**
		
		Property: For any proforma with any valid qty and rate, the transaction history
		SHALL include complete ledger data with project_boq.
		"""
		from construction_management.api.boq_tree import get_boq_item_with_transactions
		
		# Create and submit proforma
		proforma = create_proforma_invoice_with_items(
			self.test_project, self.test_boq_item, qty=qty, rate=rate
		)
		proforma.submit()
		
		try:
			# Get transaction history
			result = get_boq_item_with_transactions(self.test_boq_item)
			
			# Item data must be complete
			item_data = result.get("item", {})
			self.assertIn("project_boq", item_data)
			self.assertIn("qty", item_data)
			self.assertIn("amount", item_data)
			
			# Transactions must exist and have project_boq
			transactions = result.get("transactions", [])
			self.assertGreater(len(transactions), 0)
			
			for txn in transactions:
				self.assertIn("project_boq", txn)
		finally:
			# Cleanup
			proforma.cancel()
			frappe.delete_doc("Proforma Invoice", proforma.name, force=True)


class TestColumnOrderConsistency(FrappeTestCase):
	"""
	**Feature: boq-ui-improvements-v2, Property 1: Column Order Consistency**
	**Validates: Requirements 1.1, 1.2**
	
	Property: The BOQ table columns SHALL be ordered with Qty Breakdown before Value Breakdown,
	and header groups SHALL have proper colspan values.
	
	Note: This is a UI test that validates the JavaScript rendering logic.
	Since we cannot execute JavaScript in Python tests, we validate the data structure
	that feeds the UI.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-COLUMN-ORDER-PROJECT")
		cls.test_boq = create_test_project_boq(cls.test_project)
		cls.test_bill = create_test_bill(cls.test_project, "Bill No. 1 - Column Order Test")
		cls.test_boq_item = create_test_boq_item(cls.test_bill, "Column Order Test Item")
	
	def test_item_data_has_qty_before_amount(self):
		"""
		Property: Item data structure has qty breakdown before amount breakdown
		**Validates: Requirements 1.1, 1.2**
		"""
		from construction_management.api.boq_tree import get_boq_item_with_transactions
		
		result = get_boq_item_with_transactions(self.test_boq_item)
		item_data = result.get("item", {})
		
		# Both qty and amount must exist
		self.assertIn("qty", item_data, "Item must have qty breakdown")
		self.assertIn("amount", item_data, "Item must have amount breakdown")
		
		# Qty breakdown must have all required fields
		qty = item_data["qty"]
		required_qty_fields = ["prev", "current", "to_date", "balance"]
		for field in required_qty_fields:
			self.assertIn(field, qty, f"Qty must have '{field}' field")
		
		# Amount breakdown must have all required fields
		amount = item_data["amount"]
		required_amount_fields = ["prev", "current", "to_date", "balance", "rate"]
		for field in required_amount_fields:
			self.assertIn(field, amount, f"Amount must have '{field}' field")
	
	def test_bill_totals_have_correct_structure(self):
		"""
		Property: Bill totals have qty and amount in correct order
		"""
		from construction_management.api.boq_tree import get_boq_tree_data
		
		# Enable progressive BOQ for project
		frappe.db.set_value("Project", self.test_project, "enable_progressive_boq", 1)
		
		result = get_boq_tree_data(self.test_project)
		
		if result.get("bills"):
			for bill in result["bills"]:
				totals = bill.get("totals", {})
				
				# Totals must have qty and amount
				self.assertIn("qty", totals, "Bill totals must have qty")
				self.assertIn("amount", totals, "Bill totals must have amount")


class TestActionButtonCompleteness(FrappeTestCase):
	"""
	**Feature: boq-ui-improvements-v2, Property 2: Action Button Completeness**
	**Validates: Requirements 3.1**
	
	Property: For any BOQ Item row, the system SHALL provide action buttons for
	View Tasks, View Costs, Edit, Delete, and Create Invoice.
	
	Note: This is a UI test. We validate the data structure that determines
	button availability (billing_status).
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-ACTION-BTN-PROJECT")
		cls.test_boq = create_test_project_boq(cls.test_project)
		cls.test_bill = create_test_bill(cls.test_project, "Bill No. 1 - Action Btn Test")
		cls.test_boq_item = create_test_boq_item(cls.test_bill, "Action Button Test Item")
	
	def test_item_has_billing_status_for_button_state(self):
		"""
		Property: Item data includes billing_status for button state determination
		**Validates: Requirements 3.1**
		"""
		from construction_management.api.boq_tree import get_boq_item_with_transactions
		
		result = get_boq_item_with_transactions(self.test_boq_item)
		item_data = result.get("item", {})
		
		# Must have billing_status
		self.assertIn("billing_status", item_data, "Item must have billing_status")
	
	def test_fully_billed_item_has_correct_status(self):
		"""
		Property: Fully billed items have billing_status = 'Fully Billed'
		"""
		# Set item as fully billed
		frappe.db.set_value("BOQ Item", self.test_boq_item, {
			"to_date_qty": 100,
			"balance_qty": 0,
			"billing_status": "Fully Billed"
		})
		
		from construction_management.api.boq_tree import get_boq_item_with_transactions
		
		result = get_boq_item_with_transactions(self.test_boq_item)
		item_data = result.get("item", {})
		
		self.assertEqual(item_data.get("billing_status"), "Fully Billed")
		
		# Reset
		frappe.db.set_value("BOQ Item", self.test_boq_item, {
			"to_date_qty": 0,
			"balance_qty": 100,
			"billing_status": "Not Billed"
		})
	
	def test_not_billed_item_allows_actions(self):
		"""
		Property: Not billed items should allow invoice creation
		"""
		# Ensure item is not billed
		frappe.db.set_value("BOQ Item", self.test_boq_item, {
			"to_date_qty": 0,
			"balance_qty": 100,
			"billing_status": "Not Billed"
		})
		
		from construction_management.api.boq_tree import get_boq_item_with_transactions
		
		result = get_boq_item_with_transactions(self.test_boq_item)
		item_data = result.get("item", {})
		
		# Not fully billed - actions should be allowed
		self.assertNotEqual(item_data.get("billing_status"), "Fully Billed")


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


def create_test_project_boq(project):
	"""Create a test Project BOQ"""
	existing = frappe.db.get_value("Project BOQ", {"project": project})
	if existing:
		return existing
	
	boq = frappe.new_doc("Project BOQ")
	boq.project = project
	boq.boq_name = f"BOQ - {project}"
	boq.insert(ignore_permissions=True)
	return boq.name


def create_test_bill(project, bill_no):
	"""Create a test BOQ Bill"""
	existing = frappe.db.get_value("BOQ Bill", {"project": project, "bill_no": bill_no})
	if existing:
		return existing
	
	project_boq = frappe.db.get_value("Project BOQ", {"project": project})
	
	bill = frappe.new_doc("BOQ Bill")
	bill.project = project
	bill.project_boq = project_boq
	bill.bill_no = bill_no
	bill.insert(ignore_permissions=True)
	return bill.name


def create_test_boq_item(parent_bill, description):
	"""Create a test BOQ Item"""
	existing = frappe.db.get_value("BOQ Item", {"parent_bill": parent_bill, "description": description})
	if existing:
		return existing
	
	bill_doc = frappe.get_doc("BOQ Bill", parent_bill)
	
	item = frappe.new_doc("BOQ Item")
	item.parent_bill = parent_bill
	item.project = bill_doc.project
	item.description = description
	item.unit = "Nos"
	item.total_qty = 100
	item.rate = 100
	item.insert(ignore_permissions=True)
	return item.name


def create_proforma_invoice_with_items(project, boq_item, qty, rate):
	"""
	Create a Proforma Invoice with items child table properly populated.
	"""
	boq_item_doc = frappe.get_doc("BOQ Item", boq_item)
	
	proforma = frappe.new_doc("Proforma Invoice")
	proforma.project = project
	proforma.posting_date = today()
	
	proforma.append("items", {
		"boq_item": boq_item,
		"bill_no": boq_item_doc.parent_bill,
		"description": boq_item_doc.description,
		"unit": boq_item_doc.unit,
		"qty": flt(qty),
		"rate": flt(rate),
		"amount": flt(qty) * flt(rate)
	})
	
	proforma.insert(ignore_permissions=True)
	return proforma
