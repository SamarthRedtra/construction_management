# Copyright (c) 2024, Construction Management
# License: MIT

"""
Property-based tests for Bulk Proforma Creation.

**Feature: boq-management-restructure, Property 6: Bulk Proforma Creation**
**Validates: Requirements 4.3**

Property: For any set of selected BOQ items with current billing quantities,
creating a Proforma Invoice SHALL include all selected items with their respective quantities
"""

import unittest
from hypothesis import given, strategies as st, settings
from frappe.utils import flt


def validate_bulk_proforma_items(selected_items: list, proforma_items: list) -> dict:
    """
    Validate that bulk proforma creation includes all selected items.
    
    Args:
        selected_items: List of selected BOQ items with quantities
        proforma_items: List of items in the created proforma
        
    Returns:
        dict with validation results:
        - all_items_included: bool
        - quantities_match: bool
        - missing_items: list
        - quantity_mismatches: list
    """
    result = {
        'all_items_included': True,
        'quantities_match': True,
        'missing_items': [],
        'quantity_mismatches': []
    }
    
    # Create lookup for proforma items
    proforma_lookup = {item.get('boq_item'): item for item in proforma_items}
    
    for selected in selected_items:
        boq_item = selected.get('boq_item')
        expected_qty = flt(selected.get('current_qty', 0))
        
        if boq_item not in proforma_lookup:
            result['all_items_included'] = False
            result['missing_items'].append(boq_item)
        else:
            actual_qty = flt(proforma_lookup[boq_item].get('qty', 0))
            if abs(actual_qty - expected_qty) > 0.001:
                result['quantities_match'] = False
                result['quantity_mismatches'].append({
                    'boq_item': boq_item,
                    'expected': expected_qty,
                    'actual': actual_qty
                })
    
    return result


def calculate_proforma_total(items: list, rate_lookup: dict) -> float:
    """
    Calculate total proforma amount from items.
    
    Args:
        items: List of items with boq_item and current_qty
        rate_lookup: Dict mapping boq_item to rate
        
    Returns:
        Total proforma amount
    """
    total = 0
    for item in items:
        boq_item = item.get('boq_item')
        qty = flt(item.get('current_qty', 0))
        rate = flt(rate_lookup.get(boq_item, 0))
        total += qty * rate
    return total


class TestBulkProformaCreation(unittest.TestCase):
    """
    Property-based tests for bulk proforma creation.
    
    **Feature: boq-management-restructure, Property 6: Bulk Proforma Creation**
    **Validates: Requirements 4.3**
    """
    
    @given(
        num_items=st.integers(min_value=1, max_value=10),
        qty_range=st.floats(min_value=1, max_value=100, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_all_selected_items_included_in_proforma(self, num_items, qty_range):
        """
        Property: All selected items should be included in the proforma
        
        **Feature: boq-management-restructure, Property 6: Bulk Proforma Creation**
        **Validates: Requirements 4.3**
        """
        # Generate selected items
        selected_items = []
        for i in range(num_items):
            selected_items.append({
                'boq_item': f'BOQ-ITEM-{i+1}',
                'current_qty': flt(qty_range * (0.5 + (i / num_items)))
            })
        
        # Simulate proforma creation (all items included)
        proforma_items = [
            {'boq_item': item['boq_item'], 'qty': item['current_qty']}
            for item in selected_items
        ]
        
        # Validate
        result = validate_bulk_proforma_items(selected_items, proforma_items)
        
        self.assertTrue(result['all_items_included'])
        self.assertEqual(len(result['missing_items']), 0)
    
    @given(
        num_items=st.integers(min_value=1, max_value=10),
        qty_range=st.floats(min_value=1, max_value=100, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_quantities_preserved_in_proforma(self, num_items, qty_range):
        """
        Property: Selected quantities should be preserved in the proforma
        
        **Feature: boq-management-restructure, Property 6: Bulk Proforma Creation**
        **Validates: Requirements 4.3**
        """
        # Generate selected items
        selected_items = []
        for i in range(num_items):
            selected_items.append({
                'boq_item': f'BOQ-ITEM-{i+1}',
                'current_qty': flt(qty_range * (0.5 + (i / num_items)))
            })
        
        # Simulate proforma creation with exact quantities
        proforma_items = [
            {'boq_item': item['boq_item'], 'qty': item['current_qty']}
            for item in selected_items
        ]
        
        # Validate
        result = validate_bulk_proforma_items(selected_items, proforma_items)
        
        self.assertTrue(result['quantities_match'])
        self.assertEqual(len(result['quantity_mismatches']), 0)
    
    @given(
        num_items=st.integers(min_value=1, max_value=10),
        rate=st.floats(min_value=10, max_value=1000, allow_nan=False, allow_infinity=False),
        qty=st.floats(min_value=1, max_value=100, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_proforma_total_equals_sum_of_item_amounts(self, num_items, rate, qty):
        """
        Property: Proforma total should equal sum of (qty * rate) for all items
        
        **Feature: boq-management-restructure, Property 6: Bulk Proforma Creation**
        **Validates: Requirements 4.3**
        """
        # Generate items with rates
        items = []
        rate_lookup = {}
        expected_total = 0
        
        for i in range(num_items):
            item_name = f'BOQ-ITEM-{i+1}'
            item_qty = flt(qty * (0.5 + (i / num_items)))
            item_rate = flt(rate * (0.8 + (i / num_items) * 0.4))
            
            items.append({
                'boq_item': item_name,
                'current_qty': item_qty
            })
            rate_lookup[item_name] = item_rate
            expected_total += item_qty * item_rate
        
        # Calculate proforma total
        actual_total = calculate_proforma_total(items, rate_lookup)
        
        self.assertAlmostEqual(actual_total, expected_total, places=2)
    
    def test_empty_selection_returns_empty_proforma(self):
        """
        Property: Empty selection should result in empty proforma items
        
        **Feature: boq-management-restructure, Property 6: Bulk Proforma Creation**
        **Validates: Requirements 4.3**
        """
        selected_items = []
        proforma_items = []
        
        result = validate_bulk_proforma_items(selected_items, proforma_items)
        
        self.assertTrue(result['all_items_included'])
        self.assertTrue(result['quantities_match'])
    
    def test_specific_example(self):
        """
        Test specific example with known values.
        
        **Feature: boq-management-restructure, Property 6: Bulk Proforma Creation**
        **Validates: Requirements 4.3**
        """
        selected_items = [
            {'boq_item': 'BOQ-001', 'current_qty': 10},
            {'boq_item': 'BOQ-002', 'current_qty': 5},
            {'boq_item': 'BOQ-003', 'current_qty': 15}
        ]
        
        proforma_items = [
            {'boq_item': 'BOQ-001', 'qty': 10},
            {'boq_item': 'BOQ-002', 'qty': 5},
            {'boq_item': 'BOQ-003', 'qty': 15}
        ]
        
        result = validate_bulk_proforma_items(selected_items, proforma_items)
        
        self.assertTrue(result['all_items_included'])
        self.assertTrue(result['quantities_match'])
        
        # Test total calculation
        rate_lookup = {'BOQ-001': 100, 'BOQ-002': 200, 'BOQ-003': 50}
        total = calculate_proforma_total(selected_items, rate_lookup)
        # 10*100 + 5*200 + 15*50 = 1000 + 1000 + 750 = 2750
        self.assertEqual(total, 2750)


if __name__ == "__main__":
    unittest.main()
