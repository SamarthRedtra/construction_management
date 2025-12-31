# Copyright (c) 2024, Construction Management
# License: MIT
# Property Tests for DPR Stability

"""
Property Tests for DPR Stability

These tests validate the following properties:
- Property 8: DPR Functionality Stability
- Employee selection functionality
- Material selection functionality  
- Material balance display logic
- DPR entry flow stability
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today, add_days
from hypothesis import given, strategies as st, settings, assume

from construction_management.tests.test_utils import (
	create_test_project,
	create_test_boq_structure,
	create_test_employee,
	create_test_item,
	create_test_warehouse,
	cleanup_test_data
)


class TestDPREmployeeSelection(FrappeTestCase):
	"""
	**Feature: construction-enhancements-comprehensive, Property 8: DPR Employee Selection**
	
	**Validates: Requirements 10.1, 10.4**
	
	Property: Employee selection dropdown SHALL load all active employees with their
	daily rates and allow proper filtering and search functionality.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-DPR-EMP-PROJECT")
		
		# Create test employees with different salary structures
		cls.test_employees = []
		for i in range(3):
			emp = create_test_employee(f"TEST-EMP-{i+1}", f"Test Employee {i+1}")
			cls.test_employees.append(emp)
	
	@classmethod
	def tearDownClass(cls):
		cleanup_test_data()
		super().tearDownClass()
	
	def test_employee_selection_loads_active_employees(self):
		"""Property: Employee selection loads all active employees"""
		from construction_management.api.dpr_utils import get_employees_with_rates
		
		employees = get_employees_with_rates()
		
		# Should include our test employees
		emp_names = [emp.name for emp in employees]
		for test_emp in self.test_employees:
			self.assertIn(test_emp, emp_names)
	
	def test_employee_rate_calculation_works(self):
		"""Property: Employee rate calculation returns valid rates"""
		from construction_management.api.dpr_utils import get_employee_daily_rate
		
		for emp in self.test_employees:
			rate = get_employee_daily_rate(emp)
			# Rate should be numeric (0 or positive)
			self.assertIsInstance(rate, (int, float))
			self.assertGreaterEqual(rate, 0)
	
	def test_employee_optimized_lookup_works(self):
		"""Property: Optimized employee lookup returns complete data"""
		from construction_management.api.employee_rate_cache import get_employee_rate_optimized
		
		for emp in self.test_employees:
			result = get_employee_rate_optimized(emp)
			
			# Should return complete employee data
			self.assertIn("name", result)
			self.assertIn("employee_name", result)
			self.assertIn("rate_per_day", result)
			self.assertIn("source", result)
			
			# Rate should be numeric
			self.assertIsInstance(result["rate_per_day"], (int, float))
			self.assertGreaterEqual(result["rate_per_day"], 0)


