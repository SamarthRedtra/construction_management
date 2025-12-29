# Copyright (c) 2024, Construction Management
# License: MIT
# Property Tests for DPR Cost Validation

"""
Property Tests for DPR Cost Validation

These tests validate the following properties:
- Property 5: DPR Total Cost Validation
- Property 6: DPR Component Cost Validation
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt
from hypothesis import given, strategies as st, settings, assume

from construction_management.api.cost_validation import (
	validate_dpr_costs,
	validate_total_cost,
	validate_component_costs,
	get_incurred_costs,
	ValidationResult
)


class TestDPRTotalCostValidation(FrappeTestCase):
	"""
	**Feature: boq-costing-estimation, Property 5: DPR Total Cost Validation**
	**Validates: Requirements 3.1**
	
	Property: For any DPR submission against a BOQ Item with estimated costs,
	if (current_incurred + new_dpr_cost) > total_estimated_cost, 
	the submission SHALL be rejected.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-COST-VAL-PROJECT")
		cls.test_boq = create_test_project_boq(cls.test_project)
		cls.test_bill = create_test_bill(cls.test_project, "Bill No. 1 - Cost Validation")
	
	@given(
		estimated=st.floats(min_value=1000, max_value=100000, allow_nan=False, allow_infinity=False),
		incurred_ratio=st.floats(min_value=0, max_value=0.9, allow_nan=False, allow_infinity=False),
		new_cost_ratio=st.floats(min_value=0.05, max_value=0.5, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=100, deadline=None)
	def test_total_cost_validation_rejects_overrun(self, estimated, incurred_ratio, new_cost_ratio):
		"""Property: Submission rejected when total exceeds estimate"""
		current_incurred = estimated * incurred_ratio
		new_cost = estimated * new_cost_ratio
		
		# Calculate if this would cause overrun
		projected = current_incurred + new_cost
		should_reject = projected > estimated
		
		error = validate_total_cost(estimated, current_incurred, new_cost)
		
		if should_reject:
			self.assertIsNotNone(error, 
				f"Should reject: estimated={estimated}, incurred={current_incurred}, new={new_cost}, projected={projected}")
		else:
			self.assertIsNone(error,
				f"Should accept: estimated={estimated}, incurred={current_incurred}, new={new_cost}, projected={projected}")
	
	@given(
		estimated=st.floats(min_value=1000, max_value=100000, allow_nan=False, allow_infinity=False),
		incurred_ratio=st.floats(min_value=0, max_value=0.5, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=100, deadline=None)
	def test_total_cost_validation_accepts_within_budget(self, estimated, incurred_ratio):
		"""Property: Submission accepted when total is within estimate"""
		current_incurred = estimated * incurred_ratio
		# New cost that keeps us under budget
		remaining = estimated - current_incurred
		new_cost = remaining * 0.5  # Use only half of remaining
		
		error = validate_total_cost(estimated, current_incurred, new_cost)
		
		self.assertIsNone(error, 
			f"Should accept within budget: estimated={estimated}, incurred={current_incurred}, new={new_cost}")
	
	def test_total_cost_validation_exact_match(self):
		"""Property: Submission accepted when total exactly equals estimate"""
		estimated = 10000
		current_incurred = 5000
		new_cost = 5000  # Exactly reaches estimate
		
		error = validate_total_cost(estimated, current_incurred, new_cost)
		
		self.assertIsNone(error, "Should accept when total exactly equals estimate")
	
	def test_total_cost_validation_zero_estimate(self):
		"""Property: Validation skipped when no estimate exists"""
		error = validate_total_cost(0, 1000, 500)
		
		self.assertIsNone(error, "Should skip validation when estimate is 0")
	
	def test_total_cost_validation_negative_estimate(self):
		"""Property: Validation skipped for negative estimates"""
		error = validate_total_cost(-1000, 500, 200)
		
		self.assertIsNone(error, "Should skip validation for negative estimate")
	
	@given(
		estimated=st.floats(min_value=1000, max_value=100000, allow_nan=False, allow_infinity=False),
		overrun_amount=st.floats(min_value=1, max_value=10000, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=100, deadline=None)
	def test_total_cost_validation_error_message_contains_amounts(self, estimated, overrun_amount):
		"""Property: Error message includes all relevant amounts"""
		current_incurred = estimated * 0.8
		new_cost = estimated * 0.3 + overrun_amount  # Guaranteed overrun
		
		error = validate_total_cost(estimated, current_incurred, new_cost)
		
		self.assertIsNotNone(error)
		# Error should mention the overrun
		self.assertIn("exceeds", error.lower())


class TestDPRComponentCostValidation(FrappeTestCase):
	"""
	**Feature: boq-costing-estimation, Property 6: DPR Component Cost Validation**
	**Validates: Requirements 3.2**
	
	Property: For any DPR submission, for each cost component,
	if (current_incurred_component + new_component_cost) > estimated_component_cost,
	a warning SHALL be generated.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-COMP-VAL-PROJECT")
		cls.test_boq = create_test_project_boq(cls.test_project)
		cls.test_bill = create_test_bill(cls.test_project, "Bill No. 1 - Component Validation")
	
	def test_component_validation_warns_on_material_overrun(self):
		"""Property: Warning generated when material cost exceeds estimate"""
		# Create BOQ Item with estimates
		item = create_boq_item_with_estimates(
			self.test_bill, "Material Overrun Test",
			material=5000, labour=3000, subcontract=1000, asset=500, other=500
		)
		
		boq_doc = frappe.get_doc("BOQ Item", item)
		incurred = {"material": 4000, "labour": 0, "subcontract": 0, "asset": 0, "other": 0}
		new_costs = {"material_cost": 2000}  # Would exceed 5000 estimate
		
		warnings = validate_component_costs(boq_doc, incurred, new_costs)
		
		self.assertTrue(len(warnings) > 0, "Should generate warning for material overrun")
		self.assertTrue(any("Material" in w for w in warnings))
		
		# Cleanup
		frappe.delete_doc("BOQ Item", item, force=True)
	
	def test_component_validation_warns_on_labour_overrun(self):
		"""Property: Warning generated when labour cost exceeds estimate"""
		item = create_boq_item_with_estimates(
			self.test_bill, "Labour Overrun Test",
			material=5000, labour=3000, subcontract=1000, asset=500, other=500
		)
		
		boq_doc = frappe.get_doc("BOQ Item", item)
		incurred = {"material": 0, "labour": 2500, "subcontract": 0, "asset": 0, "other": 0}
		new_costs = {"labour_cost": 1000}  # Would exceed 3000 estimate
		
		warnings = validate_component_costs(boq_doc, incurred, new_costs)
		
		self.assertTrue(len(warnings) > 0, "Should generate warning for labour overrun")
		self.assertTrue(any("Labour" in w for w in warnings))
		
		# Cleanup
		frappe.delete_doc("BOQ Item", item, force=True)
	
	def test_component_validation_no_warning_within_budget(self):
		"""Property: No warning when all components within budget"""
		item = create_boq_item_with_estimates(
			self.test_bill, "Within Budget Test",
			material=5000, labour=3000, subcontract=1000, asset=500, other=500
		)
		
		boq_doc = frappe.get_doc("BOQ Item", item)
		incurred = {"material": 2000, "labour": 1000, "subcontract": 500, "asset": 200, "other": 100}
		new_costs = {
			"material_cost": 1000,
			"labour_cost": 500,
			"subcontract_cost": 200,
			"asset_cost": 100,
			"expense_cost": 100
		}
		
		warnings = validate_component_costs(boq_doc, incurred, new_costs)
		
		self.assertEqual(len(warnings), 0, "Should not generate warnings when within budget")
		
		# Cleanup
		frappe.delete_doc("BOQ Item", item, force=True)
	
	def test_component_validation_skips_zero_estimates(self):
		"""Property: No warning for components with zero estimates"""
		item = create_boq_item_with_estimates(
			self.test_bill, "Zero Estimate Test",
			material=5000, labour=0, subcontract=0, asset=0, other=0
		)
		
		boq_doc = frappe.get_doc("BOQ Item", item)
		incurred = {"material": 0, "labour": 1000, "subcontract": 500, "asset": 200, "other": 100}
		new_costs = {
			"material_cost": 1000,
			"labour_cost": 5000,  # Would be overrun if estimate existed
			"subcontract_cost": 2000,
			"asset_cost": 1000,
			"expense_cost": 500
		}
		
		warnings = validate_component_costs(boq_doc, incurred, new_costs)
		
		# Should only warn about material if it exceeds
		# Other components have 0 estimate so should be skipped
		material_warnings = [w for w in warnings if "Material" in w]
		labour_warnings = [w for w in warnings if "Labour" in w]
		
		self.assertEqual(len(labour_warnings), 0, "Should not warn for zero-estimate components")
		
		# Cleanup
		frappe.delete_doc("BOQ Item", item, force=True)
	
	@given(
		num_overruns=st.integers(min_value=1, max_value=5)
	)
	@settings(max_examples=50, deadline=None)
	def test_component_validation_multiple_overruns(self, num_overruns):
		"""Property: Multiple warnings generated for multiple component overruns"""
		item = create_boq_item_with_estimates(
			self.test_bill, f"Multi Overrun Test {frappe.generate_hash()[:6]}",
			material=1000, labour=1000, subcontract=1000, asset=1000, other=1000
		)
		
		boq_doc = frappe.get_doc("BOQ Item", item)
		
		# Create overruns for specified number of components
		components = ["material", "labour", "subcontract", "asset", "other"]
		incurred = {c: 800 for c in components}  # 80% used
		
		new_costs = {}
		cost_fields = ["material_cost", "labour_cost", "subcontract_cost", "asset_cost", "expense_cost"]
		
		for i, field in enumerate(cost_fields):
			if i < num_overruns:
				new_costs[field] = 500  # Would cause overrun (800 + 500 > 1000)
			else:
				new_costs[field] = 100  # Within budget
		
		warnings = validate_component_costs(boq_doc, incurred, new_costs)
		
		self.assertEqual(len(warnings), num_overruns, 
			f"Should generate {num_overruns} warnings, got {len(warnings)}")
		
		# Cleanup
		frappe.delete_doc("BOQ Item", item, force=True)


class TestValidateDPRCostsIntegration(FrappeTestCase):
	"""
	**Feature: boq-costing-estimation, Property 5 & 6: Integrated DPR Cost Validation**
	**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
	
	Integration tests for the complete validation flow.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-INT-VAL-PROJECT")
		cls.test_boq = create_test_project_boq(cls.test_project)
		cls.test_bill = create_test_bill(cls.test_project, "Bill No. 1 - Integration")
	
	def test_validate_dpr_costs_returns_validation_result(self):
		"""Property: validate_dpr_costs returns proper ValidationResult"""
		item = create_boq_item_with_estimates(
			self.test_bill, "Integration Test Item",
			material=5000, labour=3000, subcontract=1000, asset=500, other=500
		)
		
		dpr_costs = {
			"material_cost": 1000,
			"labour_cost": 500,
			"total_cost": 1500
		}
		
		result = validate_dpr_costs(item, dpr_costs)
		
		self.assertIsInstance(result, ValidationResult)
		self.assertTrue(result.is_valid)
		self.assertEqual(len(result.errors), 0)
		
		# Cleanup
		frappe.delete_doc("BOQ Item", item, force=True)
	
	def test_validate_dpr_costs_skips_when_no_estimates(self):
		"""Property: Validation skipped when BOQ Item has no estimates (Req 3.5)"""
		item = create_boq_item_with_estimates(
			self.test_bill, "No Estimates Item",
			material=0, labour=0, subcontract=0, asset=0, other=0
		)
		
		dpr_costs = {
			"material_cost": 10000,
			"labour_cost": 5000,
			"total_cost": 15000
		}
		
		result = validate_dpr_costs(item, dpr_costs)
		
		self.assertTrue(result.is_valid, "Should skip validation when no estimates")
		self.assertEqual(len(result.errors), 0)
		self.assertEqual(len(result.warnings), 0)
		
		# Cleanup
		frappe.delete_doc("BOQ Item", item, force=True)
	
	def test_validate_dpr_costs_blocks_total_overrun(self):
		"""Property: Total cost overrun blocks submission (Req 3.3)"""
		item = create_boq_item_with_estimates(
			self.test_bill, "Total Overrun Item",
			material=5000, labour=3000, subcontract=1000, asset=500, other=500
		)
		
		# Total estimate is 10000
		dpr_costs = {
			"material_cost": 6000,
			"labour_cost": 3000,
			"subcontract_cost": 1000,
			"asset_cost": 500,
			"expense_cost": 1000,
			"total_cost": 11500  # Exceeds 10000
		}
		
		result = validate_dpr_costs(item, dpr_costs)
		
		self.assertFalse(result.is_valid, "Should block total cost overrun")
		self.assertTrue(result.has_errors)
		self.assertTrue(len(result.errors) > 0)
		
		# Cleanup
		frappe.delete_doc("BOQ Item", item, force=True)
	
	def test_validate_dpr_costs_warns_component_overrun(self):
		"""Property: Component overrun generates warning but allows submission (Req 3.4)"""
		item = create_boq_item_with_estimates(
			self.test_bill, "Component Overrun Item",
			material=5000, labour=3000, subcontract=1000, asset=500, other=500
		)
		
		# Total is within budget but material exceeds
		dpr_costs = {
			"material_cost": 6000,  # Exceeds 5000 estimate
			"labour_cost": 1000,
			"subcontract_cost": 500,
			"asset_cost": 200,
			"expense_cost": 200,
			"total_cost": 7900  # Within 10000 total
		}
		
		result = validate_dpr_costs(item, dpr_costs)
		
		self.assertTrue(result.is_valid, "Should allow submission with component overrun")
		self.assertFalse(result.has_errors)
		self.assertTrue(result.has_warnings, "Should generate warning for component overrun")
		
		# Cleanup
		frappe.delete_doc("BOQ Item", item, force=True)


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


def create_boq_item_with_estimates(parent_bill, description, material=0, labour=0,
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
