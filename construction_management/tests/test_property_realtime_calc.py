# Copyright (c) 2024, Construction Management
# License: MIT

"""
Property-based tests for Real-time Value Calculation and Over-billing Prevention.

**Feature: boq-management-restructure, Property 8: Real-time Value Calculation**
**Feature: boq-management-restructure, Property 9: Over-billing Prevention**
**Validates: Requirements 7.1, 7.3**
"""

import unittest
from hypothesis import given, strategies as st, settings
from frappe.utils import flt


def calculate_current_value(qty: float, rate: float) -> float:
    """
    Calculate current billing value.
    Current Value = Qty × Rate
    """
    return flt(qty) * flt(rate)


def calculate_accumulated(prev: float, current: float) -> float:
    """
    Calculate accumulated value.
    Accumulated = Previous + Current
    """
    return flt(prev) + flt(current)


def calculate_balance(total: float, accumulated: float) -> float:
    """
    Calculate remaining balance.
    Balance = Total - Accumulated
    """
    return flt(total) - flt(accumulated)


def validate_over_billing(current_qty: float, balance_qty: float) -> dict:
    """
    Validate that current quantity doesn't exceed balance.
    
    Returns:
        dict with:
        - is_valid: bool
        - excess: float (amount over balance, 0 if valid)
    """
    if current_qty > balance_qty:
        return {
            'is_valid': False,
            'excess': current_qty - balance_qty
        }
    return {
        'is_valid': True,
        'excess': 0
    }