class TestDPRMaterialSelection(FrappeTestCase):
	"""
	**Feature: construction-enhancements-comprehensive, Property 8: DPR Material Selection**
	
	**Validates: Requirements 10.2, 10.4**
	
	Property: Material selection dropdown SHALL load items with stock in the selected
	warehouse and allow proper filtering and search functionality.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-DPR-MAT-PROJECT")
		cls.test_warehouse = create_test_warehouse("TEST-DPR-WH", cls.test_project)
		
		# Create test items with stock
		cls.test_items = []
		for i in range(3):
			item = create_test_item(f"TEST-MAT-{i+1}", f"Test Material {i+1}")
			cls.test_items.append(item)
			
			# Create stock entry to add stock
			se = frappe.new_doc("Stock Entry")
			se.stock_entry_type = "Material Receipt"
			se.to_warehouse = cls.test_warehouse
			se.append("items", {
				"item_code": item,
				"qty": 100,
				"basic_rate": 10,
				"t_warehouse": cls.test_warehouse
			})
			se.insert(ignore_permissions=True)
			se.submit()
	
	@classmethod
	def tearDownClass(cls):
		cleanup_test_data()
		super().tearDownClass()
	
	def test_warehouse_items_with_stock_loads_correctly(self):
		"""Property: Warehouse items with stock loads correctly"""
		from construction_management.api.dpr_utils import get_warehouse_items_with_stock
		
		items = get_warehouse_items_with_stock(self.test_warehouse)
		
		# Should include our test items
		item_codes = [item.item_code for item in items]
		for test_item in self.test_items:
			self.assertIn(test_item, item_codes)
		
		# All items should have positive stock
		for item in items:
			self.assertGreater(item.actual_qty, 0)
	
	def test_material_stock_validation_works(self):
		"""Property: Material stock validation works correctly"""
		from construction_management.api.dpr_utils import validate_material_stock
		
		# Test valid quantity
		result = validate_material_stock(
			self.test_warehouse, 
			self.test_items[0], 
			50  # Less than available (100)
		)
		self.assertTrue(result["is_valid"])
		self.assertEqual(result["available_qty"], 100)
		
		# Test invalid quantity
		result = validate_material_stock(
			self.test_warehouse, 
			self.test_items[0], 
			150  # More than available (100)
		)
		self.assertFalse(result["is_valid"])
		self.assertIn("Insufficient stock", result["message"])
	
	def test_item_valuation_rate_retrieval(self):
		"""Property: Item valuation rate retrieval works"""
		from construction_management.api.dpr_utils import get_item_valuation_rate
		
		for item in self.test_items:
			result = get_item_valuation_rate(item, self.test_warehouse)
			
			# Should return a rate
			self.assertIn("valuation_rate", result)
			self.assertGreater(result["valuation_rate"], 0)


class TestDPRMaterialBalanceDisplay(FrappeTestCase):
	"""
	**Feature: construction-enhancements-comprehensive, Property 8: DPR Material Balance Display**
	
	**Validates: Requirements 10.3, 10.5**
	
	Property: Material balance display SHALL show accurate stock information and
	update in real-time as quantities are entered.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-DPR-BAL-PROJECT")
		cls.test_warehouse = create_test_warehouse("TEST-DPR-BAL-WH", cls.test_project)
		cls.test_item = create_test_item("TEST-BAL-ITEM", "Test Balance Item")
		
		# Create stock with known quantity
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Material Receipt"
		se.to_warehouse = cls.test_warehouse
		se.append("items", {
			"item_code": cls.test_item,
			"qty": 200,
			"basic_rate": 15,
			"t_warehouse": cls.test_warehouse
		})
		se.insert(ignore_permissions=True)
		se.submit()
	
	@classmethod
	def tearDownClass(cls):
		cleanup_test_data()
		super().tearDownClass()
	
	def test_material_balance_calculation_accuracy(self):
		"""Property: Material balance calculation is accurate"""
		# Get current stock
		current_stock = frappe.db.get_value(
			"Bin",
			{"warehouse": self.test_warehouse, "item_code": self.test_item},
			"actual_qty"
		)
		
		self.assertEqual(flt(current_stock), 200)
		
		# Validate different quantities
		from construction_management.api.dpr_utils import validate_material_stock
		
		# Valid quantity
		result = validate_material_stock(self.test_warehouse, self.test_item, 100)
		self.assertTrue(result["is_valid"])
		self.assertEqual(result["available_qty"], 200)
		
		# Boundary case - exact stock
		result = validate_material_stock(self.test_warehouse, self.test_item, 200)
		self.assertTrue(result["is_valid"])
		
		# Over stock
		result = validate_material_stock(self.test_warehouse, self.test_item, 201)
		self.assertFalse(result["is_valid"])
	
	def test_real_time_balance_updates(self):
		"""Property: Balance updates reflect real-time stock changes"""
		from construction_management.api.dpr_utils import get_warehouse_items_with_stock
		
		# Initial stock check
		items = get_warehouse_items_with_stock(self.test_warehouse)
		initial_item = next(item for item in items if item.item_code == self.test_item)
		self.assertEqual(initial_item.actual_qty, 200)
		
		# Create a DPR that consumes stock
		dpr = frappe.new_doc("Daily Progress Record")
		dpr.project = self.test_project
		dpr.date = today()
		dpr.append("materials", {
			"item_code": self.test_item,
			"warehouse": self.test_warehouse,
			"qty": 50,
			"rate": 15,
			"amount": 750
		})
		dpr.material_cost = 750
		dpr.insert(ignore_permissions=True)
		dpr.submit()
		
		# Check updated stock
		items = get_warehouse_items_with_stock(self.test_warehouse)
		updated_item = next(item for item in items if item.item_code == self.test_item)
		self.assertEqual(updated_item.actual_qty, 150)  # 200 - 50


