# Copyright (c) 2024, Construction Management
# License: MIT

"""
BOQ Transaction History Grouping Implementation

This module implements the transaction grouping logic for the BOQ Management interface.
It groups related transactions (Proforma Invoice, Payment Certificate, Tax Invoice) into
logical billing cycles while preserving the underlying BOQ Ledger data integrity.
"""

import frappe
from frappe.utils import flt, getdate, cstr
from typing import Dict, List, Any, Optional, Tuple
import uuid
import json
from datetime import datetime


class TransactionGrouper:
    """
    Main class for grouping BOQ transactions into logical billing cycles.
    
    This class processes raw BOQ Ledger entries and Payment Certificate data
    to create grouped transaction records that follow the business workflow:
    Proforma Invoice → Payment Certificate → Tax Invoice
    """
    
    def __init__(self):
        self.grouped_cache = {}  # Cache for grouped results
        self.cache_timeout = 300  # 5 minutes cache timeout
    
    def group_transactions_by_billing_cycle(self, ledger_entries: List[Dict], 
                                           payment_certificates: List[Dict], 
                                           use_cache: bool = True) -> List[Dict]:
        """
        Group ledger entries and payment certificates into logical billing cycles.
        
        Args:
            ledger_entries: List of BOQ Progress Ledger entries
            payment_certificates: List of Payment Certificate records
            use_cache: Whether to use caching for performance optimization
            
        Returns:
            List of grouped billing cycle records
        """
        # Generate cache key based on data
        if use_cache:
            cache_key = self._generate_cache_key(ledger_entries, payment_certificates)
            cached_result = self._get_cached_result(cache_key)
            if cached_result:
                return cached_result
        
        # Step 1: Create billing cycle mapping
        billing_cycles = self._create_billing_cycle_mapping(ledger_entries, payment_certificates)
        
        # Step 2: Consolidate adjustments and deductions
        billing_cycles = self._consolidate_adjustments(billing_cycles, ledger_entries)
        
        # Step 3: Calculate consolidated values
        billing_cycles = self._calculate_consolidated_values(billing_cycles)
        
        # Step 4: Validate data integrity
        self._validate_grouped_totals(billing_cycles, ledger_entries)
        
        result = list(billing_cycles.values())
        
        # Cache the result
        if use_cache:
            self._cache_result(cache_key, result)
        
        return result
    
    def _generate_cache_key(self, ledger_entries: List[Dict], 
                           payment_certificates: List[Dict]) -> str:
        """Generate cache key based on data content."""
        import hashlib
        
        # Create a hash based on the data content
        data_str = json.dumps({
            'ledger_count': len(ledger_entries),
            'pc_count': len(payment_certificates),
            'ledger_hash': hashlib.md5(str(ledger_entries).encode()).hexdigest()[:8],
            'pc_hash': hashlib.md5(str(payment_certificates).encode()).hexdigest()[:8]
        }, sort_keys=True)
        
        return hashlib.md5(data_str.encode()).hexdigest()
    
    def _get_cached_result(self, cache_key: str) -> Optional[List[Dict]]:
        """Get cached result if available and not expired."""
        if cache_key in self.grouped_cache:
            cached_data = self.grouped_cache[cache_key]
            cache_time = cached_data.get('timestamp', 0)
            
            # Check if cache is still valid
            if (frappe.utils.now_datetime().timestamp() - cache_time) < self.cache_timeout:
                return cached_data.get('result')
            else:
                # Remove expired cache
                del self.grouped_cache[cache_key]
        
        return None
    
    def _cache_result(self, cache_key: str, result: List[Dict]):
        """Cache the grouping result."""
        self.grouped_cache[cache_key] = {
            'result': result,
            'timestamp': frappe.utils.now_datetime().timestamp()
        }
        
        # Limit cache size to prevent memory issues
        if len(self.grouped_cache) > 100:
            # Remove oldest entries
            oldest_key = min(self.grouped_cache.keys(), 
                           key=lambda k: self.grouped_cache[k]['timestamp'])
            del self.grouped_cache[oldest_key]
    
    def invalidate_cache(self, boq_item: str = None):
        """Invalidate cache for specific BOQ item or all cache."""
        if boq_item:
            # Remove cache entries related to specific BOQ item
            keys_to_remove = []
            for key in self.grouped_cache:
                # This is a simple approach - in production, you might want more sophisticated cache key management
                keys_to_remove.append(key)
            
            for key in keys_to_remove:
                if key in self.grouped_cache:
                    del self.grouped_cache[key]
        else:
            # Clear all cache
            self.grouped_cache.clear()
    
    def _create_billing_cycle_mapping(self, ledger_entries: List[Dict], 
                                    payment_certificates: List[Dict]) -> Dict[str, Dict]:
        """
        Create initial billing cycle mapping based on Proforma Invoices.
        
        Returns:
            Dict mapping cycle IDs to billing cycle data
        """
        billing_cycles = {}
        
        # Create mapping of proforma invoices to payment certificates
        proforma_to_pc = {}
        for pc in payment_certificates:
            if pc.proforma_invoice:
                proforma_to_pc[pc.proforma_invoice] = pc
        
        # Process ledger entries to identify billing cycles
        for entry in ledger_entries:
            if entry.reference_doctype == 'Proforma Invoice':
                cycle_id = self._generate_cycle_id(entry.reference_name)
                
                if cycle_id not in billing_cycles:
                    billing_cycles[cycle_id] = self._initialize_billing_cycle(
                        cycle_id, entry, proforma_to_pc.get(entry.reference_name)
                    )
            
            elif entry.reference_doctype == 'Sales Invoice':
                # Handle tax invoices - find their parent cycle through payment certificate
                parent_cycle_id = self._find_parent_cycle_for_tax_invoice(
                    entry.reference_name, payment_certificates
                )
                if parent_cycle_id and parent_cycle_id in billing_cycles:
                    billing_cycles[parent_cycle_id]['tax_invoice'] = self._create_tax_invoice_record(entry)
        
        return billing_cycles
    
    def _initialize_billing_cycle(self, cycle_id: str, proforma_entry: Dict, 
                                 payment_certificate: Optional[Dict]) -> Dict:
        """
        Initialize a billing cycle record with proforma invoice and payment certificate data.
        
        Returns:
            Dict containing initialized billing cycle
        """
        cycle = {
            'cycle_id': cycle_id,
            'proforma_invoice': self._create_proforma_record(proforma_entry),
            'payment_certificate': None,
            'tax_invoice': None,
            'adjustments': [],
            'consolidated_values': {
                'prev_qty': flt(proforma_entry.prev_qty),
                'prev_amount': flt(proforma_entry.prev_amount),
                'current_qty': flt(proforma_entry.current_qty),
                'current_amount': flt(proforma_entry.current_amount),
                'accumulated_qty': flt(proforma_entry.accumulated_qty),
                'accumulated_amount': flt(proforma_entry.accumulated_amount)
            },
            'variance': {
                'amount': 0,
                'percentage': 0
            },
            'workflow_status': 'proforma_created',
            'documents': []
        }
        
        # Add payment certificate if exists
        if payment_certificate:
            cycle['payment_certificate'] = self._create_payment_certificate_record(payment_certificate)
            cycle['variance'] = self._calculate_variance(payment_certificate)
            cycle['workflow_status'] = self._determine_workflow_status(payment_certificate)
            
            # Adjust consolidated values based on payment certificate
            if flt(payment_certificate.accepted_amount) != flt(proforma_entry.current_amount):
                cycle['consolidated_values']['current_amount'] = flt(payment_certificate.accepted_amount)
                cycle['consolidated_values']['accumulated_amount'] = (
                    flt(proforma_entry.prev_amount) + flt(payment_certificate.accepted_amount)
                )
        
        # Build documents list
        cycle['documents'] = self._build_documents_list(cycle)
        
        return cycle
    
    def _create_proforma_record(self, entry: Dict) -> Dict:
        """Create proforma invoice record for billing cycle."""
        # Check if invoice_status is present (from LEFT JOIN query), otherwise default to Draft
        status = 'Submitted' if entry.docstatus == 1 else 'Draft'
        if hasattr(entry, 'invoice_status') and entry.invoice_status:
            status = entry.invoice_status
            
        return {
            'name': entry.reference_name,
            'date': entry.posting_date,
            'amount': flt(entry.current_amount),
            'qty': flt(entry.current_qty),
            'status': status,
            'docstatus': entry.docstatus if hasattr(entry, 'docstatus') else 1
        }
    
    def _create_payment_certificate_record(self, pc: Dict) -> Dict:
        """Create payment certificate record for billing cycle."""
        return {
            'name': pc.name,
            'date': pc.posting_date,
            'proforma_amount': flt(pc.proforma_amount),
            'accepted_amount': flt(pc.accepted_amount),
            'status': pc.status or 'Draft',
            'tax_invoice': pc.tax_invoice
        }
    
    def _create_tax_invoice_record(self, entry: Dict) -> Dict:
        """Create tax invoice record for billing cycle."""
        return {
            'name': entry.reference_name,
            'date': entry.posting_date,
            'amount': flt(entry.current_amount),
            'qty': flt(entry.current_qty),
            'status': entry.invoice_status or 'Draft',
            'docstatus': entry.invoice_docstatus
        }
    
    def _calculate_variance(self, payment_certificate: Dict) -> Dict:
        """Calculate variance between proforma and payment certificate amounts."""
        proforma_amount = flt(payment_certificate.proforma_amount)
        accepted_amount = flt(payment_certificate.accepted_amount)
        variance_amount = proforma_amount - accepted_amount
        variance_percentage = (variance_amount / proforma_amount * 100) if proforma_amount else 0
        
        return {
            'amount': variance_amount,
            'percentage': round(variance_percentage, 2)
        }
    
    def _determine_workflow_status(self, payment_certificate: Dict) -> str:
        """Determine workflow status based on payment certificate data."""
        if payment_certificate.tax_invoice:
            return 'tax_invoice_generated'
        elif payment_certificate.status == 'Submitted':
            return 'pc_approved'
        else:
            return 'pc_draft'
    
    def _build_documents_list(self, cycle: Dict) -> List[Dict]:
        """Build list of documents in the billing cycle."""
        documents = []
        
        # Add proforma invoice
        if cycle['proforma_invoice']:
            documents.append({
                'type': 'proforma_invoice',
                'name': cycle['proforma_invoice']['name'],
                'date': cycle['proforma_invoice']['date'],
                'amount': cycle['proforma_invoice']['amount'],
                'status': cycle['proforma_invoice']['status']
            })
        
        # Add payment certificate
        if cycle['payment_certificate']:
            documents.append({
                'type': 'payment_certificate',
                'name': cycle['payment_certificate']['name'],
                'date': cycle['payment_certificate']['date'],
                'amount': cycle['payment_certificate']['accepted_amount'],
                'status': cycle['payment_certificate']['status']
            })
        
        # Add tax invoice
        if cycle['tax_invoice']:
            documents.append({
                'type': 'tax_invoice',
                'name': cycle['tax_invoice']['name'],
                'date': cycle['tax_invoice']['date'],
                'amount': cycle['tax_invoice']['amount'],
                'status': cycle['tax_invoice']['status']
            })
        
        return documents
    
    def _consolidate_adjustments(self, billing_cycles: Dict[str, Dict], 
                                ledger_entries: List[Dict]) -> Dict[str, Dict]:
        """
        Consolidate adjustment and deduction entries with their parent billing cycles.
        
        Args:
            billing_cycles: Dict of billing cycles
            ledger_entries: List of all ledger entries
            
        Returns:
            Updated billing cycles with consolidated adjustments
        """
        for entry in ledger_entries:
            # Skip entries already processed as main transactions
            if (entry.reference_doctype == 'Proforma Invoice' or 
                (entry.reference_doctype == 'Sales Invoice' and 
                 self._is_tax_invoice_in_cycles(entry.reference_name, billing_cycles))):
                continue
            
            # Process deduction/adjustment entries
            if flt(entry.current_amount) < 0 or 'adjustment' in (entry.remarks or '').lower():
                parent_cycle_id = self._find_parent_cycle_for_adjustment(entry, billing_cycles)
                if parent_cycle_id:
                    billing_cycles[parent_cycle_id]['adjustments'].append({
                        'name': entry.name,
                        'date': entry.posting_date,
                        'amount': flt(entry.current_amount),
                        'qty': flt(entry.current_qty),
                        'reference': entry.reference_name,
                        'remarks': entry.remarks,
                        'type': 'deduction' if flt(entry.current_amount) < 0 else 'adjustment'
                    })
        
        return billing_cycles
    
    def _calculate_consolidated_values(self, billing_cycles: Dict[str, Dict]) -> Dict[str, Dict]:
        """
        Calculate consolidated Previous, Current, and Accumulated values for each billing cycle.
        
        This method recalculates the progressive values based on the net effect of each
        billing cycle, taking into account adjustments and variances.
        """
        # Sort cycles by date for progressive calculation
        sorted_cycles = sorted(billing_cycles.values(), 
                             key=lambda x: x['proforma_invoice']['date'] if x['proforma_invoice'] else '')
        
        running_qty = 0
        running_amount = 0
        
        for cycle in sorted_cycles:
            # Get the effective current values (after adjustments)
            effective_current_qty = cycle['consolidated_values']['current_qty']
            effective_current_amount = cycle['consolidated_values']['current_amount']
            
            # Apply adjustments
            for adjustment in cycle['adjustments']:
                effective_current_qty += flt(adjustment['qty'])
                effective_current_amount += flt(adjustment['amount'])
            
            # Update consolidated values
            cycle['consolidated_values'].update({
                'prev_qty': running_qty,
                'prev_amount': running_amount,
                'current_qty': effective_current_qty,
                'current_amount': effective_current_amount,
                'accumulated_qty': running_qty + effective_current_qty,
                'accumulated_amount': running_amount + effective_current_amount
            })
            
            # Update running totals for next cycle
            running_qty += effective_current_qty
            running_amount += effective_current_amount
            
            # Update cycle ID in the dict
            billing_cycles[cycle['cycle_id']] = cycle
        
        return billing_cycles
    
    def _validate_grouped_totals(self, billing_cycles: List[Dict], ledger_entries: List[Dict]):
        """
        Validate that grouped transaction totals match underlying ledger totals.
        
        This ensures data integrity and catches any grouping errors.
        """
        # Calculate totals from grouped data
        grouped_total_qty = sum(flt(cycle['consolidated_values']['current_qty']) for cycle in billing_cycles)
        grouped_total_amount = sum(flt(cycle['consolidated_values']['current_amount']) for cycle in billing_cycles)
        
        # Calculate totals from raw ledger entries
        ledger_total_qty = sum(flt(entry.current_qty) for entry in ledger_entries)
        ledger_total_amount = sum(flt(entry.current_amount) for entry in ledger_entries)
        
        # Check for discrepancies
        qty_diff = abs(grouped_total_qty - ledger_total_qty)
        amount_diff = abs(grouped_total_amount - ledger_total_amount)
        
        if qty_diff > 0.01 or amount_diff > 0.01:  # Allow for minor rounding differences
            frappe.log_error(
                f"Transaction grouping validation failed. "
                f"Qty difference: {qty_diff}, Amount difference: {amount_diff}",
                "Transaction Grouping Validation Error"
            )
    
    def _generate_cycle_id(self, proforma_invoice: str) -> str:
        """Generate unique cycle ID based on proforma invoice."""
        return f"BC-{proforma_invoice}"
    
    def _find_parent_cycle_for_tax_invoice(self, tax_invoice_name: str, 
                                         payment_certificates: List[Dict]) -> Optional[str]:
        """Find parent billing cycle for a tax invoice through payment certificate."""
        for pc in payment_certificates:
            if pc.tax_invoice == tax_invoice_name and pc.proforma_invoice:
                return self._generate_cycle_id(pc.proforma_invoice)
        return None
    
    def _find_parent_cycle_for_adjustment(self, adjustment_entry: Dict, 
                                        billing_cycles: Dict[str, Dict]) -> Optional[str]:
        """Find parent billing cycle for an adjustment entry."""
        # Try to match by reference document
        if adjustment_entry.reference_name:
            for cycle_id, cycle in billing_cycles.items():
                if (cycle['proforma_invoice'] and 
                    cycle['proforma_invoice']['name'] == adjustment_entry.reference_name):
                    return cycle_id
                if (cycle['tax_invoice'] and 
                    cycle['tax_invoice']['name'] == adjustment_entry.reference_name):
                    return cycle_id
        
        # Try to match by date proximity (within 30 days)
        adjustment_date = getdate(adjustment_entry.posting_date)
        for cycle_id, cycle in billing_cycles.items():
            if cycle['proforma_invoice']:
                proforma_date = getdate(cycle['proforma_invoice']['date'])
                if abs((adjustment_date - proforma_date).days) <= 30:
                    return cycle_id
        
        return None
    
    def _is_tax_invoice_in_cycles(self, tax_invoice_name: str, 
                                 billing_cycles: Dict[str, Dict]) -> bool:
        """Check if tax invoice is already included in billing cycles."""
        for cycle in billing_cycles.values():
            if cycle['tax_invoice'] and cycle['tax_invoice']['name'] == tax_invoice_name:
                return True
        return False


