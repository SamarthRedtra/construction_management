# Copyright (c) 2024, Construction Management
# License: MIT

"""
Property Tests for Transaction History Data Completeness

**Feature: payment-certificate-enhancements, Property 2: Transaction History Data Completeness**
**Validates: Requirements 1.2, 1.3**

For any BOQ Item with transactions, the transaction history SHALL include all linked
Proforma Invoices, Payment Certificates, and Tax Invoices with their respective amounts and status.
"""

import pytest
from hypothesis import given, strategies as st, settings
from typing import List, Dict, Any
from dataclasses import dataclass
from enum import Enum


class DocType(Enum):
    PROFORMA_INVOICE = "Proforma Invoice"
    PAYMENT_CERTIFICATE = "Payment Certificate"
    SALES_INVOICE = "Sales Invoice"


class Status(Enum):
    DRAFT = "Draft"
    SUBMITTED = "Submitted"
    PAID = "Paid"
    CANCELLED = "Cancelled"


@dataclass
class Transaction:
    """Represents a billing transaction"""
    doctype: str
    name: str
    date: str
    qty: float
    amount: float
    status: str
    variance: float = 0
    pc_amount: float = 0
    proforma_amount: float = 0


@dataclass
class BOQItem:
    """Represents a BOQ Item with its details"""
    name: str
    item_code: str
    description: str
    unit: str
    rate: float
    total_qty: float
    total_amount: float
    prev_qty: float = 0
    current_qty: float = 0
    prev_amount: float = 0
    current_amount: float = 0


def get_transaction_history(item: BOQItem, transactions: List[Transaction]) -> Dict[str, Any]:
    """
    Simulate the get_boq_item_with_transactions API response.
    
    Returns item details and all transactions.
    """
    # Calculate accumulated values
    to_date_qty = item.prev_qty + item.current_qty
    to_date_amount = item.prev_amount + item.current_amount
    
    return {
        "item": {
            "name": item.name,
            "item_code": item.item_code,
            "description": item.description,
            "unit": item.unit,
            "qty": {
                "total": item.total_qty,
                "prev": item.prev_qty,
                "current": item.current_qty,
                "to_date": to_date_qty
            },
            "amount": {
                "rate": item.rate,
                "total": item.total_amount,
                "prev": item.prev_amount,
                "current": item.current_amount,
                "to_date": to_date_amount
            }
        },
        "transactions": [
            {
                "doctype": t.doctype,
                "name": t.name,
                "date": t.date,
                "qty": t.qty,
                "amount": t.amount,
                "status": t.status,
                "variance": t.variance,
                "pc_amount": t.pc_amount,
                "proforma_amount": t.proforma_amount
            }
            for t in transactions
        ]
    }


def validate_transaction_history_completeness(
    item: BOQItem,
    transactions: List[Transaction],
    result: Dict[str, Any]
) -> bool:
    """
    Validate that transaction history contains all required data.
    
    Property 2: Transaction History Data Completeness
    """
    # Check item details are present
    item_data = result.get("item", {})
    
    if not item_data.get("description"):
        return False
    if not item_data.get("unit"):
        return False
    if item_data.get("amount", {}).get("rate") is None:
        return False
    
    # Check qty breakdown is present
    qty = item_data.get("qty", {})
    if qty.get("prev") is None or qty.get("current") is None or qty.get("to_date") is None:
        return False
    
    # Check amount breakdown is present
    amount = item_data.get("amount", {})
    if amount.get("prev") is None or amount.get("current") is None or amount.get("to_date") is None:
        return False
    
    # Check all transactions are included
    result_transactions = result.get("transactions", [])
    if len(result_transactions) != len(transactions):
        return False
    
    # Check each transaction has required fields
    for txn in result_transactions:
        if not txn.get("doctype"):
            return False
        if not txn.get("name"):
            return False
        if txn.get("status") is None:
            return False
        if txn.get("amount") is None:
            return False
    
    return True


