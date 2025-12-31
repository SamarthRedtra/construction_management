# Copyright (c) 2024, Construction Management
# License: MIT

"""
Bill Financial Aggregator
Aggregates financial data at bill level including retention, advances, and balances.
Part of Phase 2: Financial Enhancements
"""

import frappe
from frappe import _
from frappe.utils import flt
from typing import Dict, List, Optional


class BillFinancialAggregator:
	"""
	Aggregates and calculates financial summaries at bill level.
	Tracks retention, advances, deductions, and remaining balances.
	"""
	
	def __init__(self, bill_no: str):
		self.bill_no = bill_no
		self.bill_doc = frappe.get_doc("BOQ Bill", bill_no)
		self.project = self.bill_doc.project
	
	def calculate_bill_summary(self) -> Dict:
		"""
		Calculate comprehensive financial summary for the bill.
		
		Returns:
			dict with retention, advances, deductions, and balances
		"""
		# Get bill totals
		bill_totals = self._get_bill_totals()
		
		# Get retention summary
		retention_summary = self._get_retention_summary()
		
		# Get advance summary
		advance_summary = self._get_advance_summary()
		
		# Calculate net amounts
		gross_billed = bill_totals["to_date_amount"]
		total_retention = retention_summary["total_retained"]
		total_advance_deducted = advance_summary["total_deducted"]
		
		net_amount = gross_billed - total_retention - total_advance_deducted
		
		return {
			"bill_no": self.bill_doc.bill_no,
			"bill_name": self.bill_no,
			"description": self.bill_doc.description,
			"project": self.project,
			
			# Bill totals
			"total_boq_value": bill_totals["total_amount"],
			"total_billed_to_date": bill_totals["to_date_amount"],
			"balance_to_bill": bill_totals["balance_amount"],
			
			# Retention details
			"total_retention": total_retention,
			"retention_released": retention_summary["released"],
			"retention_balance": retention_summary["balance"],
			
			# Advance details
			"total_advances_available": advance_summary["available"],
			"total_advances_deducted": advance_summary["total_deducted"],
			"advance_balance": advance_summary["remaining"],
			
			# Net calculation
			"gross_billed": gross_billed,
			"total_deductions": total_retention + total_advance_deducted,
			"net_amount": net_amount,
			
			# Invoice counts
			"invoice_count": self._get_invoice_count(),
			"last_invoice_date": self._get_last_invoice_date()
		}
	
	def _get_bill_totals(self) -> Dict:
		"""Get bill total amounts from BOQ Bill"""
		return {
			"total_amount": flt(self.bill_doc.total_amount),
			"prev_amount": flt(self.bill_doc.prev_amount),
			"current_amount": flt(self.bill_doc.current_amount),
			"to_date_amount": flt(self.bill_doc.to_date_amount),
			"balance_amount": flt(self.bill_doc.balance_amount)
		}
	
	def _get_retention_summary(self) -> Dict:
		"""Get retention amounts for this bill"""
		# Get retention deducted from invoices for items in this bill
		retention_data = frappe.db.sql("""
			SELECT 
				COALESCE(SUM(ABS(sii.amount)), 0) as total_retained
			FROM `tabSales Invoice Item` sii
			JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE si.project = %s
			AND si.docstatus = 1
			AND sii.item_code = 'RETENTION-DEDUCTION'
			AND EXISTS (
				SELECT 1 FROM `tabSales Invoice Item` sii2
				WHERE sii2.parent = si.name
				AND sii2.bill_no = %s
			)
		""", (self.project, self.bill_no), as_dict=True)
		
		total_retained = flt(retention_data[0].total_retained) if retention_data else 0
		
		# Get retention released (if any)
		released_data = frappe.db.sql("""
			SELECT 
				COALESCE(SUM(sii.amount), 0) as released
			FROM `tabSales Invoice Item` sii
			JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE si.project = %s
			AND si.docstatus = 1
			AND sii.item_code = 'RETENTION-RELEASE'
			AND sii.bill_no = %s
		""", (self.project, self.bill_no), as_dict=True)
		
		released = flt(released_data[0].released) if released_data else 0
		
		return {
			"total_retained": total_retained,
			"released": released,
			"balance": total_retained - released
		}
	
	def _get_advance_summary(self) -> Dict:
		"""Get advance amounts for this bill"""
		# Get project-level advances (not bill-specific)
		from construction_management.api.advance_adjustment_service import AdvanceAdjustmentService
		
		service = AdvanceAdjustmentService(self.project)
		project_advances = service._get_project_level_advances()
		
		# Get advances deducted from invoices for items in this bill
		deducted_data = frappe.db.sql("""
			SELECT 
				COALESCE(SUM(ABS(sii.amount)), 0) as deducted
			FROM `tabSales Invoice Item` sii
			JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE si.project = %s
			AND si.docstatus = 1
			AND sii.item_code = 'ADVANCE-DEDUCTION'
			AND EXISTS (
				SELECT 1 FROM `tabSales Invoice Item` sii2
				WHERE sii2.parent = si.name
				AND sii2.bill_no = %s
			)
		""", (self.project, self.bill_no), as_dict=True)
		
		deducted = flt(deducted_data[0].deducted) if deducted_data else 0
		
		return {
			"available": project_advances["available"],
			"total_deducted": deducted,
			"remaining": project_advances["available"]
		}
	
	def _get_invoice_count(self) -> int:
		"""Get count of invoices for this bill"""
		count = frappe.db.sql("""
			SELECT COUNT(DISTINCT si.name) as count
			FROM `tabSales Invoice` si
			JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
			WHERE sii.bill_no = %s
			AND si.docstatus = 1
		""", self.bill_no)
		
		return int(count[0][0]) if count else 0
	
	def _get_last_invoice_date(self) -> Optional[str]:
		"""Get date of last invoice for this bill"""
		result = frappe.db.sql("""
			SELECT MAX(si.posting_date) as last_date
			FROM `tabSales Invoice` si
			JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
			WHERE sii.bill_no = %s
			AND si.docstatus = 1
		""", self.bill_no)
		
		return result[0][0] if result and result[0][0] else None
	
	def get_detailed_breakdown(self) -> Dict:
		"""
		Get detailed breakdown of all financial transactions for the bill.
		
		Returns:
			dict with itemized breakdown of invoices, retention, and advances
		"""
		summary = self.calculate_bill_summary()
		
		# Get all invoices for this bill
		invoices = self._get_bill_invoices()
		
		# Get retention transactions
		retention_transactions = self._get_retention_transactions()
		
		# Get advance transactions
		advance_transactions = self._get_advance_transactions()
		
		return {
			**summary,
			"invoices": invoices,
			"retention_transactions": retention_transactions,
			"advance_transactions": advance_transactions
		}
	
	def _get_bill_invoices(self) -> List[Dict]:
		"""Get all invoices for this bill with details"""
		invoices = frappe.db.sql("""
			SELECT DISTINCT
				si.name as invoice_no,
				si.posting_date,
				si.customer,
				si.status,
				si.grand_total,
				si.outstanding_amount,
				si.custom_is_proforma as is_proforma
			FROM `tabSales Invoice` si
			JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
			WHERE sii.bill_no = %s
			AND si.docstatus = 1
			ORDER BY si.posting_date DESC
		""", self.bill_no, as_dict=True)
		
		return invoices
	
	def _get_retention_transactions(self) -> List[Dict]:
		"""Get retention transactions for this bill"""
		transactions = frappe.db.sql("""
			SELECT 
				si.name as invoice_no,
				si.posting_date,
				ABS(sii.amount) as amount,
				sii.item_code,
				CASE 
					WHEN sii.item_code = 'RETENTION-DEDUCTION' THEN 'Deduction'
					WHEN sii.item_code = 'RETENTION-RELEASE' THEN 'Release'
				END as transaction_type
			FROM `tabSales Invoice Item` sii
			JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE si.project = %s
			AND si.docstatus = 1
			AND sii.item_code IN ('RETENTION-DEDUCTION', 'RETENTION-RELEASE')
			AND EXISTS (
				SELECT 1 FROM `tabSales Invoice Item` sii2
				WHERE sii2.parent = si.name
				AND sii2.bill_no = %s
			)
			ORDER BY si.posting_date DESC
		""", (self.project, self.bill_no), as_dict=True)
		
		return transactions
	
	def _get_advance_transactions(self) -> List[Dict]:
		"""Get advance transactions for this bill"""
		transactions = frappe.db.sql("""
			SELECT 
				si.name as invoice_no,
				si.posting_date,
				ABS(sii.amount) as amount,
				'Deduction' as transaction_type
			FROM `tabSales Invoice Item` sii
			JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE si.project = %s
			AND si.docstatus = 1
			AND sii.item_code = 'ADVANCE-DEDUCTION'
			AND EXISTS (
				SELECT 1 FROM `tabSales Invoice Item` sii2
				WHERE sii2.parent = si.name
				AND sii2.bill_no = %s
			)
			ORDER BY si.posting_date DESC
		""", (self.project, self.bill_no), as_dict=True)
		
		return transactions