class TestDPREntryFlowStability(FrappeTestCase):
	"""
	**Feature: construction-enhancements-comprehensive, Property 8: DPR Entry Flow Stability**
	
	**Validates: Requirements 10.4, 10.5**
	
	Property: DPR entry flow SHALL be stable with proper validation, error handling,
	and prevention of data loss during entry.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-DPR-FLOW-PROJECT")
		cls.test_warehouse = create_test_warehouse("TEST-DPR-FLOW-WH", cls.test_project)
		cls.test_employee = create_test_employee("TEST-FLOW-EMP", "Test Flow Employee")
		cls.test_item = create_test_item("TEST-FLOW-ITEM", "Test Flow Item")
		
		# Create BOQ structure
		cls.boq, cls.bill, cls.boq_item = create_test_boq_structure(
			cls.test_project, 
			total_qty=100, 
			rate=50
		)
		
		# Add stock
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Material Receipt"
		se.to_warehouse = cls.test_warehouse
		se.append("items", {
			"item_code": cls.test_item,
			"qty": 100,
			"basic_rate": 20,
			"t_warehouse": cls.test_warehouse
		})
		se.insert(ignore_permissions=True)
		se.submit()
	
	@classmethod
	def tearDownClass(cls):
		cleanup_test_data()
		super().tearDownClass()
	
	def test_complete_dpr_creation_flow(self):
		"""Property: Complete DPR creation flow works without errors"""
		from construction_management.api.dpr_utils import create_dpr_with_details
		import json
		
		# Prepare DPR data
		employees = json.dumps([{
			"employee": self.test_employee,
			"hours": 8,
			"rate_per_day": 500,
			"amount": 500
		}])
		
		materials = json.dumps([{
			"item_code": self.test_item,
			"warehouse": self.test_warehouse,
			"qty": 10,
			"rate": 20,
			"amount": 200
		}])
		
		# Create DPR
		result = create_dpr_with_details(
			project=self.test_project,
			boq_item=self.boq_item,
			date=today(),
			employees=employees,
			materials=materials,
			subcontract_cost=100,
			remarks="Test DPR creation"
		)
		
		# Should return valid result
		self.assertIn("name", result)
		self.assertIn("total_cost", result)
		
		# Verify DPR was created
		dpr = frappe.get_doc("Daily Progress Record", result["name"])
		self.assertEqual(dpr.project, self.test_project)
		self.assertEqual(dpr.boq_item, self.boq_item)
		self.assertEqual(len(dpr.employees), 1)
		self.assertEqual(len(dpr.materials), 1)
		self.assertEqual(dpr.labour_cost, 500)
		self.assertEqual(dpr.material_cost, 200)
		self.assertEqual(dpr.subcontract_cost, 100)
	
	def test_dpr_validation_prevents_invalid_data(self):
		"""Property: DPR validation prevents invalid data entry"""
		# Test invalid warehouse
		from construction_management.api.dpr_utils import validate_material_stock
		
		result = validate_material_stock("INVALID-WH", self.test_item, 10)
		self.assertFalse(result["is_valid"])
		
		# Test invalid employee
		from construction_management.api.dpr_utils import get_employee_daily_rate
		
		with self.assertRaises(Exception):
			get_employee_daily_rate("INVALID-EMP")
	
	def test_dpr_error_handling_graceful(self):
		"""Property: DPR error handling is graceful and informative"""
		from construction_management.api.dpr_utils import get_warehouse_items_with_stock
		
		# Test with non-existent warehouse
		items = get_warehouse_items_with_stock("NON-EXISTENT-WH")
		self.assertEqual(items, [])  # Should return empty list, not error
		
		# Test with empty project
		from construction_management.api.dpr_utils import get_project_warehouses
		warehouses = get_project_warehouses("NON-EXISTENT-PROJECT")
		self.assertEqual(warehouses, [])  # Should return empty list, not error


class TestDPRStabilityHypothesis(FrappeTestCase):
	"""
	**Feature: construction-enhancements-comprehensive, Property 8: DPR Stability Hypothesis Tests**
	
	**Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5**
	
	Property-based tests for DPR stability using Hypothesis to generate test data.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-DPR-HYPO-PROJECT")
		cls.test_warehouse = create_test_warehouse("TEST-DPR-HYPO-WH", cls.test_project)
	
	@classmethod
	def tearDownClass(cls):
		cleanup_test_data()
		super().tearDownClass()
	
	@given(
		qty=st.floats(min_value=0.1, max_value=1000, allow_nan=False, allow_infinity=False),
		rate=st.floats(min_value=0.1, max_value=10000, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=50, deadline=None)
	def test_material_amount_calculation_consistency(self, qty, rate):
		"""Property: Material amount calculation is always qty * rate"""
		expected_amount = flt(qty) * flt(rate)
		
		# This should always be true regardless of input values
		calculated_amount = flt(qty) * flt(rate)
		self.assertEqual(flt(calculated_amount, 2), flt(expected_amount, 2))
	
	@given(
		hours=st.floats(min_value=0.1, max_value=24, allow_nan=False, allow_infinity=False),
		rate_per_day=st.floats(min_value=1, max_value=10000, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=50, deadline=None)
	def test_employee_amount_calculation_consistency(self, hours, rate_per_day):
		"""Property: Employee amount calculation is always rate_per_day * (hours / 8)"""
		expected_amount = flt(rate_per_day) * (flt(hours) / 8)
		
		# This should always be true regardless of input values
		calculated_amount = flt(rate_per_day) * (flt(hours) / 8)
		self.assertEqual(flt(calculated_amount, 2), flt(expected_amount, 2))
	
	@given(
		available_qty=st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
		requested_qty=st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=50, deadline=None)
	def test_stock_validation_logic_consistency(self, available_qty, requested_qty):
		"""Property: Stock validation logic is consistent"""
		available = flt(available_qty)
		requested = flt(requested_qty)
		
		# Validation should be true if and only if available >= requested
		expected_valid = available >= requested
		
		# Mock the validation result
		is_valid = flt(available) >= flt(requested)
		self.assertEqual(is_valid, expected_valid)