# Copyright (c) 2024, Construction Management
# License: MIT

"""
Property Tests for Advance Deduction Accuracy
Property 4: Advance Deduction Accuracy
Validates: Requirements 6.1, 6.2, 6.3, 6.5
"""

import frappe
import unittest
from frappe.utils import flt
from hypothesis import given, strategies as st, settings, assume
from construction_management.api.advance_adjustment_service import AdvanceAdjustmentService


class TestPropertyAdvanceDeduction(unittest.TestCase):
	"""
	Property-based tests for advance deduction functionality.
	Ensures advance deductions never exceed available balances and are properly tracked.
	"""
	
	def setUp(self):
		"""Set up test environment"""
		frappe.set_user("Administrator")
		self.test_project = self._create_test_project()
	
	def tearDown(self):
		"""Clean up test data"""
		frappe.db.rollback()
	
	def _create_test_project(self):
		"""Create a test project"""
		project = frappe.get_doc({
			"doctype": "Project",
			"project_name": "Test Advance Project",
			"status": "Open"
		})
		project.insert(ignore_permissions=True)
		return project.name
	
	@given(
		collected=st.floats(min_value=0, max_value=1000000, allow_nan=False, allow_infinity=False),
		deduction=st.floats(min_value=0, max_value=1000000, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=50, deadline=None)
	def test_property_advance_deduction_never_exceeds_balance(self, collected, deduction):
		"""
		Property: Advance deduction should never exceed available balance.
		For any collected amount C and deduction amount D:
		- If D <= C, deduction should be valid
		- If D > C, deduction should be rejected
		"""
		collected = flt(collected, 2)
		deduction = flt(deduction, 2)
		
		# Skip if values are too close (floating point precision issues)
		assume(abs(collected - deduction) > 0.01 or collected == deduction)
		
		# Create advance payment entry
		if collected > 0:
			self._create_payment_entry(self.test_project, collected)
		
		# Test validation
		service = AdvanceAdjustmentService(self.test_project)
		validation = service.validate_advance_deduction(deduction)
		
		if deduction <= collected:
			self.assertTrue(validation["valid"], 
				f"Deduction {deduction} should be valid when balance is {collected}")
			self.assertEqual(flt(validation["amount"]), deduction)
			self.assertAlmostEqual(flt(validation["remaining"]), collected - deduction, places=2)
		else:
			self.assertFalse(validation["valid"],
				f"Deduction {deduction} should be invalid when balance is {collected}")
	
	@given(
		advances=st.lists(
			st.floats(min_value=1, max_value=10000, allow_nan=False, allow_infinity=False),
			min_size=1,
			max_size=5
		)
	)
	@settings(max_examples=30, deadline=None)
	def test_property_multiple_advances_accumulate_correctly(self, advances):
		"""
		Property: Multiple advance payments should accumulate correctly.
		For any list of advance amounts [A1, A2, ..., An]:
		- Total available = SUM(Ai) - SUM(deductions)
		"""
		advances = [flt(a, 2) for a in advances]
		total_collected = sum(advances)
		
		# Create multiple payment entries
		for amount in advances:
			self._create_payment_entry(self.test_project, amount)
		
		# Get summary
		service = AdvanceAdjustmentService(self.test_project)
		summary = service.get_advance_summary()
		
		# Verify total collected matches sum of advances
		self.assertAlmostEqual(
			flt(summary["total_collected"]),
			total_collected,
			places=2,
			msg=f"Total collected should equal sum of advances: {total_collected}"
		)
		
		# Verify available balance equals collected (no deductions yet)
		self.assertAlmostEqual(
			flt(summary["available_balance"]),
			total_collected,
			places=2,
			msg="Available balance should equal total collected when no deductions"
		)
	
	@given(
		collected=st.floats(min_value=100, max_value=10000, allow_nan=False, allow_infinity=False),
		deduction_ratio=st.floats(min_value=0.1, max_value=0.9, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=30, deadline=None)
	def test_property_deduction_reduces_available_balance(self, collected, deduction_ratio):
		"""
		Property: Deduction should reduce available balance by exact amount.
		For any collected amount C and deduction D where D < C:
		- Available after deduction = C - D
		"""
		collected = flt(collected, 2)
		deduction = flt(collected * deduction_ratio, 2)
		
		# Create advance payment
		self._create_payment_entry(self.test_project, collected)
		
		# Create invoice with deduction
		self._create_invoice_with_advance_deduction(self.test_project, deduction)
		
		# Get summary after deduction
		service = AdvanceAdjustmentService(self.test_project)
		summary = service.get_advance_summary()
		
		# Verify balance reduced correctly
		expected_balance = collected - deduction
		self.assertAlmostEqual(
			flt(summary["available_balance"]),
			expected_balance,
			places=2,
			msg=f"Balance should be {expected_balance} after deducting {deduction} from {collected}"
		)
		
		# Verify deduction tracked correctly
		self.assertAlmostEqual(
			flt(summary["total_deducted"]),
			deduction,
			places=2,
			msg=f"Total deducted should be {deduction}"
		)
	
	def test_property_zero_deduction_has_no_effect(self):
		"""
		Property: Zero deduction should not affect balance.
		For any collected amount C:
		- Deduction of 0 should leave balance = C
		"""
		collected = 5000.00
		
		# Create advance payment
		self._create_payment_entry(self.test_project, collected)
		
		# Validate zero deduction
		service = AdvanceAdjustmentService(self.test_project)
		validation = service.validate_advance_deduction(0)
		
		self.assertTrue(validation["valid"])
		self.assertEqual(flt(validation["amount"]), 0)
		
		# Balance should remain unchanged
		summary = service.get_advance_summary()
		self.assertAlmostEqual(flt(summary["available_balance"]), collected, places=2)
	
	@given(
		collected=st.floats(min_value=100, max_value=10000, allow_nan=False, allow_infinity=False),
		deductions=st.lists(
			st.floats(min_value=10, max_value=500, allow_nan=False, allow_infinity=False),
			min_size=2,
			max_size=5
		)
	)
	@settings(max_examples=20, deadline=None)
	def test_property_sequential_deductions_accumulate(self, collected, deductions):
		"""
		Property: Sequential deductions should accumulate correctly.
		For collected amount C and deductions [D1, D2, ..., Dn]:
		- If SUM(Di) <= C, all deductions should succeed
		- Available = C - SUM(Di)
		"""
		collected = flt(collected, 2)
		deductions = [flt(d, 2) for d in deductions]
		total_deductions = sum(deductions)
		
		# Only test cases where total deductions don't exceed collected
		assume(total_deductions <= collected)
		
		# Create advance payment
		self._create_payment_entry(self.test_project, collected)
		
		# Apply sequential deductions
		for deduction in deductions:
			self._create_invoice_with_advance_deduction(self.test_project, deduction)
		
		# Verify final balance
		service = AdvanceAdjustmentService(self.test_project)
		summary = service.get_advance_summary()
		
		expected_balance = collected - total_deductions
		self.assertAlmostEqual(
			flt(summary["available_balance"]),
			expected_balance,
			places=2,
			msg=f"Balance should be {expected_balance} after deductions totaling {total_deductions}"
		)
		
		self.assertAlmostEqual(
			flt(summary["total_deducted"]),
			total_deductions,
			places=2,
			msg=f"Total deducted should be {total_deductions}"
		)
	
	def _create_payment_entry(self, project, amount):
		"""Helper to create a payment entry (advance)"""
		# Create a simple payment entry record
		# In real implementation, this would create a proper Payment Entry
		frappe.db.sql("""
			INSERT INTO `tabPayment Entry` 
			(name, docstatus, project, payment_type, is_advance, paid_amount, posting_date)
			VALUES (%s, 1, %s, 'Receive', 'Yes', %s, CURDATE())
		""", (frappe.generate_hash(length=10), project, amount))
		frappe.db.commit()
	
	def _create_invoice_with_advance_deduction(self, project, deduction):
		"""Helper to create an invoice with advance deduction"""
		# Create a simple invoice with advance deduction item
		invoice_name = frappe.generate_hash(length=10)
		
		frappe.db.sql("""
			INSERT INTO `tabSales Invoice`
			(name, docstatus, project, customer, posting_date, due_date)
			VALUES (%s, 1, %s, 'Test Customer', CURDATE(), CURDATE())
		""", (invoice_name, project))
		
		frappe.db.sql("""
			INSERT INTO `tabSales Invoice Item`
			(name, parent, parenttype, parentfield, item_code, qty, rate, amount)
			VALUES (%s, %s, 'Sales Invoice', 'items', 'ADVANCE-DEDUCTION', 1, %s, %s)
		""", (frappe.generate_hash(length=10), invoice_name, -deduction, -deduction))
		
		frappe.db.commit()


def run_tests():
	"""Run property tests"""
	unittest.main()


if __name__ == "__main__":
	run_tests()
