# Copyright (c) 2024, Construction Management
# License: MIT

"""
Advance Adjustment Service
Handles advance payment checking, allocation, and deduction during invoice creation.
Part of Phase 2: Financial Enhancements
"""

import frappe
from frappe import _
from frappe.utils import flt, today
from typing import Dict, List, Optional


class AdvanceAdjustmentService:
	"""
	Service for managing advance adjustments against bill items.
	Provides advance availability checking, allocation, and deduction functionality.
	"""
	
	def __init__(self, project: str):
		self.project = project
		self.project_doc = frappe.get_doc("Project", project)
	
	def get_available_advances_for_bill_items(self, bill_items: List[str]) -> Dict:
		"""
		Get available advances for specific bill items.
		
		Args:
			bill_items: List of BOQ Item names
			
		Returns:
			dict with available advances per item and total
		"""
		if not bill_items:
			return {"total_available": 0, "by_item": {}}
		
		# Get advances at project level (not item-specific)
		project_advances = self._get_project_level_advances()
		
		# Get item-specific advances if they exist
		item_advances = {}
		for item in bill_items:
			item_adv = self._get_item_advances(item)
			if item_adv["available"] > 0:
				item_advances[item] = item_adv
		
		return {
			"project_level": project_advances,
			"by_item": item_advances,
			"total_available": project_advances["available"] + sum(
				adv["available"] for adv in item_advances.values()
			)
		}
	
	def _get_project_level_advances(self) -> Dict:
		"""Get advances at project level (not linked to specific items)"""
		# Get total advances collected at project level
		# Advances are Payment Entries with payment_type='Receive' and no references
		total_collected = frappe.db.sql("""
			SELECT COALESCE(SUM(pe.paid_amount), 0) as total
			FROM `tabPayment Entry` pe
			WHERE pe.project = %s 
			AND pe.docstatus = 1
			AND pe.payment_type = 'Receive'
			AND NOT EXISTS (
				SELECT 1 FROM `tabPayment Entry Reference` per 
				WHERE per.parent = pe.name
			)
		""", self.project, as_dict=True)
		
		collected = flt(total_collected[0].total) if total_collected else 0
		
		# Get total advances already deducted
		total_deducted = frappe.db.sql("""
			SELECT COALESCE(SUM(ABS(sii.amount)), 0) as total
			FROM `tabSales Invoice Item` sii
			JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE si.project = %s 
			AND si.docstatus = 1
			AND sii.item_code = 'ADVANCE-DEDUCTION'
		""", self.project, as_dict=True)
		
		deducted = flt(total_deducted[0].total) if total_deducted else 0
		
		return {
			"collected": collected,
			"deducted": deducted,
			"available": collected - deducted
		}
	
	def _get_item_advances(self, boq_item: str) -> Dict:
		"""Get advances specific to a BOQ item"""
		# Check if there's a custom advance tracking table
		# For now, return empty as item-specific advances may not be implemented
		return {
			"boq_item": boq_item,
			"collected": 0,
			"deducted": 0,
			"available": 0
		}
	
	def validate_advance_deduction(self, amount: float) -> Dict:
		"""
		Validate if advance deduction amount is available.
		
		Args:
			amount: Amount to deduct
			
		Returns:
			dict with validation result and details
		"""
		amount = flt(amount)
		
		if amount <= 0:
			return {
				"valid": True,
				"amount": 0,
				"message": "No advance deduction requested"
			}
		
		project_advances = self._get_project_level_advances()
		available = project_advances["available"]
		
		if amount > available:
			return {
				"valid": False,
				"amount": amount,
				"available": available,
				"message": f"Advance deduction ({amount}) exceeds available balance ({available})"
			}
		
		return {
			"valid": True,
			"amount": amount,
			"available": available,
			"remaining": available - amount,
			"message": "Advance deduction is valid"
		}
	
	def apply_advance_deduction(self, invoice_doc, amount: float) -> Dict:
		"""
		Apply advance deduction to an invoice document.
		
		Args:
			invoice_doc: Sales Invoice document
			amount: Amount to deduct
			
		Returns:
			dict with deduction details
		"""
		amount = flt(amount)
		
		if amount <= 0:
			return {"applied": False, "amount": 0}
		
		# Validate
		validation = self.validate_advance_deduction(amount)
		if not validation["valid"]:
			frappe.throw(_(validation["message"]), title=_("Advance Deduction Error"))
		
		# Get or create advance deduction item
		advance_item = self._get_or_create_advance_item()
		
		# Add deduction line to invoice
		invoice_doc.append("items", {
			"item_code": advance_item,
			"item_name": "Advance Deduction",
			"description": f"Deduction from advance payment (Project: {self.project})",
			"qty": 1,
			"rate": -amount,
			"amount": -amount,
			"project": self.project
		})
		
		return {
			"applied": True,
			"amount": amount,
			"item_code": advance_item,
			"remaining_balance": validation["remaining"]
		}
	
	def _get_or_create_advance_item(self) -> str:
		"""Get or create service item for advance deductions"""
		item_code = "ADVANCE-DEDUCTION"
		
		if not frappe.db.exists("Item", item_code):
			item = frappe.new_doc("Item")
			item.item_code = item_code
			item.item_name = "Advance Deduction"
			item.item_group = "Services"
			item.stock_uom = "Nos"
			item.is_stock_item = 0
			item.is_sales_item = 1
			item.description = "Advance payment deducted from progressive billing invoices"
			item.insert(ignore_permissions=True)
		
		return item_code
	
	def get_advance_history(self) -> List[Dict]:
		"""
		Get history of advance collections and deductions for the project.
		
		Returns:
			List of advance transactions with dates and amounts
		"""
		# Get advance collections
		collections = frappe.db.sql("""
			SELECT 
				pe.name,
				pe.posting_date as date,
				pe.paid_amount as amount,
				'Collection' as transaction_type,
				pe.party as customer,
				pe.reference_no,
				pe.reference_date
			FROM `tabPayment Entry` pe
			WHERE pe.project = %s 
			AND pe.docstatus = 1
			AND pe.payment_type = 'Receive'
			AND pe.is_advance = 'Yes'
			ORDER BY pe.posting_date DESC
		""", self.project, as_dict=True)
		
		# Get advance deductions
		deductions = frappe.db.sql("""
			SELECT 
				si.name,
				si.posting_date as date,
				ABS(sii.amount) as amount,
				'Deduction' as transaction_type,
				si.customer,
				si.name as invoice_no
			FROM `tabSales Invoice Item` sii
			JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE si.project = %s 
			AND si.docstatus = 1
			AND sii.item_code = 'ADVANCE-DEDUCTION'
			ORDER BY si.posting_date DESC
		""", self.project, as_dict=True)
		
		# Combine and sort by date
		all_transactions = collections + deductions
		all_transactions.sort(key=lambda x: x["date"], reverse=True)
		
		return all_transactions
	
	def get_advance_summary(self) -> Dict:
		"""
		Get comprehensive advance summary for the project.
		
		Returns:
			dict with collections, deductions, balance, and transaction count
		"""
		project_advances = self._get_project_level_advances()
		history = self.get_advance_history()
		
		collection_count = len([t for t in history if t["transaction_type"] == "Collection"])
		deduction_count = len([t for t in history if t["transaction_type"] == "Deduction"])
		
		return {
			"project": self.project,
			"total_collected": project_advances["collected"],
			"total_deducted": project_advances["deducted"],
			"available_balance": project_advances["available"],
			"collection_count": collection_count,
			"deduction_count": deduction_count,
			"last_collection": history[0] if history and history[0]["transaction_type"] == "Collection" else None,
			"last_deduction": next((t for t in history if t["transaction_type"] == "Deduction"), None)
		}