def group_transactions_by_billing_cycle(ledger_entries: List[Dict], 
                                       payment_certificates: List[Dict]) -> List[Dict]:
    """
    Main function to group transactions by billing cycle.
    
    This is the primary interface for the transaction grouping functionality.
    
    Args:
        ledger_entries: List of BOQ Progress Ledger entries
        payment_certificates: List of Payment Certificate records
        
    Returns:
        List of grouped billing cycle records
    """
    grouper = TransactionGrouper()
    return grouper.group_transactions_by_billing_cycle(ledger_entries, payment_certificates)


def get_grouped_transaction_summary(grouped_cycles: List[Dict]) -> Dict[str, Any]:
    """
    Generate summary statistics for grouped transactions.
    
    Args:
        grouped_cycles: List of grouped billing cycles
        
    Returns:
        Dict containing summary statistics
    """
    total_cycles = len(grouped_cycles)
    complete_cycles = len([c for c in grouped_cycles if c['tax_invoice']])
    pending_cycles = total_cycles - complete_cycles
    
    total_proforma_amount = sum(
        flt(c['proforma_invoice']['amount']) for c in grouped_cycles 
        if c['proforma_invoice']
    )
    
    total_accepted_amount = sum(
        flt(c['payment_certificate']['accepted_amount']) for c in grouped_cycles 
        if c['payment_certificate']
    )
    
    total_variance = sum(
        flt(c['variance']['amount']) for c in grouped_cycles
    )
    
    return {
        'total_billing_cycles': total_cycles,
        'complete_cycles': complete_cycles,
        'pending_cycles': pending_cycles,
        'total_proforma_amount': total_proforma_amount,
        'total_accepted_amount': total_accepted_amount,
        'total_variance': total_variance,
        'average_variance_percent': (total_variance / total_proforma_amount * 100) if total_proforma_amount else 0
    }

