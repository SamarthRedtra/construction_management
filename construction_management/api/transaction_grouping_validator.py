# Copyright (c) 2024, Construction Management
# License: MIT

"""
Transaction Grouping Data Validation

This module provides comprehensive validation for the transaction grouping functionality
to ensure data integrity and catch any grouping errors or inconsistencies.
"""

import frappe
from frappe.utils import flt, getdate, cstr
from typing import Dict, List, Any, Tuple, Optional
import json


class TransactionGroupingValidator:
    """
    Validator class for transaction grouping data integrity.
    
    This class provides methods to validate that grouped transaction data
    maintains integrity with the underlying BOQ Ledger data.
    """
    
    def __init__(self):
        self.validation_errors = []
        self.validation_warnings = []
    
    def validate_grouped_totals(self, grouped_transactions: List[Dict], 
                               ledger_entries: List[Dict]) -> Dict[str, Any]:
        """
        Validate that grouped totals match underlying ledger totals.
        
        Args:
            grouped_transactions: List of grouped billing cycles
            ledger_entries: List of raw ledger entries
            
        Returns:
            Dict containing validation results
        """
        validation_result = {
            'is_valid': True,
            'total_amount_match': False,
            'total_qty_match': False,
            'amount_difference': 0,
            'qty_difference': 0,
            'errors': [],
            'warnings': []
        }
        
        try:
            # Calculate totals from raw ledger entries
            ledger_total_qty = sum(flt(entry.get('current_qty', 0)) for entry in ledger_entries)
            ledger_total_amount = sum(flt(entry.get('current_amount', 0)) for entry in ledger_entries)
            
            # Calculate totals from grouped transactions
            grouped_total_qty = sum(
                flt(cycle.get('consolidated_values', {}).get('current_qty', 0)) 
                for cycle in grouped_transactions
            )
            grouped_total_amount = sum(
                flt(cycle.get('consolidated_values', {}).get('current_amount', 0)) 
                for cycle in grouped_transactions
            )
            
            # Calculate differences
            qty_diff = abs(ledger_total_qty - grouped_total_qty)
            amount_diff = abs(ledger_total_amount - grouped_total_amount)
            
            validation_result.update({
                'amount_difference': amount_diff,
                'qty_difference': qty_diff,
                'total_amount_match': amount_diff < 0.01,  # Allow for rounding
                'total_qty_match': qty_diff < 0.01,
                'ledger_totals': {
                    'qty': ledger_total_qty,
                    'amount': ledger_total_amount
                },
                'grouped_totals': {
                    'qty': grouped_total_qty,
                    'amount': grouped_total_amount
                }
            })
            
            # Check for significant discrepancies
            if amount_diff >= 0.01:
                validation_result['errors'].append(
                    f"Amount mismatch: Ledger={ledger_total_amount}, Grouped={grouped_total_amount}, Diff={amount_diff}"
                )
                validation_result['is_valid'] = False
            
            if qty_diff >= 0.01:
                validation_result['errors'].append(
                    f"Quantity mismatch: Ledger={ledger_total_qty}, Grouped={grouped_total_qty}, Diff={qty_diff}"
                )
                validation_result['is_valid'] = False
            
        except Exception as e:
            validation_result['errors'].append(f"Validation error: {str(e)}")
            validation_result['is_valid'] = False
        
        return validation_result
    
    def check_orphaned_transactions(self, grouped_transactions: List[Dict], 
                                   ledger_entries: List[Dict]) -> Dict[str, Any]:
        """
        Check for orphaned transactions and missing relationships.
        
        Returns:
            Dict containing orphaned transaction analysis
        """
        orphaned_analysis = {
            'orphaned_proformas': [],
            'orphaned_tax_invoices': [],
            'missing_relationships': [],
            'incomplete_cycles': []
        }
        
        try:
            # Get all proforma and tax invoices from ledger entries
            proforma_invoices = set()
            tax_invoices = set()
            
            for entry in ledger_entries:
                if entry.get('reference_doctype') == 'Sales Invoice':
                    if entry.get('is_proforma'):
                        proforma_invoices.add(entry.get('reference_name'))
                    else:
                        tax_invoices.add(entry.get('reference_name'))
            
            # Get all invoices referenced in grouped transactions
            grouped_proformas = set()
            grouped_tax_invoices = set()
            
            for cycle in grouped_transactions:
                if cycle.get('proforma_invoice'):
                    grouped_proformas.add(cycle['proforma_invoice']['name'])
                if cycle.get('tax_invoice'):
                    grouped_tax_invoices.add(cycle['tax_invoice']['name'])
            
            # Find orphaned transactions
            orphaned_analysis['orphaned_proformas'] = list(proforma_invoices - grouped_proformas)
            orphaned_analysis['orphaned_tax_invoices'] = list(tax_invoices - grouped_tax_invoices)
            
            # Check for incomplete cycles
            for cycle in grouped_transactions:
                issues = []
                if cycle.get('proforma_invoice') and not cycle.get('payment_certificate'):
                    issues.append('Missing Payment Certificate')
                if cycle.get('payment_certificate') and not cycle.get('tax_invoice'):
                    issues.append('Missing Tax Invoice')
                
                if issues:
                    orphaned_analysis['incomplete_cycles'].append({
                        'cycle_id': cycle.get('cycle_id'),
                        'issues': issues
                    })
            
        except Exception as e:
            orphaned_analysis['error'] = str(e)
        
        return orphaned_analysis
    
    def validate_billing_cycle_integrity(self, grouped_transactions: List[Dict]) -> Dict[str, Any]:
        """
        Validate the integrity of individual billing cycles.
        
        Returns:
            Dict containing cycle integrity validation results
        """
        integrity_results = {
            'valid_cycles': 0,
            'invalid_cycles': 0,
            'cycle_issues': []
        }
        
        for cycle in grouped_transactions:
            cycle_issues = []
            cycle_id = cycle.get('cycle_id', 'Unknown')
            
            try:
                # Check proforma invoice presence
                if not cycle.get('proforma_invoice'):
                    cycle_issues.append('Missing proforma invoice')
                
                # Check consolidated values
                consolidated = cycle.get('consolidated_values', {})
                if not consolidated:
                    cycle_issues.append('Missing consolidated values')
                else:
                    # Validate accumulated values
                    prev_qty = flt(consolidated.get('prev_qty', 0))
                    current_qty = flt(consolidated.get('current_qty', 0))
                    accumulated_qty = flt(consolidated.get('accumulated_qty', 0))
                    
                    if abs(accumulated_qty - (prev_qty + current_qty)) > 0.01:
                        cycle_issues.append(f'Accumulated qty mismatch: {accumulated_qty} != {prev_qty} + {current_qty}')
                    
                    prev_amount = flt(consolidated.get('prev_amount', 0))
                    current_amount = flt(consolidated.get('current_amount', 0))
                    accumulated_amount = flt(consolidated.get('accumulated_amount', 0))
                    
                    if abs(accumulated_amount - (prev_amount + current_amount)) > 0.01:
                        cycle_issues.append(f'Accumulated amount mismatch: {accumulated_amount} != {prev_amount} + {current_amount}')
                
                # Check variance calculation
                if cycle.get('payment_certificate') and cycle.get('proforma_invoice'):
                    pc_amount = flt(cycle['payment_certificate'].get('accepted_amount', 0))
                    pi_amount = flt(cycle['proforma_invoice'].get('amount', 0))
                    calculated_variance = pi_amount - pc_amount
                    
                    cycle_variance = flt(cycle.get('variance', {}).get('amount', 0))
                    if abs(calculated_variance - cycle_variance) > 0.01:
                        cycle_issues.append(f'Variance calculation error: {cycle_variance} != {calculated_variance}')
                
                # Check workflow status consistency
                workflow_status = cycle.get('workflow_status', '')
                has_proforma = bool(cycle.get('proforma_invoice'))
                has_pc = bool(cycle.get('payment_certificate'))
                has_tax_invoice = bool(cycle.get('tax_invoice'))
                
                if workflow_status == 'tax_invoice_generated' and not has_tax_invoice:
                    cycle_issues.append('Workflow status indicates tax invoice generated but no tax invoice found')
                elif workflow_status == 'pc_approved' and not has_pc:
                    cycle_issues.append('Workflow status indicates PC approved but no payment certificate found')
                elif workflow_status == 'proforma_created' and not has_proforma:
                    cycle_issues.append('Workflow status indicates proforma created but no proforma invoice found')
                
            except Exception as e:
                cycle_issues.append(f'Validation error: {str(e)}')
            
            if cycle_issues:
                integrity_results['invalid_cycles'] += 1
                integrity_results['cycle_issues'].append({
                    'cycle_id': cycle_id,
                    'issues': cycle_issues
                })
            else:
                integrity_results['valid_cycles'] += 1
        
        return integrity_results
    
    def generate_validation_report(self, boq_item: str, grouped_transactions: List[Dict], 
                                 ledger_entries: List[Dict]) -> Dict[str, Any]:
        """
        Generate a comprehensive validation report.
        
        Returns:
            Dict containing complete validation report
        """
        report = {
            'boq_item': boq_item,
            'validation_timestamp': frappe.utils.now(),
            'summary': {
                'total_cycles': len(grouped_transactions),
                'total_ledger_entries': len(ledger_entries),
                'overall_status': 'pending'
            },
            'validations': {}
        }
        
        try:
            # Run all validations
            report['validations']['totals'] = self.validate_grouped_totals(grouped_transactions, ledger_entries)
            report['validations']['orphaned'] = self.check_orphaned_transactions(grouped_transactions, ledger_entries)
            report['validations']['integrity'] = self.validate_billing_cycle_integrity(grouped_transactions)
            
            # Determine overall status
            totals_valid = report['validations']['totals']['is_valid']
            has_orphaned = (len(report['validations']['orphaned']['orphaned_proformas']) > 0 or 
                           len(report['validations']['orphaned']['orphaned_tax_invoices']) > 0)
            integrity_issues = report['validations']['integrity']['invalid_cycles'] > 0
            
            if totals_valid and not has_orphaned and not integrity_issues:
                report['summary']['overall_status'] = 'passed'
            elif totals_valid and (has_orphaned or integrity_issues):
                report['summary']['overall_status'] = 'passed_with_warnings'
            else:
                report['summary']['overall_status'] = 'failed'
            
            # Add summary statistics
            report['summary'].update({
                'amount_match': report['validations']['totals']['total_amount_match'],
                'qty_match': report['validations']['totals']['total_qty_match'],
                'orphaned_count': (len(report['validations']['orphaned']['orphaned_proformas']) + 
                                 len(report['validations']['orphaned']['orphaned_tax_invoices'])),
                'invalid_cycles': report['validations']['integrity']['invalid_cycles'],
                'valid_cycles': report['validations']['integrity']['valid_cycles']
            })
            
        except Exception as e:
            report['summary']['overall_status'] = 'error'
            report['error'] = str(e)
        
        return report