# ============================================
# Whitelisted API Functions
# ============================================

@frappe.whitelist()
def get_bill_financial_summary(bill_no: str) -> Dict:
	"""
	Get financial summary for a bill.
	
	Args:
		bill_no: BOQ Bill name
		
	Returns:
		dict with financial summary
	"""
	aggregator = BillFinancialAggregator(bill_no)
	return aggregator.calculate_bill_summary()


@frappe.whitelist()
def get_bill_financial_breakdown(bill_no: str) -> Dict:
	"""
	Get detailed financial breakdown for a bill.
	
	Args:
		bill_no: BOQ Bill name
		
	Returns:
		dict with detailed breakdown
	"""
	aggregator = BillFinancialAggregator(bill_no)
	return aggregator.get_detailed_breakdown()


@frappe.whitelist()
def get_project_bills_financial_summary(project: str) -> List[Dict]:
	"""
	Get financial summaries for all bills in a project.
	
	Args:
		project: Project name
		
	Returns:
		List of bill financial summaries
	"""
	# Get all bills for the project
	bills = frappe.db.get_all(
		"BOQ Bill",
		filters={"project": project},
		fields=["name", "bill_no"],
		order_by="bill_no"
	)
	
	summaries = []
	for bill in bills:
		aggregator = BillFinancialAggregator(bill.name)
		summary = aggregator.calculate_bill_summary()
		summaries.append(summary)
	
	return summaries


