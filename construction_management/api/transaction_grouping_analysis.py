# Copyright (c) 2024, Construction Management
# License: MIT

"""
BOQ Transaction History Grouping - Analysis Documentation

This module contains the analysis of the current BOQ Ledger data structure and transaction patterns
to support the implementation of transaction history grouping in the BOQ Management interface.

Analysis Date: 2024-12-31
Analyzed by: Kiro AI Assistant
"""

import frappe
from frappe.utils import flt, getdate
from typing import Dict, List, Any, Optional


class BOQLedgerAnalyzer:
    """
    Analyzer class for understanding BOQ Ledger data structure and transaction patterns.
    
    This class provides methods to analyze the current transaction data structure,
    identify patterns, and document the relationships between different transaction types.
    """
    
    def __init__(self):
        self.transaction_types = {
            'proforma_invoice': 'Sales Invoice with custom_is_proforma = 1',
            'tax_invoice': 'Sales Invoice with custom_is_proforma = 0 or NULL',
            'payment_certificate': 'Payment Certificate document',
            'deduction_entry': 'BOQ Progress Ledger entries with negative amounts',
            'adjustment_entry': 'BOQ Progress Ledger entries created during variations'
        }
    
    def analyze_ledger_structure(self, boq_item: str) -> Dict[str, Any]:
        """
        Analyze the current BOQ Ledger structure for a specific BOQ Item.
        
        Args:
            boq_item: BOQ Item name to analyze
            
        Returns:
            Dict containing analysis results
        """
        # Get all ledger entries for analysis
        ledger_entries = frappe.db.sql("""
            SELECT 
                pl.name,
                pl.posting_date,
                pl.source,
                pl.reference_doctype,
                pl.reference_name,
                pl.qty as transaction_qty,
                pl.amount as transaction_amount,
                pl.prev_qty,
                pl.prev_amount,
                pl.current_qty,
                pl.current_amount,
                pl.accumulated_qty,
                pl.accumulated_amount,
                pl.remarks,
                si.status as invoice_status,
                si.docstatus as invoice_docstatus,
                si.outstanding_amount,
                si.custom_is_proforma as is_proforma,
                si.grand_total as invoice_total
            FROM `tabBOQ Progress Ledger` pl
            LEFT JOIN `tabSales Invoice` si 
                ON pl.reference_name = si.name 
                AND pl.reference_doctype = 'Sales Invoice'
            WHERE pl.boq_item = %s
            ORDER BY pl.posting_date ASC, pl.creation ASC
        """, boq_item, as_dict=True)
        
        # Get payment certificates for this BOQ Item
        payment_certificates = frappe.db.sql("""
            SELECT 
                pc.name,
                pc.posting_date,
                pc.proforma_invoice,
                pc.proforma_amount,
                pc.accepted_amount,
                pc.tax_invoice,
                pc.status,
                (pc.proforma_amount - pc.accepted_amount) as variance
            FROM `tabPayment Certificate` pc
            WHERE pc.boq_item = %s
            AND pc.docstatus != 2
            ORDER BY pc.posting_date ASC
        """, boq_item, as_dict=True)
        
        # Analyze transaction patterns
        analysis = {
            'boq_item': boq_item,
            'total_ledger_entries': len(ledger_entries),
            'total_payment_certificates': len(payment_certificates),
            'transaction_patterns': self._analyze_transaction_patterns(ledger_entries, payment_certificates),
            'billing_cycles': self._identify_billing_cycles(ledger_entries, payment_certificates),
            'deduction_patterns': self._analyze_deduction_patterns(ledger_entries),
            'variance_scenarios': self._analyze_variance_scenarios(payment_certificates),
            'data_relationships': self._analyze_data_relationships(ledger_entries, payment_certificates)
        }
        
        return analysis
    
    def _analyze_transaction_patterns(self, ledger_entries: List[Dict], payment_certificates: List[Dict]) -> Dict[str, Any]:
        """
        Analyze patterns in transaction data.
        
        Returns:
            Dict containing pattern analysis
        """
        patterns = {
            'proforma_invoices': [],
            'tax_invoices': [],
            'deduction_entries': [],
            'adjustment_entries': []
        }
        
        for entry in ledger_entries:
            if entry.reference_doctype == 'Sales Invoice':
                if entry.is_proforma:
                    patterns['proforma_invoices'].append({
                        'name': entry.reference_name,
                        'date': entry.posting_date,
                        'amount': entry.current_amount,
                        'qty': entry.current_qty,
                        'status': entry.invoice_status
                    })
                else:
                    patterns['tax_invoices'].append({
                        'name': entry.reference_name,
                        'date': entry.posting_date,
                        'amount': entry.current_amount,
                        'qty': entry.current_qty,
                        'status': entry.invoice_status
                    })
            
            # Identify deduction/adjustment entries
            if flt(entry.current_amount) < 0:
                patterns['deduction_entries'].append({
                    'name': entry.name,
                    'date': entry.posting_date,
                    'amount': entry.current_amount,
                    'qty': entry.current_qty,
                    'reference': entry.reference_name,
                    'remarks': entry.remarks
                })
        
        return patterns
    
    def _identify_billing_cycles(self, ledger_entries: List[Dict], payment_certificates: List[Dict]) -> List[Dict]:
        """
        Identify billing cycles from the transaction data.
        
        A billing cycle typically follows: Proforma Invoice → Payment Certificate → Tax Invoice
        
        Returns:
            List of identified billing cycles
        """
        billing_cycles = []
        
        # Create a mapping of proforma invoices to payment certificates
        proforma_to_pc = {}
        for pc in payment_certificates:
            if pc.proforma_invoice:
                proforma_to_pc[pc.proforma_invoice] = pc
        
        # Group transactions by billing cycles
        for entry in ledger_entries:
            if entry.reference_doctype == 'Sales Invoice' and entry.is_proforma:
                proforma_name = entry.reference_name
                pc = proforma_to_pc.get(proforma_name)
                
                billing_cycle = {
                    'cycle_id': f"BC-{proforma_name}",
                    'proforma_invoice': {
                        'name': proforma_name,
                        'date': entry.posting_date,
                        'amount': entry.current_amount,
                        'qty': entry.current_qty,
                        'status': entry.invoice_status
                    },
                    'payment_certificate': None,
                    'tax_invoice': None,
                    'adjustments': [],
                    'variance': 0
                }
                
                if pc:
                    billing_cycle['payment_certificate'] = {
                        'name': pc.name,
                        'date': pc.posting_date,
                        'proforma_amount': pc.proforma_amount,
                        'accepted_amount': pc.accepted_amount,
                        'status': pc.status
                    }
                    billing_cycle['variance'] = flt(pc.variance)
                    
                    # Find related tax invoice
                    if pc.tax_invoice:
                        tax_invoice_entry = next((e for e in ledger_entries 
                                                if e.reference_name == pc.tax_invoice), None)
                        if tax_invoice_entry:
                            billing_cycle['tax_invoice'] = {
                                'name': pc.tax_invoice,
                                'date': tax_invoice_entry.posting_date,
                                'amount': tax_invoice_entry.current_amount,
                                'qty': tax_invoice_entry.current_qty,
                                'status': tax_invoice_entry.invoice_status
                            }
                
                billing_cycles.append(billing_cycle)
        
        return billing_cycles
    
    def _analyze_deduction_patterns(self, ledger_entries: List[Dict]) -> Dict[str, Any]:
        """
        Analyze patterns in deduction entries.
        
        Returns:
            Dict containing deduction analysis
        """
        deductions = []
        total_deductions = 0
        
        for entry in ledger_entries:
            if flt(entry.current_amount) < 0:
                deductions.append({
                    'name': entry.name,
                    'date': entry.posting_date,
                    'amount': entry.current_amount,
                    'reference': entry.reference_name,
                    'remarks': entry.remarks
                })
                total_deductions += abs(flt(entry.current_amount))
        
        return {
            'total_deduction_entries': len(deductions),
            'total_deduction_amount': total_deductions,
            'deduction_entries': deductions,
            'patterns': {
                'variation_adjustments': len([d for d in deductions if 'variation' in (d.get('remarks') or '').lower()]),
                'payment_certificate_adjustments': len([d for d in deductions if 'payment certificate' in (d.get('remarks') or '').lower()])
            }
        }
    
    def _analyze_variance_scenarios(self, payment_certificates: List[Dict]) -> Dict[str, Any]:
        """
        Analyze variance scenarios in payment certificates.
        
        Returns:
            Dict containing variance analysis
        """
        variances = []
        total_variance = 0
        positive_variances = 0
        negative_variances = 0
        
        for pc in payment_certificates:
            variance = flt(pc.variance)
            if variance != 0:
                variances.append({
                    'pc_name': pc.name,
                    'proforma_invoice': pc.proforma_invoice,
                    'proforma_amount': pc.proforma_amount,
                    'accepted_amount': pc.accepted_amount,
                    'variance': variance,
                    'variance_percent': (variance / pc.proforma_amount * 100) if pc.proforma_amount else 0
                })
                
                total_variance += abs(variance)
                if variance > 0:
                    positive_variances += 1
                else:
                    negative_variances += 1
        
        return {
            'total_variance_cases': len(variances),
            'total_variance_amount': total_variance,
            'positive_variances': positive_variances,  # Proforma > PC (loss)
            'negative_variances': negative_variances,  # Proforma < PC (gain)
            'variance_details': variances
        }
    
    def _analyze_data_relationships(self, ledger_entries: List[Dict], payment_certificates: List[Dict]) -> Dict[str, Any]:
        """
        Analyze relationships between different data entities.
        
        Returns:
            Dict containing relationship analysis
        """
        relationships = {
            'proforma_to_pc_links': 0,
            'pc_to_tax_invoice_links': 0,
            'orphaned_proformas': 0,
            'orphaned_tax_invoices': 0,
            'complete_cycles': 0
        }
        
        # Create mappings
        proforma_invoices = [e.reference_name for e in ledger_entries 
                           if e.reference_doctype == 'Sales Invoice' and e.is_proforma]
        tax_invoices = [e.reference_name for e in ledger_entries 
                       if e.reference_doctype == 'Sales Invoice' and not e.is_proforma]
        
        linked_proformas = [pc.proforma_invoice for pc in payment_certificates if pc.proforma_invoice]
        linked_tax_invoices = [pc.tax_invoice for pc in payment_certificates if pc.tax_invoice]
        
        relationships['proforma_to_pc_links'] = len(linked_proformas)
        relationships['pc_to_tax_invoice_links'] = len(linked_tax_invoices)
        relationships['orphaned_proformas'] = len([p for p in proforma_invoices if p not in linked_proformas])
        relationships['orphaned_tax_invoices'] = len([t for t in tax_invoices if t not in linked_tax_invoices])
        relationships['complete_cycles'] = len([pc for pc in payment_certificates 
                                             if pc.proforma_invoice and pc.tax_invoice])
        
        return relationships


