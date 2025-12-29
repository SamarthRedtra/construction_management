# Copyright (c) 2024, Construction Management
# License: MIT

"""
Property-based tests for Variance Calculation.

**Feature: boq-management-restructure, Property 3: Variance Calculation**
**Validates: Requirements 3.1**

Property: For any Payment Certificate linked to a Proforma Invoice,
variance SHALL equal (PI Amount - PC Amount)
"""

import unittest
from hypothesis import given, strategies as st, settings
from frappe.utils import flt


def calculate_variance(proforma_amount: float, pc_amount: float) -> float:
    """
    Calculate variance between Proforma Invoice and Payment Certificate.
    
    Variance = PI Amount - PC Amount
    Positive variance = loss (customer paid less than billed)
    
    Args:
        proforma_amount: Proforma Invoice amount
        pc_amount: Payment Certificate accepted amount
        
    Returns:
        Variance amount (positive = loss)
    """
    return flt(proforma_amount) - flt(pc_amount)


def calculate_variance_percent(variance: float, proforma_amount: float) -> float:
    """
    Calculate variance percentage.
    
    Variance% = (Variance / PI Amount) * 100
    
    Args:
        variance: Variance amount
        proforma_amount: Proforma Invoice amount
        
    Returns:
        Variance percentage
    """
    if flt(proforma_amount) <= 0:
        return 0
    return flt(variance / proforma_amount * 100, 2)


class TestVarianceCalculation(unittest.TestCase):
    """
    Property-based tests for variance calculation.
    
    **Feature: boq-management-restructure, Property 3: Variance Calculation**
    **Validates: Requirements 3.1**
    """
    
    @given(
        proforma_amount=st.floats(min_value=100, max_value=1000000, allow_nan=False, allow_infinity=False),
        pc_amount=st.floats(min_value=0, max_value=1000000, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_variance_equals_pi_minus_pc(self, proforma_amount, pc_amount):
        """
        Property: Variance = PI Amount - PC Amount
        
        **Feature: boq-management-restructure, Property 3: Variance Calculation**
        **Validates: Requirements 3.1**
        """
        variance = calculate_variance(proforma_amount, pc_amount)
        expected = flt(proforma_amount) - flt(pc_amount)
        
        self.assertAlmostEqual(variance, expected, places=2)
    
    @given(
        proforma_amount=st.floats(min_value=1000, max_value=100000, allow_nan=False, allow_infinity=False),
        discount_pct=st.floats(min_value=0.01, max_value=0.5, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_variance_positive_when_pc_less_than_pi(self, proforma_amount, discount_pct):
        """
        Property: Variance should be positive (loss) when PC < PI
        
        **Feature: boq-management-restructure, Property 3: Variance Calculation**
        **Validates: Requirements 3.1**
        """
        pc_amount = proforma_amount * (1 - discount_pct)
        variance = calculate_variance(proforma_amount, pc_amount)
        
        # Variance should be positive when PC < PI (discount_pct > 0.01 ensures meaningful difference)
        self.assertGreater(variance, 0)
    
    @given(
        proforma_amount=st.floats(min_value=1000, max_value=100000, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=50)
    def test_variance_zero_when_pc_equals_pi(self, proforma_amount):
        """
        Property: Variance should be zero when PC = PI
        
        **Feature: boq-management-restructure, Property 3: Variance Calculation**
        **Validates: Requirements 3.1**
        """
        pc_amount = proforma_amount
        variance = calculate_variance(proforma_amount, pc_amount)
        
        self.assertAlmostEqual(variance, 0, places=2)
    
    @given(
        proforma_amount=st.floats(min_value=1000, max_value=100000, allow_nan=False, allow_infinity=False),
        discount_pct=st.floats(min_value=0.01, max_value=0.5, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=50)
    def test_variance_percent_formula(self, proforma_amount, discount_pct):
        """
        Property: Variance% = (Variance / PI Amount) * 100
        
        **Feature: boq-management-restructure, Property 3: Variance Calculation**
        **Validates: Requirements 3.1**
        """
        pc_amount = proforma_amount * (1 - discount_pct)
        variance = calculate_variance(proforma_amount, pc_amount)
        variance_pct = calculate_variance_percent(variance, proforma_amount)
        
        expected_pct = discount_pct * 100
        
        self.assertAlmostEqual(variance_pct, expected_pct, places=1)
    
    def test_specific_example_from_requirements(self):
        """
        Test the specific example from requirements.
        
        If PI = 1000, PC = 900:
        - Variance should be 100 (loss)
        - Variance% should be 10%
        
        **Feature: boq-management-restructure, Property 3: Variance Calculation**
        **Validates: Requirements 3.1**
        """
        proforma_amount = 1000
        pc_amount = 900
        
        variance = calculate_variance(proforma_amount, pc_amount)
        variance_pct = calculate_variance_percent(variance, proforma_amount)
        
        self.assertEqual(variance, 100)
        self.assertEqual(variance_pct, 10)
    
    @given(
        proforma_amount=st.floats(min_value=1000, max_value=100000, allow_nan=False, allow_infinity=False),
        pc_amount=st.floats(min_value=0, max_value=1000000, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=50)
    def test_variance_plus_pc_equals_pi(self, proforma_amount, pc_amount):
        """
        Property: Variance + PC Amount should equal PI Amount
        
        **Feature: boq-management-restructure, Property 3: Variance Calculation**
        **Validates: Requirements 3.1**
        """
        variance = calculate_variance(proforma_amount, pc_amount)
        
        # Variance + PC = PI
        self.assertAlmostEqual(variance + pc_amount, proforma_amount, places=2)


if __name__ == "__main__":
    unittest.main()
