# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BOQBill(Document):
	def validate(self):
		self.validate_boq_status()
		self.calculate_totals()
	
	def validate_boq_status(self):
		"""Prevent modifications when parent BOQ is locked"""
		if self.is_new():
			return
		
		from construction_management.construction_management.doctype.project_boq.project_boq import is_boq_locked
		
		if is_boq_locked(self.project_boq):
			frappe.throw(
				_("Cannot modify Bill Number. The parent BOQ is locked."),
				title=_("BOQ Locked")
			)
	
	def before_insert(self):
		"""Validate BOQ status before creating new bill"""
		from construction_management.construction_management.doctype.project_boq.project_boq import is_boq_locked
		
		if is_boq_locked(self.project_boq):
			frappe.throw(
				_("Cannot add Bill Number. The parent BOQ is locked."),
				title=_("BOQ Locked")
			)
	
	def calculate_totals(self):
		"""
		Calculate totals from child BOQ Items.
		
		Property 6: Bill Totals Calculation Correctness
		- total_amount = SUM(child.total_amount)
		- current_amount = SUM(child.current_qty × child.rate)
		- to_date_amount = prev_amount + current_amount
		- balance_amount = total_amount - to_date_amount
		"""
		# Get totals from BOQ Items - sum all child item amounts
		totals = frappe.db.sql("""
			SELECT 
				COALESCE(SUM(total_qty), 0) as total_qty,
				COALESCE(SUM(total_amount), 0) as total_amount,
				COALESCE(SUM(total_estimated_cost), 0) as total_estimated_cost,
				COALESCE(SUM(estimated_material_cost), 0) as estimated_material_cost,
				COALESCE(SUM(estimated_labour_cost), 0) as estimated_labour_cost,
				COALESCE(SUM(estimated_subcontract_cost), 0) as estimated_subcontract_cost,
				COALESCE(SUM(estimated_asset_cost), 0) as estimated_asset_cost,
				COALESCE(SUM(estimated_other_cost), 0) as estimated_other_cost,
				COALESCE(SUM(prev_qty), 0) as prev_qty,
				COALESCE(SUM(current_qty), 0) as current_qty,
				COALESCE(SUM(to_date_qty), 0) as to_date_qty,
				COALESCE(SUM(balance_qty), 0) as balance_qty,
				COALESCE(SUM(total_retention_amount), 0) as total_retention_amount,
				COALESCE(SUM(total_advance_deducted), 0) as total_advance_deducted
			FROM `tabBOQ Item`
			WHERE parent_bill = %s
		""", self.name, as_dict=True)
		
		if totals:
			self.total_qty = flt(totals[0].total_qty)
			self.total_amount = flt(totals[0].total_amount)
			# Estimated costs aggregation
			self.total_estimated_cost = flt(totals[0].total_estimated_cost)
			self.estimated_material_cost = flt(totals[0].estimated_material_cost)
			self.estimated_labour_cost = flt(totals[0].estimated_labour_cost)
			self.estimated_subcontract_cost = flt(totals[0].estimated_subcontract_cost)
			self.estimated_asset_cost = flt(totals[0].estimated_asset_cost)
			self.estimated_other_cost = flt(totals[0].estimated_other_cost)
			# Financials
			self.total_retention_amount = flt(totals[0].total_retention_amount)
			self.total_advance_deducted = flt(totals[0].total_advance_deducted)
			# Quantity tracking
			if hasattr(self, 'prev_qty'):
				self.prev_qty = flt(totals[0].prev_qty)
			if hasattr(self, 'current_qty'):
				self.current_qty = flt(totals[0].current_qty)
			if hasattr(self, 'to_date_qty'):
				self.to_date_qty = flt(totals[0].to_date_qty)
			if hasattr(self, 'balance_qty'):
				self.balance_qty = flt(totals[0].balance_qty)
		
		# Get prev_amount from ledger entries with source 'Invoice' or 'Reversal'
		ledger_totals = frappe.db.sql("""
			SELECT 
				COALESCE(SUM(CASE WHEN source IN ('Invoice', 'Reversal') THEN amount ELSE 0 END), 0) as prev_amount,
				COALESCE(SUM(CASE WHEN source IN ('Invoice', 'Reversal') THEN qty ELSE 0 END), 0) as prev_qty_ledger
			FROM `tabBOQ Progress Ledger`
			WHERE bill_no = %s
		""", self.name, as_dict=True)
		
		if ledger_totals:
			self.prev_amount = flt(ledger_totals[0].prev_amount)
		else:
			self.prev_amount = 0
		
		# Calculate current_amount = SUM(current_qty × rate) for all child items
		current = frappe.db.sql("""
			SELECT COALESCE(SUM(current_qty * rate), 0) as current_amount
			FROM `tabBOQ Item`
			WHERE parent_bill = %s
		""", self.name)
		
		self.current_amount = flt(current[0][0]) if current else 0
		
		# to_date_amount = prev_amount + current_amount
		self.to_date_amount = flt(self.prev_amount) + flt(self.current_amount)
		
		# balance_amount = total_amount - to_date_amount
		self.balance_amount = flt(self.total_amount) - flt(self.to_date_amount)

		# Calculate Total Estimated BOQ Value (Total value of Project's BOQ Items)
		total_boq_val = frappe.db.sql("""
			SELECT COALESCE(SUM(bi.total_amount), 0)
			FROM `tabBOQ Item` bi
			WHERE bi.project = %s
		""", self.project)
		
		self.total_estimated_boq_value = flt(total_boq_val[0][0]) if total_boq_val else 0.0
	
	def get_estimated_costs(self):
		"""Get aggregated estimated costs from child BOQ Items"""
		return {
			"total_estimated_cost": flt(self.total_estimated_cost),
			"estimated_material_cost": flt(self.estimated_material_cost),
			"estimated_labour_cost": flt(self.estimated_labour_cost),
			"estimated_subcontract_cost": flt(self.estimated_subcontract_cost),
			"estimated_asset_cost": flt(self.estimated_asset_cost),
			"estimated_other_cost": flt(self.estimated_other_cost)
		}
	
	def on_update(self):
		"""Update parent Project BOQ totals"""
		if self.project_boq:
			boq = frappe.get_doc("Project BOQ", self.project_boq)
			boq.calculate_totals()
			boq.db_update()
	
	def on_trash(self):
		"""Validate before deletion"""
		from construction_management.construction_management.doctype.project_boq.project_boq import is_boq_locked
		
		if is_boq_locked(self.project_boq):
			frappe.throw(
				_("Cannot delete Bill Number. The parent BOQ is locked."),
				title=_("BOQ Locked")
			)
		
		# Check if there are any ledger entries
		ledger_count = frappe.db.count("BOQ Progress Ledger", {"bill_no": self.name})
		if ledger_count > 0:
			frappe.throw(
				_("Cannot delete Bill Number with existing billing transactions."),
				title=_("Has Transactions")
			)
