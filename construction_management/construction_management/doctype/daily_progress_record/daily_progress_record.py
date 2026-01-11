# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate
from construction_management.api.budget_control import validate_dpr_budget


class DailyProgressRecord(Document):
	def validate(self):
		self.validate_boq_item()
		self.fetch_bill_no()
		self.validate_material_stock()
		self.calculate_asset_costs()
		self.calculate_employee_costs()
		self.calculate_material_costs()
		self.calculate_overhead_costs()
		self.calculate_expense_costs()
		self.calculate_total_cost()
		self.calculate_quantity_totals()
		self.run_budget_controls()
	
	def before_submit(self):
		"""Validate costs against BOQ estimates before submission"""
		self.validate_cost_against_estimates()
		self.run_budget_controls()
	
	def fetch_bill_no(self):
		"""Fetch Bill No from BOQ Item"""
		if self.boq_item and not self.bill_no:
			self.bill_no = frappe.db.get_value("BOQ Item", self.boq_item, "parent_bill")
	
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
	
	def validate_material_stock(self):
		"""
		Validate that sufficient stock is available for each material entry.
		Throws an error if any material has insufficient stock in its warehouse.
		(Requirement 2.6: Prevent submission if stock is insufficient)
		"""
		if not self.materials:
			return
		
		errors = []
		
		for row in self.materials:
			if not row.item_code or not row.qty or flt(row.qty) <= 0:
				continue
			
			if not row.warehouse:
				continue
			
			# Get available stock in warehouse
			available_qty = frappe.db.get_value(
				"Bin",
				{"warehouse": row.warehouse, "item_code": row.item_code},
				"actual_qty"
			) or 0
			
			requested_qty = flt(row.qty)
			
			if flt(available_qty) < requested_qty:
				errors.append(
					_("Insufficient stock for item <b>{0}</b> in warehouse <b>{1}</b>. "
					  "Available: {2}, Requested: {3}").format(
						row.item_code,
						row.warehouse,
						flt(available_qty),
						requested_qty
					)
				)
		
		if errors:
			frappe.throw(
				_("Cannot save DPR due to insufficient stock:") + "<br><br>" + "<br>".join(errors),
				title=_("Insufficient Stock")
			)
	
	def calculate_asset_costs(self):
		"""Calculate asset costs from child table based on billing frequency"""
		from construction_management.api.asset_billing import (
			get_billing_rate, 
			calculate_cost,
			get_prorated_monthly_cost
		)
		
		total = 0
		for row in self.assets or []:
			if not row.asset:
				continue
			
			# Get billing configuration
			billing = get_billing_rate(self.project, row.asset, self.date)
			hours = flt(row.hours) or 8
			
			if flt(billing.rate) <= 0:
				frappe.throw(
					_("No billing rate configured for Asset {0} in Project {1}. Please set Project Asset Billing.").format(
						row.asset, self.project
					),
					title=_("Missing Asset Rate")
				)
			
			# Set rate fields based on frequency
			row.rate_per_hour = billing.value_per_hour
			row.rate_per_day = billing.value_per_day or (billing.value_per_hour * 8)
			row.rate = billing.rate
			
			# Calculate cost based on frequency
			if billing.frequency == "Hourly":
				row.amount = calculate_cost(billing.rate, "Hourly", hours)
			elif billing.frequency == "Daily":
				# Convert hours to days (8 hours = 1 day)
				days = hours / 8
				row.amount = calculate_cost(billing.rate, "Daily", days)
			elif billing.frequency == "Monthly":
				# For monthly, calculate prorated cost for 1 day per DPR entry
				row.amount = get_prorated_monthly_cost(billing.rate, 1, self.date)
			else:
				# Default to hourly calculation
				row.amount = flt(row.rate_per_hour) * hours
			
			total += flt(row.amount)
		self.asset_cost = total
	
	def calculate_employee_costs(self):
		"""Calculate employee costs from child table"""
		total = 0
		for row in self.employees or []:
			if not row.rate_per_day and row.employee:
				row.rate_per_day = get_employee_daily_rate(row.employee)
			hours = flt(row.hours) or 8
			row.amount = flt(row.rate_per_day) * (hours / 8)
			total += flt(row.amount)
		self.labour_cost = total
	
	def calculate_material_costs(self):
		"""Calculate material costs from child table"""
		total = 0
		for row in self.materials or []:
			if not row.rate and row.item_code:
				row.rate = get_item_valuation_rate(row.item_code, row.warehouse)
			row.amount = flt(row.qty) * flt(row.rate)
			total += flt(row.amount)
		self.material_cost = total
	
	def calculate_overhead_costs(self):
		"""Calculate overhead costs from child table"""
		total = 0
		for row in self.overheads or []:
			total += flt(row.amount)
		self.overhead_cost = total
	
	def calculate_expense_costs(self):
		"""Calculate expense costs from child table"""
		total = 0
		for row in self.expenses or []:
			total += flt(row.amount)
		self.expense_cost = total
	
	def calculate_total_cost(self):
		"""Calculate total cost from all cost categories"""
		self.total_cost = (
			flt(self.labour_cost) +
			flt(self.material_cost) +
			flt(self.asset_cost) +
			flt(self.subcontract_cost) +
			flt(self.overhead_cost) +
			flt(self.expense_cost)
		)

	def run_budget_controls(self):
		"""Enforce project/BOQ budget limits (soft/hard) per project settings."""
		try:
			validate_dpr_budget(self)
		except Exception:
			# Re-raise to respect hard limits / validation errors
			raise
	
	def calculate_quantity_totals(self):
		"""
		Calculate quantity totals for DPR summary display.
		(Task 3.2: Display Quantities in DPR Totals)
		"""
		# Total labour hours
		total_labour_hours = 0
		for row in self.employees or []:
			total_labour_hours += flt(row.hours) or 8
		
		# Total material quantity
		total_material_qty = 0
		for row in self.materials or []:
			total_material_qty += flt(row.qty)
		
		# Total asset hours
		total_asset_hours = 0
		for row in self.assets or []:
			total_asset_hours += flt(row.hours) or 8
		
		# Total subcontract quantity (count of entries if no qty field)
		total_subcontract_qty = 0
		if hasattr(self, 'subcontracts') and self.subcontracts:
			for row in self.subcontracts:
				total_subcontract_qty += flt(row.qty) if hasattr(row, 'qty') else 1
		
		# Total expense count
		total_expense_count = len(self.expenses or [])
		
		# Set fields if they exist
		if hasattr(self, 'total_labour_hours'):
			self.total_labour_hours = total_labour_hours
		if hasattr(self, 'total_material_qty'):
			self.total_material_qty = total_material_qty
		if hasattr(self, 'total_asset_hours'):
			self.total_asset_hours = total_asset_hours
		if hasattr(self, 'total_subcontract_qty'):
			self.total_subcontract_qty = total_subcontract_qty
		if hasattr(self, 'total_expense_count'):
			self.total_expense_count = total_expense_count
	
	def validate_cost_against_estimates(self):
		"""
		Validate DPR costs against BOQ Item estimated costs.
		
		Property 5: Block submission if total cost exceeds estimate
		Property 6: Warn if component costs exceed estimates
		
		Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
		"""
		if not self.boq_item:
			return  # No BOQ Item linked, skip validation
		
		from construction_management.api.cost_validation import validate_dpr_costs
		
		# Prepare DPR costs dict
		dpr_costs = {
			"material_cost": flt(self.material_cost),
			"labour_cost": flt(self.labour_cost),
			"subcontract_cost": flt(self.subcontract_cost),
			"asset_cost": flt(self.asset_cost),
			"expense_cost": flt(self.expense_cost),
			"total_cost": flt(self.total_cost)
		}
		
		# Validate costs (exclude current DPR if updating)
		exclude_dpr = self.name if not self.is_new() else None
		result = validate_dpr_costs(self.boq_item, dpr_costs, exclude_dpr)
		
		# Block submission on total cost overrun (Requirement 3.3)
		if result.has_errors:
			frappe.throw(
				"<br>".join(result.errors),
				title=_("Cost Validation Failed")
			)
		
		# Show warnings for component overruns (Requirement 3.4)
		if result.has_warnings:
			for warning in result.warnings:
				frappe.msgprint(
					warning,
					title=_("Cost Warning"),
					indicator="orange"
				)
	
	def on_submit(self):
		"""Create accounting entries on submit"""
		self.create_stock_entries()
		self.create_journal_entries()
		self._assert_required_entries_created()
		self.update_boq_item_costs()
		self.update_project_costs()
	
	def on_cancel(self):
		"""Cancel linked accounting entries"""
		self.cancel_stock_entries()
		self.cancel_journal_entries()
		self.update_boq_item_costs()
		self.update_project_costs()
	
	def get_company(self):
		"""Get company from project or default"""
		company = frappe.db.get_value("Project", self.project, "company")
		if not company:
			company = frappe.defaults.get_user_default("Company")
		if not company:
			company = frappe.db.get_single_value("Global Defaults", "default_company")
		return company
	
	def create_stock_entries(self):
		"""Create Stock Entries for materials"""
		if not self.materials:
			return
		
		stock_entry_names = []
		
		for row in self.materials:
			if not row.item_code or not row.qty or flt(row.qty) <= 0:
				continue
			
			if not row.warehouse:
				frappe.msgprint(_("Skipping material {0} - no warehouse specified").format(row.item_code), indicator="orange")
				continue
			
			try:
				se = frappe.new_doc("Stock Entry")
				se.stock_entry_type = "Material Issue"
				se.posting_date = self.date
				se.project = self.project
				se.company = self.get_company()
				
				se.append("items", {
					"item_code": row.item_code,
					"qty": row.qty,
					"s_warehouse": row.warehouse,
					"project": self.project
				})
				
				se.insert()
				se.submit()
				row.db_set("stock_entry", se.name)
				stock_entry_names.append(se.name)
				
			except Exception as e:
				frappe.log_error(f"Error creating Stock Entry for DPR {self.name}, Item {row.item_code}: {str(e)}")
				frappe.msgprint(_("Could not create Stock Entry for {0}: {1}").format(row.item_code, str(e)), indicator="orange")
		
		if stock_entry_names:
			self.db_set("stock_entries", ", ".join(stock_entry_names))

	def create_journal_entries(self):
		"""Create Journal Entries for overheads, expenses, and labour"""
		journal_entry_names = []
		
		# Create JE for labour
		if self.employees and flt(self.labour_cost) > 0:
			je = self._create_labour_journal_entry()
			if je:
				journal_entry_names.append(je)
		
		# Create JE for overheads
		if self.overheads and flt(self.overhead_cost) > 0:
			je = self._create_overhead_journal_entry()
			if je:
				journal_entry_names.append(je)
				for row in self.overheads:
					row.db_set("journal_entry", je)
		
		# Create JE for expenses
		if self.expenses and flt(self.expense_cost) > 0:
			je = self._create_expense_journal_entry()
			if je:
				journal_entry_names.append(je)
				for row in self.expenses:
					row.db_set("journal_entry", je)
		
		if journal_entry_names:
			self.db_set("journal_entries", ", ".join(journal_entry_names))
		
		# Track whether any JE was created (used for submit enforcement)
		self._je_created = bool(journal_entry_names)
	
	def _create_labour_journal_entry(self):
		"""Create Journal Entry for labour costs"""
		if not self.employees or flt(self.labour_cost) <= 0:
			return None
			
		company = self.get_company()
		if not company:
			frappe.msgprint(_("Cannot create Journal Entry - no company found"), indicator="orange")
			return None
			
		settings = frappe.db.get_value("BOQ Settings", company, ["salary_labor_account", "asset_labor_cost_account"], as_dict=True) or {}
		
		debit_account = settings.get("asset_labor_cost_account") #expense
		credit_account = settings.get("salary_labor_account") #liability
		
		if not debit_account or not credit_account:
			frappe.msgprint(_("Cannot create Labour JE - Salary Labour Account or Asset Labour Cost Account not configured in BOQ Settings"), indicator="orange")
			return None
			
		try:
			je = frappe.new_doc("Journal Entry")
			je.voucher_type = "Journal Entry"
			je.posting_date = self.date
			je.company = company
			je.user_remark = f"Labour costs for DPR {self.name}"
			
			cost_center = frappe.db.get_value("Company", company, "cost_center")
			
			# Debit Salary Labour Account (Expense)
			je.append("accounts", {
				"account": debit_account,
				"debit_in_account_currency": flt(self.labour_cost),
				"project": self.project,
				"cost_center": cost_center
			})
			
			# Credit Asset Labour Cost Account (Liability)
			je.append("accounts", {
				"account": credit_account,
				"credit_in_account_currency": flt(self.labour_cost),
				"project": self.project,
				"cost_center": cost_center
			})
			
			je.insert()
			je.submit()
			return je.name
			
		except Exception as e:
			frappe.log_error(f"Error creating Labour JE for DPR {self.name}: {str(e)}")
			frappe.msgprint(_("Could not create Journal Entry for labour: {0}").format(str(e)), indicator="orange")
			return None
	
	def _create_overhead_journal_entry(self):
		"""Create Journal Entry for overhead costs"""
		if not self.overheads or flt(self.overhead_cost) <= 0:
			return None
		
		company = self.get_company()
		if not company:
			frappe.msgprint(_("Cannot create Journal Entry - no company found"), indicator="orange")
			return None
		
		settings = frappe.db.get_value("BOQ Settings", company, ["overhead_account", "expenses_account"], as_dict=True) or {}
		
		# Get payable account from BOQ Settings or Company default
		payable_account = settings.get("overhead_account")
		if not payable_account:
			payable_account = frappe.db.get_value("Company", company, "default_payable_account")
			
		if not payable_account:
			payable_account = frappe.db.get_value(
				"Account",
				{"company": company, "account_type": "Payable", "is_group": 0},
				"name"
			)
		
		if not payable_account:
			frappe.msgprint(_("Cannot create Overhead JE - no payable account found for company {0}").format(company), indicator="orange")
			return None
		
		try:
			je = frappe.new_doc("Journal Entry")
			je.voucher_type = "Journal Entry"
			je.posting_date = self.date
			je.company = company
			je.user_remark = f"Overhead costs for DPR {self.name}"
			
			cost_center = frappe.db.get_value("Company", company, "cost_center")
			
			# Debit entries for each overhead account
			for row in self.overheads:
				target_account = row.account
				if flt(row.amount) > 0 and target_account:
					je.append("accounts", {
						"account": target_account,
						"debit_in_account_currency": flt(row.amount),
						"project": self.project,
						"cost_center": cost_center
					})
			
			# Credit entry to payable account
			je.append("accounts", {
				"account": payable_account,
				"credit_in_account_currency": flt(self.overhead_cost),
				"project": self.project,
				"cost_center": cost_center
			})
			
			je.insert()
			je.submit()
			return je.name
			
		except Exception as e:
			frappe.log_error(f"Error creating Overhead JE for DPR {self.name}: {str(e)}")
			frappe.msgprint(_("Could not create Journal Entry for overheads: {0}").format(str(e)), indicator="orange")
			return None
	
	def _create_expense_journal_entry(self):
		"""Create Journal Entry for expense costs"""
		if not self.expenses or flt(self.expense_cost) <= 0:
			return None
		
		company = self.get_company()
		if not company:
			frappe.msgprint(_("Cannot create Journal Entry - no company found"), indicator="orange")
			return None
		
		settings = frappe.db.get_value("BOQ Settings", company, ["expenses_account"], as_dict=True) or {}
		
		# Get payable account from BOQ Settings or Company default
		payable_account = settings.get("expenses_account")
		if not payable_account:
			payable_account = frappe.db.get_value("Company", company, "default_payable_account")

		if not payable_account:
			payable_account = frappe.db.get_value(
				"Account",
				{"company": company, "account_type": "Payable", "is_group": 0},
				"name"
			)
		
		if not payable_account:
			frappe.msgprint(_("Cannot create Expense JE - no payable account found for company {0}").format(company), indicator="orange")
			return None
		
		# Get default expense account
		default_expense = frappe.db.get_value("Company", company, "default_expense_account")
		if not default_expense:
			default_expense = frappe.db.get_value(
				"Account",
				{"company": company, "account_type": "Expense Account", "is_group": 0},
				"name"
			)
		
		try:
			je = frappe.new_doc("Journal Entry")
			je.voucher_type = "Journal Entry"
			je.posting_date = self.date
			je.company = company
			je.user_remark = f"Expense costs for DPR {self.name}"
			
			cost_center = frappe.db.get_value("Company", company, "cost_center")
			
			# Debit entries for each expense type
			for row in self.expenses:
				if flt(row.amount) > 0:
					expense_account = None
					if row.expense_type:
						expense_account = frappe.db.get_value(
							"Expense Claim Account",
							{"parent": row.expense_type, "company": company},
							"default_account"
						)
					
					if not expense_account:
						expense_account = default_expense
					
					if expense_account:
						je.append("accounts", {
							"account": expense_account,
							"debit_in_account_currency": flt(row.amount),
							"project": self.project,
							"cost_center": cost_center
						})
			
			# Credit entry to payable account
			je.append("accounts", {
				"account": payable_account,
				"credit_in_account_currency": flt(self.expense_cost),
				"project": self.project,
				"cost_center": cost_center
			})
			
			je.insert()
			je.submit()
			return je.name
			
		except Exception as e:
			frappe.log_error(f"Error creating Expense JE for DPR {self.name}: {str(e)}")
			frappe.msgprint(_("Could not create Journal Entry for expenses: {0}").format(str(e)), indicator="orange")
			return None
	
	def cancel_stock_entries(self):
		"""Cancel linked Stock Entries"""
		cancelled_entries = []
		
		# Cancel from comma-separated list in parent
		if self.stock_entries:
			for se_name in self.stock_entries.split(", "):
				se_name = se_name.strip()
				if se_name and frappe.db.exists("Stock Entry", se_name):
					try:
						se = frappe.get_doc("Stock Entry", se_name)
						if se.docstatus == 1:
							se.cancel()
							cancelled_entries.append(se_name)
					except Exception as e:
						frappe.log_error(f"Error cancelling Stock Entry {se_name}: {str(e)}")
						frappe.msgprint(_("Could not cancel Stock Entry {0}: {1}").format(se_name, str(e)), indicator="orange")
		
		# Also cancel from individual material rows
		for row in self.materials or []:
			if row.stock_entry and row.stock_entry not in cancelled_entries:
				se_name = row.stock_entry
				if frappe.db.exists("Stock Entry", se_name):
					try:
						se = frappe.get_doc("Stock Entry", se_name)
						if se.docstatus == 1:
							se.cancel()
							cancelled_entries.append(se_name)
					except Exception as e:
						frappe.log_error(f"Error cancelling Stock Entry {se_name}: {str(e)}")
						frappe.msgprint(_("Could not cancel Stock Entry {0}: {1}").format(se_name, str(e)), indicator="orange")
				# Clear the reference
				row.db_set("stock_entry", None)
		
		# Clear the parent reference
		if self.stock_entries:
			self.db_set("stock_entries", None)
		
		if cancelled_entries:
			frappe.msgprint(_("Cancelled Stock Entries: {0}").format(", ".join(cancelled_entries)), indicator="blue")
		
		if cancelled_entries:
			self._stock_entries_cancelled = True
		return cancelled_entries
	
	def cancel_journal_entries(self):
		"""Cancel linked Journal Entries"""
		cancelled_entries = []
		
		# Cancel from comma-separated list in parent
		if self.journal_entries:
			for je_name in self.journal_entries.split(", "):
				je_name = je_name.strip()
				if je_name and frappe.db.exists("Journal Entry", je_name):
					try:
						je = frappe.get_doc("Journal Entry", je_name)
						if je.docstatus == 1:
							je.cancel()
							cancelled_entries.append(je_name)
					except Exception as e:
						frappe.log_error(f"Error cancelling Journal Entry {je_name}: {str(e)}")
						frappe.msgprint(_("Could not cancel Journal Entry {0}: {1}").format(je_name, str(e)), indicator="orange")
		
		# Also cancel from individual overhead rows
		for row in self.overheads or []:
			if row.journal_entry and row.journal_entry not in cancelled_entries:
				je_name = row.journal_entry
				if frappe.db.exists("Journal Entry", je_name):
					try:
						je = frappe.get_doc("Journal Entry", je_name)
						if je.docstatus == 1:
							je.cancel()
							cancelled_entries.append(je_name)
					except Exception as e:
						frappe.log_error(f"Error cancelling Journal Entry {je_name}: {str(e)}")
						frappe.msgprint(_("Could not cancel Journal Entry {0}: {1}").format(je_name, str(e)), indicator="orange")
				# Clear the reference
				row.db_set("journal_entry", None)
		
		# Also cancel from individual expense rows
		for row in self.expenses or []:
			if row.journal_entry and row.journal_entry not in cancelled_entries:
				je_name = row.journal_entry
				if frappe.db.exists("Journal Entry", je_name):
					try:
						je = frappe.get_doc("Journal Entry", je_name)
						if je.docstatus == 1:
							je.cancel()
							cancelled_entries.append(je_name)
					except Exception as e:
						frappe.log_error(f"Error cancelling Journal Entry {je_name}: {str(e)}")
						frappe.msgprint(_("Could not cancel Journal Entry {0}: {1}").format(je_name, str(e)), indicator="orange")
				# Clear the reference
				row.db_set("journal_entry", None)
		
		# Clear the parent reference
		if self.journal_entries:
			self.db_set("journal_entries", None)
		
		if cancelled_entries:
			frappe.msgprint(_("Cancelled Journal Entries: {0}").format(", ".join(cancelled_entries)), indicator="blue")
		
		if cancelled_entries:
			self._journal_entries_cancelled = True
		return cancelled_entries

	def _assert_required_entries_created(self):
		"""Ensure required accounting docs are created when costs exist."""
		labour_needed = flt(self.labour_cost) > 0
		overhead_needed = flt(self.overhead_cost) > 0
		expense_needed = flt(self.expense_cost) > 0
		material_needed = flt(self.material_cost) > 0
		
		stock_created = bool(self.stock_entries)
		je_created = bool(self.journal_entries) or getattr(self, "_je_created", False)
		
		# If any cost exists but no JE created, block submit
		if (labour_needed or overhead_needed or expense_needed) and not je_created:
			frappe.throw(_("Journal Entries were not created for labour/overhead/expenses. Please try again."))
		
		# If material cost present, ensure stock entry exists
		if material_needed and not stock_created:
			frappe.throw(_("Stock Entries were not created for materials. Please try again."))
	
	def update_boq_item_costs(self):
		"""Update the BOQ Item's cost tracking fields"""
		if not self.boq_item:
			return
		
		try:
			boq_item = frappe.get_doc("BOQ Item", self.boq_item)
			boq_item.calculate_amounts()
			boq_item.db_update()
		except frappe.DoesNotExistError:
			pass
	
	def update_project_costs(self):
		"""Update the Project's estimated cost field with DPR totals"""
		if not self.project:
			return
		
		try:
			# Calculate total DPR costs for this project
			total_dpr_cost = frappe.db.sql("""
				SELECT COALESCE(SUM(total_cost), 0) as total
				FROM `tabDaily Progress Record`
				WHERE project = %s AND docstatus = 1
			""", self.project)[0][0]
			
			# Update project's estimated_costing field
			frappe.db.set_value("Project", self.project, "estimated_costing", flt(total_dpr_cost))
			
		except Exception as e:
			frappe.log_error(f"Error updating project costs for {self.project}: {str(e)}")


