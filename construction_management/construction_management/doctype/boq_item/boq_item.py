# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BOQItem(Document):
	def validate(self):
		self.validate_boq_status()
		self.validate_current_qty()
		self.calculate_amounts()
		self.update_billing_status()
	
	def validate_boq_status(self):
		"""Prevent modifications to qty/rate when parent BOQ is locked"""
		if self.is_new():
			return
		
		from construction_management.construction_management.doctype.project_boq.project_boq import is_boq_locked
		
		if is_boq_locked(self.project_boq):
			old_doc = self.get_doc_before_save()
			if old_doc:
				# Only allow current_qty changes on locked BOQ
				if (flt(old_doc.total_qty) != flt(self.total_qty) or 
					flt(old_doc.rate) != flt(self.rate)):
					frappe.throw(
						_("Cannot modify quantity or rate. The parent BOQ is locked."),
						title=_("BOQ Locked")
					)
	
	def validate_current_qty(self):
		"""Validate current qty doesn't exceed balance"""
		if flt(self.current_qty) < 0:
			frappe.throw(_("Current quantity cannot be negative"))
		
		# Calculate balance
		from construction_management.api.boq_ledger import get_to_date_qty
		to_date_qty = get_to_date_qty(self.name) if not self.is_new() else 0
		balance_qty = flt(self.total_qty) - flt(to_date_qty)
		
		if flt(self.current_qty) > balance_qty:
			frappe.throw(
				_("Current quantity ({0}) exceeds available balance ({1})").format(
					self.current_qty, balance_qty
				),
				title=_("Over-Billing Error")
			)
	
	def calculate_amounts(self):
		"""Calculate all amount fields"""
		# Total amount
		self.total_amount = flt(self.total_qty) * flt(self.rate)
		
		# Current amount
		self.current_amount = flt(self.current_qty) * flt(self.rate)
		
		# Get ledger values
		if not self.is_new():
			from construction_management.api.boq_ledger import (
				get_previous_qty, get_previous_amount,
				get_to_date_qty, get_to_date_amount,
				get_cost_to_date
			)
			
			self.prev_qty = get_previous_qty(self.name)
			self.prev_amount = get_previous_amount(self.name)
			
			# To-date includes current
			self.to_date_qty = flt(self.prev_qty) + flt(self.current_qty)
			self.to_date_amount = flt(self.prev_amount) + flt(self.current_amount)
			
			# Balance
			self.balance_qty = flt(self.total_qty) - flt(self.to_date_qty)
			self.balance_amount = flt(self.total_amount) - flt(self.to_date_amount)
			
			# Cost tracking
			self.cost_to_date = get_cost_to_date(self.name)
			self.margin = flt(self.to_date_amount) - flt(self.cost_to_date)
			
			# Get cost breakdown from DPR
			cost_breakdown = frappe.db.sql("""
				SELECT 
					COALESCE(SUM(labour_cost), 0) as labour_cost,
					COALESCE(SUM(material_cost), 0) as material_cost,
					COALESCE(SUM(asset_cost), 0) as asset_cost,
					COALESCE(SUM(subcontract_cost), 0) as subcontract_cost,
					COALESCE(SUM(expense_cost), 0) as expense_cost
				FROM `tabDaily Progress Record`
				WHERE boq_item = %s
			""", self.name, as_dict=True)
			
			if cost_breakdown:
				self.labour_cost = flt(cost_breakdown[0].labour_cost)
				self.material_cost = flt(cost_breakdown[0].material_cost)
				self.asset_cost = flt(cost_breakdown[0].asset_cost)
				self.subcontract_cost = flt(cost_breakdown[0].subcontract_cost)
				self.expense_cost = flt(cost_breakdown[0].expense_cost)
		else:
			# New item - initialize to zero
			self.prev_qty = 0
			self.prev_amount = 0
			self.to_date_qty = flt(self.current_qty)
			self.to_date_amount = flt(self.current_amount)
			self.balance_qty = flt(self.total_qty) - flt(self.current_qty)
			self.balance_amount = flt(self.total_amount) - flt(self.current_amount)
			self.cost_to_date = 0
			self.margin = 0
	
	def update_billing_status(self):
		"""Update billing status based on progress"""
		if flt(self.balance_qty) <= 0:
			self.billing_status = "Fully Billed"
		elif flt(self.prev_qty) > 0 or flt(self.current_qty) > 0:
			self.billing_status = "Partially Billed"
		else:
			self.billing_status = "Not Billed"
	
	def before_insert(self):
		"""Validate BOQ status before creating new item and generate item_code if needed"""
		from construction_management.construction_management.doctype.project_boq.project_boq import is_boq_locked
		
		if self.project_boq and is_boq_locked(self.project_boq):
			frappe.throw(
				_("Cannot add BOQ Item. The parent BOQ is locked."),
				title=_("BOQ Locked")
			)
		
		# Auto-generate item_code if not provided
		if not self.item_code:
			# Generate a unique item code based on description
			desc_slug = (self.description or "item")[:30].strip()
			# Remove special characters and replace spaces with hyphens
			import re
			desc_slug = re.sub(r'[^a-zA-Z0-9\s-]', '', desc_slug)
			desc_slug = re.sub(r'\s+', '-', desc_slug).upper()
			self.item_code = f"BOQ-{desc_slug}"
	
	def after_insert(self):
		"""Create linked ERPNext Item after BOQ Item is created"""
		self.create_linked_item()
	
	def create_linked_item(self):
		"""Auto-create an ERPNext Item from this BOQ Item"""
		if self.linked_item:
			return  # Already linked
		
		try:
			# Generate item code - use item_code if provided, otherwise use BOQ Item name
			item_code = self.item_code if self.item_code else f"BOQ-{self.name}"
			
			# Check if item already exists
			if frappe.db.exists("Item", item_code):
				# Link to existing item
				self.db_set("linked_item", item_code)
				frappe.msgprint(_("Linked to existing Item: {0}").format(item_code))
				return
			
			# Get default item group - try "Services" first, then "All Item Groups", then first available
			item_group = None
			if frappe.db.exists("Item Group", "Services"):
				item_group = "Services"
			elif frappe.db.exists("Item Group", "All Item Groups"):
				item_group = "All Item Groups"
			else:
				# Get first available item group
				item_group = frappe.db.get_value("Item Group", filters={}, fieldname="name")
			
			if not item_group:
				frappe.log_error("No Item Group found for BOQ Item creation", "BOQ Item")
				return
			
			# Get valid UOM
			stock_uom = self.unit
			if stock_uom and not frappe.db.exists("UOM", stock_uom):
				stock_uom = "Nos"
			if not stock_uom:
				stock_uom = "Nos"
			
			# Create new Item
			item = frappe.new_doc("Item")
			item.item_code = item_code
			item.item_name = (self.description[:140] if self.description else item_code).strip()
			item.item_group = item_group
			item.stock_uom = stock_uom
			item.is_stock_item = 0  # BOQ items are typically services
			item.is_sales_item = 1
			item.is_purchase_item = 1
			item.description = self.description
			item.standard_rate = flt(self.rate)
			
			item.flags.ignore_permissions = True
			item.flags.ignore_mandatory = True
			item.insert()
			
			# Update BOQ Item with linked item
			self.db_set("linked_item", item.name)
			
			frappe.msgprint(_("Created and linked Item: {0}").format(item.name))
			
		except Exception as e:
			frappe.log_error(
				message=f"Error creating linked Item for BOQ Item {self.name}: {str(e)}",
				title="BOQ Item - Linked Item Creation Error"
			)
			frappe.msgprint(
				_("Could not create linked Item: {0}").format(str(e)),
				indicator="orange",
				alert=True
			)
	
	def on_update(self):
		"""Update parent Bill totals"""
		if self.parent_bill:
			bill = frappe.get_doc("BOQ Bill", self.parent_bill)
			bill.calculate_totals()
			bill.db_update()
	
	def on_trash(self):
		"""Validate before deletion"""
		from construction_management.construction_management.doctype.project_boq.project_boq import is_boq_locked
		
		if self.project_boq and is_boq_locked(self.project_boq):
			frappe.throw(
				_("Cannot delete BOQ Item. The parent BOQ is locked."),
				title=_("BOQ Locked")
			)
		
		# Check if there are any ledger entries
		ledger_count = frappe.db.count("BOQ Progress Ledger", {"boq_item": self.name})
		if ledger_count > 0:
			frappe.throw(
				_("Cannot delete BOQ Item with existing billing transactions."),
				title=_("Has Transactions")
			)
	
	@frappe.whitelist()
	def create_invoice(self):
		"""Create Sales Invoice from current billing quantity"""
		if flt(self.current_qty) <= 0:
			frappe.throw(_("Current quantity must be greater than zero to create invoice"))
		
		from construction_management.api.boq_invoice import create_invoice_from_boq_item
		return create_invoice_from_boq_item(
			project=self.project,
			boq_item=self.name,
			current_qty=self.current_qty
		)
	
	@frappe.whitelist()
	def create_linked_task(self):
		"""Create a Task linked to this BOQ Item"""
		if self.linked_task:
			frappe.throw(_("A task is already linked to this BOQ Item"))
		
		task = frappe.new_doc("Task")
		task.subject = f"BOQ: {self.description[:100]}" if self.description else f"BOQ Item: {self.name}"
		task.project = self.project
		task.description = f"""
			<p><strong>BOQ Item:</strong> {self.name}</p>
			<p><strong>Description:</strong> {self.description}</p>
			<p><strong>Quantity:</strong> {self.total_qty} {self.unit}</p>
			<p><strong>Rate:</strong> {self.rate}</p>
			<p><strong>Total Amount:</strong> {self.total_amount}</p>
		"""
		task.flags.ignore_permissions = True
		task.insert()
		
		# Link task to BOQ Item
		self.db_set("linked_task", task.name)
		
		frappe.msgprint(_("Task {0} created and linked").format(task.name))
		return {"task": task.name}
