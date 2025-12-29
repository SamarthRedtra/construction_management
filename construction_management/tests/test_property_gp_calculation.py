# Copyright (c) 2024, Construction Management
# License: MIT

"""
Property-based tests for GP (Gross Profit) Calculation.

**Feature: boq-management-restructure, Property 1: GP Calculation Correctness**
**Validates: Requirements 1.6**

Property: For any BOQ item with revenue and actual cost, GP SHALL equal (Revenue - Actual Cost)
and GP% SHALL equal (GP / Revenue * 100)
"""

import unittest
from hypothesis import given, strategies as st, settings
from frappe.utils import flt


def calculate_gp(revenue: float, actual_cost: float) -> float:
    """
    Calculate Gross Profit.
    
    GP = Revenue - Actual Cost
    
    Args:
        revenue: Revenue amount (Tax Invoice or PC amount)
        actual_cost: Actual cost from DPR
        
    Returns:
        Gross Profit amount
    """
    return flt(revenue) - flt(actual_cost)


def calculate_gp_percent(gp: float, revenue: float) -> float:
    """
    Calculate Gross Profit Percentage.
    
    GP% = (GP / Revenue) * 100
    Returns 0 if revenue is 0 to avoid division by zero.
    
    Args:
        gp: Gross Profit amount
        revenue: Revenue amount
        
    Returns:
        Gross Profit percentage
    """
    if flt(revenue) <= 0:
        return 0
    return flt(gp / revenue * 100, 2)


class TestGPCalculation(unittest.TestCase):
    """
    Property-based tests for GP calculation.
    
    **Feature: boq-management-restructure, Property 1: GP Calculation Correctness**
    **Validates: Requirements 1.6**
    """
    
    @given(
        revenue=st.floats(min_value=0, max_value=1000000, allow_nan=False, allow_infinity=False),
        actual_cost=st.floats(min_value=0, max_value=1000000, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_gp_equals_revenue_minus_cost(self, revenue, actual_cost):
        """
        Property: GP = Revenue - Actual Cost
        
        **Feature: boq-management-restructure, Property 1: GP Calculation Correctness**
        **Validates: Requirements 1.6**
        """
        gp = calculate_gp(revenue, actual_cost)
        expected = flt(revenue) - flt(actual_cost)
        
        self.assertAlmostEqual(gp, expected, places=2)
    
    @given(
        revenue=st.floats(min_value=100, max_value=1000000, allow_nan=False, allow_infinity=False),
        cost_ratio=st.floats(min_value=0, max_value=2, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_gp_percent_formula(self, revenue, cost_ratio):
        """
        Property: GP% = (GP / Revenue) * 100
        
        **Feature: boq-management-restructure, Property 1: GP Calculation Correctness**
        **Validates: Requirements 1.6**
        """
        actual_cost = revenue * cost_ratio
        gp = calculate_gp(revenue, actual_cost)
        gp_percent = calculate_gp_percent(gp, revenue)
        
        # GP% should equal (1 - cost_ratio) * 100
        expected_percent = (1 - cost_ratio) * 100
        
        self.assertAlmostEqual(gp_percent, expected_percent, places=1)
    
    @given(
        actual_cost=st.floats(min_value=0, max_value=1000000, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=50)
    def test_gp_percent_zero_revenue(self, actual_cost):
        """
        Property: GP% should be 0 when revenue is 0 (avoid division by zero)
        
        **Feature: boq-management-restructure, Property 1: GP Calculation Correctness**
        **Validates: Requirements 1.6**
        """
        revenue = 0
        gp = calculate_gp(revenue, actual_cost)
        gp_percent = calculate_gp_percent(gp, revenue)
        
        # GP% should be 0 when revenue is 0
        self.assertEqual(gp_percent, 0)
    
    @given(
        revenue=st.floats(min_value=1000, max_value=100000, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=50)
    def test_gp_positive_when_revenue_exceeds_cost(self, revenue):
        """
        Property: GP should be positive when revenue > cost
        
        **Feature: boq-management-restructure, Property 1: GP Calculation Correctness**
        **Validates: Requirements 1.6**
        """
        actual_cost = revenue * 0.7  # 70% cost ratio = 30% margin
        gp = calculate_gp(revenue, actual_cost)
        
        self.assertGreater(gp, 0)
        
        gp_percent = calculate_gp_percent(gp, revenue)
        self.assertAlmostEqual(gp_percent, 30, places=1)
    
    @given(
        revenue=st.floats(min_value=1000, max_value=100000, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=50)
    def test_gp_negative_when_cost_exceeds_revenue(self, revenue):
        """
        Property: GP should be negative when cost > revenue (loss)
        
        **Feature: boq-management-restructure, Property 1: GP Calculation Correctness**
        **Validates: Requirements 1.6**
        """
        actual_cost = revenue * 1.2  # 120% cost ratio = -20% margin (loss)
        gp = calculate_gp(revenue, actual_cost)
        
        self.assertLess(gp, 0)
        
        gp_percent = calculate_gp_percent(gp, revenue)
        self.assertAlmostEqual(gp_percent, -20, places=1)
    
    def test_specific_examples(self):
        """
        Test specific examples for GP calculation.
        
        **Feature: boq-management-restructure, Property 1: GP Calculation Correctness**
        **Validates: Requirements 1.6**
        """
        # Example 1: Revenue 10000, Cost 7000 → GP 3000, GP% 30%
        gp = calculate_gp(10000, 7000)
        gp_percent = calculate_gp_percent(gp, 10000)
        self.assertEqual(gp, 3000)
        self.assertEqual(gp_percent, 30)
        
        # Example 2: Revenue 5000, Cost 5000 → GP 0, GP% 0%
        gp = calculate_gp(5000, 5000)
        gp_percent = calculate_gp_percent(gp, 5000)
        self.assertEqual(gp, 0)
        self.assertEqual(gp_percent, 0)
        
        # Example 3: Revenue 1000, Cost 1200 → GP -200, GP% -20%
        gp = calculate_gp(1000, 1200)
        gp_percent = calculate_gp_percent(gp, 1000)
        self.assertEqual(gp, -200)
        self.assertEqual(gp_percent, -20)


if __name__ == "__main__":
    unittest.main()
