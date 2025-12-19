# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BOQAdvancePayment(Document):
	def validate(self):
		self.validate_amount()
	
	def validate_amount(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be greater than zero"))
	
	def on_submit(self):
		self.status = "Active"
		self.update_advance_status()
	
	def on_cancel(self):
		self.status = "Cancelled"
	
	def update_advance_status(self):
		"""Update status based on utilization"""
		from construction_management.api.boq_invoice import get_advance_balance
		
		# Get total advances for this project
		total_advances = frappe.db.sql("""
			SELECT COALESCE(SUM(amount), 0) as total
			FROM `tabBOQ Advance Payment`
			WHERE project = %s AND docstatus = 1
		""", self.project, as_dict=True)
		
		total_collected = flt(total_advances[0].total) if total_advances else 0
		balance = get_advance_balance(self.project)
		
		# If balance is zero, mark all advances as fully utilized
		if balance <= 0 and total_collected > 0:
			frappe.db.sql("""
				UPDATE `tabBOQ Advance Payment`
				SET status = 'Fully Utilized'
				WHERE project = %s AND docstatus = 1 AND status = 'Active'
			""", self.project)