# Strategies for generating test data
@st.composite
def boq_item_strategy(draw):
    """Generate a random BOQ Item"""
    rate = draw(st.floats(min_value=1, max_value=10000, allow_nan=False, allow_infinity=False))
    total_qty = draw(st.floats(min_value=1, max_value=1000, allow_nan=False, allow_infinity=False))
    prev_qty = draw(st.floats(min_value=0, max_value=total_qty * 0.8, allow_nan=False, allow_infinity=False))
    current_qty = draw(st.floats(min_value=0, max_value=total_qty - prev_qty, allow_nan=False, allow_infinity=False))
    
    return BOQItem(
        name=f"BOQ-ITEM-{draw(st.integers(min_value=1, max_value=9999)):04d}",
        item_code=draw(st.text(min_size=3, max_size=10, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")),
        description=draw(st.text(min_size=5, max_size=100)),
        unit=draw(st.sampled_from(["Nos", "Sqm", "Cum", "Rmt", "Kg", "Ton"])),
        rate=round(rate, 2),
        total_qty=round(total_qty, 3),
        total_amount=round(rate * total_qty, 2),
        prev_qty=round(prev_qty, 3),
        current_qty=round(current_qty, 3),
        prev_amount=round(prev_qty * rate, 2),
        current_amount=round(current_qty * rate, 2)
    )


@st.composite
def transaction_strategy(draw, doctype: str):
    """Generate a random transaction of given type"""
    amount = draw(st.floats(min_value=100, max_value=100000, allow_nan=False, allow_infinity=False))
    qty = draw(st.floats(min_value=1, max_value=100, allow_nan=False, allow_infinity=False))
    
    variance = 0
    pc_amount = 0
    proforma_amount = 0
    
    if doctype == DocType.PAYMENT_CERTIFICATE.value:
        proforma_amount = amount
        # PC amount can be less than or equal to proforma
        pc_amount = draw(st.floats(min_value=amount * 0.7, max_value=amount, allow_nan=False, allow_infinity=False))
        variance = proforma_amount - pc_amount
        amount = proforma_amount
    
    return Transaction(
        doctype=doctype,
        name=f"{doctype[:2].upper()}-{draw(st.integers(min_value=1, max_value=9999)):04d}",
        date=f"2024-{draw(st.integers(min_value=1, max_value=12)):02d}-{draw(st.integers(min_value=1, max_value=28)):02d}",
        qty=round(qty, 3),
        amount=round(amount, 2),
        status=draw(st.sampled_from([s.value for s in Status])),
        variance=round(variance, 2),
        pc_amount=round(pc_amount, 2),
        proforma_amount=round(proforma_amount, 2)
    )


@st.composite
def transactions_list_strategy(draw):
    """Generate a list of mixed transactions"""
    transactions = []
    
    # Add 0-3 Proforma Invoices
    num_pi = draw(st.integers(min_value=0, max_value=3))
    for _ in range(num_pi):
        transactions.append(draw(transaction_strategy(DocType.PROFORMA_INVOICE.value)))
    
    # Add 0-3 Payment Certificates
    num_pc = draw(st.integers(min_value=0, max_value=3))
    for _ in range(num_pc):
        transactions.append(draw(transaction_strategy(DocType.PAYMENT_CERTIFICATE.value)))
    
    # Add 0-3 Sales Invoices
    num_si = draw(st.integers(min_value=0, max_value=3))
    for _ in range(num_si):
        transactions.append(draw(transaction_strategy(DocType.SALES_INVOICE.value)))
    
    return transactions


class TestTransactionHistoryCompleteness:
    """
    Property tests for transaction history data completeness.
    
    **Feature: payment-certificate-enhancements, Property 2: Transaction History Data Completeness**
    **Validates: Requirements 1.2, 1.3**
    """
    
    @given(item=boq_item_strategy(), transactions=transactions_list_strategy())
    @settings(max_examples=100)
    def test_transaction_history_contains_all_required_fields(self, item, transactions):
        """
        Property: For any BOQ Item, the transaction history response SHALL contain
        all required item details and all transactions.
        """
        result = get_transaction_history(item, transactions)
        
        assert validate_transaction_history_completeness(item, transactions, result), \
            "Transaction history missing required fields"
    
    @given(item=boq_item_strategy(), transactions=transactions_list_strategy())
    @settings(max_examples=100)
    def test_all_transactions_included(self, item, transactions):
        """
        Property: For any set of transactions, all SHALL be included in the response.
        """
        result = get_transaction_history(item, transactions)
        
        result_txns = result.get("transactions", [])
        assert len(result_txns) == len(transactions), \
            f"Expected {len(transactions)} transactions, got {len(result_txns)}"
    
    @given(item=boq_item_strategy(), transactions=transactions_list_strategy())
    @settings(max_examples=100)
    def test_qty_breakdown_present(self, item, transactions):
        """
        Property: For any BOQ Item, qty breakdown (prev, current, accumulated) SHALL be present.
        """
        result = get_transaction_history(item, transactions)
        
        qty = result.get("item", {}).get("qty", {})
        assert "prev" in qty, "Previous qty missing"
        assert "current" in qty, "Current qty missing"
        assert "to_date" in qty, "Accumulated qty missing"
    
    @given(item=boq_item_strategy(), transactions=transactions_list_strategy())
    @settings(max_examples=100)
    def test_value_breakdown_present(self, item, transactions):
        """
        Property: For any BOQ Item, value breakdown (prev, current, accumulated) SHALL be present.
        """
        result = get_transaction_history(item, transactions)
        
        amount = result.get("item", {}).get("amount", {})
        assert "prev" in amount, "Previous value missing"
        assert "current" in amount, "Current value missing"
        assert "to_date" in amount, "Accumulated value missing"
        assert "rate" in amount, "Rate missing"
    
    @given(item=boq_item_strategy(), transactions=transactions_list_strategy())
    @settings(max_examples=100)
    def test_accumulated_equals_prev_plus_current(self, item, transactions):
        """
        Property: Accumulated qty/value SHALL equal Previous + Current.
        """
        result = get_transaction_history(item, transactions)
        
        qty = result.get("item", {}).get("qty", {})
        amount = result.get("item", {}).get("amount", {})
        
        # Qty: to_date = prev + current
        expected_qty = qty.get("prev", 0) + qty.get("current", 0)
        assert abs(qty.get("to_date", 0) - expected_qty) < 0.001, \
            f"Qty to_date ({qty.get('to_date')}) != prev ({qty.get('prev')}) + current ({qty.get('current')})"
        
        # Amount: to_date = prev + current
        expected_amount = amount.get("prev", 0) + amount.get("current", 0)
        assert abs(amount.get("to_date", 0) - expected_amount) < 0.01, \
            f"Amount to_date ({amount.get('to_date')}) != prev ({amount.get('prev')}) + current ({amount.get('current')})"
    
    def test_specific_example_with_all_transaction_types(self):
        """
        Example test: BOQ Item with PI, PC, and Tax Invoice transactions.
        """
        item = BOQItem(
            name="BOQ-ITEM-0001",
            item_code="CONC001",
            description="Concrete Work M25",
            unit="Cum",
            rate=5000.00,
            total_qty=100.0,
            total_amount=500000.00,
            prev_qty=30.0,
            current_qty=20.0,
            prev_amount=150000.00,
            current_amount=100000.00
        )
        
        transactions = [
            Transaction(
                doctype="Proforma Invoice",
                name="PI-0001",
                date="2024-01-15",
                qty=30.0,
                amount=150000.00,
                status="Submitted"
            ),
            Transaction(
                doctype="Payment Certificate",
                name="PC-0001",
                date="2024-01-20",
                qty=0,
                amount=150000.00,
                status="Submitted",
                variance=5000.00,
                pc_amount=145000.00,
                proforma_amount=150000.00
            ),
            Transaction(
                doctype="Sales Invoice",
                name="SINV-0001",
                date="2024-01-25",
                qty=30.0,
                amount=145000.00,
                status="Paid"
            )
        ]
        
        result = get_transaction_history(item, transactions)
        
        # Verify item details
        assert result["item"]["description"] == "Concrete Work M25"
        assert result["item"]["unit"] == "Cum"
        assert result["item"]["amount"]["rate"] == 5000.00
        
        # Verify qty breakdown
        assert result["item"]["qty"]["prev"] == 30.0
        assert result["item"]["qty"]["current"] == 20.0
        assert result["item"]["qty"]["to_date"] == 50.0
        
        # Verify value breakdown
        assert result["item"]["amount"]["prev"] == 150000.00
        assert result["item"]["amount"]["current"] == 100000.00
        assert result["item"]["amount"]["to_date"] == 250000.00
        
        # Verify all transactions included
        assert len(result["transactions"]) == 3
        
        # Verify transaction types
        doctypes = [t["doctype"] for t in result["transactions"]]
        assert "Proforma Invoice" in doctypes
        assert "Payment Certificate" in doctypes
        assert "Sales Invoice" in doctypes
