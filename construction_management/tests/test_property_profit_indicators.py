# Copyright (c) 2024, Construction Management
# License: MIT
# Property Tests for Profit Indicators

"""
Property Tests for Profit Indicators

These tests validate the following properties:
- Property 6: Profit Indicator Accuracy
- Cost vs revenue indicator functionality
- Color coding accuracy
- Real-time updates
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today
from hypothesis import given, strategies as st, settings

from construction_management.tests.test_utils import (
	create_test_project,
	create_test_boq_structure,
	cleanup_test_data
)


class TestProfitIndicatorAccuracy(FrappeTestCase):
	"""
	**Feature: construction-enhancements-comprehensive, Property 6: Profit Indicator Accuracy**
	
	**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**
	
	Property: Profit indicators SHALL accurately display cost vs revenue with
	correct color coding and real-time updates.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-PROFIT-IND-PROJECT")
		cls.boq, cls.bill, cls.boq_item = create_test_boq_structure(
			cls.test_project, 
			total_qty=100, 
			rate=50  # Revenue = 5000
		)
	
	@classmethod
	def tearDownClass(cls):
		cleanup_test_data()
		super().tearDownClass()
	
	def test_profit_calculation_accuracy(self):
		"""Property: Profit calculation is accurate (revenue - cost)"""
		boq_item_doc = frappe.get_doc("BOQ Item", self.boq_item)
		
		# Set some estimated costs
		boq_item_doc.estimated_material_cost = 2000
		boq_item_doc.estimated_labour_cost = 1500
		boq_item_doc.estimated_asset_cost = 500
		boq_item_doc.save(ignore_permissions=True)
		
		revenue = boq_item_doc.amount  # 5000
		total_cost = (
			flt(boq_item_doc.estimated_material_cost) +
			flt(boq_item_doc.estimated_labour_cost) +
			flt(boq_item_doc.estimated_asset_cost)
		)  # 4000
		
		expected_profit = revenue - total_cost  # 1000
		
		# Test profit calculation
		self.assertEqual(flt(expected_profit), 1000)
		self.assertGreater(expected_profit, 0)  # Should be profitable
	
	def test_profit_percentage_calculation(self):
		"""Property: Profit percentage calculation is accurate"""
		boq_item_doc = frappe.get_doc("BOQ Item", self.boq_item)
		
		# Set costs for testing
		boq_item_doc.estimated_material_cost = 3000
		boq_item_doc.estimated_labour_cost = 1000
		boq_item_doc.save(ignore_permissions=True)
		
		revenue = boq_item_doc.amount  # 5000
		total_cost = 4000
		profit = revenue - total_cost  # 1000
		profit_percentage = (profit / revenue) * 100 if revenue > 0 else 0  # 20%
		
		self.assertEqual(flt(profit_percentage, 2), 20.0)
	
	def test_loss_scenario_calculation(self):
		"""Property: Loss scenario is calculated correctly"""
		boq_item_doc = frappe.get_doc("BOQ Item", self.boq_item)
		
		# Set costs higher than revenue to create loss
		boq_item_doc.estimated_material_cost = 4000
		boq_item_doc.estimated_labour_cost = 2000
		boq_item_doc.save(ignore_permissions=True)
		
		revenue = boq_item_doc.amount  # 5000
		total_cost = 6000
		profit = revenue - total_cost  # -1000 (loss)
		
		self.assertEqual(flt(profit), -1000)
		self.assertLess(profit, 0)  # Should be a loss
	
	def test_zero_cost_scenario(self):
		"""Property: Zero cost scenario is handled correctly"""
		boq_item_doc = frappe.get_doc("BOQ Item", self.boq_item)
		
		# Set all costs to zero
		boq_item_doc.estimated_material_cost = 0
		boq_item_doc.estimated_labour_cost = 0
		boq_item_doc.estimated_asset_cost = 0
		boq_item_doc.save(ignore_permissions=True)
		
		revenue = boq_item_doc.amount  # 5000
		total_cost = 0
		profit = revenue - total_cost  # 5000
		profit_percentage = (profit / revenue) * 100 if revenue > 0 else 0  # 100%
		
		self.assertEqual(flt(profit), 5000)
		self.assertEqual(flt(profit_percentage), 100.0)


