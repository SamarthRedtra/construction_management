# Copyright (c) 2024, Construction Management
# License: MIT

"""
Property Tests for Bill Financial Summary Consistency
Property 5: Bill Financial Summary Consistency
Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5
"""

import frappe
import unittest
from frappe.utils import flt
from hypothesis import given, strategies as st, settings, assume
from construction_management.api.bill_financial_aggregator import BillFinancialAggregator


class TestPropertyBillFinancialSummary(unittest.TestCase):
	"""
	Property-based tests for bill financial summary calculations.
	Ensures financial summaries accurately reflect retention, advances, and balances.
	"""
	
	def setUp(self):
		"""Set up test environment"""
		frappe.set_user("Administrator")
		self.test_project = self._create_test_project()
		self.test_bill = self._create_test_bill(self.test_project)
	
	def tearDown(self):
		"""Clean up test data"""
		frappe.db.rollback()
	
	def _create_test_project(self):
		"""Create a test project"""
		project = frappe.get_doc({
			"doctype": "Project",
			"project_name": "Test Financial Project",
			"status": "Open"
		})
		project.insert(ignore_permissions=True)
		return project.name
	
	def _create_test_bill(self, project):
		"""Create a test BOQ bill"""
		# Get or create Project BOQ
		boq_name = frappe.db.get_value("Project BOQ", {"project": project})
		if not boq_name:
			boq = frappe.get_doc({
				"doctype": "Project BOQ",
				"project": project,
				"boq_date": frappe.utils.today()
			})
			boq.insert(ignore_permissions=True)
			boq_name = boq.name
		
		bill = frappe.get_doc({
			"doctype": "BOQ Bill",
			"project_boq": boq_name,
			"project": project,
			"bill_no": "TEST-001",
			"description": "Test Bill",
			"total_amount": 0
		})
		bill.insert(ignore_permissions=True)
		return bill.name
	
	@given(
		total_amount=st.floats(min_value=1000, max_value=100000, allow_nan=False, allow_infinity=False),
		billed_ratio=st.floats(min_value=0.1, max_value=1.0, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=30, deadline=None)
	def test_property_balance_equals_total_minus_billed(self, total_amount, billed_ratio):
		"""
		Property: Balance to bill = Total BOQ value - Total billed to date.
		For any total T and billed amount B where B <= T:
		- Balance = T - B
		"""
		total_amount = flt(total_amount, 2)
		billed_amount = flt(total_amount * billed_ratio, 2)
		
		# Update bill totals
		frappe.db.set_value("BOQ Bill", self.test_bill, {
			"total_amount": total_amount,
			"to_date_amount": billed_amount,
			"balance_amount": total_amount - billed_amount
		})
		
		# Get financial summary
		aggregator = BillFinancialAggregator(self.test_bill)
		summary = aggregator.calculate_bill_summary()
		
		# Verify balance calculation
		expected_balance = total_amount - billed_amount
		self.assertAlmostEqual(
			flt(summary["balance_to_bill"]),
			expected_balance,
			places=2,
			msg=f"Balance should be {expected_balance} (Total: {total_amount}, Billed: {billed_amount})"
		)
	
	@given(
		billed=st.floats(min_value=1000, max_value=50000, allow_nan=False, allow_infinity=False),
		retention_percent=st.floats(min_value=0, max_value=20, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=30, deadline=None)
	def test_property_retention_calculated_from_billed_amount(self, billed, retention_percent):
		"""
		Property: Retention amount = Billed amount × Retention percentage.
		For any billed amount B and retention % R:
		- Retention = B × (R / 100)
		"""
		billed = flt(billed, 2)
		retention_percent = flt(retention_percent, 2)
		expected_retention = flt(billed * retention_percent / 100, 2)
		
		# Update bill
		frappe.db.set_value("BOQ Bill", self.test_bill, {
			"total_amount": billed * 2,  # Make total larger than billed
			"to_date_amount": billed
		})
		
		# Create retention deduction in invoice
		if expected_retention > 0:
			self._create_retention_deduction(self.test_project, self.test_bill, expected_retention)
		
		# Get financial summary
		aggregator = BillFinancialAggregator(self.test_bill)
		summary = aggregator.calculate_bill_summary()
		
		# Verify retention amount
		self.assertAlmostEqual(
			flt(summary["total_retention"]),
			expected_retention,
			places=2,
			msg=f"Retention should be {expected_retention} ({retention_percent}% of {billed})"
		)
	
	@given(
		billed=st.floats(min_value=1000, max_value=50000, allow_nan=False, allow_infinity=False),
		retention_percent=st.floats(min_value=5, max_value=15, allow_nan=False, allow_infinity=False),
		advance_ratio=st.floats(min_value=0.1, max_value=0.5, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=20, deadline=None)
	def test_property_net_amount_equals_gross_minus_deductions(self, billed, retention_percent, advance_ratio):
		"""
		Property: Net amount = Gross billed - Retention - Advance deductions.
		For any billed B, retention R, and advance A:
		- Net = B - R - A
		"""
		billed = flt(billed, 2)
		retention_percent = flt(retention_percent, 2)
		retention = flt(billed * retention_percent / 100, 2)
		advance = flt(billed * advance_ratio, 2)
		
		# Update bill
		frappe.db.set_value("BOQ Bill", self.test_bill, {
			"total_amount": billed * 2,
			"to_date_amount": billed
		})
		
		# Create retention and advance deductions
		if retention > 0:
			self._create_retention_deduction(self.test_project, self.test_bill, retention)
		if advance > 0:
			self._create_advance_deduction(self.test_project, self.test_bill, advance)
		
		# Get financial summary
		aggregator = BillFinancialAggregator(self.test_bill)
		summary = aggregator.calculate_bill_summary()
		
		# Verify net amount calculation
		expected_net = billed - retention - advance
		self.assertAlmostEqual(
			flt(summary["net_amount"]),
			expected_net,
			places=2,
			msg=f"Net should be {expected_net} (Billed: {billed}, Retention: {retention}, Advance: {advance})"
		)
	
	@given(
		retentions=st.lists(
			st.floats(min_value=100, max_value=5000, allow_nan=False, allow_infinity=False),
			min_size=1,
			max_size=5
		)
	)
	@settings(max_examples=20, deadline=None)
	def test_property_multiple_retentions_accumulate(self, retentions):
		"""
		Property: Multiple retention deductions should accumulate correctly.
		For retention amounts [R1, R2, ..., Rn]:
		- Total retention = SUM(Ri)
		"""
		retentions = [flt(r, 2) for r in retentions]
		total_retention = sum(retentions)
		
		# Create multiple retention deductions
		for retention in retentions:
			self._create_retention_deduction(self.test_project, self.test_bill, retention)
		
		# Get financial summary
		aggregator = BillFinancialAggregator(self.test_bill)
		summary = aggregator.calculate_bill_summary()
		
		# Verify total retention
		self.assertAlmostEqual(
			flt(summary["total_retention"]),
			total_retention,
			places=2,
			msg=f"Total retention should be {total_retention}"
		)
	
	@given(
		advances=st.lists(
			st.floats(min_value=100, max_value=5000, allow_nan=False, allow_infinity=False),
			min_size=1,
			max_size=5
		)
	)
	@settings(max_examples=20, deadline=None)
	def test_property_multiple_advances_accumulate(self, advances):
		"""
		Property: Multiple advance deductions should accumulate correctly.
		For advance amounts [A1, A2, ..., An]:
		- Total advances deducted = SUM(Ai)
		"""
		advances = [flt(a, 2) for a in advances]
		total_advances = sum(advances)
		
		# Create multiple advance deductions
		for advance in advances:
			self._create_advance_deduction(self.test_project, self.test_bill, advance)
		
		# Get financial summary
		aggregator = BillFinancialAggregator(self.test_bill)
		summary = aggregator.calculate_bill_summary()
		
		# Verify total advances deducted
		self.assertAlmostEqual(
			flt(summary["total_advances_deducted"]),
			total_advances,
			places=2,
			msg=f"Total advances deducted should be {total_advances}"
		)
	
	def test_property_zero_deductions_result_in_net_equals_gross(self):
		"""
		Property: With no deductions, net amount should equal gross billed.
		For any billed amount B with no retention or advances:
		- Net = B
		"""
		billed = 10000.00
		
		# Update bill
		frappe.db.set_value("BOQ Bill", self.test_bill, {
			"total_amount": billed * 2,
			"to_date_amount": billed
		})
		
		# Get financial summary (no deductions created)
		aggregator = BillFinancialAggregator(self.test_bill)
		summary = aggregator.calculate_bill_summary()
		
		# Verify net equals gross
		self.assertAlmostEqual(
			flt(summary["net_amount"]),
			billed,
			places=2,
			msg=f"Net should equal gross ({billed}) when no deductions"
		)
		
		# Verify deductions are zero
		self.assertEqual(flt(summary["total_retention"]), 0)
		self.assertEqual(flt(summary["total_advances_deducted"]), 0)
	
	def _create_retention_deduction(self, project, bill_no, amount):
		"""Helper to create a retention deduction"""
		invoice_name = frappe.generate_hash(length=10)
		
		# Create invoice
		frappe.db.sql("""
			INSERT INTO `tabSales Invoice`
			(name, docstatus, project, customer, posting_date, due_date)
			VALUES (%s, 1, %s, 'Test Customer', CURDATE(), CURDATE())
		""", (invoice_name, project))
		
		# Add BOQ item (to link invoice to bill)
		frappe.db.sql("""
			INSERT INTO `tabSales Invoice Item`
			(name, parent, parenttype, parentfield, item_code, qty, rate, amount, bill_no)
			VALUES (%s, %s, 'Sales Invoice', 'items', 'TEST-ITEM', 1, 1000, 1000, %s)
		""", (frappe.generate_hash(length=10), invoice_name, bill_no))
		
		# Add retention deduction
		frappe.db.sql("""
			INSERT INTO `tabSales Invoice Item`
			(name, parent, parenttype, parentfield, item_code, qty, rate, amount)
			VALUES (%s, %s, 'Sales Invoice', 'items', 'RETENTION-DEDUCTION', 1, %s, %s)
		""", (frappe.generate_hash(length=10), invoice_name, -amount, -amount))
		
		frappe.db.commit()
	
	def _create_advance_deduction(self, project, bill_no, amount):
		"""Helper to create an advance deduction"""
		invoice_name = frappe.generate_hash(length=10)
		
		# Create invoice
		frappe.db.sql("""
			INSERT INTO `tabSales Invoice`
			(name, docstatus, project, customer, posting_date, due_date)
			VALUES (%s, 1, %s, 'Test Customer', CURDATE(), CURDATE())
		""", (invoice_name, project))
		
		# Add BOQ item (to link invoice to bill)
		frappe.db.sql("""
			INSERT INTO `tabSales Invoice Item`
			(name, parent, parenttype, parentfield, item_code, qty, rate, amount, bill_no)
			VALUES (%s, %s, 'Sales Invoice', 'items', 'TEST-ITEM', 1, 1000, 1000, %s)
		""", (frappe.generate_hash(length=10), invoice_name, bill_no))
		
		# Add advance deduction
		frappe.db.sql("""
			INSERT INTO `tabSales Invoice Item`
			(name, parent, parenttype, parentfield, item_code, qty, rate, amount)
			VALUES (%s, %s, 'Sales Invoice', 'items', 'ADVANCE-DEDUCTION', 1, %s, %s)
		""", (frappe.generate_hash(length=10), invoice_name, -amount, -amount))
		
		frappe.db.commit()


def run_tests():
	"""Run property tests"""
	unittest.main()


if __name__ == "__main__":
	run_tests()
