# Copyright (c) 2024, Construction Management
# License: MIT

"""
Payment Certificate DocType Controller
Manages proforma to tax invoice workflow with customer approval.
(Tasks 9.1-9.10: Payment Certificate Workflow)
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today
from erpnext.controllers.accounts_controller import get_default_taxes_and_charges


class PaymentCertificate(Document):
	def validate(self):
		if not self.get("company") and self.get("project"):
			self.company = frappe.db.get_value("Project", self.project, "company")
		
		self.calculate_totals()
		self.calculate_retention()
		self.validate_type_based_fields()
		self.validate_sales_order()
		self.validate_purchase_receipt()
		self.calculate_variance()
		self.validate_duplicate()
		self.validate_amounts()
	
	def calculate_totals(self):
		"""Calculate totals from child table if items present"""
		if not self.get("items"):
			self.total_advance_deducted = 0
			self._apply_discount_and_taxes()
			return

		total_advance = 0
		total_proforma = 0
		total_accepted = 0
		
		for item in self.get("items") or []:
			item.amount = flt(item.qty) * flt(item.rate)
			
			# Ensure accepted_amount is initialized if zero and newly added
			if not item.accepted_amount and flt(item.qty) > 0:
				item.accepted_amount = item.amount
				
			item.variance = flt(item.amount) - flt(item.accepted_amount)
			
			total_proforma += flt(item.amount)
			total_accepted += flt(item.accepted_amount)
			total_advance += abs(flt(item.get("advance_amount")))
			
		self.proforma_amount = total_proforma
		self.accepted_amount = total_accepted

		self.total_advance_deducted = total_advance
		self._apply_discount_and_taxes()

	def _get_additional_discount(self, base_amount: float) -> float:
		"""Calculate additional discount based on type and base amount."""
		discount_type = (self.discount_type or "").strip()
		discount_amount = 0
		if discount_type == "Percentage":
			discount_amount = flt(base_amount) * flt(self.percentage) / 100.0
		elif discount_type == "Amount":
			discount_amount = flt(self.discount_amount)
		
		# Clamp discount to valid range
		discount_amount = max(0, min(flt(base_amount), flt(discount_amount)))
		return discount_amount

	def _map_discount_apply_on(self) -> str:
		"""Map PC discount apply-on values to Invoice choices."""
		value = (self.get("select_discount_on") or "").strip()
		mapping = {
			"On Net Total": "Net Total",
			"On Grand Total": "Grand Total",
			"Net Total": "Net Total",
			"Grand Total": "Grand Total",
		}
		return mapping.get(value, "")

	def _apply_discount_and_taxes(self):
		"""Compute taxes and grand total without discount."""
		net_total = flt(self.accepted_amount)
		self.discount_amount = 0
		self.calculate_taxes(net_total)
		self.grand_total = flt(net_total) + flt(self.get("total_taxes_and_charges") or 0)

	def calculate_taxes(self, net_total: float | None = None):
		"""Calculate taxes from taxes table"""
		base = flt(net_total) if net_total is not None else flt(self.accepted_amount)
		total_taxes = 0
		for tax in self.get("taxes") or []:
			if tax.charge_type == "On Net Total":
				tax.tax_amount = flt(base) * flt(tax.rate) / 100.0
			
			total_taxes += flt(tax.tax_amount)
		
		self.total_taxes_and_charges = total_taxes

	def calculate_retention(self):
		"""Calculate retention amount from BOQ Settings if not manually set"""
		if self.type != "Sales" or not self.project:
			return
			
		company = frappe.db.get_value("Project", self.project, "company")
		if not company:
			return
			
		# Fetch retention % from BOQ Settings if not already set
		if not self.retention_percentage:
			ret_percentage = frappe.db.get_value("BOQ Settings", company, "default_retention_percentage")
			if ret_percentage:
				self.retention_percentage = flt(ret_percentage)
		
		# Calculate amount
		if self.retention_percentage:
			self.retention_amount = flt(self.accepted_amount) * (flt(self.retention_percentage) / 100.0)
	
	def validate_type_based_fields(self):
		"""
		Validate required fields based on type (Sales/Purchase).
		Property 7: Type-Based Field Validation
		Requirements: 7.2, 7.3
		"""
		if self.type == "Sales":
			if not self.customer:
				# Try to fetch from project
				self.customer = frappe.db.get_value("Project", self.project, "customer")
			if not self.customer:
				frappe.throw(_("Customer is required for Sales type Payment Certificate"))
		
		elif self.type == "Purchase":
			if not self.supplier:
				frappe.throw(_("Supplier is required for Purchase type Payment Certificate"))
			if not self.purchase_receipt:
				frappe.throw(_("Purchase Receipt is required for Purchase type Payment Certificate"))
	
	def validate_amounts(self):
		"""Validate accepted amount is positive"""
		if flt(self.accepted_amount) <= 0:
			frappe.throw(_("Accepted Amount must be greater than zero"))
	
	def validate_sales_order(self):
		"""Validate Sales Order exists and is submitted (Sales type only)"""
		if self.type != "Sales" or not self.sales_order:
			return
			
		so = frappe.db.get_value(
			"Sales Order", 
			self.sales_order, 
			["docstatus", "base_grand_total", "customer", "project"],
			as_dict=True
		)
		
		if not so:
			frappe.throw(_("Sales Order {0} not found").format(self.sales_order))
		
		# SO should be submitted (docstatus = 1)
		if so.docstatus != 1:
			frappe.throw(_("Sales Order must be submitted"))
		
		# Set proforma amount from SO if not set (use total amount)
		# Only fallback if items table is empty
		if not self.get("items") and not self.proforma_amount:
			self.proforma_amount = flt(so.base_grand_total)
		
		# Auto-populate accepted_amount if not set
		if not self.accepted_amount:
			self.accepted_amount = flt(self.proforma_amount)
		
		# Auto-populate customer from SO if not set
		if not self.customer and so.customer:
			self.customer = so.customer
		
		# Auto-populate project from SO if not set
		if not self.project and so.project:
			self.project = so.project
	
	def validate_purchase_receipt(self):
		"""Validate purchase receipt exists (Purchase type only)"""
		if self.type != "Purchase" or not self.purchase_receipt:
			return
		
		pr = frappe.db.get_value(
			"Purchase Receipt",
			self.purchase_receipt,
			["docstatus", "grand_total", "supplier"],
			as_dict=True
		)
		
		if not pr:
			frappe.throw(_("Purchase Receipt {0} not found").format(self.purchase_receipt))
		
		# PR should be submitted
		if pr.docstatus != 1:
			frappe.throw(_("Purchase Receipt must be submitted"))
		
		# Set PR amount if not set
		if not self.pr_amount:
			self.pr_amount = flt(pr.grand_total)
		
		# Set supplier from PR if not set
		if not self.supplier:
			self.supplier = pr.supplier
	
	def calculate_variance(self):
		"""
		Calculate variance between original and accepted amounts.
		For Sales: Proforma Amount - Accepted Amount
		For Purchase: PR Amount - Accepted Amount
		(Property 13: Variance Calculation)
		"""
		if self.get("items"):
			self.calculate_totals()
			
		original_amount = flt(self.proforma_amount) if self.type == "Sales" else flt(self.pr_amount)
		self.variance = original_amount - flt(self.accepted_amount)
		
		if original_amount > 0:
			self.variance_percent = (flt(self.variance) / original_amount) * 100
		else:
			self.variance_percent = 0
	
	def validate_duplicate(self):
		"""Prevent creating multiple Payment Certificates for same proforma/PR"""
		if self.type == "Sales" and self.sales_order:
			existing = frappe.db.exists(
				"Payment Certificate",
				{
					"sales_order": self.sales_order,
					"docstatus": ["!=", 2],
					"name": ["!=", self.name]
				}
			)
			if existing:
				frappe.throw(
					_("Payment Certificate {0} already exists for Sales Order {1}").format(
						existing, self.sales_order
					)
				)
		
		elif self.type == "Purchase" and self.purchase_receipt:
			existing = frappe.db.exists(
				"Payment Certificate",
				{
					"purchase_receipt": self.purchase_receipt,
					"docstatus": ["!=", 2],
					"name": ["!=", self.name]
				}
			)
			if existing:
				frappe.throw(
					_("Payment Certificate {0} already exists for Purchase Receipt {1}").format(
						existing, self.purchase_receipt
					)
				)
	
	def on_submit(self):
		"""
		On submit:
		For Sales type:
		1. Create Tax Invoice with accepted amount
		2. Update BOQ Progress Ledger
		3. Close Sales Order with comment
		"""
		self.status = "Submitted"
		
		if self.type == "Sales":
			self.create_tax_invoice()
			self.update_boq_progress_ledger()
			self.close_sales_order()
		else:  # Purchase
			self.create_purchase_invoice()
			self.update_boq_progress_ledger()
		
		self.db_set("status", "Invoiced")
	
	def on_cancel(self):
		"""Cancel linked invoice if not paid"""
		self.db_set("status", "Cancelled")
		
		if self.type == "Sales" and self.tax_invoice and not self.flags.ignore_sales_invoice_cancel:
			tax_inv = frappe.get_doc("Sales Invoice", self.tax_invoice)
			if tax_inv.docstatus == 1:
				# Allow cancel even if linked
				tax_inv.flags.ignore_payment_certificate_cancel = True
				tax_inv.cancel()
				frappe.msgprint(_("Tax Invoice {0} cancelled").format(self.tax_invoice))
		
		elif self.type == "Purchase" and self.purchase_invoice:
			pi = frappe.get_doc("Purchase Invoice", self.purchase_invoice)
			if pi.docstatus == 1 and flt(pi.outstanding_amount) == flt(pi.grand_total):
				# Only cancel if no payment made
				pi.cancel()
				frappe.msgprint(_("Purchase Invoice {0} cancelled").format(self.purchase_invoice))
			elif flt(pi.outstanding_amount) < flt(pi.grand_total):
				frappe.throw(_("Cannot cancel - Purchase Invoice has payments made"))
		
		# Roll back BOQ ledger values linked to this Payment Certificate
		self.revert_boq_progress_ledger()
	
	def create_tax_invoice(self):
		"""
		Create final Tax Invoice with accepted amount.
		Supports multiple items and maps Sales Order references per item.
		"""
		if not self.customer:
			self.customer = frappe.db.get_value("Project", self.project, "customer")
		
		if not self.customer:
			frappe.throw(_("Project {0} must have a Customer assigned").format(self.project))
		
		# Get company from project or default
		company = frappe.db.get_value("Project", self.project, "company")
		if not company:
			company = frappe.defaults.get_user_default("Company")
		
		# Get default income account and retention account
		settings = frappe.get_doc("BOQ Settings", company)
		income_account = frappe.db.get_value("Company", company, "default_income_account")
		retention_account = settings.retention_account
		
		# Create invoice
		invoice = frappe.new_doc("Sales Invoice")
		invoice.customer = self.customer
		invoice.company = company
		invoice.project = self.project
		invoice.posting_date = self.posting_date or today()
		invoice.due_date = self.posting_date or today()
		invoice.custom_payment_certificate = self.name
		invoice.custom_sales_order = self.sales_order
		invoice.custom_is_proforma = 0  # This is a final tax invoice
		invoice.cost_center = frappe.db.get_value("Company", company, "cost_center")
		
		# Set retention fields on invoice
		if hasattr(invoice, "custom_retention_amount"):
			invoice.custom_retention_amount = flt(self.retention_amount)
			invoice.custom_retention_percentage = flt(self.retention_percentage)
			invoice.custom_retention_account = retention_account
		
		# Add items from PC items table with per-item deductions
		from construction_management.api.boq_invoice import get_deduction_details, get_or_create_retention_item, get_or_create_advance_item
		
		# Get deduction settings for the project
		deduction_details = get_deduction_details(self.project, self.items, invoice_name=None)
		suggested_retention = flt(deduction_details.get("suggested_retention"))
		suggested_advance = flt(deduction_details.get("suggested_advance"))
		
		total_proforma = flt(self.proforma_amount)
		total_accepted = flt(self.accepted_amount)
		
		variance_item_code = settings.varience_item
		retention_item_code = "RETENTION-DEDUCTION"
		advance_item_code = "ADVANCE-DEDUCTION"
		
		get_or_create_retention_item()
		get_or_create_advance_item()

		if self.get("items"):
			for pc_item in self.items:
				# 1. Main BOQ Item line
				invoice.append("items", {
					"item_code": frappe.db.get_value("BOQ Item", pc_item.boq_item, "item_code") or "Service",
					"description": pc_item.description,
					"qty": pc_item.qty,
					"rate": pc_item.rate,
					"amount": flt(pc_item.qty) * flt(pc_item.rate),
					"income_account": income_account,
					"project": self.project,
					"boq_item": pc_item.boq_item,
					"bill_no": pc_item.bill_no,
					"sales_order": self.sales_order,
					"so_detail": pc_item.sales_order_item,
					"cost_center": invoice.cost_center
				})
				
				# 2. Per-item Variance Deduction
				item_variance = flt(pc_item.amount) - flt(pc_item.accepted_amount)
				if item_variance > 0:
					if not variance_item_code:
						frappe.throw(_("Please set 'Varience Deduction Item' in BOQ Settings matching company {0}").format(company))
					
					invoice.append("items", {
						"item_code": variance_item_code,
						"item_name": "Variance Deduction",
						"description": f"Variance adjustment for: {pc_item.description or pc_item.boq_item}",
						"qty": 1,
						"rate": -item_variance,
						"amount": -item_variance,
						"income_account": income_account,
						"project": self.project,
						"boq_item": pc_item.boq_item,
						"bill_no": pc_item.bill_no,
						"cost_center": invoice.cost_center
					})
				
				# 3. Per-item Retention Deduction
				if suggested_retention > 0 and total_proforma > 0:
					share = flt(pc_item.amount) / total_proforma
					item_retention = flt(suggested_retention * share, 2)
					if item_retention > 0:
						invoice.append("items", {
							"item_code": retention_item_code,
							"item_name": "Retention Deduction",
							"description": f"Retention deduction ({deduction_details['retention_percentage']}%) for: {pc_item.description or pc_item.boq_item}",
							"qty": 1,
							"rate": -item_retention,
							"amount": -item_retention,
							"income_account": income_account,
							"project": self.project,
							"boq_item": pc_item.boq_item,
							"bill_no": pc_item.bill_no,
							"cost_center": invoice.cost_center
						})

				# 4. Per-item Advance Deduction
				if suggested_advance > 0 and total_accepted > 0:
					share = flt(pc_item.accepted_amount) / total_accepted
					item_advance = flt(suggested_advance * share, 2)
					if item_advance > 0:
						invoice.append("items", {
							"item_code": advance_item_code,
							"item_name": "Advance Deduction",
							"description": f"Deduction from advance payment for: {pc_item.description or pc_item.boq_item}",
							"qty": 1,
							"rate": -item_advance,
							"amount": -item_advance,
							"income_account": income_account,
							"project": self.project,
							"boq_item": pc_item.boq_item,
							"bill_no": pc_item.bill_no,
							"cost_center": invoice.cost_center
						})
		
		# Populate taxes from Payment Certificate or Defaults
		if self.get("taxes_and_charges"):
			invoice.taxes_and_charges = self.taxes_and_charges
		
		if self.get("taxes"):
			for tax in self.get("taxes"):
				invoice.append("taxes", {
					"charge_type": tax.charge_type,
					"account_head": tax.account_head,
					"description": tax.description,
					"rate": tax.rate,
					"tax_amount": tax.tax_amount,
					"cost_center": tax.cost_center or invoice.cost_center,
					"included_in_print_rate": tax.included_in_print_rate
				})
		
		# If no taxes on invoice yet, try default taxes
		if not invoice.get("taxes") and not invoice.get("taxes_and_charges"):
			default_tax = get_default_taxes_and_charges("Sales Taxes and Charges Template", company=company)
			if default_tax and default_tax.get("taxes_and_charges"):
				invoice.taxes_and_charges = default_tax["taxes_and_charges"]
				if not invoice.get("taxes"):
					for tax in default_tax.get("taxes", []):
						invoice.append("taxes", tax)
		
		if not invoice.get("taxes") and not invoice.get("taxes_and_charges"):
			invoice.run_method("set_taxes_and_charges")
   
		mapped_apply_on = self._map_discount_apply_on()
		if self.discount_type and mapped_apply_on and (self.discount_amount or self.percentage):
			invoice.apply_discount_on = mapped_apply_on
			invoice.additional_discount_percentage = self.percentage
			invoice.additional_discount_amount = self.discount_amount
			invoice.run_method("apply_discount_and_taxes")

		invoice.run_method("calculate_taxes_and_totals")
		# invoice.run_method("calculate_taxes_and_totals")
		invoice.flags.ignore_permissions = True
		invoice.insert()
		invoice.submit()
		
		self.db_set({
			"tax_invoice": invoice.name,
			"tax_invoice_amount": invoice.grand_total,
			"invoice_status": "Submitted"
		})
		
		frappe.msgprint(_("Tax Invoice {0} created with amount {1}").format(
			invoice.name, invoice.grand_total
		))
		
		return invoice.name
	
	def create_purchase_invoice(self):
		"""
		Create Purchase Invoice with accepted amount for Purchase type PC.
		"""
		if not self.supplier:
			frappe.throw(_("Supplier is required to create Purchase Invoice"))
		
		# Get company from project or default
		company = frappe.db.get_value("Project", self.project, "company")
		if not company:
			company = frappe.defaults.get_user_default("Company")
		
		# Get default expense account
		expense_account = frappe.db.get_value("Company", company, "default_expense_account")
		
		# Create Purchase Invoice
		pi = frappe.new_doc("Purchase Invoice")
		pi.supplier = self.supplier
		pi.company = company
		pi.project = self.project
		pi.posting_date = self.posting_date or today()
		pi.due_date = self.posting_date or today()
		pi.bill_no = self.name  # Reference to Payment Certificate
		
		if self.purchase_receipt:
			pi.purchase_receipt = self.purchase_receipt
		
		if self.purchase_order:
			pi.purchase_order = self.purchase_order
		
		# Get item description
		item_desc = "Purchase Payment Certificate"
		if self.boq_item:
			item_desc = frappe.db.get_value("BOQ Item", self.boq_item, "description") or item_desc
		elif self.bill_no:
			item_desc = frappe.db.get_value("BOQ Bill", self.bill_no, "description") or f"Bill: {self.bill_no}"
		
		# Add main item with PR amount
		pi.append("items", {
			"item_name": item_desc[:140],
			"description": item_desc,
			"qty": 1,
			"rate": flt(self.pr_amount),
			"expense_account": expense_account,
			"project": self.project
		})
		
		# Add variance discount if applicable
		if flt(self.variance) > 0:
			pi.append("items", {
				"item_name": "Variance Discount",
				"description": f"Variance adjustment (PC: {self.name})",
				"qty": 1,
				"rate": -flt(self.variance),
				"expense_account": expense_account,
				"project": self.project
			})
		
		# Populate taxes from Payment Certificate or Defaults
		if self.get("taxes_and_charges"):
			pi.taxes_and_charges = self.taxes_and_charges
		
		if self.get("taxes"):
			for tax in self.get("taxes"):
				pi.append("taxes", {
					"charge_type": tax.charge_type,
					"account_head": tax.account_head,
					"description": tax.description,
					"rate": tax.rate,
					"tax_amount": tax.tax_amount,
					"cost_center": tax.cost_center or pi.cost_center,
					"included_in_print_rate": tax.included_in_print_rate
				})
		
		# If no taxes yet, try default taxes
		if not pi.get("taxes") and not pi.get("taxes_and_charges"):
			default_tax = get_default_taxes_and_charges("Purchase Taxes and Charges Template", company=company)
			if default_tax and default_tax.get("taxes_and_charges"):
				pi.taxes_and_charges = default_tax["taxes_and_charges"]
				if not pi.get("taxes"):
					for tax in default_tax.get("taxes", []):
						pi.append("taxes", tax)
		
		if not pi.get("taxes") and not pi.get("taxes_and_charges"):
			# Fetch default taxes from Supplier or Company
			pi.run_method("set_taxes")
   
		mapped_apply_on = self._map_discount_apply_on()
		if self.discount_type and mapped_apply_on and (self.discount_amount or self.percentage):
			pi.apply_discount_on = mapped_apply_on
			pi.additional_discount_percentage = self.percentage
			pi.additional_discount_amount = self.discount_amount
			pi.run_method("apply_discount_and_taxes")
		
		pi.run_method("calculate_taxes_and_totals")
		pi.flags.ignore_permissions = True
		pi.insert()
		pi.submit()
		
		self.db_set({
			"purchase_invoice": pi.name,
			"invoice_status": "Submitted"
		})
		
		frappe.msgprint(_("Purchase Invoice {0} created with amount {1}").format(
			pi.name, pi.grand_total
		))
		
		return pi.name
	
	def update_boq_progress_ledger(self):
		"""
		Update BOQ Progress Ledger with accepted amount.
		"""
		from construction_management.api.boq_ledger import create_ledger_entry, recalculate_ledger_for_item
		
		# If it's a multi-item PC, we update ledger per item
		if self.get("items"):
			for pc_item in self.items:
				# Pro-rate tax invoice amount based on item's share of total accepted amount
				item_tax_invoice_amount = 0
				if flt(self.accepted_amount) > 0:
					item_share = flt(pc_item.accepted_amount) / flt(self.accepted_amount)
					item_tax_invoice_amount = flt(self.tax_invoice_amount) * item_share
				
				self._update_ledger_for_item(
					pc_item.boq_item, 
					pc_item.qty, 
					pc_item.amount, 
					pc_item.accepted_amount,
					item_tax_invoice_amount
				)
		elif self.boq_item:
			self._update_ledger_for_item(self.boq_item, 0, self.proforma_amount, self.accepted_amount, self.tax_invoice_amount)

	def _update_ledger_for_item(self, boq_item, qty, amount, accepted_val, item_tax_invoice_amount=0):
		"""Update ledger entry for a specific BOQ item"""
		from construction_management.api.boq_ledger import create_ledger_entry, recalculate_ledger_for_item
		
		# Try to find ledger entry from Sales Order
		ledger_entry = None
		if self.sales_order:
			ledger_entry = frappe.db.get_value(
				"BOQ Progress Ledger",
				{
					"boq_item": boq_item,
					"reference_doctype": "Sales Order",
					"reference_name": self.sales_order
				},
				"name"
			)
		
		if ledger_entry:
			frappe.db.set_value(
				"BOQ Progress Ledger",
				ledger_entry,
				{
					"payment_certificate": self.name,
					"certified_amount": flt(accepted_val),
					"tax_invoice": self.tax_invoice,
					"tax_invoice_amount": flt(item_tax_invoice_amount),
					"posting_date": self.posting_date
				},
				update_modified=False
			)
		else:
			# Create new entry if missing
			create_ledger_entry(
				boq_item=boq_item,
				qty=qty,
				amount=amount,
				source="Order",
				reference_doctype="Sales Order" if self.sales_order else None,
				reference_name=self.sales_order,
				posting_date=self.posting_date,
				remarks=f"Auto-created from Payment Certificate {self.name}",
				proforma_amount=amount,
				payment_certificate=self.name,
				certified_amount=flt(accepted_val),
				tax_invoice=self.tax_invoice,
				tax_invoice_amount=flt(item_tax_invoice_amount)
			)
		
		recalculate_ledger_for_item(boq_item)

	def revert_boq_progress_ledger(self):
		"""Undo Payment Certificate impact on BOQ Progress Ledger"""
		from construction_management.api.boq_ledger import recalculate_ledger_for_item
		
		items_to_recalc = []
		if self.get("items"):
			items_to_recalc = [i.boq_item for i in self.items]
		elif self.boq_item:
			items_to_recalc = [self.boq_item]
			
		for boq_item in items_to_recalc:
			ledger_entries = frappe.get_all("BOQ Progress Ledger", {
				"boq_item": boq_item,
				"payment_certificate": self.name
			})
			
			for entry in ledger_entries:
				frappe.db.set_value(
					"BOQ Progress Ledger",
					entry.name,
					{
						"payment_certificate": None,
						"certified_amount": 0,
						"tax_invoice": None,
						"tax_invoice_amount": 0,
						"remarks": f"Payment Certificate {self.name} cancelled",
						"source": "Order" if self.sales_order else "Adjustment"
					},
					update_modified=False
				)
			
			recalculate_ledger_for_item(boq_item)
	
	def close_sales_order(self):
		"""Mark Sales Order with progress details"""
		if self.sales_order:
			try:
				so = frappe.get_doc("Sales Order", self.sales_order)
				so.add_comment(
					"Comment",
					text=f"Progress certified via Payment Certificate {self.name}. Tax Invoice: {self.tax_invoice}"
				)
			except Exception as e:
				frappe.log_error(f"Error updating sales order: {str(e)}")
	
	def update_payment_status(self):
		"""Update payment status from tax invoice"""
		if self.tax_invoice:
			inv = frappe.db.get_value(
				"Sales Invoice",
				self.tax_invoice,
				["grand_total", "outstanding_amount", "status"],
				as_dict=True
			)
			if inv:
				self.db_set({
					"payment_received": flt(inv.grand_total) - flt(inv.outstanding_amount),
					"invoice_status": inv.status
				})
				if flt(inv.outstanding_amount) <= 0:
					self.db_set("status", "Paid")


# ============================================
# API Functions
# ============================================

@frappe.whitelist()
def get_pending_sales_orders(project: str = None) -> list:
	"""Get Sales Orders with BOQ items that are not fully certificated."""
	filters = {"docstatus": 1}
	if project:
		filters["project"] = project
	
	sos = frappe.get_all(
		"Sales Order",
		filters=filters,
		fields=[
			"name", "project", "customer", "customer_name",
			"base_grand_total", "transaction_date as posting_date"
		],
		order_by="transaction_date DESC"
	)
	
	def get_invoiced_amount(so_name: str) -> float:
		conditions = "si.docstatus = 1 AND si.is_return = 0 AND sii.sales_order = %s"
		if frappe.db.has_column("Sales Invoice", "custom_is_proforma"):
			conditions += " AND (si.custom_is_proforma = 0 OR si.custom_is_proforma IS NULL)"
		total = frappe.db.sql(f"""
			SELECT SUM(sii.base_amount)
			FROM `tabSales Invoice Item` sii
			JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE {conditions}
		""", so_name)[0][0] or 0
		return flt(total)

	pending = []
	for so in sos:
		so_items = frappe.get_all(
			"Sales Order Item",
			filters={"parent": so.name, "boq_item": ["!=", ""]},
			fields=["boq_item", "bill_no"]
		)
		
		if not so_items:
			continue
			
		# Calculate total accepted amount for this SO across all PCs
		total_accepted = frappe.db.sql("""
			SELECT SUM(accepted_amount)
			FROM `tabPayment Certificate`
			WHERE sales_order = %s AND docstatus != 2
		""", so.name)[0][0] or 0
		total_accepted = flt(total_accepted)
		
		# A Sales Order is pending if it has an uncertified balance
		if flt(so.base_grand_total) > total_accepted:
			so["amount"] = so.base_grand_total # Mapping for UI
			so["invoiced_amount"] = get_invoiced_amount(so.name)
			so["has_invoice"] = 1 if so["invoiced_amount"] > 0 else 0
			so["boq_items"] = list(set(item.boq_item for item in so_items if item.boq_item))
			so["bill_nos"] = list(set(item.bill_no for item in so_items if item.bill_no))
			pending.append(so)
			
	return pending


@frappe.whitelist()
def create_payment_certificate_from_sales_order(sales_order: str, accepted_amount: float = None, remarks: str = None) -> dict:
	"""Create Payment Certificate from a Sales Order with multiple items."""
	so = frappe.get_doc("Sales Order", sales_order)
	
	if so.docstatus != 1:
		frappe.throw(_("Sales Order must be submitted"))
	
	# Check if PC already exists for this SO
	existing_pc = frappe.db.exists("Payment Certificate", {
		"sales_order": sales_order,
		"docstatus": ["!=", 2]
	})
	if existing_pc:
		frappe.throw(_("Payment Certificate {0} already exists for this Sales Order").format(existing_pc))
	
	pc = frappe.new_doc("Payment Certificate")
	pc.type = "Sales"
	pc.project = so.project
	pc.customer = so.customer
	pc.sales_order = sales_order
	pc.remarks = remarks

	def get_latest_sales_invoice_for_so(so_name: str):
		latest = frappe.get_all(
			"Sales Invoice",
			filters={"custom_sales_order": so_name, "docstatus": 1},
			fields=["name"],
			order_by="posting_date desc, creation desc",
			limit=1
		)
		if latest:
			return frappe.get_doc("Sales Invoice", latest[0].name)
		return None

	def apply_si_deductions_to_items(pc_doc, si_doc, company_name):
		"""Map SI retention/advance deductions to PC items."""
		if not pc_doc.get("items"):
			return
		
		if not si_doc:
			for pc_item in pc_doc.items:
				pc_item.invoiced_amount = flt(pc_item.amount)
			return
		
		variance_item_code = None
		if company_name and frappe.db.exists("BOQ Settings", company_name):
			variance_item_code = frappe.db.get_value("BOQ Settings", company_name, "varience_item")
		
		gross_by_boq = {}
		total_gross = 0
		item_specific = {}
		global_deductions = {"retention": 0, "advance": 0}
		
		for item in si_doc.items:
			is_retention = item.item_code == "RETENTION-DEDUCTION"
			is_advance = item.item_code == "ADVANCE-DEDUCTION"
			is_variance = variance_item_code and item.item_code == variance_item_code
			
			if not (is_retention or is_advance or is_variance) and item.get("boq_item"):
				gross_by_boq[item.boq_item] = flt(gross_by_boq.get(item.boq_item)) + flt(item.amount)
				total_gross += flt(item.amount)
			elif is_retention or is_advance:
				target_boq_item = item.get("boq_item")
				val = flt(item.amount)
				if target_boq_item:
					item_specific.setdefault(target_boq_item, {"retention": 0, "advance": 0})
					if is_retention:
						item_specific[target_boq_item]["retention"] += val
					if is_advance:
						item_specific[target_boq_item]["advance"] += val
				else:
					if is_retention:
						global_deductions["retention"] += val
					if is_advance:
						global_deductions["advance"] += val
		
		for pc_item in pc_doc.items:
			boq_item = pc_item.boq_item
			gross_amount = flt(gross_by_boq.get(boq_item) or pc_item.amount)
			spec = item_specific.get(boq_item, {"retention": 0, "advance": 0})
			
			allocated_retention = 0
			allocated_advance = 0
			if total_gross > 0:
				share = gross_amount / total_gross
				allocated_retention = global_deductions["retention"] * share
				allocated_advance = global_deductions["advance"] * share
			
			retention_amount = abs(flt(spec["retention"] + allocated_retention))
			advance_amount = abs(flt(spec["advance"] + allocated_advance))
			
			pc_item.retention_amount = retention_amount
			pc_item.advance_amount = advance_amount
			pc_item.invoiced_amount = gross_amount - retention_amount - advance_amount
	
	# Populate items from Sales Order
	if so.items:
		for item in so.items:
			# Skip deduction items created on Sales Order as PC calculates its own
			if item.item_code in ["RETENTION-DEDUCTION", "ADVANCE-DEDUCTION"]:
				continue
				
			pc.append("items", {
				"boq_item": item.get("boq_item"),
				"bill_no": item.get("bill_no"),
				"description": item.description,
				"unit": item.uom,
				"qty": item.qty,
				"rate": item.rate,
				"amount": item.amount,
				"accepted_amount": item.amount, # Default to full amount
				"sales_order_item": item.name
			})
	
	# Populate default taxes
	company = frappe.db.get_value("Project", so.project, "company")
	latest_si = get_latest_sales_invoice_for_so(so.name)
	apply_si_deductions_to_items(pc, latest_si, company)
	default_tax = get_default_taxes_and_charges("Sales Taxes and Charges Template", company=company)
	if default_tax and default_tax.get("taxes_and_charges"):
		pc.taxes_and_charges = default_tax["taxes_and_charges"]
		for tax in default_tax.get("taxes", []):
			pc.append("taxes", tax)
	
	# Trigger totals calculation
	pc.calculate_totals()
	pc.calculate_retention()
	
	# Override if specific amount provided
	if accepted_amount is not None:
		pc.accepted_amount = flt(accepted_amount)
		# Recalculate retention if accepted amount is changed
		pc.calculate_retention()
	
	pc.insert()
	
	return {
		"name": pc.name,
		"project": pc.project,
		"proforma_amount": pc.proforma_amount,
		"accepted_amount": pc.accepted_amount,
		"variance": pc.variance
	}


@frappe.whitelist()
def get_payment_certificate_summary(project: str) -> dict:
	"""Get project-level Payment Certificate summary."""
	summary = frappe.db.sql("""
		SELECT 
			COUNT(*) as total_count,
			SUM(CASE WHEN status = 'Paid' THEN 1 ELSE 0 END) as paid_count,
			COALESCE(SUM(proforma_amount), 0) as total_proforma,
			COALESCE(SUM(accepted_amount), 0) as total_accepted,
			COALESCE(SUM(variance), 0) as total_variance,
			COALESCE(SUM(payment_received), 0) as total_received
		FROM `tabPayment Certificate`
		WHERE project = %s AND docstatus != 2
	""", project, as_dict=True)[0]
	
	return {
		"project": project,
		"total_count": summary.total_count or 0,
		"total_proforma": flt(summary.total_proforma),
		"total_accepted": flt(summary.total_accepted),
		"total_variance": flt(summary.total_variance),
		"total_received": flt(summary.total_received)
	}


@frappe.whitelist()
def get_payment_certificates_with_items(project: str) -> list:
	"""Fetch Payment Certificates with associated BOQ items and bills for filtering"""
	pcs = frappe.get_all(
		"Payment Certificate",
		filters={"project": project},
		fields=["name", "posting_date", "proforma_amount", "accepted_amount", "variance", "status", "tax_invoice", "sales_order", "boq_item", "bill_no"],
		order_by="posting_date desc"
	)
	
	for pc in pcs:
		# If it's a multi-item PC, fetch all items/bills
		pc_items = frappe.get_all(
			"Payment Certificate Item",
			filters={"parent": pc.name},
			fields=["boq_item", "bill_no"]
		)
		
		# Combine direct fields and child items
		boq_items = set()
		bill_nos = set()
		
		if pc.boq_item: boq_items.add(pc.boq_item)
		if pc.bill_no: bill_nos.add(pc.bill_no)
		
		for item in pc_items:
			if item.boq_item: boq_items.add(item.boq_item)
			if item.bill_no: bill_nos.add(item.bill_no)
			
		pc["boq_items"] = list(boq_items)
		pc["bill_nos"] = list(bill_nos)
		
	return pcs


@frappe.whitelist()
def get_pending_proformas(project: str = None, bill_no: str = None) -> list:
	"""Wrapper for legacy path to get pending proformas"""
	from construction_management.construction_management.doctype.proforma_invoice.proforma_invoice import get_pending_proformas as original_get
	return original_get(project, bill_no)


@frappe.whitelist()
def create_payment_certificate_from_proforma(proforma_invoice: str, posting_date: str = None, accepted_amount: float = None) -> str:
	"""Wrapper for legacy path to create Payment Certificate from Proforma"""
	from construction_management.api.boq_invoice import create_payment_certificate
	return create_payment_certificate(proforma_invoice, posting_date, accepted_amount)
