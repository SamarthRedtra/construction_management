# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt, today
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice


class SalesInvoiceOverride(SalesInvoice):
	def validate(self):
		super().validate()
		if self.project and not self.custom_is_advanced and self.is_bill_invoice() and self.docstatus == 0:
			self.apply_automatic_deductions()


	def is_bill_invoice(self):
		is_bill_invoice = False
		for item in self.items:
			if item.get("boq_item"):
				is_bill_invoice = True
				break
		return is_bill_invoice

	def before_insert(self):
		"""Auto-set BOQ dimensions on Sales Invoice Items"""
		for item in self.items:
			if item.get("boq_item"):
				# Fetch BOQ Item details
				boq_item = frappe.get_doc("BOQ Item", item.boq_item)
				
				# Set dimensions
				item.bill_no = boq_item.parent_bill
				
				# Ensure boq_item is set (it should already be)
				if not item.boq_item:
					item.boq_item = boq_item.name

	def on_submit(self):
		super().on_submit()
		"""Create ledger entries for BOQ items on invoice submit"""
		
		# Calculate totals for distribution
		total_boq_amount = 0
		total_variance = 0
		
		# Fetch settings safely
		variance_item_code = None
		if frappe.db.exists("BOQ Settings", self.company):
			variance_item_code = frappe.db.get_value("BOQ Settings", self.company, "varience_item")
			
		for item in self.items:
			if item.get("boq_item"):
				total_boq_amount += flt(item.amount)
				
			# Check only for Variance for BOQ Ledger Impact
			is_variance = variance_item_code and item.item_code == variance_item_code
			
			if is_variance:
				total_variance += flt(item.amount) # Variance is negative
				
		for item in self.items:
			if item.get("boq_item"):
				net_amount = flt(item.amount)
				if total_boq_amount > 0 and total_variance != 0:
					# Distribute variance proportionally
					share = flt(item.amount) / total_boq_amount
					allocated_variance = total_variance * share
					net_amount = flt(item.amount) + allocated_variance # + because variance is negative
					
				create_boq_ledger_entry(self, item, net_amount=net_amount)
				update_boq_item_after_invoice(item.boq_item)
		
		# Update project completion percentage
		if self.project:
			from construction_management.api.project_completion import update_project_completion
			try:
				update_project_completion(self.project)
			except Exception as e:
				frappe.log_error(f"Error updating project completion: {str(e)}")

	def on_cancel(self):
		super().on_cancel()
		"""Create reversing ledger entries on invoice cancel"""
		for item in self.items:
			if item.get("boq_item"):
				create_boq_reversal_entry(self, item)
				update_boq_item_after_invoice(item.boq_item)
		
		# Update project completion percentage
		if self.project:
			from construction_management.api.project_completion import update_project_completion
			try:
				update_project_completion(self.project)
			except Exception as e:
				frappe.log_error(f"Error updating project completion: {str(e)}")

	def on_update(self):
		"""Handle status changes on update"""
		if self.get("custom_is_advanced") and self.status == "Paid" and self.docstatus == 1:
			create_boq_advance_payment_from_invoice(self)

	def apply_automatic_deductions(self):
		"""Automatically apply retention and advance deductions if enabled"""
		from construction_management.api.boq_invoice import get_deduction_details, get_or_create_retention_item, get_or_create_advance_item
		
		details = get_deduction_details(self.project, self.items, invoice_name=self.name)
		
		if not details.get("enable_progressive_boq"):
			return
			
		# Common defaults for deduction items
		default_income_account = frappe.db.get_value("Company", self.company, "default_income_account")
		default_cost_center = frappe.db.get_value("Company", self.company, "cost_center")
		
		# 1. Handle Retention Deduction
		if details.get("suggested_retention") > 0:
			retention_item = "RETENTION-DEDUCTION"
			get_or_create_retention_item() # Ensure it exists
			
			# Find existing or add new
			found = False
			for item in self.items:
				if item.item_code == retention_item:
					item.rate = -flt(details["suggested_retention"])
					item.amount = -flt(details["suggested_retention"])
					item.qty = 1
					item.description = f"Retention deduction ({details['retention_percentage']}%)"
					item.project = self.project
					found = True
					break
			
			if not found:
				self.append("items", {
					"item_code": retention_item,
					"qty": 1,
					"rate": -flt(details["suggested_retention"]),
					"amount": -flt(details["suggested_retention"]),
					"description": f"Retention deduction ({details['retention_percentage']}%)",
					"project": self.project,
					"income_account": default_income_account,
					"cost_center": default_cost_center,
					"uom": "Nos",
					"conversion_factor": 1.0,
					"item_name": "Retention Deduction"
				})

		# 2. Advance Deduction
		if details.get("suggested_advance") > 0:
			advance_item = "ADVANCE-DEDUCTION"
			get_or_create_advance_item()
			
			# Find existing or add new
			found = False
			for item in self.items:
				if item.item_code == advance_item:
					item.rate = -flt(details["suggested_advance"])
					item.amount = -flt(details["suggested_advance"])
					item.qty = 1
					item.description = "Deduction from advance payment"
					item.project = self.project
					found = True
					break
			
			if not found:
				self.append("items", {
					"item_code": advance_item,
					"qty": 1,
					"rate": -flt(details["suggested_advance"]),
					"amount": -flt(details["suggested_advance"]),
					"description": "Deduction from advance payment",
					"project": self.project,
					"income_account": default_income_account,
					"cost_center": default_cost_center,
					"uom": "Nos",
					"conversion_factor": 1.0,
					"item_name": "Advance Deduction"
				})

		# Recalculate totals to handle the new items
		self.run_method("calculate_taxes_and_totals")

	def get_gl_entries(self, warehouse_account=None):
		gl_entries = super().get_gl_entries(warehouse_account)

		# Fetch BOQ Settings for the company
		boq_settings = frappe.get_doc("BOQ Settings", self.company)
		retention_account = boq_settings.retention_account
		advance_account = boq_settings.advance_account
		variance_account = boq_settings.varience_account_debit
		variance_item_code = boq_settings.varience_item

		if not (retention_account or advance_account or variance_account):
			return gl_entries

		# Identify which items were handled by super (usually they are merged into one Sales/Income credit)
		total_retention = 0
		total_advance = 0
		total_variance = 0
		
		for item in self.items:
			if item.item_code == "RETENTION-DEDUCTION" and retention_account:
				total_retention += abs(flt(item.base_amount))
			elif item.item_code == "ADVANCE-DEDUCTION" and advance_account:
				total_advance += abs(flt(item.base_amount))
			elif variance_item_code and item.item_code == variance_item_code and variance_account:
				total_variance += abs(flt(item.base_amount))

		if total_retention == 0 and total_advance == 0 and total_variance == 0:
			return gl_entries

		# Find and consolidate all income/sales entries for this project
		default_income_account = frappe.db.get_value("Company", self.company, "default_income_account")

		# 1. Separate income entries from others
		other_entries = []
		income_net_credit = 0
		income_entry_template = None

		for entry in gl_entries:
			if entry.get("account") == default_income_account and entry.get("project") == self.project:
				income_net_credit += flt(entry.get("credit")) - flt(entry.get("debit"))
				if not income_entry_template:
					income_entry_template = entry
			else:
				other_entries.append(entry)

		if not income_entry_template:
			# If no income entry found (e.g. all items were deductions?), 
			# we might need to create one, but usually there's at least one BOQ item.
			return gl_entries

		# 2. Create the consolidated Gross Credit entry
		gross_credit = income_net_credit + total_retention + total_advance + total_variance
		income_entry_template.update({
			"credit": gross_credit,
			"debit": 0
		})
		
		new_entries = [income_entry_template] + other_entries

		# 3. Add separate entries for deductions (Debit specific accounts)
		def add_party_if_needed(gl_dict, account):
			acc_type = frappe.db.get_value("Account", account, "account_type")
			if acc_type in ["Receivable", "Payable"]:
				gl_dict.update({
					"party_type": "Customer",
					"party": self.customer
				})
			return gl_dict

		if total_retention > 0 and retention_account:
			new_entries.append(self.get_gl_dict(add_party_if_needed({
				"account": retention_account,
				"debit": total_retention,
				"credit": 0,
				"project": self.project,
				"against": self.customer,
				"cost_center": self.cost_center,
				"remarks": f"Retention deduction for {self.name}"
			}, retention_account)))
		
		if total_advance > 0 and advance_account:
			new_entries.append(self.get_gl_dict(add_party_if_needed({
				"account": advance_account,
				"debit": total_advance,
				"credit": 0,
				"project": self.project,
				"against": self.customer,
				"cost_center": self.cost_center,
				"remarks": f"Advance deduction for {self.name}"
			}, advance_account)))

		if total_variance > 0 and variance_account:
			new_entries.append(self.get_gl_dict(add_party_if_needed({
				"account": variance_account,
				"debit": total_variance,
				"credit": 0,
				"project": self.project,
				"against": self.customer,
				"cost_center": self.cost_center,
				"remarks": f"Variance for {self.name}"
			}, variance_account)))

		return new_entries



