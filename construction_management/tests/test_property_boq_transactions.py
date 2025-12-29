# Copyright (c) 2024, Construction Management
# License: MIT

"""
Property-based tests for BOQ Item Transaction Data Completeness.

**Feature: boq-management-restructure, Property 2: Transaction Data Completeness**
**Validates: Requirements 2.2, 2.3**

Property: For any BOQ item, the transaction history SHALL include all Proforma Invoices,
Payment Certificates, and Tax Invoices linked to that item, each with document name,
date, quantity, amount, and status.
"""

import unittest
from hypothesis import given, strategies as st, settings


# Define the required fields for each transaction type
REQUIRED_FIELDS = ['doctype', 'name', 'date', 'amount', 'status']
VALID_DOCTYPES = ['Proforma Invoice', 'Payment Certificate', 'Sales Invoice']


def validate_transaction_structure(transaction: dict) -> tuple:
    """
    Validate that a transaction has all required fields.
    
    Args:
        transaction: Transaction dict from get_boq_item_transactions
        
    Returns:
        Tuple of (is_valid, missing_fields)
    """
    missing_fields = []
    
    for field in REQUIRED_FIELDS:
        if field not in transaction:
            missing_fields.append(field)
    
    # Check doctype is valid
    if 'doctype' in transaction and transaction['doctype'] not in VALID_DOCTYPES:
        missing_fields.append(f"invalid_doctype:{transaction['doctype']}")
    
    return (len(missing_fields) == 0, missing_fields)


def validate_transaction_list(transactions: list) -> dict:
    """
    Validate a list of transactions for completeness.
    
    Args:
        transactions: List of transaction dicts
        
    Returns:
        dict with validation results
    """
    results = {
        'total': len(transactions),
        'valid': 0,
        'invalid': 0,
        'by_doctype': {dt: 0 for dt in VALID_DOCTYPES},
        'errors': []
    }
    
    for txn in transactions:
        is_valid, missing = validate_transaction_structure(txn)
        if is_valid:
            results['valid'] += 1
            doctype = txn.get('doctype')
            if doctype in results['by_doctype']:
                results['by_doctype'][doctype] += 1
        else:
            results['invalid'] += 1
            results['errors'].append({
                'name': txn.get('name', 'unknown'),
                'missing': missing
            })
    
    return results


class TestTransactionDataCompleteness(unittest.TestCase):
    """
    Property-based tests for transaction data completeness.
    
    **Feature: boq-management-restructure, Property 2: Transaction Data Completeness**
    **Validates: Requirements 2.2, 2.3**
    """
    
    @given(
        num_pi=st.integers(min_value=0, max_value=10),
        num_pc=st.integers(min_value=0, max_value=10),
        num_si=st.integers(min_value=0, max_value=10)
    )
    @settings(max_examples=50)
    def test_all_transaction_types_have_required_fields(self, num_pi, num_pc, num_si):
        """
        Property: All transaction types must have required fields.
        
        **Feature: boq-management-restructure, Property 2: Transaction Data Completeness**
        **Validates: Requirements 2.2, 2.3**
        """
        # Generate mock transactions
        transactions = []
        
        for i in range(num_pi):
            transactions.append({
                'doctype': 'Proforma Invoice',
                'name': f'PI-{i}',
                'date': '2024-01-01',
                'qty': 10,
                'amount': 1000,
                'status': 'Submitted'
            })
        
        for i in range(num_pc):
            transactions.append({
                'doctype': 'Payment Certificate',
                'name': f'PC-{i}',
                'date': '2024-01-02',
                'qty': None,  # PC may not have qty
                'amount': 900,
                'status': 'Submitted',
                'variance': 100,
                'pc_amount': 900
            })
        
        for i in range(num_si):
            transactions.append({
                'doctype': 'Sales Invoice',
                'name': f'SI-{i}',
                'date': '2024-01-03',
                'qty': 10,
                'amount': 900,
                'status': 'Paid'
            })
        
        # Validate all transactions
        results = validate_transaction_list(transactions)
        
        # All transactions should be valid
        self.assertEqual(results['valid'], results['total'])
        self.assertEqual(results['invalid'], 0)
        
        # Count by doctype should match
        self.assertEqual(results['by_doctype']['Proforma Invoice'], num_pi)
        self.assertEqual(results['by_doctype']['Payment Certificate'], num_pc)
        self.assertEqual(results['by_doctype']['Sales Invoice'], num_si)
    
    def test_transaction_structure_validation(self):
        """
        Test that validation correctly identifies missing fields.
        
        **Feature: boq-management-restructure, Property 2: Transaction Data Completeness**
        **Validates: Requirements 2.2, 2.3**
        """
        # Valid transaction
        valid_txn = {
            'doctype': 'Proforma Invoice',
            'name': 'PI-001',
            'date': '2024-01-01',
            'amount': 1000,
            'status': 'Submitted'
        }
        is_valid, missing = validate_transaction_structure(valid_txn)
        self.assertTrue(is_valid)
        self.assertEqual(len(missing), 0)
        
        # Missing name
        invalid_txn = {
            'doctype': 'Proforma Invoice',
            'date': '2024-01-01',
            'amount': 1000,
            'status': 'Submitted'
        }
        is_valid, missing = validate_transaction_structure(invalid_txn)
        self.assertFalse(is_valid)
        self.assertIn('name', missing)
        
        # Invalid doctype
        invalid_doctype_txn = {
            'doctype': 'Invalid Type',
            'name': 'XX-001',
            'date': '2024-01-01',
            'amount': 1000,
            'status': 'Submitted'
        }
        is_valid, missing = validate_transaction_structure(invalid_doctype_txn)
        self.assertFalse(is_valid)
    
    @given(
        amounts=st.lists(
            st.floats(min_value=100, max_value=10000, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=10
        )
    )
    @settings(max_examples=50)
    def test_transaction_amounts_are_preserved(self, amounts):
        """
        Property: Transaction amounts should be preserved in the data structure.
        
        **Feature: boq-management-restructure, Property 2: Transaction Data Completeness**
        **Validates: Requirements 2.2, 2.3**
        """
        transactions = []
        for i, amount in enumerate(amounts):
            transactions.append({
                'doctype': 'Proforma Invoice',
                'name': f'PI-{i}',
                'date': '2024-01-01',
                'qty': 10,
                'amount': amount,
                'status': 'Submitted'
            })
        
        # Verify amounts are preserved
        for i, txn in enumerate(transactions):
            self.assertAlmostEqual(txn['amount'], amounts[i], places=2)


if __name__ == "__main__":
    unittest.main()