# Global grouper instance for caching
_global_grouper = None

def get_grouper_instance() -> TransactionGrouper:
    """Get or create global grouper instance for caching."""
    global _global_grouper
    if _global_grouper is None:
        _global_grouper = TransactionGrouper()
    return _global_grouper


@frappe.whitelist()
def invalidate_grouping_cache(boq_item: str = None):
    """
    API endpoint to invalidate transaction grouping cache.
    
    Args:
        boq_item: Specific BOQ Item to invalidate cache for, or None for all
    """
    try:
        grouper = get_grouper_instance()
        grouper.invalidate_cache(boq_item)
        
        return {
            'status': 'success',
            'message': f'Cache invalidated for {"all items" if not boq_item else boq_item}'
        }
    except Exception as e:
        return {
            'status': 'error',
            'error_message': str(e)
        }


def setup_cache_invalidation_hooks():
    """
    Set up hooks to invalidate cache when relevant data changes.
    This should be called during app initialization.
    """
    # Hook into BOQ Progress Ledger changes
    def invalidate_on_ledger_change(doc, method):
        if hasattr(doc, 'boq_item') and doc.boq_item:
            grouper = get_grouper_instance()
            grouper.invalidate_cache(doc.boq_item)
    
    # Hook into Payment Certificate changes
    def invalidate_on_pc_change(doc, method):
        if hasattr(doc, 'boq_item') and doc.boq_item:
            grouper = get_grouper_instance()
            grouper.invalidate_cache(doc.boq_item)
    
    # Hook into Sales Invoice changes (for proforma and tax invoices)
    def invalidate_on_invoice_change(doc, method):
        # Find related BOQ items through invoice items
        if hasattr(doc, 'items'):
            for item in doc.items:
                if hasattr(item, 'boq_item') and item.boq_item:
                    grouper = get_grouper_instance()
                    grouper.invalidate_cache(item.boq_item)
    
    # Register hooks (this would typically be done in hooks.py)
    return {
        'BOQ Progress Ledger': {
            'on_update': invalidate_on_ledger_change,
            'on_submit': invalidate_on_ledger_change,
            'on_cancel': invalidate_on_ledger_change
        },
        'Payment Certificate': {
            'on_update': invalidate_on_pc_change,
            'on_submit': invalidate_on_pc_change,
            'on_cancel': invalidate_on_pc_change
        },
        'Sales Invoice': {
            'on_update': invalidate_on_invoice_change,
            'on_submit': invalidate_on_invoice_change,
            'on_cancel': invalidate_on_invoice_change
        }
    }


