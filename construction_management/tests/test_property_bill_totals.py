# Copyright (c) 2024, Construction Management
# License: MIT

"""
Property-based tests for Bill Totals Aggregation.

**Feature: boq-management-restructure, Property 7: Bill Grouping with Totals**
**Validates: Requirements 5.1, 5.2**

Property: For any Bill, the displayed totals SHALL equal the sum of all BOQ item values
within that Bill for each column (Revenue, Cost, Profitability)
"""

import unittest
from hypothesis import given, strategies as st, settings
from frappe.utils import flt


def aggregate_bill_totals(items: list) -> dict:
    """
    Aggregate totals for a bill from its items.
    
    Args:
        items: List of BOQ items with revenue, cost, and profitability data
        
    Returns:
        dict with aggregated totals:
        - revenue: {proforma, pc, tax_invoice, variance, total, balance}
        - estimated_costs: {material, labour, asset, subcontract, other, total}
        - actual_costs: {material, labour, asset, subcontract, other, total}
        - profitability: {gp, gp_percent}
    """
    totals = {
        'revenue': {
            'proforma': 0,
            'pc': 0,
            'tax_invoice': 0,
            'variance': 0,
            'total': 0,
            'balance': 0
        },
        'estimated_costs': {
            'material': 0,
            'labour': 0,
            'asset': 0,
            'subcontract': 0,
            'other': 0,
            'total': 0
        },
        'actual_costs': {
            'material': 0,
            'labour': 0,
            'asset': 0,
            'subcontract': 0,
            'other': 0,
            'total': 0
        },
        'profitability': {
            'gp': 0,
            'gp_percent': 0
        }
    }
    
    if not items:
        return totals
    
    # Sum up all item values
    for item in items:
        revenue = item.get('revenue', {})
        estimated = item.get('estimated_costs', {})
        actual = item.get('actual_costs', {})
        profit = item.get('profitability', {})
        
        # Revenue totals
        totals['revenue']['proforma'] += flt(revenue.get('proforma', 0))
        totals['revenue']['pc'] += flt(revenue.get('pc', 0))
        totals['revenue']['tax_invoice'] += flt(revenue.get('tax_invoice', 0))
        totals['revenue']['variance'] += flt(revenue.get('variance', 0))
        totals['revenue']['total'] += flt(revenue.get('total', 0))
        totals['revenue']['balance'] += flt(revenue.get('balance', 0))
        
        # Estimated cost totals
        totals['estimated_costs']['material'] += flt(estimated.get('material', 0))
        totals['estimated_costs']['labour'] += flt(estimated.get('labour', 0))
        totals['estimated_costs']['asset'] += flt(estimated.get('asset', 0))
        totals['estimated_costs']['subcontract'] += flt(estimated.get('subcontract', 0))
        totals['estimated_costs']['other'] += flt(estimated.get('other', 0))
        totals['estimated_costs']['total'] += flt(estimated.get('total', 0))
        
        # Actual cost totals
        totals['actual_costs']['material'] += flt(actual.get('material', 0))
        totals['actual_costs']['labour'] += flt(actual.get('labour', 0))
        totals['actual_costs']['asset'] += flt(actual.get('asset', 0))
        totals['actual_costs']['subcontract'] += flt(actual.get('subcontract', 0))
        totals['actual_costs']['other'] += flt(actual.get('other', 0))
        totals['actual_costs']['total'] += flt(actual.get('total', 0))
        
        # Profitability totals
        totals['profitability']['gp'] += flt(profit.get('gp', 0))
    
    # Calculate GP% for the bill
    total_revenue = totals['revenue']['total']
    if total_revenue > 0:
        gp_percent = (totals['profitability']['gp'] / total_revenue) * 100
        totals['profitability']['gp_percent'] = round(gp_percent, 2)
    else:
        totals['profitability']['gp_percent'] = 0
    
    return totals