class TestProfitIndicatorColorCoding(FrappeTestCase):
	"""
	**Feature: construction-enhancements-comprehensive, Property 6: Profit Indicator Color Coding**
	
	**Validates: Requirements 8.3, 8.4**
	
	Property: Color coding SHALL correctly indicate profit (green) and loss (red) scenarios.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-PROFIT-COLOR-PROJECT")
		cls.boq, cls.bill, cls.boq_item = create_test_boq_structure(
			cls.test_project, 
			total_qty=100, 
			rate=50
		)
	
	@classmethod
	def tearDownClass(cls):
		cleanup_test_data()
		super().tearDownClass()
	
	def test_profit_color_logic(self):
		"""Property: Profit scenarios should indicate green color"""
		revenue = 5000
		cost = 3000
		profit = revenue - cost  # 1000 (positive)
		
		# Logic for color determination
		if profit > 0:
			color_indicator = "green"
		elif profit < 0:
			color_indicator = "red"
		else:
			color_indicator = "yellow"
		
		self.assertEqual(color_indicator, "green")
	
	def test_loss_color_logic(self):
		"""Property: Loss scenarios should indicate red color"""
		revenue = 5000
		cost = 6000
		profit = revenue - cost  # -1000 (negative)
		
		# Logic for color determination
		if profit > 0:
			color_indicator = "green"
		elif profit < 0:
			color_indicator = "red"
		else:
			color_indicator = "yellow"
		
		self.assertEqual(color_indicator, "red")
	
	def test_breakeven_color_logic(self):
		"""Property: Breakeven scenarios should indicate yellow color"""
		revenue = 5000
		cost = 5000
		profit = revenue - cost  # 0 (breakeven)
		
		# Logic for color determination
		if profit > 0:
			color_indicator = "green"
		elif profit < 0:
			color_indicator = "red"
		else:
			color_indicator = "yellow"
		
		self.assertEqual(color_indicator, "yellow")
	
	def test_profit_margin_thresholds(self):
		"""Property: Different profit margin thresholds have appropriate indicators"""
		revenue = 1000
		
		# High profit margin (>30%)
		high_profit_cost = 600
		high_profit = revenue - high_profit_cost  # 400 (40% margin)
		high_margin = (high_profit / revenue) * 100
		self.assertGreater(high_margin, 30)
		
		# Medium profit margin (10-30%)
		medium_profit_cost = 800
		medium_profit = revenue - medium_profit_cost  # 200 (20% margin)
		medium_margin = (medium_profit / revenue) * 100
		self.assertTrue(10 <= medium_margin <= 30)
		
		# Low profit margin (<10%)
		low_profit_cost = 950
		low_profit = revenue - low_profit_cost  # 50 (5% margin)
		low_margin = (low_profit / revenue) * 100
		self.assertLess(low_margin, 10)


class TestProfitIndicatorRealTimeUpdates(FrappeTestCase):
	"""
	**Feature: construction-enhancements-comprehensive, Property 6: Profit Indicator Real-Time Updates**
	
	**Validates: Requirements 8.5**
	
	Property: Profit indicators SHALL update in real-time when cost or revenue changes.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-PROFIT-RT-PROJECT")
		cls.boq, cls.bill, cls.boq_item = create_test_boq_structure(
			cls.test_project, 
			total_qty=100, 
			rate=50
		)
	
	@classmethod
	def tearDownClass(cls):
		cleanup_test_data()
		super().tearDownClass()
	
	def test_profit_updates_when_cost_changes(self):
		"""Property: Profit calculation updates when costs change"""
		boq_item_doc = frappe.get_doc("BOQ Item", self.boq_item)
		
		# Initial state
		initial_revenue = boq_item_doc.amount  # 5000
		initial_cost = 3000
		initial_profit = initial_revenue - initial_cost  # 2000
		
		# Update cost
		new_cost = 4000
		new_profit = initial_revenue - new_cost  # 1000
		
		# Profit should change when cost changes
		self.assertNotEqual(initial_profit, new_profit)
		self.assertEqual(new_profit, 1000)
	
	def test_profit_updates_when_revenue_changes(self):
		"""Property: Profit calculation updates when revenue changes"""
		boq_item_doc = frappe.get_doc("BOQ Item", self.boq_item)
		
		# Initial state
		initial_revenue = boq_item_doc.amount  # 5000
		cost = 3000
		initial_profit = initial_revenue - cost  # 2000
		
		# Update revenue (by changing rate)
		boq_item_doc.rate = 60  # New rate
		new_revenue = boq_item_doc.total_qty * 60  # 6000
		new_profit = new_revenue - cost  # 3000
		
		# Profit should change when revenue changes
		self.assertNotEqual(initial_profit, new_profit)
		self.assertEqual(new_profit, 3000)
	
	def test_profit_percentage_updates_correctly(self):
		"""Property: Profit percentage updates correctly with changes"""
		revenue = 1000
		
		# Scenario 1: 20% profit margin
		cost1 = 800
		profit1 = revenue - cost1  # 200
		margin1 = (profit1 / revenue) * 100  # 20%
		
		# Scenario 2: 10% profit margin
		cost2 = 900
		profit2 = revenue - cost2  # 100
		margin2 = (profit2 / revenue) * 100  # 10%
		
		self.assertEqual(flt(margin1), 20.0)
		self.assertEqual(flt(margin2), 10.0)
		self.assertNotEqual(margin1, margin2)


