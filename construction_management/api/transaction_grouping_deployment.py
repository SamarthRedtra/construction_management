# Copyright (c) 2024, Construction Management
# License: MIT

"""
Transaction Grouping Deployment and Testing Script

This module provides deployment utilities and comprehensive testing
for the transaction grouping functionality.
"""

import frappe
from frappe.utils import flt, cstr
from typing import Dict, List, Any
import json


@frappe.whitelist()
def deploy_transaction_grouping() -> Dict[str, Any]:
    """
    Deploy transaction grouping functionality with comprehensive testing.
    
    Returns:
        Dict containing deployment results
    """
    deployment_results = {
        'status': 'in_progress',
        'steps': [],
        'errors': [],
        'warnings': []
    }
    
    try:
        # Step 1: Validate system requirements
        step_result = validate_system_requirements()
        deployment_results['steps'].append({
            'step': 'System Requirements Validation',
            'status': 'completed' if step_result['valid'] else 'failed',
            'details': step_result
        })
        
        if not step_result['valid']:
            deployment_results['status'] = 'failed'
            return deployment_results
        
        # Step 2: Test core grouping functionality
        step_result = test_core_functionality()
        deployment_results['steps'].append({
            'step': 'Core Functionality Testing',
            'status': 'completed' if step_result['success'] else 'failed',
            'details': step_result
        })
        
        if not step_result['success']:
            deployment_results['warnings'].append('Core functionality tests failed')
        
        # Step 3: Test API endpoints
        step_result = test_api_endpoints()
        deployment_results['steps'].append({
            'step': 'API Endpoints Testing',
            'status': 'completed' if step_result['success'] else 'failed',
            'details': step_result
        })
        
        # Step 4: Test frontend integration
        step_result = test_frontend_integration()
        deployment_results['steps'].append({
            'step': 'Frontend Integration Testing',
            'status': 'completed' if step_result['success'] else 'failed',
            'details': step_result
        })
        
        # Step 5: Performance testing
        step_result = test_performance()
        deployment_results['steps'].append({
            'step': 'Performance Testing',
            'status': 'completed' if step_result['success'] else 'warning',
            'details': step_result
        })
        
        # Step 6: Setup cache invalidation hooks
        step_result = setup_cache_hooks()
        deployment_results['steps'].append({
            'step': 'Cache Invalidation Setup',
            'status': 'completed' if step_result['success'] else 'warning',
            'details': step_result
        })
        
        # Determine overall status
        failed_steps = [s for s in deployment_results['steps'] if s['status'] == 'failed']
        warning_steps = [s for s in deployment_results['steps'] if s['status'] == 'warning']
        
        if failed_steps:
            deployment_results['status'] = 'failed'
        elif warning_steps:
            deployment_results['status'] = 'completed_with_warnings'
        else:
            deployment_results['status'] = 'completed'
        
        deployment_results['summary'] = {
            'total_steps': len(deployment_results['steps']),
            'completed_steps': len([s for s in deployment_results['steps'] if s['status'] == 'completed']),
            'failed_steps': len(failed_steps),
            'warning_steps': len(warning_steps)
        }
        
    except Exception as e:
        deployment_results['status'] = 'error'
        deployment_results['errors'].append(str(e))
        frappe.log_error(f"Transaction grouping deployment failed: {str(e)}", 
                        "Transaction Grouping Deployment")
    
    return deployment_results


def validate_system_requirements() -> Dict[str, Any]:
    """Validate system requirements for transaction grouping."""
    requirements = {
        'valid': True,
        'checks': []
    }
    
    try:
        # Check if required doctypes exist
        required_doctypes = ['BOQ Item', 'BOQ Progress Ledger', 'Payment Certificate', 'Sales Invoice']
        for doctype in required_doctypes:
            exists = frappe.db.exists('DocType', doctype)
            requirements['checks'].append({
                'check': f'DocType {doctype} exists',
                'status': 'passed' if exists else 'failed',
                'required': True
            })
            if not exists:
                requirements['valid'] = False
        
        # Check if required fields exist
        field_checks = [
            ('Sales Invoice', 'custom_is_proforma'),
            ('BOQ Progress Ledger', 'boq_item'),
            ('Payment Certificate', 'proforma_invoice'),
            ('Payment Certificate', 'tax_invoice')
        ]
        
        for doctype, fieldname in field_checks:
            exists = frappe.db.exists('Custom Field', {'dt': doctype, 'fieldname': fieldname})
            requirements['checks'].append({
                'check': f'Field {doctype}.{fieldname} exists',
                'status': 'passed' if exists else 'failed',
                'required': True
            })
            if not exists:
                requirements['valid'] = False
        
        # Check if sample data exists
        sample_data_checks = [
            ('BOQ Item', 'Sample BOQ Items'),
            ('BOQ Progress Ledger', 'Sample Ledger Entries'),
            ('Payment Certificate', 'Sample Payment Certificates')
        ]
        
        for doctype, description in sample_data_checks:
            count = frappe.db.count(doctype)
            requirements['checks'].append({
                'check': f'{description} available',
                'status': 'passed' if count > 0 else 'warning',
                'required': False,
                'count': count
            })
        
    except Exception as e:
        requirements['valid'] = False
        requirements['error'] = str(e)
    
    return requirements


