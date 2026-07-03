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
		self.log_rate_change()
	
	def calculate_estimated_costs(self):
		"""Calculate total estimated cost as sum of all cost components.
		
		Prioritizes itemized Unit Cost fields.
		Otherwise checks Unit Level Breakdown table.
		Otherwise checks Materials child table.
		Otherwise respects manual entry.
		"""
		# Priority 1: Itemized unit cost fields
		has_unit_costs = any([
			flt(getattr(self, 'estimated_material_cost_per_unit', 0)),
			flt(getattr(self, 'estimated_labour_cost_per_unit', 0)),
			flt(getattr(self, 'estimated_subcontract_cost_per_unit', 0)),
			flt(getattr(self, 'estimated_asset_cost_per_unit', 0)),
			flt(getattr(self, 'estimated_other_cost_per_unit', 0))
		])

		if has_unit_costs:
			self.estimated_material_cost = flt(self.estimated_material_cost_per_unit) * flt(self.total_qty)
			self.estimated_labour_cost = flt(self.estimated_labour_cost_per_unit) * flt(self.total_qty)
			self.estimated_subcontract_cost = flt(self.estimated_subcontract_cost_per_unit) * flt(self.total_qty)
			self.estimated_asset_cost = flt(self.estimated_asset_cost_per_unit) * flt(self.total_qty)
			self.estimated_other_cost = flt(self.estimated_other_cost_per_unit) * flt(self.total_qty)
			
			self.total_estimated_cost = (
				flt(self.estimated_material_cost) +
				flt(self.estimated_labour_cost) +
				flt(self.estimated_subcontract_cost) +
				flt(self.estimated_asset_cost) +
				flt(self.estimated_other_cost)
			)
			self.total_unit_rate = (
				flt(self.estimated_material_cost_per_unit) +
				flt(self.estimated_labour_cost_per_unit) +
				flt(self.estimated_subcontract_cost_per_unit) +
				flt(self.estimated_asset_cost_per_unit) +
				flt(self.estimated_other_cost_per_unit)
			)
			return

		# Priority 2: Unit Level Breakdown (Table)
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
				
				ctype = row.cost_type
				if ctype in costs:
					costs[ctype] += (row.amount * flt(self.total_qty))
			
			self.total_unit_rate = unit_rate_total
			self.total_estimated_cost = unit_rate_total * flt(self.total_qty)
			
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
		# Get ledger values if not new
		if not self.is_new():
			from construction_management.api.boq_ledger import (
				get_previous_qty, get_previous_amount
			)
			
			self.prev_qty = get_previous_qty(self.name)
			self.prev_amount = get_previous_amount(self.name)
			
			# Use gross SI amounts for total_amount (contract value) so that
			# deductions don't deflate the displayed contract value.
			gross_billed = self._get_gross_billed_amount()
			if gross_billed:
				billed_qty = flt(gross_billed.get("qty", 0))
				billed_amount = flt(gross_billed.get("amount", 0))
			else:
				billed_qty = flt(self.prev_qty)
				billed_amount = flt(self.prev_amount)

			remaining_qty = flt(self.total_qty) - billed_qty
			self.total_amount = billed_amount + remaining_qty * flt(self.rate)
		else:
			# For new items, standard calculation applies
			self.prev_qty = 0
			self.prev_amount = 0
			self.total_amount = flt(self.total_qty) * flt(self.rate)
		
		# Current amount
		self.current_amount = flt(self.current_qty) * flt(self.rate)
		
		# Get ledger values
		if not self.is_new():
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
				WHERE boq_item = %s
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

	def _get_gross_billed_amount(self) -> dict | None:
		"""Sum gross qty and amount from submitted Sales Invoice items for this BOQ item,
		excluding negative deduction rows so the result reflects the actual billed value."""
		result = frappe.db.sql("""
			SELECT COALESCE(SUM(sii.qty), 0) AS qty,
				   COALESCE(SUM(sii.amount), 0) AS amount
			FROM `tabSales Invoice Item` sii
			JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE sii.boq_item = %s AND si.docstatus = 1
				AND sii.qty > 0 AND sii.rate > 0
		""", self.name, as_dict=True)
		if result and flt(result[0].qty):
			return {"qty": flt(result[0].qty), "amount": flt(result[0].amount)}
		return None

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
				COALESCE(SUM(pii.amount), 0) as pi_subcontract
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
		"""Update parent Bill and Project BOQ totals"""
		self.update_parent_totals()
	
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
	
	def update_parent_totals(self):
		"""Update parent BOQ Bill and Project BOQ totals."""
		update_parent_totals(self)

	
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

	def log_rate_change(self):
		check_rate_history_table()
		
		# Check if rate changed
		is_changed = False
		if self.is_new():
			is_changed = True
		else:
			db_rate = frappe.db.get_value("BOQ Item", self.name, "rate")
			if db_rate is not None and flt(db_rate) != flt(self.rate):
				is_changed = True
				
		if is_changed:
			from construction_management.api.boq_ledger import get_previous_amount, get_previous_qty

			prev_qty = flt(get_previous_qty(self.name))
			prev_amount = flt(get_previous_amount(self.name))
			balance_qty = flt(self.total_qty) - prev_qty
			balance_value = flt(balance_qty) * flt(self.rate)
			# Log the new rate change
			import uuid
			frappe.db.sql("""
				INSERT INTO `tabBOQ Rate History`
					(name, parent, changed_by, changed_date, rate, amount, prev_qty, prev_amount, balance_qty, balance_value)
				VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s, %s, %s)
			""", (
				str(uuid.uuid4()),
				self.name,
				frappe.session.user or "Administrator",
				flt(self.rate),
				flt(self.total_amount),
				prev_qty,
				prev_amount,
				balance_qty,
				balance_value,
			))


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