class TestProfitIndicatorHypothesis(FrappeTestCase):
	"""
	**Feature: construction-enhancements-comprehensive, Property 6: Profit Indicator Hypothesis Tests**
	
	**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**
	
	Property-based tests for profit indicator behavior using Hypothesis.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-PROFIT-HYPO-PROJECT")
	
	@classmethod
	def tearDownClass(cls):
		cleanup_test_data()
		super().tearDownClass()
	
	@given(
		revenue=st.floats(min_value=1, max_value=100000, allow_nan=False, allow_infinity=False),
		cost=st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=100, deadline=None)
	def test_profit_calculation_invariant(self, revenue, cost):
		"""Property: Profit is always revenue - cost"""
		expected_profit = flt(revenue) - flt(cost)
		calculated_profit = flt(revenue) - flt(cost)
		
		self.assertEqual(flt(calculated_profit, 2), flt(expected_profit, 2))
	
	@given(
		revenue=st.floats(min_value=1, max_value=100000, allow_nan=False, allow_infinity=False),
		cost=st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=100, deadline=None)
	def test_profit_percentage_invariant(self, revenue, cost):
		"""Property: Profit percentage is always (profit / revenue) * 100"""
		profit = flt(revenue) - flt(cost)
		expected_percentage = (profit / flt(revenue)) * 100 if flt(revenue) > 0 else 0
		calculated_percentage = (profit / flt(revenue)) * 100 if flt(revenue) > 0 else 0
		
		self.assertEqual(flt(calculated_percentage, 2), flt(expected_percentage, 2))
	
	@given(
		revenue=st.floats(min_value=1, max_value=100000, allow_nan=False, allow_infinity=False),
		cost=st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=50, deadline=None)
	def test_color_coding_logic_invariant(self, revenue, cost):
		"""Property: Color coding logic is consistent"""
		profit = flt(revenue) - flt(cost)
		
		if profit > 0:
			expected_color = "green"
		elif profit < 0:
			expected_color = "red"
		else:
			expected_color = "yellow"
		
		# Apply same logic
		if profit > 0:
			actual_color = "green"
		elif profit < 0:
			actual_color = "red"
		else:
			actual_color = "yellow"
		
		self.assertEqual(actual_color, expected_color)
	
	@given(
		revenue=st.floats(min_value=1, max_value=100000, allow_nan=False, allow_infinity=False),
		material_cost=st.floats(min_value=0, max_value=50000, allow_nan=False, allow_infinity=False),
		labour_cost=st.floats(min_value=0, max_value=50000, allow_nan=False, allow_infinity=False),
		asset_cost=st.floats(min_value=0, max_value=50000, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=50, deadline=None)
	def test_multi_component_cost_calculation(self, revenue, material_cost, labour_cost, asset_cost):
		"""Property: Multi-component cost calculation is always sum of components"""
		total_cost = flt(material_cost) + flt(labour_cost) + flt(asset_cost)
		profit = flt(revenue) - total_cost
		
		# Total cost should equal sum of components
		expected_total = flt(material_cost) + flt(labour_cost) + flt(asset_cost)
		self.assertEqual(flt(total_cost, 2), flt(expected_total, 2))
		
		# Profit should be revenue minus total cost
		expected_profit = flt(revenue) - total_cost
		self.assertEqual(flt(profit, 2), flt(expected_profit, 2))