def get_asset_hourly_rate(project: str, asset: str, date: str = None) -> float:
	"""Get the hourly rate for an asset in a project"""
	from frappe.utils import today
	
	rate = frappe.db.get_value(
		"Project Asset Billing",
		{
			"project": project,
			"asset": asset,
			"effective_from": ["<=", date or today()]
		},
		"value_per_hour",
		order_by="effective_from desc"
	)
	return flt(rate) if rate else 0


def get_asset_daily_rate(project: str, asset: str, date: str = None) -> float:
	"""Get the daily rate for an asset in a project (backward compatibility)"""
	hourly_rate = get_asset_hourly_rate(project, asset, date)
	return flt(hourly_rate) * 8


def get_employee_daily_rate(employee: str) -> float:
	"""Get the daily rate for an employee based on their Salary Structure Assignment."""
	ssa = frappe.db.get_value(
		"Salary Structure Assignment",
		{"employee": employee, "docstatus": 1},
		["base", "variable"],
		as_dict=True,
		order_by="from_date desc"
	)
	
	if ssa:
		monthly_salary = flt(ssa.base) + flt(ssa.variable)
		return monthly_salary / 30
	
	return 0


def get_item_valuation_rate(item_code: str, warehouse: str = None) -> float:
	"""Get the valuation rate for an item."""
	if warehouse:
		rate = frappe.db.get_value(
			"Bin",
			{"item_code": item_code, "warehouse": warehouse},
			"valuation_rate"
		)
		if rate:
			return flt(rate)
	
	return flt(frappe.db.get_value("Item", item_code, "valuation_rate"))