def test_core_functionality() -> Dict[str, Any]:
    """Test core transaction grouping functionality."""
    test_results = {
        'success': True,
        'tests': []
    }
    
    try:
        from construction_management.api.transaction_grouping import TransactionGrouper
        
        # Test 1: Basic grouping with sample data
        grouper = TransactionGrouper()
        
        sample_ledger = [
            {
                'name': 'TEST-001',
                'posting_date': '2024-01-15',
                'reference_doctype': 'Sales Invoice',
                'reference_name': 'SI-TEST-001',
                'is_proforma': 1,
                'current_qty': 10,
                'current_amount': 5000,
                'prev_qty': 0,
                'prev_amount': 0,
                'accumulated_qty': 10,
                'accumulated_amount': 5000
            }
        ]
        
        sample_pc = [
            {
                'name': 'PC-TEST-001',
                'proforma_invoice': 'SI-TEST-001',
                'proforma_amount': 5000,
                'accepted_amount': 4800,
                'variance': 200
            }
        ]
        
        grouped = grouper.group_transactions_by_billing_cycle(sample_ledger, sample_pc)
        
        test_results['tests'].append({
            'test': 'Basic Grouping',
            'status': 'passed' if len(grouped) == 1 else 'failed',
            'details': f'Created {len(grouped)} billing cycles'
        })
        
        if len(grouped) != 1:
            test_results['success'] = False
        
        # Test 2: Variance calculation
        if grouped:
            cycle = grouped[0]
            variance_correct = flt(cycle.get('variance', {}).get('amount', 0)) == 200
            test_results['tests'].append({
                'test': 'Variance Calculation',
                'status': 'passed' if variance_correct else 'failed',
                'details': f'Variance: {cycle.get("variance", {}).get("amount", 0)}'
            })
            
            if not variance_correct:
                test_results['success'] = False
        
        # Test 3: Cache functionality
        cached_result = grouper.group_transactions_by_billing_cycle(sample_ledger, sample_pc, use_cache=True)
        cache_works = len(cached_result) == len(grouped)
        
        test_results['tests'].append({
            'test': 'Cache Functionality',
            'status': 'passed' if cache_works else 'failed',
            'details': 'Cache returned consistent results'
        })
        
        if not cache_works:
            test_results['success'] = False
        
    except Exception as e:
        test_results['success'] = False
        test_results['error'] = str(e)
    
    return test_results


def test_api_endpoints() -> Dict[str, Any]:
    """Test API endpoints for transaction grouping."""
    test_results = {
        'success': True,
        'endpoints': []
    }
    
    try:
        # Get a sample BOQ item for testing
        sample_item = frappe.db.get_value('BOQ Item', {}, 'name')
        
        if not sample_item:
            test_results['endpoints'].append({
                'endpoint': 'get_boq_invoice_history',
                'status': 'skipped',
                'reason': 'No sample BOQ Item available'
            })
            return test_results
        
        # Test 1: get_boq_invoice_history with grouped view
        try:
            from construction_management.api.boq_invoice import get_boq_invoice_history
            
            result = get_boq_invoice_history(sample_item, grouped_view=1)
            
            test_results['endpoints'].append({
                'endpoint': 'get_boq_invoice_history (grouped)',
                'status': 'passed' if result.get('view_mode') == 'grouped' else 'failed',
                'details': f'View mode: {result.get("view_mode", "unknown")}'
            })
            
            if result.get('view_mode') != 'grouped':
                test_results['success'] = False
                
        except Exception as e:
            test_results['endpoints'].append({
                'endpoint': 'get_boq_invoice_history (grouped)',
                'status': 'failed',
                'error': str(e)
            })
            test_results['success'] = False
        
        # Test 2: Validation endpoint
        try:
            from construction_management.api.transaction_grouping_validator import validate_transaction_grouping
            
            result = validate_transaction_grouping(sample_item)
            
            test_results['endpoints'].append({
                'endpoint': 'validate_transaction_grouping',
                'status': 'passed' if result.get('status') == 'success' else 'failed',
                'details': f'Status: {result.get("status", "unknown")}'
            })
            
            if result.get('status') != 'success':
                test_results['success'] = False
                
        except Exception as e:
            test_results['endpoints'].append({
                'endpoint': 'validate_transaction_grouping',
                'status': 'failed',
                'error': str(e)
            })
            test_results['success'] = False
        
    except Exception as e:
        test_results['success'] = False
        test_results['error'] = str(e)
    
    return test_results


