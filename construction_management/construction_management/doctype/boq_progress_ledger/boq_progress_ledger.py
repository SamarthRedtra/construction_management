# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BOQProgressLedger(Document):
	"""
	BOQ Progress Ledger - Append-only ledger for tracking billing transactions.
	
	This doctype maintains an immutable record of all billing transactions
	against BOQ Items. Records cannot be updated or deleted to maintain
	data integrity and audit trail.
	
	Each entry stores:
	- Transaction qty/amount (the current transaction)
	- Previous qty/amount (total before this transaction)
	- Accumulated qty/amount (total including this transaction)
	"""
	
	def validate(self):
		"""Validate ledger entry"""
		self.validate_append_only()
	
	def validate_append_only(self):
		"""Prevent updates to existing records"""
		if not self.is_new():
			frappe.throw(
				_("BOQ Progress Ledger entries cannot be modified. This is an append-only ledger."),
				title=_("Ledger Immutable")
			)
	
	def before_save(self):
		"""Additional validation before save"""
		if not self.is_new():
			frappe.throw(
				_("BOQ Progress Ledger entries cannot be modified."),
				title=_("Ledger Immutable")
			)
	
	def on_trash(self):
		"""Prevent deletion of ledger entries"""
		frappe.throw(
			_("BOQ Progress Ledger entries cannot be deleted. This is an append-only ledger."),
			title=_("Ledger Immutable")
		)
	
	@staticmethod
	def get_accumulated_totals(boq_item: str) -> dict:
		"""
		Get the current accumulated totals for a BOQ Item.
		
		Args:
			boq_item: BOQ Item name
			
		Returns:
			dict with accumulated_qty and accumulated_amount
		"""
		result = frappe.db.sql("""
			SELECT 
				COALESCE(SUM(qty), 0) as accumulated_qty,
				COALESCE(SUM(amount), 0) as accumulated_amount
			FROM `tabBOQ Progress Ledger`
			WHERE boq_item = %s
		""", boq_item, as_dict=True)
		
		if result:
			return {
				"accumulated_qty": flt(result[0].accumulated_qty),
				"accumulated_amount": flt(result[0].accumulated_amount)
			}
		return {"accumulated_qty": 0, "accumulated_amount": 0}
	
	@staticmethod
	def create_entry(
		project: str,
		project_boq: str,
		bill_no: str,
		boq_item: str,
		posting_date: str,
		qty: float,
		amount: float,
		source: str,
		reference_doctype: str = None,
		reference_name: str = None,
		remarks: str = None
	) -> "BOQProgressLedger":
		"""
		Create a new ledger entry with prev/curr/accumulated tracking.
		
		This is the only way to add entries to the ledger.
		
		Args:
			project: Project name
			project_boq: Project BOQ name
			bill_no: BOQ Bill name
			boq_item: BOQ Item name
			posting_date: Transaction date
			qty: Quantity
			amount: Amount
			source: Source type (Invoice/Adjustment/Reversal)
			reference_doctype: Reference document type
			reference_name: Reference document name
			remarks: Optional remarks
			
		Returns:
			Created BOQProgressLedger document
		"""
		# Get current accumulated totals (this becomes "previous" for the new entry)
		prev_totals = BOQProgressLedger.get_accumulated_totals(boq_item)
		prev_qty = flt(prev_totals["accumulated_qty"])
		prev_amount = flt(prev_totals["accumulated_amount"])
		
		# Current transaction values
		current_qty = flt(qty)
		current_amount = flt(amount)
		
		# New accumulated totals (prev + current)
		accumulated_qty = prev_qty + current_qty
		accumulated_amount = prev_amount + current_amount
		
		# Create ledger entry
		ledger = frappe.new_doc("BOQ Progress Ledger")
		ledger.project = project
		ledger.project_boq = project_boq
		ledger.bill_no = bill_no
		ledger.boq_item = boq_item
		ledger.posting_date = posting_date
		
		# Transaction values
		ledger.qty = current_qty
		ledger.amount = current_amount
		ledger.source = source
		ledger.reference_doctype = reference_doctype
		ledger.reference_name = reference_name
		ledger.remarks = remarks
		
		# Progressive tracking values
		ledger.prev_qty = prev_qty
		ledger.prev_amount = prev_amount
		ledger.current_qty = current_qty
		ledger.current_amount = current_amount
		ledger.accumulated_qty = accumulated_qty
		ledger.accumulated_amount = accumulated_amount
		
		ledger.insert(ignore_permissions=True)
		
		return ledger
