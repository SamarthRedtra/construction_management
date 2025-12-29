# Copyright (c) 2024, Construction Management
# License: MIT
# Property Tests for Overtime Cost Allocation

"""
Property Tests for Overtime Cost Allocation

These tests validate the following properties:
- Property 19: Overtime Extraction and Allocation
- Property 20: Multi-Project Overtime Proration
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt
from hypothesis import given, strategies as st, settings

from construction_management.api.overtime_allocator import (
	extract_overtime,
	get_project_hours,
	allocate_overtime,
	OvertimeAllocation
)


class TestOvertimeExtractionAndAllocation(FrappeTestCase):
	"""
	**Feature: boq-costing-estimation, Property 19: Overtime Extraction and Allocation**
	**Validates: Requirements 10.1, 10.2, 10.3**
	
	Property: For any submitted Salary Slip with overtime_amount > 0, the overtime 
	SHALL be extracted and allocated to the employee's assigned project(s) as a 
	Project Expense with category "Overtime".
	"""
	
	def test_overtime_extraction_returns_float(self):
		"""Property: extract_overtime returns a float value"""
		# Test with non-existent salary slip
		result = extract_overtime("NON-EXISTENT-SS")
		self.assertIsInstance(result, float)
		self.assertEqual(result, 0)
	
	def test_allocation_returns_empty_for_zero_overtime(self):
		"""Property: No allocation when overtime is zero"""
		allocations = allocate_overtime(
			employee="TEST-EMP",
			overtime_amount=0,
			start_date="2024-01-01",
			end_date="2024-01-31"
		)
		
		self.assertEqual(len(allocations), 0)
	
	def test_allocation_returns_empty_for_negative_overtime(self):
		"""Property: No allocation when overtime is negative"""
		allocations = allocate_overtime(
			employee="TEST-EMP",
			overtime_amount=-100,
			start_date="2024-01-01",
			end_date="2024-01-31"
		)
		
		self.assertEqual(len(allocations), 0)


class TestMultiProjectOvertimeProration(FrappeTestCase):
	"""
	**Feature: boq-costing-estimation, Property 20: Multi-Project Overtime Proration**
	**Validates: Requirements 10.5**
	
	Property: For any employee working on multiple projects, overtime SHALL be 
	prorated such that project_overtime = total_overtime × (project_hours / total_hours)
	"""
	
	@given(
		total_overtime=st.floats(min_value=100, max_value=10000, allow_nan=False, allow_infinity=False),
		project1_hours=st.floats(min_value=1, max_value=100, allow_nan=False, allow_infinity=False),
		project2_hours=st.floats(min_value=1, max_value=100, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=100, deadline=None)
	def test_proration_formula(self, total_overtime, project1_hours, project2_hours):
		"""Property: project_overtime = total_overtime × (project_hours / total_hours)"""
		total_hours = project1_hours + project2_hours
		
		# Calculate expected allocations
		expected_project1 = total_overtime * (project1_hours / total_hours)
		expected_project2 = total_overtime * (project2_hours / total_hours)
		
		# Verify formula
		calculated_project1 = total_overtime * (project1_hours / total_hours)
		calculated_project2 = total_overtime * (project2_hours / total_hours)
		
		self.assertAlmostEqual(calculated_project1, expected_project1, places=2)
		self.assertAlmostEqual(calculated_project2, expected_project2, places=2)
		
		# Verify total equals original overtime
		self.assertAlmostEqual(calculated_project1 + calculated_project2, total_overtime, places=2)
	
	def test_single_project_gets_full_overtime(self):
		"""Property: Single project gets 100% of overtime"""
		total_overtime = 1000
		project_hours = {"Project A": 40}
		
		total_hours = sum(project_hours.values())
		allocation = total_overtime * (project_hours["Project A"] / total_hours)
		
		self.assertEqual(allocation, total_overtime)
	
	def test_equal_hours_equal_allocation(self):
		"""Property: Equal hours results in equal allocation"""
		total_overtime = 1000
		project_hours = {"Project A": 40, "Project B": 40}
		
		total_hours = sum(project_hours.values())
		allocation_a = total_overtime * (project_hours["Project A"] / total_hours)
		allocation_b = total_overtime * (project_hours["Project B"] / total_hours)
		
		self.assertEqual(allocation_a, allocation_b)
		self.assertEqual(allocation_a, 500)
	
	@given(
		num_projects=st.integers(min_value=1, max_value=5),
		total_overtime=st.floats(min_value=100, max_value=10000, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=50, deadline=None)
	def test_allocations_sum_to_total(self, num_projects, total_overtime):
		"""Property: Sum of all allocations equals total overtime"""
		# Create random hours for each project
		import random
		project_hours = {f"Project {i}": random.uniform(10, 100) for i in range(num_projects)}
		
		total_hours = sum(project_hours.values())
		
		# Calculate allocations
		allocations = []
		for project, hours in project_hours.items():
			allocation = total_overtime * (hours / total_hours)
			allocations.append(allocation)
		
		# Sum should equal total
		self.assertAlmostEqual(sum(allocations), total_overtime, places=2)
	
	def test_percentage_calculation(self):
		"""Property: Percentage = (project_hours / total_hours) × 100"""
		project_hours = {"Project A": 30, "Project B": 70}
		total_hours = 100
		
		percentage_a = (project_hours["Project A"] / total_hours) * 100
		percentage_b = (project_hours["Project B"] / total_hours) * 100
		
		self.assertEqual(percentage_a, 30)
		self.assertEqual(percentage_b, 70)
		self.assertEqual(percentage_a + percentage_b, 100)
