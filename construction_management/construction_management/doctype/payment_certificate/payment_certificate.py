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


class PaymentCertificate(Document):
	def validate(self):
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
			return
			
		total_proforma = 0
		total_accepted = 0
		
		for item in self.items:
			item.amount = flt(item.qty) * flt(item.rate)
			
			# Ensure accepted_amount is initialized if zero and newly added
			if not item.accepted_amount and flt(item.qty) > 0:
				item.accepted_amount = item.amount
				
			item.variance = flt(item.amount) - flt(item.accepted_amount)
			
			total_proforma += flt(item.amount)
			total_accepted += flt(item.accepted_amount)
			
		self.proforma_amount = total_proforma
		self.accepted_amount = total_accepted

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
		
		if self.type == "Sales" and self.tax_invoice:
			tax_inv = frappe.get_doc("Sales Invoice", self.tax_invoice)
			if tax_inv.docstatus == 1:
				# Allow cancel even if linked
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
		
		# Set retention fields on invoice
		if hasattr(invoice, "custom_retention_amount"):
			invoice.custom_retention_amount = flt(self.retention_amount)
			invoice.custom_retention_percentage = flt(self.retention_percentage)
			invoice.custom_retention_account = retention_account
		
		# Add items from PC items table
		if self.get("items"):
			for pc_item in self.items:
				invoice.append("items", {
					"item_code": frappe.db.get_value("BOQ Item", pc_item.boq_item, "item_code") or "Service",
					"item_name": pc_item.description[:140],
					"description": pc_item.description,
					"qty": flt(pc_item.accepted_amount) / flt(pc_item.rate) if flt(pc_item.rate) > 0 else 0,
					"rate": pc_item.rate,
					"income_account": income_account,
					"project": self.project,
					"boq_item": pc_item.boq_item,
					"bill_no": pc_item.bill_no,
					"sales_order": self.sales_order,
					"so_detail": pc_item.sales_order_item
				})
		else:
			# Fallback for old single-item PCs
			item_desc = "Progress Billing"
			if self.boq_item:
				item_desc = frappe.db.get_value("BOQ Item", self.boq_item, "description") or item_desc
			elif self.bill_no:
				item_desc = frappe.db.get_value("BOQ Bill", self.bill_no, "description") or f"Bill: {self.bill_no}"
				
			invoice.append("items", {
				"item_name": item_desc[:140],
				"description": item_desc,
				"qty": 1,
				"rate": flt(self.proforma_amount),
				"income_account": income_account,
				"project": self.project,
				"boq_item": self.boq_item,
				"bill_no": self.bill_no,
				"sales_order": self.sales_order
			})
		
		# Add global variance discount line if total variance exists
		if flt(self.variance) > 0:
			invoice.append("items", {
				"item_name": "Variance Discount",
				"description": f"Variance adjustment (PC: {self.name})",
				"qty": 1,
				"rate": -flt(self.variance),
				"income_account": income_account,
				"project": self.project
			})
		
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
				self._update_ledger_for_item(pc_item.boq_item, pc_item.qty, pc_item.amount, pc_item.accepted_amount)
		elif self.boq_item:
			self._update_ledger_for_item(self.boq_item, 0, self.proforma_amount, self.accepted_amount)

	def _update_ledger_for_item(self, boq_item, qty, amount, accepted_val):
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
					"tax_invoice_amount": flt(self.tax_invoice_amount) if self.tax_invoice else 0,
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
				tax_invoice_amount=flt(self.tax_invoice_amount) if self.tax_invoice else 0
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
	
	pending = []
	for so in sos:
		has_boq = frappe.db.exists("Sales Order Item", {"parent": so.name, "boq_item": ["!=", ""]})
		if not has_boq:
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
	
	# Populate items from Sales Order
	if so.items:
		for item in so.items:
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
	
	# Trigger totals calculation
	pc.calculate_totals()
	pc.calculate_retention()
	
	# Override if specific amount provided
	if accepted_amount is not None:
		pc.accepted_amount = flt(accepted_amount)
	
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
def get_pending_proformas(project: str = None, bill_no: str = None) -> list:
	"""Wrapper for legacy path to get pending proformas"""
	from construction_management.construction_management.doctype.proforma_invoice.proforma_invoice import get_pending_proformas as original_get
	return original_get(project, bill_no)


@frappe.whitelist()
def create_payment_certificate_from_proforma(proforma_invoice: str, posting_date: str = None, accepted_amount: float = None) -> str:
	"""Wrapper for legacy path to create Payment Certificate from Proforma"""
	from construction_management.api.boq_invoice import create_payment_certificate
	return create_payment_certificate(proforma_invoice, posting_date, accepted_amount)