@frappe.whitelist()
def validate_transaction_grouping(boq_item: str) -> Dict[str, Any]:
    """
    API endpoint to validate transaction grouping for a specific BOQ Item.
    
    Args:
        boq_item: BOQ Item name to validate
        
    Returns:
        Dict containing validation results
    """
    try:
        # Get both raw and grouped data
        from construction_management.api.boq_invoice import get_boq_invoice_history
        
        raw_data = get_boq_invoice_history(boq_item, grouped_view=0)
        grouped_data = get_boq_invoice_history(boq_item, grouped_view=1)
        
        if grouped_data.get('view_mode') != 'grouped':
            return {
                'status': 'error',
                'error_message': 'Failed to get grouped view data',
                'boq_item': boq_item
            }
        
        # Run validation
        validator = TransactionGroupingValidator()
        report = validator.generate_validation_report(
            boq_item,
            grouped_data.get('grouped_transactions', []),
            raw_data.get('ledger_entries', [])
        )
        
        return {
            'status': 'success',
            'validation_report': report
        }
        
    except Exception as e:
        frappe.log_error(f"Transaction grouping validation failed for {boq_item}: {str(e)}", 
                        "Transaction Grouping Validation")
        return {
            'status': 'error',
            'error_message': str(e),
            'boq_item': boq_item
        }