class TestRealtimeValueCalculation(unittest.TestCase):
    """
    Property-based tests for real-time value calculation.
    
    **Feature: boq-management-restructure, Property 8: Real-time Value Calculation**
    **Validates: Requirements 7.1**
    """
    
    @given(
        qty=st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
        rate=st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_current_value_equals_qty_times_rate(self, qty, rate):
        """
        Property: Current Value = Qty × Rate
        
        **Feature: boq-management-restructure, Property 8: Real-time Value Calculation**
        **Validates: Requirements 7.1**
        """
        value = calculate_current_value(qty, rate)
        expected = flt(qty) * flt(rate)
        
        self.assertAlmostEqual(value, expected, places=2)
    
    @given(
        prev=st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False),
        current=st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_accumulated_equals_prev_plus_current(self, prev, current):
        """
        Property: Accumulated = Previous + Current
        
        **Feature: boq-management-restructure, Property 8: Real-time Value Calculation**
        **Validates: Requirements 7.1**
        """
        accumulated = calculate_accumulated(prev, current)
        expected = flt(prev) + flt(current)
        
        self.assertAlmostEqual(accumulated, expected, places=2)
    
    @given(
        total=st.floats(min_value=1000, max_value=100000, allow_nan=False, allow_infinity=False),
        accumulated_ratio=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_balance_equals_total_minus_accumulated(self, total, accumulated_ratio):
        """
        Property: Balance = Total - Accumulated
        
        **Feature: boq-management-restructure, Property 8: Real-time Value Calculation**
        **Validates: Requirements 7.1**
        """
        accumulated = total * accumulated_ratio
        balance = calculate_balance(total, accumulated)
        expected = flt(total) - flt(accumulated)
        
        self.assertAlmostEqual(balance, expected, places=2)
    
    @given(
        qty=st.floats(min_value=1, max_value=100, allow_nan=False, allow_infinity=False),
        rate=st.floats(min_value=10, max_value=1000, allow_nan=False, allow_infinity=False),
        prev_qty=st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_full_calculation_chain(self, qty, rate, prev_qty):
        """
        Property: Full calculation chain should be consistent
        
        **Feature: boq-management-restructure, Property 8: Real-time Value Calculation**
        **Validates: Requirements 7.1**
        """
        total_qty = 100
        
        # Calculate current value
        current_value = calculate_current_value(qty, rate)
        prev_value = calculate_current_value(prev_qty, rate)
        
        # Calculate accumulated
        accumulated_value = calculate_accumulated(prev_value, current_value)
        
        # Calculate balance
        total_value = calculate_current_value(total_qty, rate)
        balance = calculate_balance(total_value, accumulated_value)
        
        # Verify chain consistency
        self.assertAlmostEqual(
            balance,
            total_value - prev_value - current_value,
            places=2
        )
    
    def test_specific_example(self):
        """
        Test specific example with known values.
        
        **Feature: boq-management-restructure, Property 8: Real-time Value Calculation**
        **Validates: Requirements 7.1**
        """
        # Given: qty=10, rate=100, prev=500, total=2000
        qty = 10
        rate = 100
        prev = 500
        total = 2000
        
        # Current Value = 10 × 100 = 1000
        current_value = calculate_current_value(qty, rate)
        self.assertEqual(current_value, 1000)
        
        # Accumulated = 500 + 1000 = 1500
        accumulated = calculate_accumulated(prev, current_value)
        self.assertEqual(accumulated, 1500)
        
        # Balance = 2000 - 1500 = 500
        balance = calculate_balance(total, accumulated)
        self.assertEqual(balance, 500)


class TestOverBillingPrevention(unittest.TestCase):
    """
    Property-based tests for over-billing prevention.
    
    **Feature: boq-management-restructure, Property 9: Over-billing Prevention**
    **Validates: Requirements 7.3**
    """
    
    @given(
        balance_qty=st.floats(min_value=10, max_value=100, allow_nan=False, allow_infinity=False),
        excess_ratio=st.floats(min_value=0.01, max_value=1, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_over_billing_detected_when_qty_exceeds_balance(self, balance_qty, excess_ratio):
        """
        Property: Over-billing should be detected when qty > balance
        
        **Feature: boq-management-restructure, Property 9: Over-billing Prevention**
        **Validates: Requirements 7.3**
        """
        current_qty = balance_qty + (balance_qty * excess_ratio)  # Exceeds balance
        
        result = validate_over_billing(current_qty, balance_qty)
        
        self.assertFalse(result['is_valid'])
        self.assertGreater(result['excess'], 0)
    
    @given(
        balance_qty=st.floats(min_value=10, max_value=100, allow_nan=False, allow_infinity=False),
        usage_ratio=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_valid_billing_when_qty_within_balance(self, balance_qty, usage_ratio):
        """
        Property: Billing should be valid when qty <= balance
        
        **Feature: boq-management-restructure, Property 9: Over-billing Prevention**
        **Validates: Requirements 7.3**
        """
        current_qty = balance_qty * usage_ratio  # Within balance
        
        result = validate_over_billing(current_qty, balance_qty)
        
        self.assertTrue(result['is_valid'])
        self.assertEqual(result['excess'], 0)
    
    @given(
        balance_qty=st.floats(min_value=10, max_value=100, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=50)
    def test_exact_balance_is_valid(self, balance_qty):
        """
        Property: Billing exactly at balance should be valid
        
        **Feature: boq-management-restructure, Property 9: Over-billing Prevention**
        **Validates: Requirements 7.3**
        """
        current_qty = balance_qty  # Exactly at balance
        
        result = validate_over_billing(current_qty, balance_qty)
        
        self.assertTrue(result['is_valid'])
    
    def test_specific_examples(self):
        """
        Test specific examples for over-billing prevention.
        
        **Feature: boq-management-restructure, Property 9: Over-billing Prevention**
        **Validates: Requirements 7.3**
        """
        # Example 1: qty=15, balance=10 → Invalid, excess=5
        result = validate_over_billing(15, 10)
        self.assertFalse(result['is_valid'])
        self.assertEqual(result['excess'], 5)
        
        # Example 2: qty=8, balance=10 → Valid
        result = validate_over_billing(8, 10)
        self.assertTrue(result['is_valid'])
        
        # Example 3: qty=10, balance=10 → Valid (exact)
        result = validate_over_billing(10, 10)
        self.assertTrue(result['is_valid'])
        
        # Example 4: qty=0, balance=10 → Valid
        result = validate_over_billing(0, 10)
        self.assertTrue(result['is_valid'])


if __name__ == "__main__":
    unittest.main()
