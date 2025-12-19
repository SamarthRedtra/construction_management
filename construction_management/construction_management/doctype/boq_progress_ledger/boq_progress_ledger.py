# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document


class BOQProgressLedger(Document):
	"""
	BOQ Progress Ledger - Append-only ledger for tracking billing transactions.
	
	This doctype maintains an immutable record of all billing transactions
	against BOQ Items. Records cannot be updated or deleted to maintain
	data integrity and audit trail.
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
		Create a new ledger entry.
		
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
		ledger = frappe.new_doc("BOQ Progress Ledger")
		ledger.project = project
		ledger.project_boq = project_boq
		ledger.bill_no = bill_no
		ledger.boq_item = boq_item
		ledger.posting_date = posting_date
		ledger.qty = qty
		ledger.amount = amount
		ledger.source = source
		ledger.reference_doctype = reference_doctype
		ledger.reference_name = reference_name
		ledger.remarks = remarks
		ledger.insert(ignore_permissions=True)
		
		return ledger