@frappe.whitelist()
def run_batch_validation(limit: int = 10) -> Dict[str, Any]:
    """
    Run validation on multiple BOQ Items to test grouping functionality.
    
    Args:
        limit: Maximum number of items to validate
        
    Returns:
        Dict containing batch validation results
    """
    try:
        # Get BOQ Items with transaction data
        items = frappe.db.sql("""
            SELECT DISTINCT bi.name
            FROM `tabBOQ Item` bi
            INNER JOIN `tabBOQ Progress Ledger` pl ON pl.boq_item = bi.name
            WHERE bi.docstatus != 2
            ORDER BY bi.creation DESC
            LIMIT %s
        """, limit, as_dict=True)
        
        batch_results = {
            'total_items': len(items),
            'passed': 0,
            'passed_with_warnings': 0,
            'failed': 0,
            'errors': 0,
            'item_results': []
        }
        
        for item in items:
            result = validate_transaction_grouping(item.name)
            
            if result['status'] == 'success':
                report = result['validation_report']
                status = report['summary']['overall_status']
                
                if status == 'passed':
                    batch_results['passed'] += 1
                elif status == 'passed_with_warnings':
                    batch_results['passed_with_warnings'] += 1
                elif status == 'failed':
                    batch_results['failed'] += 1
                else:
                    batch_results['errors'] += 1
                
                batch_results['item_results'].append({
                    'boq_item': item.name,
                    'status': status,
                    'summary': report['summary']
                })
            else:
                batch_results['errors'] += 1
                batch_results['item_results'].append({
                    'boq_item': item.name,
                    'status': 'error',
                    'error': result.get('error_message', 'Unknown error')
                })
        
        return {
            'status': 'completed',
            'batch_results': batch_results
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'error_message': str(e)
        }