def generate_analysis_report(boq_item: str) -> str:
    """
    Generate a comprehensive analysis report for a BOQ Item's transaction patterns.
    
    Args:
        boq_item: BOQ Item name to analyze
        
    Returns:
        String containing formatted analysis report
    """
    analyzer = BOQLedgerAnalyzer()
    analysis = analyzer.analyze_ledger_structure(boq_item)
    
    report = f"""
BOQ TRANSACTION ANALYSIS REPORT
===============================

BOQ Item: {boq_item}
Analysis Date: {frappe.utils.now()}

SUMMARY STATISTICS
------------------
Total Ledger Entries: {analysis['total_ledger_entries']}
Total Payment Certificates: {analysis['total_payment_certificates']}

TRANSACTION PATTERNS
--------------------
Proforma Invoices: {len(analysis['transaction_patterns']['proforma_invoices'])}
Tax Invoices: {len(analysis['transaction_patterns']['tax_invoices'])}
Deduction Entries: {len(analysis['transaction_patterns']['deduction_entries'])}

BILLING CYCLES IDENTIFIED
--------------------------
Total Billing Cycles: {len(analysis['billing_cycles'])}
Complete Cycles (Proforma → PC → Tax Invoice): {analysis['data_relationships']['complete_cycles']}

VARIANCE ANALYSIS
-----------------
Total Variance Cases: {analysis['variance_scenarios']['total_variance_cases']}
Positive Variances (Loss): {analysis['variance_scenarios']['positive_variances']}
Negative Variances (Gain): {analysis['variance_scenarios']['negative_variances']}
Total Variance Amount: {analysis['variance_scenarios']['total_variance_amount']}

DEDUCTION PATTERNS
------------------
Total Deduction Entries: {analysis['deduction_patterns']['total_deduction_entries']}
Total Deduction Amount: {analysis['deduction_patterns']['total_deduction_amount']}

DATA RELATIONSHIPS
------------------
Proforma to PC Links: {analysis['data_relationships']['proforma_to_pc_links']}
PC to Tax Invoice Links: {analysis['data_relationships']['pc_to_tax_invoice_links']}
Orphaned Proformas: {analysis['data_relationships']['orphaned_proformas']}
Orphaned Tax Invoices: {analysis['data_relationships']['orphaned_tax_invoices']}

GROUPING IMPLICATIONS
---------------------
Based on this analysis, the transaction grouping algorithm should:

1. Group transactions by Proforma Invoice as the primary key
2. Link Payment Certificates to their corresponding Proforma Invoices
3. Connect Tax Invoices through Payment Certificate references
4. Consolidate deduction entries with their parent billing cycles
5. Handle orphaned transactions gracefully
6. Preserve variance information for display

RECOMMENDED GROUPING STRATEGY
-----------------------------
1. Start with Proforma Invoices as billing cycle initiators
2. Find related Payment Certificates by proforma_invoice field
3. Locate Tax Invoices through Payment Certificate tax_invoice field
4. Group deduction entries by date proximity and document references
5. Calculate net values for each complete billing cycle
6. Display consolidated Previous/Current/Accumulated values
"""
    
    return report


