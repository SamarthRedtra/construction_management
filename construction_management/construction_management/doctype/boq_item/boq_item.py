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
		self.calculate_estimated_costs()
		self.calculate_amounts()
		self.update_billing_status()
	
	def calculate_estimated_costs(self):
		"""Calculate total estimated cost as sum of all cost components.
		
		Prioritizes Unit Level Breakdown if available.
		Otherwise checks Materials child table.
		Otherwise respects manual entry.
		"""
		# Requirement 3: Unit Level Breakdown Calculation
		if hasattr(self, 'item_breakdown') and self.item_breakdown:
			costs = {
				"Material": 0.0,
				"Labour": 0.0,
				"Subcontract": 0.0,
				"Asset": 0.0,
				"Other": 0.0
			}
			unit_rate_total = 0.0
			
			for row in self.item_breakdown:
				# Calculate row amount (Unit Level)
				row.amount = flt(row.qty_per_unit) * flt(row.rate)
				unit_rate_total += row.amount
				
				# Aggregate into specific cost type totals (Unit Amount * Total Qty)
				# Ensure case-insensitive matching or exact matching
				ctype = row.cost_type
				if ctype in costs:
					costs[ctype] += (row.amount * flt(self.total_qty))
			
			# Set Totals
			self.total_unit_rate = unit_rate_total
			self.total_estimated_cost = unit_rate_total * flt(self.total_qty)
			
			# Update component fields
			self.estimated_material_cost = costs["Material"]
			self.estimated_labour_cost = costs["Labour"]
			self.estimated_subcontract_cost = costs["Subcontract"]
			self.estimated_asset_cost = costs["Asset"]
			self.estimated_other_cost = costs["Other"]
			
			return

		# Legacy Logic: Calculate from materials child table
		if hasattr(self, 'materials') and self.materials:
			materials_total = sum(flt(m.amount) for m in self.materials)
			if materials_total > 0:
				self.estimated_material_cost = materials_total
		
		breakdown_total = (
			flt(self.estimated_material_cost) +
			flt(self.estimated_labour_cost) +
			flt(self.estimated_subcontract_cost) +
			flt(self.estimated_asset_cost) +
			flt(self.estimated_other_cost)
		)
		
		# If breakdown costs exist, use their sum
		# Otherwise preserve the manually entered total_estimated_cost
		if breakdown_total > 0:
			self.total_estimated_cost = breakdown_total
		elif not self.total_estimated_cost:
			self.total_estimated_cost = 0
			
		# Calculate Estimated GP
		# Calculate Estimated GP
		# Note: self.total_amount might not be updated yet as calculate_amounts is called after this
		potential_total_amount = flt(self.total_qty) * flt(self.rate)
		
		if potential_total_amount:
			self.estimated_gp = potential_total_amount - flt(self.total_estimated_cost)
			self.estimated_gp_percent = (self.estimated_gp / potential_total_amount * 100)
		else:
			self.estimated_gp = 0
			self.estimated_gp_percent = 0
	
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
			# Check setup
			allow_overbilling = frappe.db.get_value("Project BOQ", self.project_boq, "allow_overbilling")
			if not allow_overbilling:
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
				get_to_date_qty, get_to_date_amount
			)
			
			self.prev_qty = get_previous_qty(self.name)
			self.prev_amount = get_previous_amount(self.name)
			
			# To-date includes current
			self.to_date_qty = flt(self.prev_qty) + flt(self.current_qty)
			self.to_date_amount = flt(self.prev_amount) + flt(self.current_amount)
			
			# Balance
			self.balance_qty = flt(self.total_qty) - flt(self.to_date_qty)
			self.balance_amount = flt(self.total_amount) - flt(self.to_date_amount)
			
			# Cost tracking from operational sources (not billing ledger)
			costs = self._get_operational_costs()
			self.labour_cost = costs.get("labour_cost", 0)
			self.material_cost = costs.get("material_cost", 0)
			self.asset_cost = costs.get("asset_cost", 0)
			self.subcontract_cost = costs.get("subcontract_cost", 0)
			self.expense_cost = costs.get("expense_cost", 0)
			self.overhead_cost = costs.get("overhead_cost", 0)
			
			self.cost_to_date = (
				flt(self.labour_cost) +
				flt(self.material_cost) +
				flt(self.asset_cost) +
				flt(self.subcontract_cost) +
				flt(self.expense_cost) +
				flt(self.overhead_cost)
			)
			self.margin = flt(self.to_date_amount) - flt(self.cost_to_date)
			
			# Calculate Total Retention and Advance from billing ledger
			ret_adv = frappe.db.sql("""
				SELECT 
					COALESCE(SUM(retention_amount), 0),
					COALESCE(SUM(advance_deduction), 0)
				FROM `tabBOQ Progress Ledger`
				WHERE boq_item = %s AND docstatus = 1
			""", self.name)
			
			if ret_adv:
				self.total_retention_amount = flt(ret_adv[0][0])
				self.total_advance_deducted = flt(ret_adv[0][1])
			else:
				self.total_retention_amount = 0.0
				self.total_advance_deducted = 0.0

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
			self.total_retention_amount = 0.0
			self.total_advance_deducted = 0.0

	def _get_purchase_invoice_subcontract_cost(self) -> float:
		"""Sum subcontract cost from Purchase Invoice items linked to this BOQ item."""
		result = frappe.db.sql("""
			SELECT COALESCE(SUM(pii.amount), 0) as total
			FROM `tabPurchase Invoice Item` pii
			JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
			WHERE pii.boq_item = %s
			AND pi.docstatus = 1
		""", self.name)

		return flt(result[0][0]) if result else 0.0

	def _get_operational_costs(self) -> dict:
		"""
		Aggregate costs from operational sources (DPR + PI), excluding billing ledger.
		Returns a dict with labour_cost, material_cost, asset_cost, subcontract_cost, expense_cost.
		"""
		project = getattr(self, "project", None)
		
		# DPR costs
		dpr_totals = frappe.db.sql("""
			SELECT 
				COALESCE(SUM(labour_cost), 0) as labour_cost,
				COALESCE(SUM(material_cost), 0) as material_cost,
				COALESCE(SUM(asset_cost), 0) as asset_cost,
				COALESCE(SUM(subcontract_cost), 0) as subcontract_cost,
				COALESCE(SUM(expense_cost), 0) as expense_cost,
				COALESCE(SUM(overhead_cost), 0) as overhead_cost
			FROM `tabDaily Progress Record`
			WHERE boq_item = %s AND docstatus = 1
		""", self.name, as_dict=True)
		
		dpr_costs = dpr_totals[0] if dpr_totals else frappe._dict({})
		# Avoid double counting: subcontracting cost will be sourced from PI/JE/SE, not DPR
		dpr_subcontract_cost = 0
		
		# Purchase Invoice subcontract/expense adders
		pi_totals = frappe.db.sql("""
			SELECT 
				COALESCE(SUM(CASE WHEN pii.expense_account IS NOT NULL THEN pii.amount ELSE 0 END), 0) as pi_expense,
				pii.amount as pi_subcontract
			FROM `tabPurchase Invoice Item` pii
			JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
			WHERE pii.boq_item = %s AND pi.docstatus = 1
		""", self.name, as_dict=True)
		
		pi_costs = pi_totals[0] if pi_totals else frappe._dict({})
		
		# Non-DPR Journal/Stock Entries carrying BOQ dimensions (project + boq_item)
		je_se_totals = frappe.db.sql("""
			SELECT 
				COALESCE(SUM(CASE WHEN acc.root_type = 'Expense' THEN GREATEST(gle.debit - gle.credit, 0) ELSE 0 END), 0) AS je_se_expense,
				COALESCE(SUM(CASE WHEN acc.root_type <> 'Expense' THEN GREATEST(gle.debit - gle.credit, 0) ELSE 0 END), 0) AS je_se_subcontract
			FROM `tabGL Entry` gle
			LEFT JOIN `tabAccount` acc ON acc.name = gle.account
			WHERE gle.boq_item = %s
			AND gle.project = %s
			AND gle.is_cancelled = 0
			AND gle.docstatus = 1
			AND gle.voucher_type IN ('Journal Entry', 'Stock Entry')
			AND NOT EXISTS (
				SELECT 1 FROM `tabDaily Progress Record` dpr
				WHERE dpr.docstatus = 1
				AND (
					dpr.journal_entries LIKE CONCAT('%%', gle.voucher_no, '%%')
					OR dpr.stock_entries LIKE CONCAT('%%', gle.voucher_no, '%%')
				)
			)
		""", (self.name, project), as_dict=True) if project else []
		
		je_se_costs = je_se_totals[0] if je_se_totals else frappe._dict({})
		
		return {
			"labour_cost": flt(dpr_costs.get("labour_cost")),
			"material_cost": flt(dpr_costs.get("material_cost")),
			"asset_cost": flt(dpr_costs.get("asset_cost")),
			"subcontract_cost": dpr_subcontract_cost + flt(pi_costs.get("pi_subcontract")) + flt(je_se_costs.get("je_se_subcontract")),
			"expense_cost": flt(dpr_costs.get("expense_cost")),
			"overhead_cost": flt(dpr_costs.get("overhead_cost"))
		}
	
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
	
	@frappe.whitelist()
	def get_cost_progress(self):
		"""
		Get cost progress comparing estimated vs incurred costs.
		
		Returns:
			dict with progress percentage, breakup by category, and variance
		"""
		# Get incurred costs from DPR
		incurred = frappe.db.sql("""
			SELECT 
				COALESCE(SUM(material_cost), 0) as material,
				COALESCE(SUM(labour_cost), 0) as labour,
				COALESCE(SUM(subcontract_cost), 0) as subcontract,
				COALESCE(SUM(asset_cost), 0) as asset,
				COALESCE(SUM(expense_cost), 0) as other,
				COALESCE(SUM(total_cost), 0) as total
			FROM `tabDaily Progress Record`
			WHERE boq_item = %s AND docstatus = 1
		""", self.name, as_dict=True)[0]
		
		# Get estimated costs
		estimated = {
			"material": flt(self.estimated_material_cost),
			"labour": flt(self.estimated_labour_cost),
			"subcontract": flt(self.estimated_subcontract_cost),
			"asset": flt(self.estimated_asset_cost),
			"other": flt(self.estimated_other_cost),
			"total": flt(self.total_estimated_cost)
		}
		
		# Calculate progress percentage
		total_estimated = flt(estimated["total"])
		total_incurred = flt(incurred.total)
		
		if total_estimated > 0:
			progress_percentage = (total_incurred / total_estimated) * 100
		else:
			progress_percentage = 0 if total_incurred == 0 else 100  # 100% if incurred but no estimate
		
		# Calculate variance for each category
		variance = {}
		for category in ["material", "labour", "subcontract", "asset", "other", "total"]:
			variance[category] = flt(estimated[category]) - flt(incurred.get(category, 0))
		
		# Determine if overrun
		is_overrun = total_incurred > total_estimated and total_estimated > 0
		
		return {
			"estimated": estimated,
			"incurred": {
				"material": flt(incurred.material),
				"labour": flt(incurred.labour),
				"subcontract": flt(incurred.subcontract),
				"asset": flt(incurred.asset),
				"other": flt(incurred.other),
				"total": flt(incurred.total)
			},
			"variance": variance,
			"progress_percentage": round(progress_percentage, 2),
			"is_overrun": is_overrun,
			"has_estimates": total_estimated > 0
		}


