# Copyright (c) 2024, Construction Management
# License: MIT

import unittest
import frappe
from frappe.utils import flt
from construction_management.api.transaction_grouping import (
    TransactionGrouper, 
    group_transactions_by_billing_cycle,
    get_grouped_transaction_summary
)


class TestTransactionGrouping(unittest.TestCase):
    """Test cases for transaction grouping functionality."""
    
    def setUp(self):
        """Set up test data."""
        self.grouper = TransactionGrouper()
        
        # Sample ledger entries for testing
        self.sample_ledger_entries = [
            {
                'name': 'BPL-001',
                'posting_date': '2024-01-15',
                'reference_doctype': 'Sales Invoice',
                'reference_name': 'SI-001',
                'is_proforma': 1,
                'prev_qty': 0,
                'prev_amount': 0,
                'current_qty': 10,
                'current_amount': 5000,
                'accumulated_qty': 10,
                'accumulated_amount': 5000,
                'invoice_status': 'Draft',
                'invoice_docstatus': 0
            },
            {
                'name': 'BPL-002',
                'posting_date': '2024-01-20',
                'reference_doctype': 'Sales Invoice',
                'reference_name': 'SI-002',
                'is_proforma': 0,
                'prev_qty': 10,
                'prev_amount': 4800,  # Adjusted amount after PC
                'current_qty': 5,
                'current_amount': 2500,
                'accumulated_qty': 15,
                'accumulated_amount': 7300,
                'invoice_status': 'Submitted',
                'invoice_docstatus': 1
            }
        ]
        
        # Sample payment certificates for testing
        self.sample_payment_certificates = [
            {
                'name': 'PC-001',
                'posting_date': '2024-01-18',
                'proforma_invoice': 'SI-001',
                'proforma_amount': 5000,
                'accepted_amount': 4800,
                'tax_invoice': 'SI-002',
                'status': 'Submitted',
                'variance': 200
            }
        ]
    
    def test_billing_cycle_creation(self):
        """Test that billing cycles are created correctly."""
        grouped_transactions = self.grouper.group_transactions_by_billing_cycle(
            self.sample_ledger_entries, 
            self.sample_payment_certificates
        )
        
        self.assertEqual(len(grouped_transactions), 1, "Should create one billing cycle")
        
        cycle = grouped_transactions[0]
        self.assertTrue(cycle['cycle_id'].startswith('BC-PI-SI-001'), "Cycle ID should be based on proforma invoice")
        self.assertIsNotNone(cycle['proforma_invoice'], "Should have proforma invoice")
        self.assertIsNotNone(cycle['payment_certificate'], "Should have payment certificate")
        self.assertIsNotNone(cycle['tax_invoice'], "Should have tax invoice")
    
    def test_variance_calculation(self):
        """Test that variance is calculated correctly."""
        grouped_transactions = self.grouper.group_transactions_by_billing_cycle(
            self.sample_ledger_entries, 
            self.sample_payment_certificates
        )
        
        cycle = grouped_transactions[0]
        variance = cycle['variance']
        
        self.assertEqual(variance['amount'], 200, "Variance amount should be 200")
        self.assertEqual(variance['percentage'], 4.0, "Variance percentage should be 4%")
    
    def test_consolidated_values(self):
        """Test that consolidated values are calculated correctly."""
        grouped_transactions = self.grouper.group_transactions_by_billing_cycle(
            self.sample_ledger_entries, 
            self.sample_payment_certificates
        )
        
        cycle = grouped_transactions[0]
        consolidated = cycle['consolidated_values']
        
        # Check that current amount reflects PC accepted amount
        self.assertEqual(flt(consolidated['current_amount']), 4800, 
                        "Current amount should reflect PC accepted amount")
    
    def test_workflow_status(self):
        """Test that workflow status is determined correctly."""
        grouped_transactions = self.grouper.group_transactions_by_billing_cycle(
            self.sample_ledger_entries, 
            self.sample_payment_certificates
        )
        
        cycle = grouped_transactions[0]
        self.assertEqual(cycle['workflow_status'], 'tax_invoice_generated', 
                        "Should show tax invoice generated status")
    
    def test_documents_list(self):
        """Test that documents list is built correctly."""
        grouped_transactions = self.grouper.group_transactions_by_billing_cycle(
            self.sample_ledger_entries, 
            self.sample_payment_certificates
        )
        
        cycle = grouped_transactions[0]
        documents = cycle['documents']
        
        self.assertEqual(len(documents), 3, "Should have 3 documents")
        
        doc_types = [doc['type'] for doc in documents]
        self.assertIn('proforma_invoice', doc_types)
        self.assertIn('payment_certificate', doc_types)
        self.assertIn('tax_invoice', doc_types)
    
    def test_grouping_summary(self):
        """Test that grouping summary is generated correctly."""
        grouped_transactions = self.grouper.group_transactions_by_billing_cycle(
            self.sample_ledger_entries, 
            self.sample_payment_certificates
        )
        
        summary = get_grouped_transaction_summary(grouped_transactions)
        
        self.assertEqual(summary['total_billing_cycles'], 1)
        self.assertEqual(summary['complete_cycles'], 1)
        self.assertEqual(summary['pending_cycles'], 0)
        self.assertEqual(summary['total_proforma_amount'], 5000)
        self.assertEqual(summary['total_accepted_amount'], 4800)
        self.assertEqual(summary['total_variance'], 200)
    
    def test_empty_data_handling(self):
        """Test handling of empty data."""
        grouped_transactions = self.grouper.group_transactions_by_billing_cycle([], [])
        self.assertEqual(len(grouped_transactions), 0, "Should handle empty data gracefully")
    
    def test_orphaned_proforma_handling(self):
        """Test handling of proforma invoices without payment certificates."""
        orphaned_entries = [
            {
                'name': 'BPL-003',
                'posting_date': '2024-01-25',
                'reference_doctype': 'Sales Invoice',
                'reference_name': 'SI-003',
                'is_proforma': 1,
                'prev_qty': 0,
                'prev_amount': 0,
                'current_qty': 8,
                'current_amount': 4000,
                'accumulated_qty': 8,
                'accumulated_amount': 4000,
                'invoice_status': 'Draft',
                'invoice_docstatus': 0
            }
        ]
        
        grouped_transactions = self.grouper.group_transactions_by_billing_cycle(
            orphaned_entries, []
        )
        
        self.assertEqual(len(grouped_transactions), 1, "Should create cycle for orphaned proforma")
        
        cycle = grouped_transactions[0]
        self.assertIsNotNone(cycle['proforma_invoice'])
        self.assertIsNone(cycle['payment_certificate'])
        self.assertIsNone(cycle['tax_invoice'])
        self.assertEqual(cycle['workflow_status'], 'proforma_created')


def run_transaction_grouping_tests():
    """Run all transaction grouping tests."""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestTransactionGrouping)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return {
        'tests_run': result.testsRun,
        'failures': len(result.failures),
        'errors': len(result.errors),
        'success': result.wasSuccessful()
    }


if __name__ == '__main__':
    unittest.main()