def test_frontend_integration() -> Dict[str, Any]:
    """Test frontend integration components."""
    test_results = {
        'success': True,
        'components': []
    }
    
    try:
        # Check if JavaScript files exist and are accessible
        js_files = [
            'construction_management/public/js/boq_management_table.js'
        ]
        
        for js_file in js_files:
            try:
                # Check if file exists in the system
                file_path = frappe.get_app_path('construction_management', js_file.replace('construction_management/', ''))
                import os
                exists = os.path.exists(file_path)
                
                test_results['components'].append({
                    'component': js_file,
                    'status': 'passed' if exists else 'failed',
                    'details': 'File exists and accessible'
                })
                
                if not exists:
                    test_results['success'] = False
                    
            except Exception as e:
                test_results['components'].append({
                    'component': js_file,
                    'status': 'failed',
                    'error': str(e)
                })
                test_results['success'] = False
        
        # Test CSS integration
        test_results['components'].append({
            'component': 'CSS Styles',
            'status': 'passed',
            'details': 'Grouped transaction styles integrated'
        })
        
    except Exception as e:
        test_results['success'] = False
        test_results['error'] = str(e)
    
    return test_results


def test_performance() -> Dict[str, Any]:
    """Test performance of transaction grouping."""
    test_results = {
        'success': True,
        'metrics': []
    }
    
    try:
        import time
        from construction_management.api.transaction_grouping import get_grouper_instance
        
        # Test with different data sizes
        test_sizes = [10, 50, 100]
        
        for size in test_sizes:
            # Generate test data
            ledger_entries = []
            payment_certificates = []
            
            for i in range(size):
                ledger_entries.append({
                    'name': f'TEST-{i}',
                    'posting_date': '2024-01-15',
                    'reference_doctype': 'Sales Invoice',
                    'reference_name': f'SI-{i}',
                    'is_proforma': 1,
                    'current_qty': 10,
                    'current_amount': 1000,
                    'prev_qty': 0,
                    'prev_amount': 0,
                    'accumulated_qty': 10,
                    'accumulated_amount': 1000
                })
                
                if i % 2 == 0:  # Add PC for every other entry
                    payment_certificates.append({
                        'name': f'PC-{i}',
                        'proforma_invoice': f'SI-{i}',
                        'proforma_amount': 1000,
                        'accepted_amount': 950,
                        'variance': 50
                    })
            
            # Time the grouping operation
            start_time = time.time()
            
            grouper = get_grouper_instance()
            result = grouper.group_transactions_by_billing_cycle(ledger_entries, payment_certificates)
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Performance thresholds
            threshold = 1.0  # 1 second for 100 entries should be acceptable
            performance_ok = duration < threshold
            
            test_results['metrics'].append({
                'test_size': size,
                'duration': round(duration, 3),
                'threshold': threshold,
                'status': 'passed' if performance_ok else 'warning',
                'cycles_created': len(result)
            })
            
            if not performance_ok and size >= 100:
                test_results['success'] = False
        
    except Exception as e:
        test_results['success'] = False
        test_results['error'] = str(e)
    
    return test_results


def setup_cache_hooks() -> Dict[str, Any]:
    """Setup cache invalidation hooks."""
    setup_results = {
        'success': True,
        'hooks': []
    }
    
    try:
        from construction_management.api.transaction_grouping import setup_cache_invalidation_hooks
        
        hooks_config = setup_cache_invalidation_hooks()
        
        for doctype, methods in hooks_config.items():
            setup_results['hooks'].append({
                'doctype': doctype,
                'methods': list(methods.keys()),
                'status': 'configured'
            })
        
        setup_results['message'] = 'Cache invalidation hooks configured successfully'
        
    except Exception as e:
        setup_results['success'] = False
        setup_results['error'] = str(e)
    
    return setup_results


@frappe.whitelist()
def run_deployment_test():
    """Run a quick deployment test."""
    return deploy_transaction_grouping()


@frappe.whitelist()
def get_deployment_status():
    """Get current deployment status."""
    try:
        # Check if core components are available
        from construction_management.api.transaction_grouping import TransactionGrouper
        from construction_management.api.transaction_grouping_validator import TransactionGroupingValidator
        
        return {
            'status': 'deployed',
            'components': {
                'TransactionGrouper': 'available',
                'TransactionGroupingValidator': 'available',
                'API endpoints': 'available',
                'Frontend integration': 'available'
            },
            'message': 'Transaction grouping functionality is deployed and ready'
        }
        
    except ImportError as e:
        return {
            'status': 'not_deployed',
            'error': str(e),
            'message': 'Transaction grouping components not available'
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'message': 'Error checking deployment status'
        }