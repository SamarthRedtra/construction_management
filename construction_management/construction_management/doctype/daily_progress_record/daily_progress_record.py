# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class DailyProgressRecord(Document):
	def validate(self):
		self.calculate_total_cost()
		self.validate_boq_item()
	
	def calculate_total_cost(self):
		"""Calculate total cost from all cost categories"""
		self.total_cost = (
			flt(self.labour_cost) +
			flt(self.material_cost) +
			flt(self.asset_cost) +
			flt(self.subcontract_cost) +
			flt(self.expense_cost)
		)
	
	def validate_boq_item(self):
		"""Validate BOQ Item belongs to the selected project"""
		if self.boq_item and self.project:
			item_project = frappe.db.get_value("BOQ Item", self.boq_item, "project")
			if item_project and item_project != self.project:
				frappe.throw(
					_("BOQ Item {0} does not belong to Project {1}").format(
						self.boq_item, self.project
					)
				)
	
	def on_update(self):
		"""Update BOQ Item cost tracking"""
		self.update_boq_item_costs()
	
	def on_trash(self):
		"""Update BOQ Item cost tracking after deletion"""
		# Store boq_item before deletion for update
		self._boq_item_to_update = self.boq_item
	
	def after_delete(self):
		"""Update BOQ Item after DPR deletion"""
		if hasattr(self, '_boq_item_to_update') and self._boq_item_to_update:
			self.update_boq_item_costs(self._boq_item_to_update)
	
	def update_boq_item_costs(self, boq_item_name=None):
		"""
		Update the BOQ Item's cost tracking fields.
		
		Args:
			boq_item_name: Optional BOQ Item name (used after deletion)
		"""
		boq_item_name = boq_item_name or self.boq_item
		if not boq_item_name:
			return
		
		try:
			boq_item = frappe.get_doc("BOQ Item", boq_item_name)
			boq_item.calculate_amounts()
			boq_item.db_update()
		except frappe.DoesNotExistError:
			pass  # BOQ Item may have been deleted
