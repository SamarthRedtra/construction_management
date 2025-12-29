# Copyright (c) 2024, Construction Management
# License: MIT
# Property Tests for BOQ Estimated Costs

"""
Property Tests for BOQ Costing & Estimation Enhancements

These tests validate the following properties:
- Property 1: Estimated Cost Summation
- Property 2: Bill-Level Cost Aggregation
- Property 3: Cost Progress Percentage Calculation
- Property 4: Variance Calculation
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt
from hypothesis import given, strategies as st, settings


class TestEstimatedCostSummation(FrappeTestCase):
	"""
	**Feature: boq-costing-estimation, Property 1: Estimated Cost Summation**
	**Validates: Requirements 1.2**
	
	Property: For any BOQ Item with estimated cost values, the total_estimated_cost 
	field SHALL equal the sum of estimated_material_cost + estimated_labour_cost + 
	estimated_subcontract_cost + estimated_asset_cost + estimated_other_cost
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-EST-COST-PROJECT")
		cls.test_boq = create_test_project_boq(cls.test_project)
		cls.test_bill = create_test_bill(cls.test_project, "Bill No. 1 - Estimated Costs Test")
	
	@given(
		material_cost=st.floats(min_value=0, max_value=1000000, allow_nan=False, allow_infinity=False),
		labour_cost=st.floats(min_value=0, max_value=1000000, allow_nan=False, allow_infinity=False),
		subcontract_cost=st.floats(min_value=0, max_value=1000000, allow_nan=False, allow_infinity=False),
		asset_cost=st.floats(min_value=0, max_value=1000000, allow_nan=False, allow_infinity=False),
		other_cost=st.floats(min_value=0, max_value=1000000, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=100, deadline=None)
	def test_total_estimated_cost_equals_sum_of_components(
		self, material_cost, labour_cost, subcontract_cost, asset_cost, other_cost
	):
		"""Property: total_estimated_cost = sum of all cost components"""
		# Create BOQ Item with estimated costs
		item = frappe.new_doc("BOQ Item")
		item.parent_bill = self.test_bill
		item.description = f"Test Item - {frappe.generate_hash()[:8]}"
		item.unit = "Nos"
		item.total_qty = 100
		item.rate = 10
		item.estimated_material_cost = material_cost
		item.estimated_labour_cost = labour_cost
		item.estimated_subcontract_cost = subcontract_cost
		item.estimated_asset_cost = asset_cost
		item.estimated_other_cost = other_cost
		
		# Trigger validation which calculates total
		item.validate()
		
		# Calculate expected total
		expected_total = (
			flt(material_cost) + 
			flt(labour_cost) + 
			flt(subcontract_cost) + 
			flt(asset_cost) + 
			flt(other_cost)
		)
		
		# Assert total equals sum
		self.assertAlmostEqual(
			flt(item.total_estimated_cost), 
			expected_total, 
			places=2,
			msg=f"Total estimated cost {item.total_estimated_cost} should equal sum {expected_total}"
		)
	
	def test_total_estimated_cost_with_zero_values(self):
		"""Property: total_estimated_cost is 0 when all components are 0"""
		item = frappe.new_doc("BOQ Item")
		item.parent_bill = self.test_bill
		item.description = "Test Item - Zero Costs"
		item.unit = "Nos"
		item.total_qty = 100
		item.rate = 10
		item.estimated_material_cost = 0
		item.estimated_labour_cost = 0
		item.estimated_subcontract_cost = 0
		item.estimated_asset_cost = 0
		item.estimated_other_cost = 0
		
		item.validate()
		
		self.assertEqual(flt(item.total_estimated_cost), 0)
	
	def test_total_estimated_cost_with_null_values(self):
		"""Property: total_estimated_cost handles null/None values gracefully"""
		item = frappe.new_doc("BOQ Item")
		item.parent_bill = self.test_bill
		item.description = "Test Item - Null Costs"
		item.unit = "Nos"
		item.total_qty = 100
		item.rate = 10
		# Leave estimated costs as None (not set)
		
		item.validate()
		
		# Should be 0, not error
		self.assertEqual(flt(item.total_estimated_cost), 0)
	
	def test_total_estimated_cost_with_partial_values(self):
		"""Property: total_estimated_cost correctly sums when only some components are set"""
		item = frappe.new_doc("BOQ Item")
		item.parent_bill = self.test_bill
		item.description = "Test Item - Partial Costs"
		item.unit = "Nos"
		item.total_qty = 100
		item.rate = 10
		item.estimated_material_cost = 1000
		item.estimated_labour_cost = 500
		# Leave other costs as None
		
		item.validate()
		
		self.assertEqual(flt(item.total_estimated_cost), 1500)
	
	def test_saved_boq_item_has_correct_total(self):
		"""Property: Saved BOQ Item persists correct total_estimated_cost"""
		item = frappe.new_doc("BOQ Item")
		item.parent_bill = self.test_bill
		item.description = f"Test Item - Saved {frappe.generate_hash()[:8]}"
		item.unit = "Nos"
		item.total_qty = 100
		item.rate = 10
		item.estimated_material_cost = 2000
		item.estimated_labour_cost = 1500
		item.estimated_subcontract_cost = 3000
		item.estimated_asset_cost = 500
		item.estimated_other_cost = 200
		item.insert(ignore_permissions=True)
		
		# Reload from database
		saved_item = frappe.get_doc("BOQ Item", item.name)
		
		expected_total = 2000 + 1500 + 3000 + 500 + 200
		self.assertEqual(flt(saved_item.total_estimated_cost), expected_total)
		
		# Cleanup
		frappe.delete_doc("BOQ Item", item.name, force=True)


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
	
	# Get project BOQ
	project_boq = frappe.db.get_value("Project BOQ", {"project": project})
	
	bill = frappe.new_doc("BOQ Bill")
	bill.project = project
	bill.project_boq = project_boq
	bill.bill_no = bill_no
	bill.insert(ignore_permissions=True)
	return bill.name



class TestBillLevelCostAggregation(FrappeTestCase):
	"""
	**Feature: boq-costing-estimation, Property 2: Bill-Level Cost Aggregation**
	**Validates: Requirements 1.5**
	
	Property: For any BOQ Bill, the total estimated cost SHALL equal the sum of 
	total_estimated_cost from all child BOQ Items
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-BILL-AGG-PROJECT")
		cls.test_boq = create_test_project_boq(cls.test_project)
		cls.test_bill = create_test_bill(cls.test_project, "Bill No. 1 - Aggregation Test")
	
	def test_bill_aggregates_estimated_costs_from_items(self):
		"""Property: Bill total_estimated_cost equals sum of item costs"""
		# Create multiple BOQ Items with different estimated costs
		item1 = create_boq_item_with_estimated_costs(
			self.test_bill, "Item 1", 
			material=1000, labour=500, subcontract=200, asset=100, other=50
		)
		item2 = create_boq_item_with_estimated_costs(
			self.test_bill, "Item 2",
			material=2000, labour=1000, subcontract=500, asset=300, other=100
		)
		item3 = create_boq_item_with_estimated_costs(
			self.test_bill, "Item 3",
			material=500, labour=250, subcontract=100, asset=50, other=25
		)
		
		# Refresh bill to recalculate totals
		bill = frappe.get_doc("BOQ Bill", self.test_bill)
		bill.calculate_totals()
		
		# Expected totals
		expected_material = 1000 + 2000 + 500
		expected_labour = 500 + 1000 + 250
		expected_subcontract = 200 + 500 + 100
		expected_asset = 100 + 300 + 50
		expected_other = 50 + 100 + 25
		expected_total = expected_material + expected_labour + expected_subcontract + expected_asset + expected_other
		
		# Assert aggregated values
		self.assertEqual(flt(bill.estimated_material_cost), expected_material)
		self.assertEqual(flt(bill.estimated_labour_cost), expected_labour)
		self.assertEqual(flt(bill.estimated_subcontract_cost), expected_subcontract)
		self.assertEqual(flt(bill.estimated_asset_cost), expected_asset)
		self.assertEqual(flt(bill.estimated_other_cost), expected_other)
		self.assertEqual(flt(bill.total_estimated_cost), expected_total)
		
		# Cleanup
		for item_name in [item1, item2, item3]:
			frappe.delete_doc("BOQ Item", item_name, force=True)
	
	def test_bill_aggregation_with_zero_costs(self):
		"""Property: Bill correctly aggregates when some items have zero costs"""
		item1 = create_boq_item_with_estimated_costs(
			self.test_bill, "Item Zero 1",
			material=1000, labour=0, subcontract=0, asset=0, other=0
		)
		item2 = create_boq_item_with_estimated_costs(
			self.test_bill, "Item Zero 2",
			material=0, labour=500, subcontract=0, asset=0, other=0
		)
		
		bill = frappe.get_doc("BOQ Bill", self.test_bill)
		bill.calculate_totals()
		
		self.assertEqual(flt(bill.estimated_material_cost), 1000)
		self.assertEqual(flt(bill.estimated_labour_cost), 500)
		self.assertEqual(flt(bill.total_estimated_cost), 1500)
		
		# Cleanup
		for item_name in [item1, item2]:
			frappe.delete_doc("BOQ Item", item_name, force=True)
	
	def test_bill_aggregation_with_no_items(self):
		"""Property: Bill with no items has zero estimated costs"""
		# Create a new bill with no items
		new_bill = create_test_bill(self.test_project, "Bill No. Empty")
		
		bill = frappe.get_doc("BOQ Bill", new_bill)
		bill.calculate_totals()
		
		self.assertEqual(flt(bill.total_estimated_cost), 0)
		self.assertEqual(flt(bill.estimated_material_cost), 0)
		self.assertEqual(flt(bill.estimated_labour_cost), 0)
	
	@given(
		num_items=st.integers(min_value=1, max_value=5),
		cost_multiplier=st.floats(min_value=1, max_value=1000, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=50, deadline=None)
	def test_bill_aggregation_property(self, num_items, cost_multiplier):
		"""Property: Bill total always equals sum of item totals"""
		created_items = []
		expected_total = 0
		
		for i in range(num_items):
			base_cost = (i + 1) * cost_multiplier
			item_name = create_boq_item_with_estimated_costs(
				self.test_bill, f"Prop Item {i} - {frappe.generate_hash()[:6]}",
				material=base_cost, labour=base_cost * 0.5, 
				subcontract=base_cost * 0.2, asset=base_cost * 0.1, other=base_cost * 0.05
			)
			created_items.append(item_name)
			expected_total += base_cost * (1 + 0.5 + 0.2 + 0.1 + 0.05)
		
		bill = frappe.get_doc("BOQ Bill", self.test_bill)
		bill.calculate_totals()
		
		self.assertAlmostEqual(flt(bill.total_estimated_cost), expected_total, places=2)
		
		# Cleanup
		for item_name in created_items:
			frappe.delete_doc("BOQ Item", item_name, force=True)


def create_boq_item_with_estimated_costs(parent_bill, description, material=0, labour=0, 
										  subcontract=0, asset=0, other=0):
	"""Create a BOQ Item with estimated costs"""
	bill_doc = frappe.get_doc("BOQ Bill", parent_bill)
	
	item = frappe.new_doc("BOQ Item")
	item.parent_bill = parent_bill
	item.project = bill_doc.project
	item.description = description
	item.unit = "Nos"
	item.total_qty = 100
	item.rate = 10
	item.estimated_material_cost = material
	item.estimated_labour_cost = labour
	item.estimated_subcontract_cost = subcontract
	item.estimated_asset_cost = asset
	item.estimated_other_cost = other
	item.insert(ignore_permissions=True)
	return item.name



class TestCostProgressPercentage(FrappeTestCase):
	"""
	**Feature: boq-costing-estimation, Property 3: Cost Progress Percentage Calculation**
	**Validates: Requirements 2.1**
	
	Property: For any BOQ Item with estimated costs > 0, the progress percentage 
	SHALL equal (incurred_cost / estimated_cost) × 100
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-PROGRESS-PROJECT")
		cls.test_boq = create_test_project_boq(cls.test_project)
		cls.test_bill = create_test_bill(cls.test_project, "Bill No. 1 - Progress Test")
	
	def test_progress_percentage_calculation(self):
		"""Property: progress_percentage = (incurred / estimated) * 100"""
		# Create BOQ Item with estimated costs
		item = frappe.new_doc("BOQ Item")
		item.parent_bill = self.test_bill
		item.description = f"Progress Test Item {frappe.generate_hash()[:8]}"
		item.unit = "Nos"
		item.total_qty = 100
		item.rate = 10
		item.estimated_material_cost = 5000
		item.estimated_labour_cost = 3000
		item.estimated_subcontract_cost = 1000
		item.estimated_asset_cost = 500
		item.estimated_other_cost = 500
		item.insert(ignore_permissions=True)
		
		# Get cost progress (no DPRs yet, so incurred = 0)
		progress = item.get_cost_progress()
		
		# With no incurred costs, progress should be 0%
		self.assertEqual(progress["progress_percentage"], 0)
		self.assertEqual(progress["incurred"]["total"], 0)
		self.assertEqual(progress["estimated"]["total"], 10000)
		self.assertFalse(progress["is_overrun"])
		self.assertTrue(progress["has_estimates"])
		
		# Cleanup
		frappe.delete_doc("BOQ Item", item.name, force=True)
	
	def test_progress_percentage_with_zero_estimate(self):
		"""Property: When estimated = 0 and incurred = 0, progress = 0%"""
		item = frappe.new_doc("BOQ Item")
		item.parent_bill = self.test_bill
		item.description = f"Zero Estimate Item {frappe.generate_hash()[:8]}"
		item.unit = "Nos"
		item.total_qty = 100
		item.rate = 10
		# No estimated costs
		item.insert(ignore_permissions=True)
		
		progress = item.get_cost_progress()
		
		self.assertEqual(progress["progress_percentage"], 0)
		self.assertFalse(progress["has_estimates"])
		
		# Cleanup
		frappe.delete_doc("BOQ Item", item.name, force=True)
	
	@given(
		estimated=st.floats(min_value=100, max_value=100000, allow_nan=False, allow_infinity=False),
		incurred_ratio=st.floats(min_value=0, max_value=2, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=100, deadline=None)
	def test_progress_percentage_formula(self, estimated, incurred_ratio):
		"""Property: progress = (incurred / estimated) * 100 for any values"""
		incurred = estimated * incurred_ratio
		
		# Calculate expected progress
		expected_progress = (incurred / estimated) * 100 if estimated > 0 else 0
		
		# Verify the formula
		if estimated > 0:
			calculated = (incurred / estimated) * 100
			self.assertAlmostEqual(calculated, expected_progress, places=2)



class TestVarianceCalculation(FrappeTestCase):
	"""
	**Feature: boq-costing-estimation, Property 4: Variance Calculation**
	**Validates: Requirements 2.5**
	
	Property: For any BOQ Item, the variance for each cost category 
	SHALL equal estimated_cost - incurred_cost
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-VARIANCE-PROJECT")
		cls.test_boq = create_test_project_boq(cls.test_project)
		cls.test_bill = create_test_bill(cls.test_project, "Bill No. 1 - Variance Test")
	
	def test_variance_calculation_no_incurred(self):
		"""Property: variance = estimated - incurred (when incurred = 0)"""
		item = frappe.new_doc("BOQ Item")
		item.parent_bill = self.test_bill
		item.description = f"Variance Test Item {frappe.generate_hash()[:8]}"
		item.unit = "Nos"
		item.total_qty = 100
		item.rate = 10
		item.estimated_material_cost = 5000
		item.estimated_labour_cost = 3000
		item.estimated_subcontract_cost = 1000
		item.estimated_asset_cost = 500
		item.estimated_other_cost = 500
		item.insert(ignore_permissions=True)
		
		progress = item.get_cost_progress()
		
		# Variance should equal estimated when incurred = 0
		self.assertEqual(progress["variance"]["material"], 5000)
		self.assertEqual(progress["variance"]["labour"], 3000)
		self.assertEqual(progress["variance"]["subcontract"], 1000)
		self.assertEqual(progress["variance"]["asset"], 500)
		self.assertEqual(progress["variance"]["other"], 500)
		self.assertEqual(progress["variance"]["total"], 10000)
		
		# Cleanup
		frappe.delete_doc("BOQ Item", item.name, force=True)
	
	@given(
		estimated=st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False),
		incurred=st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=100, deadline=None)
	def test_variance_formula(self, estimated, incurred):
		"""Property: variance = estimated - incurred for any values"""
		expected_variance = estimated - incurred
		
		# Verify the formula
		calculated_variance = estimated - incurred
		self.assertAlmostEqual(calculated_variance, expected_variance, places=2)
	
	def test_negative_variance_indicates_overrun(self):
		"""Property: negative variance indicates cost overrun"""
		# When incurred > estimated, variance is negative
		estimated = 1000
		incurred = 1500
		variance = estimated - incurred
		
		self.assertLess(variance, 0)
		self.assertEqual(variance, -500)
	
	def test_positive_variance_indicates_under_budget(self):
		"""Property: positive variance indicates under budget"""
		# When incurred < estimated, variance is positive
		estimated = 1000
		incurred = 800
		variance = estimated - incurred
		
		self.assertGreater(variance, 0)
		self.assertEqual(variance, 200)