def create_boq_advance_payment_from_invoice(invoice):
	"""Automatically create BOQ Advance Payment record from a Paid Advance Invoice"""
	# Check if already exists to avoid duplication
	if frappe.db.exists("BOQ Advance Payment", {"linked_invoice": invoice.name, "docstatus": ["!=", 2]}):
		return

	adv = frappe.new_doc("BOQ Advance Payment")
	adv.project = invoice.project
	adv.amount = invoice.net_total
	adv.linked_invoice = invoice.name
	adv.date = invoice.posting_date
	adv.remarks = f"Automatically created from Advance Invoice {invoice.name}"
	
	adv.flags.ignore_permissions = True
	adv.insert()
	adv.submit()
	frappe.msgprint(_("BOQ Advance Payment {0} created automatically.").format(adv.name))
	frappe.db.commit()


def create_boq_ledger_entry(invoice, item, net_amount=None):
	"""
	Create or Update a BOQ Progress Ledger entry for an invoice item.
	Updates existing PC/PI ledger entry if found to maintain single-row-per-cycle.
	"""
	from construction_management.api.boq_ledger import create_ledger_entry, recalculate_ledger_for_item
	
	boq_item = item.boq_item
	amount_to_book = net_amount if net_amount is not None else flt(item.amount)
	
	# Try to find an existing ledger entry to update
	ledger_entry = None
	if invoice.custom_payment_certificate:
		ledger_entry = frappe.db.get_value("BOQ Progress Ledger", {
			"payment_certificate": invoice.custom_payment_certificate,
			"boq_item": boq_item,
		}, "name")
	
	if not ledger_entry and invoice.get("custom_proforma_invoice"):
		ledger_entry = frappe.db.get_value("BOQ Progress Ledger", {
			"proforma_invoice": invoice.custom_proforma_invoice,
			"boq_item": boq_item,
		}, "name")

	if not ledger_entry and item.get("sales_order"):
		ledger_entry = frappe.db.get_value("BOQ Progress Ledger", {
			"boq_item": boq_item,
			"reference_doctype": "Sales Order",
			"reference_name": item.sales_order
		}, "name")
		
	if ledger_entry:
		# Update existing entry with Tax Invoice details
		frappe.db.set_value(
			"BOQ Progress Ledger",
			ledger_entry,
			{
				"tax_invoice": invoice.name,
				"tax_invoice_amount": flt(amount_to_book),
				"source": "Invoice",
				"amount": flt(amount_to_book)
			},
			update_modified=False
		)
		
		recalculate_ledger_for_item(boq_item)
		return

	if invoice.custom_payment_certificate or invoice.get("custom_proforma_invoice") or any(it.get("sales_order") for it in invoice.items):
		frappe.logger().warning(
			f"Missing ledger row for BOQ Item {boq_item} on invoice {invoice.name}; skipping creation to avoid duplication."
		)
		return
	
	existing = frappe.db.get_value(
		"BOQ Progress Ledger",
		{
			"boq_item": boq_item,
			"reference_doctype": "Sales Invoice",
			"reference_name": invoice.name
		},
		"name"
	)
	if existing:
		return
	
	create_ledger_entry(
		boq_item=boq_item,
		qty=flt(item.qty),
		amount=flt(amount_to_book),
		source="Invoice",
		reference_doctype="Sales Invoice",
		reference_name=invoice.name,
		posting_date=invoice.posting_date or today(),
		remarks=f"Invoice {invoice.name}",
		tax_invoice=invoice.name,
		tax_invoice_amount=flt(amount_to_book)
	)
	
	recalculate_ledger_for_item(boq_item)