class PerformanceMonitor:
    """Monitor performance of transaction grouping operations."""
    
    @staticmethod
    def time_operation(operation_name: str):
        """Decorator to time operations."""
        def decorator(func):
            def wrapper(*args, **kwargs):
                import time
                start_time = time.time()
                
                try:
                    result = func(*args, **kwargs)
                    end_time = time.time()
                    duration = end_time - start_time
                    
                    # Log performance metrics
                    frappe.logger().info(f"Transaction Grouping - {operation_name}: {duration:.3f}s")
                    
                    # Store metrics for analysis
                    PerformanceMonitor.store_metric(operation_name, duration, 'success')
                    
                    return result
                    
                except Exception as e:
                    end_time = time.time()
                    duration = end_time - start_time
                    
                    # Log error with timing
                    frappe.logger().error(f"Transaction Grouping - {operation_name} failed after {duration:.3f}s: {str(e)}")
                    
                    # Store error metrics
                    PerformanceMonitor.store_metric(operation_name, duration, 'error')
                    
                    raise
            
            return wrapper
        return decorator
    
    @staticmethod
    def store_metric(operation: str, duration: float, status: str):
        """Store performance metric for analysis."""
        try:
            # Store in a simple cache for now - in production, you might use a proper metrics system
            if not hasattr(frappe.local, 'grouping_metrics'):
                frappe.local.grouping_metrics = []
            
            frappe.local.grouping_metrics.append({
                'operation': operation,
                'duration': duration,
                'status': status,
                'timestamp': frappe.utils.now()
            })
            
            # Keep only last 100 metrics to prevent memory issues
            if len(frappe.local.grouping_metrics) > 100:
                frappe.local.grouping_metrics = frappe.local.grouping_metrics[-100:]
                
        except Exception:
            # Don't let metrics storage break the main functionality
            pass
    
    @staticmethod
    def get_performance_stats() -> Dict[str, Any]:
        """Get performance statistics."""
        try:
            metrics = getattr(frappe.local, 'grouping_metrics', [])
            
            if not metrics:
                return {'message': 'No performance data available'}
            
            # Calculate statistics
            operations = {}
            for metric in metrics:
                op = metric['operation']
                if op not in operations:
                    operations[op] = {'durations': [], 'success_count': 0, 'error_count': 0}
                
                operations[op]['durations'].append(metric['duration'])
                if metric['status'] == 'success':
                    operations[op]['success_count'] += 1
                else:
                    operations[op]['error_count'] += 1
            
            # Calculate averages and statistics
            stats = {}
            for op, data in operations.items():
                durations = data['durations']
                stats[op] = {
                    'avg_duration': sum(durations) / len(durations),
                    'min_duration': min(durations),
                    'max_duration': max(durations),
                    'total_calls': len(durations),
                    'success_rate': data['success_count'] / len(durations) * 100,
                    'error_count': data['error_count']
                }
            
            return {
                'total_metrics': len(metrics),
                'operations': stats
            }
            
        except Exception as e:
            return {'error': str(e)}


