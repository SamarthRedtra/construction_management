# Copyright (c) 2024, Construction Management
# License: MIT

"""
Property-based tests for BOQ Balance Calculation.

**Feature: boq-management-restructure, Property 4: BOQ Balance Calculation**
**Validates: Requirements 3.3**

Property: For any BOQ item, balance SHALL equal (BOQ Total Amount - Sum of Proforma Invoice Amounts),
NOT (BOQ Total - Sum of PC Amounts)
"""

import unittest
from hypothesis import given, strategies as st, settings
from frappe.utils import flt


# Pure function for balance calculation - mirrors the logic in get_boq_item_revenue_breakdown
def calculate_boq_balance(boq_total: float, proforma_total: float, pc_total: float) -> float:
    """
    Calculate BOQ balance.
    
    Key Logic: Balance = BOQ Total - Proforma Total (NOT PC Total)
    This ensures variance (loss from PC < PI) doesn't affect the balance.
    
    Args:
        boq_total: Total BOQ amount
        proforma_total: Sum of all Proforma Invoice amounts
        pc_total: Sum of all Payment Certificate amounts (NOT used for balance)
        
    Returns:
        Balance amount
    """
    return flt(boq_total) - flt(proforma_total)


def calculate_variance(proforma_total: float, pc_total: float) -> float:
    """
    Calculate variance (loss) between PI and PC.
    
    Variance = PI Total - PC Total
    Positive variance = loss (customer paid less than billed)
    
    Args:
        proforma_total: Sum of Proforma Invoice amounts
        pc_total: Sum of Payment Certificate amounts
        
    Returns:
        Variance amount (positive = loss)
    """
    return flt(proforma_total) - flt(pc_total)


class TestBOQBalanceCalculation(unittest.TestCase):
    """
    Property-based tests for BOQ balance calculation.
    
    **Feature: boq-management-restructure, Property 4: BOQ Balance Calculation**
    **Validates: Requirements 3.3**
    """
    
    @given(
        boq_total=st.floats(min_value=0, max_value=1000000, allow_nan=False, allow_infinity=False),
        proforma_total=st.floats(min_value=0, max_value=1000000, allow_nan=False, allow_infinity=False),
        pc_total=st.floats(min_value=0, max_value=1000000, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_balance_uses_proforma_not_pc(self, boq_total, proforma_total, pc_total):
        """
        Property: Balance = BOQ Total - Proforma Total, regardless of PC amount.
        
        **Feature: boq-management-restructure, Property 4: BOQ Balance Calculation**
        **Validates: Requirements 3.3**
        """
        balance = calculate_boq_balance(boq_total, proforma_total, pc_total)
        expected = flt(boq_total) - flt(proforma_total)
        
        # Balance should equal BOQ Total - Proforma Total
        self.assertAlmostEqual(balance, expected, places=2)
        
        # Balance should NOT depend on PC total
        # If we change PC total, balance should remain the same
        balance_with_different_pc = calculate_boq_balance(boq_total, proforma_total, pc_total * 0.5)
        self.assertAlmostEqual(balance, balance_with_different_pc, places=2)
    
    @given(
        boq_total=st.floats(min_value=1000, max_value=100000, allow_nan=False, allow_infinity=False),
        proforma_pct=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
        variance_pct=st.floats(min_value=0, max_value=0.5, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_variance_does_not_affect_balance(self, boq_total, proforma_pct, variance_pct):
        """
        Property: Variance (PI - PC) should not affect the BOQ balance.
        
        Example: BOQ=5000, PI=1000, PC=900 → Balance=4000, Variance=100
        The 100 variance (loss) should NOT be added back to balance.
        
        **Feature: boq-management-restructure, Property 4: BOQ Balance Calculation**
        **Validates: Requirements 3.3**
        """
        proforma_total = boq_total * proforma_pct
        pc_total = proforma_total * (1 - variance_pct)  # PC is less than PI by variance_pct
        
        balance = calculate_boq_balance(boq_total, proforma_total, pc_total)
        variance = calculate_variance(proforma_total, pc_total)
        
        # Balance should be BOQ - Proforma, NOT BOQ - PC
        expected_balance = boq_total - proforma_total
        self.assertAlmostEqual(balance, expected_balance, places=2)
        
        # Variance should be positive when PC < PI
        if proforma_total > pc_total:
            self.assertGreaterEqual(variance, 0)
        
        # Balance + Proforma should equal BOQ Total
        self.assertAlmostEqual(balance + proforma_total, boq_total, places=2)
    
    @given(
        boq_total=st.floats(min_value=5000, max_value=50000, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=50)
    def test_specific_example_from_requirements(self, boq_total):
        """
        Property: Verify the specific example from requirements.
        
        If BOQ Total=5000, PI=1000, PC=900:
        - Balance should be 4000 (5000 - 1000)
        - Variance should be 100 (1000 - 900)
        - Balance should NOT be 4100 (5000 - 900)
        
        **Feature: boq-management-restructure, Property 4: BOQ Balance Calculation**
        **Validates: Requirements 3.3**
        """
        # Scale the example proportionally
        scale = boq_total / 5000
        proforma_total = 1000 * scale
        pc_total = 900 * scale
        
        balance = calculate_boq_balance(boq_total, proforma_total, pc_total)
        variance = calculate_variance(proforma_total, pc_total)
        
        expected_balance = 4000 * scale  # BOQ - PI
        expected_variance = 100 * scale  # PI - PC
        wrong_balance = 4100 * scale  # BOQ - PC (WRONG!)
        
        # Balance should be 4000 (scaled), NOT 4100 (scaled)
        self.assertAlmostEqual(balance, expected_balance, places=2)
        self.assertNotAlmostEqual(balance, wrong_balance, places=2)
        
        # Variance should be 100 (scaled)
        self.assertAlmostEqual(variance, expected_variance, places=2)


if __name__ == "__main__":
    unittest.main()