@frappe.whitelist()
def recalculate_progressive_billing(boq_item_name: str):
	"""Manually trigger recalculation of progressive billing from ledger."""
	try:
		from construction_management.api.boq_ledger import recalculate_ledger_for_item
		
		# 1. Recalculate ledger state (Active row amount etc)
		recalculate_ledger_for_item(boq_item_name)
		
		# 2. Update BOQ Item statistics from ledger
		doc = frappe.get_doc("BOQ Item", boq_item_name)
		doc.calculate_amounts()
		doc.update_billing_status()
		doc.save()
		
		return {"success": True}
	except Exception as e:
		frappe.log_error(f"Error recalculating progressive billing for {boq_item_name}: {str(e)}")
		return {"success": False, "error": str(e)}


def update_parent_totals(doc, method=None):
	"""Update parent Bill and Project BOQ totals after an item is updated or deleted"""
	if doc.parent_bill:
		try:
			bill = frappe.get_doc("BOQ Bill", doc.parent_bill)
			bill.calculate_totals()
			bill.db_update()
		except frappe.DoesNotExistError:
			pass
	
	if doc.project_boq:
		try:
			boq = frappe.get_doc("Project BOQ", doc.project_boq)
			boq.calculate_totals()
			boq.db_update()
		except frappe.DoesNotExistError:
			pass


def check_rate_history_table():
	frappe.db.sql("""
		CREATE TABLE IF NOT EXISTS `tabBOQ Rate History` (
			name VARCHAR(140) PRIMARY KEY,
			parent VARCHAR(140),
			changed_by VARCHAR(140),
			changed_date DATETIME,
			rate DECIMAL(18, 6),
			amount DECIMAL(18, 6),
			prev_qty DECIMAL(18, 6) DEFAULT 0,
			prev_amount DECIMAL(18, 6) DEFAULT 0,
			balance_qty DECIMAL(18, 6) DEFAULT 0,
			balance_value DECIMAL(18, 6) DEFAULT 0,
			INDEX (parent)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
	""")


@frappe.whitelist()
def get_rate_history(boq_item):
	check_rate_history_table()
	
	history = frappe.db.sql("""
		SELECT changed_date as posting_date, changed_by, rate, amount
		FROM `tabBOQ Rate History`
		WHERE parent = %s
		ORDER BY changed_date DESC
	""", boq_item, as_dict=True)
	
	if not history:
		# Fallback to current state
		creation, rate, amount, owner = frappe.db.get_value(
			"BOQ Item",
			boq_item,
			["creation", "rate", "total_amount", "owner"]
		)
		history = [{
			"posting_date": creation,
			"changed_by": owner,
			"rate": flt(rate),
			"amount": flt(amount)
		}]
		
	for h in history:
		full_name = frappe.db.get_value("User", h.get("changed_by"), "full_name")
		h["user_name"] = full_name or h.get("changed_by")
		
	return history


@frappe.whitelist()
def get_rate_split_summary(boq_item):
	"""Return per-invoice billing tiers, remaining balance and rate history."""
	from construction_management.api.boq_ledger import get_previous_amount, get_previous_qty

	check_rate_history_table()
	item = frappe.get_doc("BOQ Item", boq_item)
	current_rate = flt(item.rate)
	total_qty = flt(item.total_qty)

	# Per-invoice gross billing tiers (excludes deduction line items)
	billing_tiers = frappe.db.sql("""
		SELECT sii.parent AS invoice, sii.qty, sii.rate, sii.amount,
			   si.posting_date
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE sii.boq_item = %s AND si.docstatus = 1
			AND sii.qty > 0 AND sii.rate > 0
		ORDER BY si.posting_date ASC, sii.idx ASC
	""", boq_item, as_dict=True)

	billed_qty = sum(flt(t.qty) for t in billing_tiers)
	billed_amount = sum(flt(t.amount) for t in billing_tiers)

	# Fallback to ledger when no SI data exists
	if not billing_tiers:
		prev_qty = flt(get_previous_qty(boq_item))
		prev_amount = flt(get_previous_amount(boq_item))
		if prev_qty:
			billing_tiers = [{
				"invoice": None,
				"qty": prev_qty,
				"rate": flt(prev_amount / prev_qty),
				"amount": prev_amount,
				"posting_date": None,
			}]
			billed_qty = prev_qty
			billed_amount = prev_amount

	balance_qty = flt(total_qty) - billed_qty
	balance_value = flt(balance_qty) * current_rate
	total_amount = flt(billed_amount) + balance_value

	return {
		"billing_tiers": billing_tiers,
		"billed_qty": billed_qty,
		"billed_amount": billed_amount,
		"balance_qty": balance_qty,
		"current_rate": current_rate,
		"balance_value": balance_value,
		"total_amount": total_amount,
		"rate_history": get_rate_history(boq_item),
	}