@frappe.whitelist()
def get_project_financial_overview(project: str) -> Dict:
	"""
	Get comprehensive financial overview for entire project.
	Aggregates all bills, retention, and advances.
	
	Args:
		project: Project name
		
	Returns:
		dict with project-wide financial overview
	"""
	# Get all bill summaries
	bill_summaries = get_project_bills_financial_summary(project)
	
	# Aggregate totals
	total_boq_value = sum(flt(b["total_boq_value"]) for b in bill_summaries)
	total_billed = sum(flt(b["total_billed_to_date"]) for b in bill_summaries)
	total_retention = sum(flt(b["total_retention"]) for b in bill_summaries)
	total_advance_deducted = sum(flt(b["total_advances_deducted"]) for b in bill_summaries)
	
	# Get project-level advance summary
	from construction_management.api.advance_adjustment_service import AdvanceAdjustmentService
	service = AdvanceAdjustmentService(project)
	advance_summary = service.get_advance_summary()
	
	return {
		"project": project,
		"bill_count": len(bill_summaries),
		
		# BOQ totals
		"total_boq_value": total_boq_value,
		"total_billed_to_date": total_billed,
		"balance_to_bill": total_boq_value - total_billed,
		"billing_percentage": (total_billed / total_boq_value * 100) if total_boq_value > 0 else 0,
		
		# Retention totals
		"total_retention": total_retention,
		"retention_balance": total_retention,  # Simplified - can be enhanced
		
		# Advance totals
		"total_advances_collected": advance_summary["total_collected"],
		"total_advances_deducted": total_advance_deducted,
		"advance_balance": advance_summary["available_balance"],
		
		# Net calculation
		"gross_billed": total_billed,
		"total_deductions": total_retention + total_advance_deducted,
		"net_amount": total_billed - total_retention - total_advance_deducted,
		
		# Bill breakdown
		"bills": bill_summaries
	}
