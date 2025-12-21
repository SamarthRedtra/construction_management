# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class DailyProgressRecord(Document):
	def validate(self):
		self.validate_boq_item()
		self.fetch_bill_no()
		self.calculate_asset_costs()
		self.calculate_employee_costs()
		self.calculate_material_costs()
		self.calculate_overhead_costs()
		self.calculate_expense_costs()
		self.calculate_total_cost()
	
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
	
	def calculate_asset_costs(self):
		"""Calculate asset costs from child table"""
		total = 0
		for row in self.assets or []:
			# Fetch rate from Project Asset Billing if not set
			if not row.rate_per_day and row.asset:
				row.rate_per_day = get_asset_daily_rate(self.project, row.asset, self.date)
			
			# Calculate amount based on hours (8 hours = full day)
			hours = flt(row.hours) or 8
			row.amount = flt(row.rate_per_day) * (hours / 8)
			total += flt(row.amount)
		
		self.asset_cost = total
	
	def calculate_employee_costs(self):
		"""Calculate employee costs from child table"""
		total = 0
		for row in self.employees or []:
			# Fetch rate from Salary Structure Assignment if not set
			if not row.rate_per_day and row.employee:
				row.rate_per_day = get_employee_daily_rate(row.employee)
			
			# Calculate amount based on hours (8 hours = full day)
			hours = flt(row.hours) or 8
			row.amount = flt(row.rate_per_day) * (hours / 8)
			total += flt(row.amount)
		
		self.labour_cost = total
	
	def calculate_material_costs(self):
		"""Calculate material costs from child table"""
		total = 0
		for row in self.materials or []:
			# Fetch rate from Item if not set
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
	
	def on_submit(self):
		"""Create accounting entries on submit"""
		self.create_stock_entries()
		self.create_journal_entries()
		self.update_boq_item_costs()
	
	def on_cancel(self):
		"""Cancel linked accounting entries"""
		self.cancel_stock_entries()
		self.cancel_journal_entries()
		self.update_boq_item_costs()
	
	def create_stock_entries(self):
		"""Create Stock Entries for materials"""
		if not self.materials:
			return
		
		stock_entry_names = []
		
		for row in self.materials:
			if not row.item_code or not row.qty:
				continue
			
			# Create Material Issue stock entry
			se = frappe.new_doc("Stock Entry")
			se.stock_entry_type = "Material Issue"
			se.posting_date = self.date
			se.project = self.project
			
			se.append("items", {
				"item_code": row.item_code,
				"qty": row.qty,
				"s_warehouse": row.warehouse,
				"project": self.project,
				"boq_item": self.boq_item,
				"bill_no": self.bill_no
			})
			
			try:
				se.insert()
				se.submit()
				row.stock_entry = se.name
				stock_entry_names.append(se.name)
			except Exception as e:
				frappe.log_error(f"Error creating Stock Entry for DPR {self.name}: {str(e)}")
				frappe.msgprint(_("Could not create Stock Entry for {0}: {1}").format(row.item_code, str(e)), indicator="orange")
		
		if stock_entry_names:
			self.stock_entries = ", ".join(stock_entry_names)
			self.db_update()
	
	def create_journal_entries(self):
		"""Create Journal Entries for overheads and expenses"""
		journal_entry_names = []
		
		# Create JE for overheads
		if self.overheads:
			je = self._create_overhead_journal_entry()
			if je:
				journal_entry_names.append(je)
				for row in self.overheads:
					row.journal_entry = je
		
		# Create JE for expenses
		if self.expenses:
			je = self._create_expense_journal_entry()
			if je:
				journal_entry_names.append(je)
				for row in self.expenses:
					row.journal_entry = je
		
		if journal_entry_names:
			self.journal_entries = ", ".join(journal_entry_names)
			self.db_update()
	
	def _create_overhead_journal_entry(self):
		"""Create Journal Entry for overhead costs"""
		if not self.overheads or flt(self.overhead_cost) <= 0:
			return None
		
		company = frappe.db.get_value("Project", self.project, "company")
		if not company:
			company = frappe.defaults.get_user_default("Company")
		
		# Get default payable account
		default_payable = frappe.db.get_value("Company", company, "default_payable_account")
		
		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.posting_date = self.date
		je.company = company
		je.user_remark = f"Overhead costs for DPR {self.name}"
		
		# Debit entries for each overhead account
		for row in self.overheads:
			if flt(row.amount) > 0:
				je.append("accounts", {
					"account": row.account,
					"debit_in_account_currency": flt(row.amount),
					"project": self.project,
					"boq_item": self.boq_item,
					"bill_no": self.bill_no
				})
		
		# Credit entry to payable account
		je.append("accounts", {
			"account": default_payable,
			"credit_in_account_currency": flt(self.overhead_cost),
			"project": self.project
		})
		
		try:
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
		
		company = frappe.db.get_value("Project", self.project, "company")
		if not company:
			company = frappe.defaults.get_user_default("Company")
		
		# Get default payable account
		default_payable = frappe.db.get_value("Company", company, "default_payable_account")
		
		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.posting_date = self.date
		je.company = company
		je.user_remark = f"Expense costs for DPR {self.name}"
		
		# Debit entries for each expense type
		for row in self.expenses:
			if flt(row.amount) > 0:
				# Get expense account from Expense Claim Type
				expense_account = frappe.db.get_value(
					"Expense Claim Account",
					{"parent": row.expense_type, "company": company},
					"default_account"
				)
				if not expense_account:
					# Fallback to a default expense account
					expense_account = frappe.db.get_value("Company", company, "default_expense_account")
				
				if expense_account:
					je.append("accounts", {
						"account": expense_account,
						"debit_in_account_currency": flt(row.amount),
						"project": self.project,
						"boq_item": self.boq_item,
						"bill_no": self.bill_no
					})
		
		# Credit entry to payable account
		je.append("accounts", {
			"account": default_payable,
			"credit_in_account_currency": flt(self.expense_cost),
			"project": self.project
		})
		
		try:
			je.insert()
			je.submit()
			return je.name
		except Exception as e:
			frappe.log_error(f"Error creating Expense JE for DPR {self.name}: {str(e)}")
			frappe.msgprint(_("Could not create Journal Entry for expenses: {0}").format(str(e)), indicator="orange")
			return None
	
	def cancel_stock_entries(self):
		"""Cancel linked Stock Entries"""
		if not self.stock_entries:
			return
		
		for se_name in self.stock_entries.split(", "):
			se_name = se_name.strip()
			if se_name and frappe.db.exists("Stock Entry", se_name):
				try:
					se = frappe.get_doc("Stock Entry", se_name)
					if se.docstatus == 1:
						se.cancel()
				except Exception as e:
					frappe.log_error(f"Error cancelling Stock Entry {se_name}: {str(e)}")
	
	def cancel_journal_entries(self):
		"""Cancel linked Journal Entries"""
		if not self.journal_entries:
			return
		
		for je_name in self.journal_entries.split(", "):
			je_name = je_name.strip()
			if je_name and frappe.db.exists("Journal Entry", je_name):
				try:
					je = frappe.get_doc("Journal Entry", je_name)
					if je.docstatus == 1:
						je.cancel()
				except Exception as e:
					frappe.log_error(f"Error cancelling Journal Entry {je_name}: {str(e)}")
	
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