# Analysis constants and patterns identified
TRANSACTION_FLOW_PATTERNS = {
    'standard_cycle': 'Proforma Invoice → Payment Certificate → Tax Invoice',
    'variation_cycle': 'Proforma Invoice → Payment Certificate (with variance) → Deduction Entry → Tax Invoice',
    'partial_cycle': 'Proforma Invoice → Payment Certificate (no Tax Invoice yet)',
    'orphaned_proforma': 'Proforma Invoice (no Payment Certificate)',
    'orphaned_tax_invoice': 'Tax Invoice (no Payment Certificate link)'
}

GROUPING_RULES = {
    'primary_grouping': 'Group by Proforma Invoice reference',
    'secondary_grouping': 'Link Payment Certificates by proforma_invoice field',
    'tertiary_grouping': 'Connect Tax Invoices through Payment Certificate tax_invoice field',
    'adjustment_handling': 'Consolidate deduction entries with parent billing cycles',
    'variance_calculation': 'Calculate variance as Proforma Amount - Payment Certificate Amount',
    'display_priority': 'Show consolidated billing cycles, hide technical deduction entries'
}

IDENTIFIED_CHALLENGES = {
    'multiple_proformas': 'Handle cases where multiple Proforma Invoices exist for same BOQ Item',
    'amendment_scenarios': 'Handle amended/cancelled documents in grouping logic',
    'partial_billing': 'Handle incomplete billing cycles gracefully',
    'data_integrity': 'Ensure grouped totals match underlying ledger totals',
    'performance': 'Optimize grouping algorithm for large datasets'
}