@frappe.whitelist()
def recalculate_costs(boq_item_name: str) -> dict:
	"""
	Recalculate all cost fields for a BOQ Item.
	This refreshes labour_cost, material_cost, asset_cost, subcontract_cost, 
	expense_cost, overhead_cost, and cost_to_date from operational sources.
	
	Args:
		boq_item_name: Name of the BOQ Item to recalculate
		
	Returns:
		dict with success status and updated cost values
	"""
	try:
		boq_item = frappe.get_doc("BOQ Item", boq_item_name)
		
		# Recalculate all amounts (includes costs from DPR, PI, JE, SE)
		boq_item.calculate_amounts()
		
		# Update billing status
		boq_item.update_billing_status()
		
		# Save the updated values
		boq_item.db_update()
		
		# Update parent bill totals if exists
		if boq_item.parent_bill:
			bill = frappe.get_doc("BOQ Bill", boq_item.parent_bill)
			bill.calculate_totals()
			bill.db_update()
		
		# Update Project BOQ totals if exists
		if boq_item.project_boq:
			project_boq = frappe.get_doc("Project BOQ", boq_item.project_boq)
			project_boq.calculate_totals()
			project_boq.db_update()
		
		frappe.db.commit()
		
		return {
			"success": True,
			"costs": {
				"labour_cost": flt(boq_item.labour_cost),
				"material_cost": flt(boq_item.material_cost),
				"asset_cost": flt(boq_item.asset_cost),
				"subcontract_cost": flt(boq_item.subcontract_cost),
				"expense_cost": flt(boq_item.expense_cost),
				"overhead_cost": flt(boq_item.overhead_cost),
				"cost_to_date": flt(boq_item.cost_to_date),
				"margin": flt(boq_item.margin)
			}
		}
		
	except Exception as e:
		frappe.log_error(f"Error recalculating costs for {boq_item_name}: {str(e)}")
		return {
			"success": False,
			"error": str(e)
		}
