# Copyright (c) 2024, Construction Management
# License: MIT

"""
Test utility for transaction grouping functionality.
This module provides test functions to validate the transaction grouping implementation.
"""

import frappe
from frappe.utils import flt
from typing import Dict, List, Any


@frappe.whitelist()
def test_transaction_grouping(boq_item: str) -> Dict[str, Any]:
    """
    Test the transaction grouping functionality for a specific BOQ Item.
    
    Args:
        boq_item: BOQ Item name to test
        
    Returns:
        Dict containing test results and validation data
    """
    try:
        # Get both raw and grouped data
        from construction_management.api.boq_invoice import get_boq_invoice_history
        
        raw_data = get_boq_invoice_history(boq_item, grouped_view=0)
        grouped_data = get_boq_invoice_history(boq_item, grouped_view=1)
        
        # Validate data integrity
        validation_results = validate_grouping_integrity(raw_data, grouped_data)
        
        return {
            "status": "success",
            "boq_item": boq_item,
            "raw_data_summary": {
                "ledger_entries": len(raw_data.get("ledger_entries", [])),
                "payment_certificates": len(raw_data.get("payment_certificates", [])),
                "total_amount": sum(flt(entry.get("current_amount", 0)) for entry in raw_data.get("ledger_entries", []))
            },
            "grouped_data_summary": {
                "billing_cycles": len(grouped_data.get("grouped_transactions", [])),
                "grouping_summary": grouped_data.get("grouping_summary", {}),
                "total_amount": sum(
                    flt(cycle.get("consolidated_values", {}).get("current_amount", 0)) 
                    for cycle in grouped_data.get("grouped_transactions", [])
                )
            },
            "validation_results": validation_results,
            "view_mode": grouped_data.get("view_mode", "unknown")
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
            "boq_item": boq_item
        }


def validate_grouping_integrity(raw_data: Dict, grouped_data: Dict) -> Dict[str, Any]:
    """
    Validate that grouped data maintains integrity with raw data.
    
    Returns:
        Dict containing validation results
    """
    validation = {
        "total_amount_match": False,
        "total_qty_match": False,
        "amount_difference": 0,
        "qty_difference": 0,
        "issues": []
    }
    
    try:
        # Calculate totals from raw data
        raw_total_amount = sum(flt(entry.get("current_amount", 0)) for entry in raw_data.get("ledger_entries", []))
        raw_total_qty = sum(flt(entry.get("current_qty", 0)) for entry in raw_data.get("ledger_entries", []))
        
        # Calculate totals from grouped data
        grouped_total_amount = sum(
            flt(cycle.get("consolidated_values", {}).get("current_amount", 0)) 
            for cycle in grouped_data.get("grouped_transactions", [])
        )
        grouped_total_qty = sum(
            flt(cycle.get("consolidated_values", {}).get("current_qty", 0)) 
            for cycle in grouped_data.get("grouped_transactions", [])
        )
        
        # Check differences
        amount_diff = abs(raw_total_amount - grouped_total_amount)
        qty_diff = abs(raw_total_qty - grouped_total_qty)
        
        validation["amount_difference"] = amount_diff
        validation["qty_difference"] = qty_diff
        validation["total_amount_match"] = amount_diff < 0.01  # Allow for rounding
        validation["total_qty_match"] = qty_diff < 0.01
        
        # Check for issues
        if not validation["total_amount_match"]:
            validation["issues"].append(f"Amount mismatch: Raw={raw_total_amount}, Grouped={grouped_total_amount}")
        
        if not validation["total_qty_match"]:
            validation["issues"].append(f"Quantity mismatch: Raw={raw_total_qty}, Grouped={grouped_total_qty}")
        
        # Check for orphaned transactions
        grouped_cycles = grouped_data.get("grouped_transactions", [])
        if len(grouped_cycles) == 0 and len(raw_data.get("ledger_entries", [])) > 0:
            validation["issues"].append("No billing cycles created despite having ledger entries")
        
    except Exception as e:
        validation["issues"].append(f"Validation error: {str(e)}")
    
    return validation


@frappe.whitelist()
def get_sample_boq_items_for_testing() -> List[Dict]:
    """
    Get a list of BOQ Items that have transaction data for testing purposes.
    
    Returns:
        List of BOQ Items with transaction counts
    """
    try:
        items = frappe.db.sql("""
            SELECT 
                bi.name,
                bi.description,
                bi.project,
                COUNT(DISTINCT pl.name) as ledger_entries,
                COUNT(DISTINCT pc.name) as payment_certificates
            FROM `tabBOQ Item` bi
            LEFT JOIN `tabBOQ Progress Ledger` pl ON pl.boq_item = bi.name
            LEFT JOIN `tabPayment Certificate` pc ON pc.boq_item = bi.name AND pc.docstatus != 2
            WHERE bi.docstatus != 2
            GROUP BY bi.name
            HAVING ledger_entries > 0
            ORDER BY ledger_entries DESC, payment_certificates DESC
            LIMIT 20
        """, as_dict=True)
        
        return items
        
    except Exception as e:
        frappe.log_error(f"Error getting sample BOQ items: {str(e)}", "Transaction Grouping Test")
        return []


@frappe.whitelist()
def run_comprehensive_test() -> Dict[str, Any]:
    """
    Run comprehensive tests on multiple BOQ Items to validate grouping functionality.
    
    Returns:
        Dict containing comprehensive test results
    """
    try:
        sample_items = get_sample_boq_items_for_testing()
        test_results = []
        
        for item in sample_items[:5]:  # Test first 5 items
            result = test_transaction_grouping(item["name"])
            test_results.append(result)
        
        # Aggregate results
        total_tests = len(test_results)
        successful_tests = len([r for r in test_results if r.get("status") == "success"])
        failed_tests = total_tests - successful_tests
        
        integrity_passes = len([
            r for r in test_results 
            if r.get("status") == "success" and 
            r.get("validation_results", {}).get("total_amount_match", False) and
            r.get("validation_results", {}).get("total_qty_match", False)
        ])
        
        return {
            "status": "completed",
            "summary": {
                "total_tests": total_tests,
                "successful_tests": successful_tests,
                "failed_tests": failed_tests,
                "integrity_passes": integrity_passes,
                "integrity_failures": successful_tests - integrity_passes
            },
            "detailed_results": test_results,
            "sample_items_tested": [item["name"] for item in sample_items[:5]]
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e)
        }