def create_boq_reversal_entry(invoice, item):
	"""
	Undo Tax Invoice impact on the existing BOQ Progress Ledger row.
	"""
	from construction_management.api.boq_ledger import recalculate_ledger_for_item
	
	boq_item = item.boq_item
	is_orphan = not invoice.custom_payment_certificate and not invoice.get("custom_proforma_invoice")
	
	ledger_entry = None
	if invoice.custom_payment_certificate:
		ledger_entry = frappe.db.get_value(
			"BOQ Progress Ledger",
			{
				"boq_item": boq_item,
				"payment_certificate": invoice.custom_payment_certificate
			},
			"name"
		)
	
	if not ledger_entry and invoice.get("custom_proforma_invoice"):
		ledger_entry = frappe.db.get_value(
			"BOQ Progress Ledger",
			{
				"boq_item": boq_item,
				"proforma_invoice": invoice.custom_proforma_invoice
			},
			"name"
		)
	
	if not ledger_entry and item.get("sales_order"):
		ledger_entry = frappe.db.get_value(
			"BOQ Progress Ledger",
			{
				"boq_item": boq_item,
				"reference_doctype": "Sales Order",
				"reference_name": item.sales_order
			},
			"name"
		)
	
	if not ledger_entry:
		ledger_entry = frappe.db.get_value(
			"BOQ Progress Ledger",
			{
				"boq_item": boq_item,
				"tax_invoice": invoice.name
			},
			"name"
		)
	
	if ledger_entry:
		if is_orphan:
			frappe.flags.allow_boq_ledger_deletion = True
			try:
				frappe.delete_doc("BOQ Progress Ledger", ledger_entry, force=1, ignore_permissions=True)
			finally:
				frappe.flags.allow_boq_ledger_deletion = False
		else:
			frappe.db.set_value(
				"BOQ Progress Ledger",
				ledger_entry,
				{
					"tax_invoice": None,
					"tax_invoice_amount": 0,
					"remarks": f"Reversal of Invoice {invoice.name}",
					"source": "Order" if item.get("sales_order") else ("Proforma" if invoice.get("custom_proforma_invoice") else "Adjustment")
				},
				update_modified=False
			)
		
		recalculate_ledger_for_item(boq_item)


def update_boq_item_after_invoice(boq_item_name):
	"""
	Update BOQ Item calculated fields after invoice submit/cancel.
	"""
	boq_item = frappe.get_doc("BOQ Item", boq_item_name)
	boq_item.current_qty = 0
	boq_item.calculate_amounts()
	boq_item.update_billing_status()
	boq_item.db_update()
	
	if boq_item.parent_bill:
		bill = frappe.get_doc("BOQ Bill", boq_item.parent_bill)
		bill.calculate_totals()
		bill.db_update()
	
	if boq_item.project_boq:
		project_boq = frappe.get_doc("Project BOQ", boq_item.project_boq)
		project_boq.calculate_totals()
		project_boq.db_update()
