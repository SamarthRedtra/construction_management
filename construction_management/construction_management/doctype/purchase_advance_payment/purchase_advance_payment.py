# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class PurchaseAdvancePayment(Document):
	def validate(self):
		self.validate_amount()
		self.calculate_unallocated()

	def validate_amount(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be greater than zero"))

	def calculate_unallocated(self):
		"""Calculate unallocated amount"""
		self.unallocated_amount = flt(self.amount) - flt(self.allocated_amount)

	def on_submit(self):
		self.status = "Active"
		self.db_set("unallocated_amount", flt(self.amount) - flt(self.allocated_amount))

	def on_cancel(self):
		self.db_set("status", "Cancelled")