# ============================================
# Whitelisted API Functions
# ============================================

@frappe.whitelist()
def get_available_advances(project: str, bill_items: Optional[str] = None) -> Dict:
	"""
	Get available advances for a project or specific bill items.
	
	Args:
		project: Project name
		bill_items: Optional JSON string of BOQ Item names
		
	Returns:
		dict with available advance details
	"""
	import json
	
	service = AdvanceAdjustmentService(project)
	
	if bill_items:
		items = json.loads(bill_items) if isinstance(bill_items, str) else bill_items
		return service.get_available_advances_for_bill_items(items)
	
	# Return project-level summary
	return service.get_advance_summary()


@frappe.whitelist()
def validate_advance_amount(project: str, amount: float) -> Dict:
	"""
	Validate if an advance deduction amount is available.
	
	Args:
		project: Project name
		amount: Amount to validate
		
	Returns:
		dict with validation result
	"""
	service = AdvanceAdjustmentService(project)
	return service.validate_advance_deduction(flt(amount))


@frappe.whitelist()
def get_advance_history(project: str) -> List[Dict]:
	"""
	Get advance transaction history for a project.
	
	Args:
		project: Project name
		
	Returns:
		List of advance transactions
	"""
	service = AdvanceAdjustmentService(project)
	return service.get_advance_history()


@frappe.whitelist()
def get_advance_summary(project: str) -> Dict:
	"""
	Get comprehensive advance summary for a project.
	
	Args:
		project: Project name
		
	Returns:
		dict with advance summary
	"""
	service = AdvanceAdjustmentService(project)
	return service.get_advance_summary()