# Apply performance monitoring to key functions
@PerformanceMonitor.time_operation("group_transactions_by_billing_cycle")
def group_transactions_by_billing_cycle_monitored(ledger_entries: List[Dict], 
                                                 payment_certificates: List[Dict]) -> List[Dict]:
    """Monitored version of the main grouping function."""
    grouper = get_grouper_instance()
    return grouper.group_transactions_by_billing_cycle(ledger_entries, payment_certificates)


@frappe.whitelist()
def get_grouping_performance_stats():
    """API endpoint to get performance statistics."""
    try:
        return {
            'status': 'success',
            'stats': PerformanceMonitor.get_performance_stats()
        }
    except Exception as e:
        return {
            'status': 'error',
            'error_message': str(e)
        }


# Database query optimization helpers
def optimize_ledger_query(boq_item: str) -> str:
    """
    Generate optimized query for BOQ Progress Ledger entries.
    
    Returns:
        Optimized SQL query string
    """
    return """
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
            CASE 
                WHEN pl.reference_doctype = 'Sales Invoice' THEN si.status
                WHEN pl.reference_doctype = 'Proforma Invoice' THEN pi.status
                ELSE NULL
            END as invoice_status,
            CASE 
                WHEN pl.reference_doctype = 'Sales Invoice' THEN si.docstatus
                WHEN pl.reference_doctype = 'Proforma Invoice' THEN pi.docstatus
                ELSE NULL
            END as invoice_docstatus,
            si.outstanding_amount,
            0 as is_proforma
        FROM `tabBOQ Progress Ledger` pl
        LEFT JOIN `tabSales Invoice` si 
            ON pl.reference_name = si.name 
            AND pl.reference_doctype = 'Sales Invoice'
            AND si.docstatus != 2
        LEFT JOIN `tabProforma Invoice` pi
            ON pl.reference_name = pi.name
            AND pl.reference_doctype = 'Proforma Invoice'
            AND pi.docstatus != 2
        WHERE pl.boq_item = %s
        ORDER BY pl.posting_date ASC, pl.creation ASC
    """


def optimize_payment_certificate_query(boq_item: str) -> str:
    """
    Generate optimized query for Payment Certificate entries.
    
    Returns:
        Optimized SQL query string
    """
    return """
        SELECT 
            pc.name,
            pc.posting_date,
            pc.proforma_invoice,
            pc.proforma_amount,
            pc.accepted_amount,
            (pc.proforma_amount - pc.accepted_amount) as variance,
            pc.tax_invoice,
            pc.status,
            pc.payment_received,
            pc.invoice_status
        FROM `tabPayment Certificate` pc
        WHERE pc.boq_item = %s
        AND pc.docstatus != 2
        ORDER BY pc.posting_date ASC
    """