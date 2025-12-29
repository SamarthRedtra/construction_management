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
		"""Calculate totals from child BOQ Items"""
		# Get totals from BOQ Items
		totals = frappe.db.sql("""
			SELECT 
				COALESCE(SUM(total_qty), 0) as total_qty,
				COALESCE(SUM(total_amount), 0) as total_amount,
				COALESCE(SUM(total_estimated_cost), 0) as total_estimated_cost,
				COALESCE(SUM(estimated_material_cost), 0) as estimated_material_cost,
				COALESCE(SUM(estimated_labour_cost), 0) as estimated_labour_cost,
				COALESCE(SUM(estimated_subcontract_cost), 0) as estimated_subcontract_cost,
				COALESCE(SUM(estimated_asset_cost), 0) as estimated_asset_cost,
				COALESCE(SUM(estimated_other_cost), 0) as estimated_other_cost
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
		
		# Get ledger-based amounts
		ledger_totals = frappe.db.sql("""
			SELECT 
				COALESCE(SUM(CASE WHEN source IN ('Invoice', 'Reversal') THEN amount ELSE 0 END), 0) as prev_amount
			FROM `tabBOQ Progress Ledger`
			WHERE bill_no = %s
		""", self.name, as_dict=True)
		
		if ledger_totals:
			self.prev_amount = flt(ledger_totals[0].prev_amount)
		
		# Calculate current amount from items
		current = frappe.db.sql("""
			SELECT COALESCE(SUM(current_qty * rate), 0) as current_amount
			FROM `tabBOQ Item`
			WHERE parent_bill = %s
		""", self.name)
		
		self.current_amount = flt(current[0][0]) if current else 0
		self.to_date_amount = flt(self.prev_amount) + flt(self.current_amount)
		self.balance_amount = flt(self.total_amount) - flt(self.to_date_amount)
	
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