def get_asset_daily_rate(project: str, asset: str, date: str = None) -> float:
	"""Get the daily rate for an asset in a project"""
	from construction_management.construction_management.doctype.project_asset_billing.project_asset_billing import get_asset_daily_rate as _get_rate
	return _get_rate(project, asset, date)


def get_employee_daily_rate(employee: str) -> float:
	"""
	Get the daily rate for an employee based on their Salary Structure Assignment.
	
	Args:
		employee: Employee name
		
	Returns:
		Daily rate (monthly salary / 30)
	"""
	# Get active salary structure assignment
	ssa = frappe.db.get_value(
		"Salary Structure Assignment",
		{
			"employee": employee,
			"docstatus": 1
		},
		["base", "variable"],
		as_dict=True,
		order_by="from_date desc"
	)
	
	if ssa:
		monthly_salary = flt(ssa.base) + flt(ssa.variable)
		return monthly_salary / 30  # Daily rate
	
	return 0


def get_item_valuation_rate(item_code: str, warehouse: str = None) -> float:
	"""
	Get the valuation rate for an item.
	
	Args:
		item_code: Item code
		warehouse: Warehouse (optional)
		
	Returns:
		Valuation rate
	"""
	if warehouse:
		rate = frappe.db.get_value(
			"Bin",
			{"item_code": item_code, "warehouse": warehouse},
			"valuation_rate"
		)
		if rate:
			return flt(rate)
	
	# Fallback to item's valuation rate
	return flt(frappe.db.get_value("Item", item_code, "valuation_rate"))