class TestBillTotalsAggregation(unittest.TestCase):
    """
    Property-based tests for bill totals aggregation.
    
    **Feature: boq-management-restructure, Property 7: Bill Grouping with Totals**
    **Validates: Requirements 5.1, 5.2**
    """
    
    @given(
        num_items=st.integers(min_value=1, max_value=20),
        revenue_range=st.floats(min_value=100, max_value=10000, allow_nan=False, allow_infinity=False),
        cost_ratio=st.floats(min_value=0.5, max_value=1.5, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_bill_revenue_totals_equal_sum_of_items(self, num_items, revenue_range, cost_ratio):
        """
        Property: Bill revenue totals = sum of item revenues
        
        **Feature: boq-management-restructure, Property 7: Bill Grouping with Totals**
        **Validates: Requirements 5.1, 5.2**
        """
        # Generate random items
        items = []
        expected_total_revenue = 0
        
        for _ in range(num_items):
            item_revenue = flt(revenue_range * (0.5 + (_ / num_items)))
            expected_total_revenue += item_revenue
            
            items.append({
                'revenue': {
                    'proforma': item_revenue * 0.8,
                    'pc': item_revenue * 0.75,
                    'tax_invoice': item_revenue * 0.75,
                    'variance': item_revenue * 0.05,
                    'total': item_revenue,
                    'balance': item_revenue * 0.2
                }
            })
        
        # Aggregate totals
        totals = aggregate_bill_totals(items)
        
        # Verify total revenue equals sum of item revenues
        self.assertAlmostEqual(
            totals['revenue']['total'],
            expected_total_revenue,
            places=2
        )
    
    @given(
        num_items=st.integers(min_value=1, max_value=20),
        cost_range=st.floats(min_value=100, max_value=10000, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_bill_cost_totals_equal_sum_of_items(self, num_items, cost_range):
        """
        Property: Bill cost totals = sum of item costs
        
        **Feature: boq-management-restructure, Property 7: Bill Grouping with Totals**
        **Validates: Requirements 5.1, 5.2**
        """
        # Generate random items with cost breakdown
        items = []
        expected_total_cost = 0
        
        for i in range(num_items):
            material = flt(cost_range * 0.4 * (0.5 + (i / num_items)))
            labour = flt(cost_range * 0.3 * (0.5 + (i / num_items)))
            asset = flt(cost_range * 0.1 * (0.5 + (i / num_items)))
            subcontract = flt(cost_range * 0.15 * (0.5 + (i / num_items)))
            other = flt(cost_range * 0.05 * (0.5 + (i / num_items)))
            total = material + labour + asset + subcontract + other
            expected_total_cost += total
            
            items.append({
                'actual_costs': {
                    'material': material,
                    'labour': labour,
                    'asset': asset,
                    'subcontract': subcontract,
                    'other': other,
                    'total': total
                }
            })
        
        # Aggregate totals
        totals = aggregate_bill_totals(items)
        
        # Verify total cost equals sum of item costs
        self.assertAlmostEqual(
            totals['actual_costs']['total'],
            expected_total_cost,
            places=2
        )
    
    @given(
        num_items=st.integers(min_value=1, max_value=20),
        revenue_range=st.floats(min_value=1000, max_value=10000, allow_nan=False, allow_infinity=False),
        cost_ratio=st.floats(min_value=0.5, max_value=1.2, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_bill_gp_equals_sum_of_item_gp(self, num_items, revenue_range, cost_ratio):
        """
        Property: Bill GP = sum of item GPs
        
        **Feature: boq-management-restructure, Property 7: Bill Grouping with Totals**
        **Validates: Requirements 5.1, 5.2**
        """
        # Generate random items with GP
        items = []
        expected_total_gp = 0
        
        for i in range(num_items):
            item_revenue = flt(revenue_range * (0.5 + (i / num_items)))
            item_cost = flt(item_revenue * cost_ratio)
            item_gp = item_revenue - item_cost
            expected_total_gp += item_gp
            
            items.append({
                'revenue': {'total': item_revenue},
                'actual_costs': {'total': item_cost},
                'profitability': {'gp': item_gp}
            })
        
        # Aggregate totals
        totals = aggregate_bill_totals(items)
        
        # Verify total GP equals sum of item GPs
        self.assertAlmostEqual(
            totals['profitability']['gp'],
            expected_total_gp,
            places=2
        )
    
    @given(
        num_items=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=50)
    def test_bill_gp_percent_calculated_from_totals(self, num_items):
        """
        Property: Bill GP% = (Total GP / Total Revenue) * 100
        
        **Feature: boq-management-restructure, Property 7: Bill Grouping with Totals**
        **Validates: Requirements 5.1, 5.2**
        """
        # Generate items with consistent 30% margin
        items = []
        total_revenue = 0
        total_gp = 0
        
        for i in range(num_items):
            item_revenue = 1000 * (i + 1)
            item_cost = item_revenue * 0.7  # 30% margin
            item_gp = item_revenue - item_cost
            
            total_revenue += item_revenue
            total_gp += item_gp
            
            items.append({
                'revenue': {'total': item_revenue},
                'actual_costs': {'total': item_cost},
                'profitability': {'gp': item_gp}
            })
        
        # Aggregate totals
        totals = aggregate_bill_totals(items)
        
        # Verify GP% is calculated correctly from totals
        expected_gp_percent = (total_gp / total_revenue) * 100
        self.assertAlmostEqual(
            totals['profitability']['gp_percent'],
            expected_gp_percent,
            places=1
        )
        
        # Should be approximately 30% (since all items have 30% margin)
        # Allow some tolerance due to floating point arithmetic
        self.assertGreater(totals['profitability']['gp_percent'], 29)
        self.assertLess(totals['profitability']['gp_percent'], 31)
    
    def test_empty_bill_returns_zero_totals(self):
        """
        Property: Empty bill should have zero totals
        
        **Feature: boq-management-restructure, Property 7: Bill Grouping with Totals**
        **Validates: Requirements 5.1, 5.2**
        """
        items = []
        totals = aggregate_bill_totals(items)
        
        self.assertEqual(totals['revenue']['total'], 0)
        self.assertEqual(totals['actual_costs']['total'], 0)
        self.assertEqual(totals['profitability']['gp'], 0)
        self.assertEqual(totals['profitability']['gp_percent'], 0)
    
    def test_specific_bill_example(self):
        """
        Test specific example with known values.
        
        **Feature: boq-management-restructure, Property 7: Bill Grouping with Totals**
        **Validates: Requirements 5.1, 5.2**
        """
        items = [
            {
                'revenue': {'total': 10000, 'proforma': 8000, 'balance': 2000},
                'actual_costs': {'total': 7000, 'material': 4000, 'labour': 3000},
                'profitability': {'gp': 3000}
            },
            {
                'revenue': {'total': 5000, 'proforma': 5000, 'balance': 0},
                'actual_costs': {'total': 3500, 'material': 2000, 'labour': 1500},
                'profitability': {'gp': 1500}
            }
        ]
        
        totals = aggregate_bill_totals(items)
        
        # Revenue totals
        self.assertEqual(totals['revenue']['total'], 15000)
        self.assertEqual(totals['revenue']['proforma'], 13000)
        self.assertEqual(totals['revenue']['balance'], 2000)
        
        # Cost totals
        self.assertEqual(totals['actual_costs']['total'], 10500)
        self.assertEqual(totals['actual_costs']['material'], 6000)
        self.assertEqual(totals['actual_costs']['labour'], 4500)
        
        # Profitability - GP is sum of item GPs
        self.assertEqual(totals['profitability']['gp'], 4500)
        # GP% is calculated from totals: (4500 / 15000) * 100 = 30%
        self.assertAlmostEqual(totals['profitability']['gp_percent'], 30, places=1)


if __name__ == "__main__":
    unittest.main()
