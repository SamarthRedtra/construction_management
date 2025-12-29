# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class BOQItemMaterial(Document):
	def validate(self):
		self.calculate_amount()
	
	def calculate_amount(self):
		"""Calculate amount from qty and rate"""
		self.amount = flt(self.qty) * flt(self.rate)
