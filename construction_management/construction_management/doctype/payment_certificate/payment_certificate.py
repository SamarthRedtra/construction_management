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
		self.validate_amounts()
		self.validate_proforma_invoice()
		self.calculate_variance()
		self.validate_duplicate()
	
	def validate_amounts(self):
		"""Validate accepted amount is positive"""
		if flt(self.accepted_amount) <= 0:
			frappe.throw(_("Accepted Amount must be greater than zero"))
	
	def validate_proforma_invoice(self):
		"""Validate proforma invoice exists and is in draft status"""
		if self.proforma_invoice:
			proforma = frappe.db.get_value(
				"Sales Invoice", 
				self.proforma_invoice, 
				["docstatus", "grand_total", "custom_is_proforma"],
				as_dict=True
			)
			
			if not proforma:
				frappe.throw(_("Proforma Invoice {0} not found").format(self.proforma_invoice))
			
			# Proforma should be in draft (docstatus = 0)
			if proforma.docstatus != 0:
				frappe.throw(_("Proforma Invoice must be in Draft status"))
			
			# Set proforma amount from invoice if not set
			if not self.proforma_amount:
				self.proforma_amount = flt(proforma.grand_total)
	
	def calculate_variance(self):
		"""
		Calculate variance between proforma and accepted amounts.
		(Property 13: Variance Calculation)
		"""
		self.variance = flt(self.proforma_amount) - flt(self.accepted_amount)
		
		if flt(self.proforma_amount) > 0:
			self.variance_percent = (flt(self.variance) / flt(self.proforma_amount)) * 100
		else:
			self.variance_percent = 0
	
	def validate_duplicate(self):
		"""Prevent creating multiple Payment Certificates for same proforma"""
		if self.proforma_invoice:
			existing = frappe.db.exists(
				"Payment Certificate",
				{
					"proforma_invoice": self.proforma_invoice,
					"docstatus": ["!=", 2],
					"name": ["!=", self.name]
				}
			)
			if existing:
				frappe.throw(
					_("Payment Certificate {0} already exists for Proforma Invoice {1}").format(
						existing, self.proforma_invoice
					)
				)
	
	def on_submit(self):
		"""
		On submit:
		1. Create Tax Invoice with accepted amount
		2. Update BOQ Progress Ledger
		3. Cancel/close proforma invoice
		"""
		self.status = "Submitted"
		self.create_tax_invoice()
		self.update_boq_progress_ledger()
		self.close_proforma_invoice()
		self.db_set("status", "Invoiced")
	
	def on_cancel(self):
		"""Cancel linked tax invoice if not paid"""
		self.db_set("status", "Cancelled")
		
		if self.tax_invoice:
			tax_inv = frappe.get_doc("Sales Invoice", self.tax_invoice)
			if tax_inv.docstatus == 1 and flt(tax_inv.outstanding_amount) == flt(tax_inv.grand_total):
				# Only cancel if no payment received
				tax_inv.cancel()
				frappe.msgprint(_("Tax Invoice {0} cancelled").format(self.tax_invoice))
			elif flt(tax_inv.outstanding_amount) < flt(tax_inv.grand_total):
				frappe.throw(_("Cannot cancel - Tax Invoice has received payments"))
	
	def create_tax_invoice(self):
		"""
		Create final Tax Invoice with accepted amount.
		(Property 10: Tax Invoice Generation)
		"""
		if not self.customer:
			self.customer = frappe.db.get_value("Project", self.project, "customer")
		
		if not self.customer:
			frappe.throw(_("Project {0} must have a Customer assigned").format(self.project))
		
		# Get company from project or default
		company = frappe.db.get_value("Project", self.project, "company")
		if not company:
			company = frappe.defaults.get_user_default("Company")
		
		# Get default income account
		income_account = frappe.db.get_value("Company", company, "default_income_account")
		
		# Create invoice
		invoice = frappe.new_doc("Sales Invoice")
		invoice.customer = self.customer
		invoice.company = company
		invoice.project = self.project
		invoice.posting_date = self.posting_date or today()
		invoice.due_date = self.posting_date or today()
		invoice.custom_payment_certificate = self.name
		invoice.custom_is_proforma = 0  # This is a final tax invoice
		
		# Add bill_no and boq_item as dimensions if fields exist
		if hasattr(invoice, "custom_bill_number"):
			invoice.custom_bill_number = self.bill_no
		
		# Get item description
		item_desc = "Progress Billing"
		if self.boq_item:
			item_desc = frappe.db.get_value("BOQ Item", self.boq_item, "description") or item_desc
		elif self.bill_no:
			item_desc = frappe.db.get_value("BOQ Bill", self.bill_no, "description") or f"Bill: {self.bill_no}"
		
		# Add item with accounting dimensions (project, bill_no, boq_item)
		invoice.append("items", {
			"item_name": item_desc[:140],
			"description": item_desc,
			"qty": 1,
			"rate": flt(self.accepted_amount),
			"income_account": income_account,
			"project": self.project,  # Set project on item level for accounting dimension
			"boq_item": self.boq_item,  # Set boq_item on item level for accounting dimension
			"bill_no": self.bill_no  # Set bill_no on item level for accounting dimension
		})
		
		invoice.flags.ignore_permissions = True
		invoice.insert()
		invoice.submit()
		
		self.db_set({
			"tax_invoice": invoice.name,
			"tax_invoice_amount": invoice.grand_total,
			"invoice_status": "Submitted"
		})
		
		frappe.msgprint(_("Tax Invoice {0} created").format(invoice.name))
		
		return invoice.name
	
	def update_boq_progress_ledger(self):
		"""
		Update BOQ Progress Ledger with accepted amount.
		(Property 11: Ledger Update with Accepted Amount)
		"""
		if not self.boq_item:
			return
		
		# Check if BOQ Progress Ledger exists
		if not frappe.db.exists("DocType", "BOQ Progress Ledger"):
			return
		
		try:
			ledger = frappe.new_doc("BOQ Progress Ledger")
			ledger.boq_item = self.boq_item
			ledger.project = self.project
			ledger.bill_no = self.bill_no
			ledger.posting_date = self.posting_date
			ledger.payment_certificate = self.name
			ledger.certified_amount = flt(self.accepted_amount)  # Use accepted, not proforma
			ledger.tax_invoice = self.tax_invoice
			ledger.insert()
		except Exception as e:
			frappe.log_error(f"Error creating BOQ Progress Ledger: {str(e)}")
	
	def close_proforma_invoice(self):
		"""Mark proforma invoice as converted to tax invoice"""
		if self.proforma_invoice:
			try:
				# Cancel the proforma (draft) invoice
				proforma = frappe.get_doc("Sales Invoice", self.proforma_invoice)
				if proforma.docstatus == 0:
					# Add remarks about conversion
					proforma.add_comment(
						"Comment",
						text=f"Converted to Tax Invoice {self.tax_invoice} via Payment Certificate {self.name}"
					)
					# Delete or keep based on preference - here we keep for audit
					proforma.db_set("custom_converted_to_tax_invoice", self.tax_invoice)
			except Exception as e:
				frappe.log_error(f"Error closing proforma invoice: {str(e)}")
	
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
def get_pending_proformas(project: str = None) -> list:
	"""
	Get proforma invoices without Payment Certificate.
	(Property 12: Pending Proforma Tracking)
	
	Args:
		project: Optional project filter
		
	Returns:
		List of pending proforma invoices
	"""
	filters = ["si.docstatus = 0", "si.custom_is_proforma = 1"]
	params = []
	
	# Exclude those already linked to Payment Certificate
	filters.append("""
		NOT EXISTS (
			SELECT 1 FROM `tabPayment Certificate` pc 
			WHERE pc.proforma_invoice = si.name 
			AND pc.docstatus != 2
		)
	""")
	
	if project:
		filters.append("si.project = %s")
		params.append(project)
	
	proformas = frappe.db.sql("""
		SELECT 
			si.name,
			si.project,
			si.customer,
			si.customer_name,
			si.grand_total,
			si.posting_date,
			si.creation,
			DATEDIFF(CURDATE(), si.posting_date) as age_days
		FROM `tabSales Invoice` si
		WHERE {filters}
		ORDER BY si.posting_date DESC
	""".format(filters=" AND ".join(filters)), tuple(params), as_dict=True)
	
	return proformas


@frappe.whitelist()
def create_proforma_invoice(
	project: str,
	customer: str,
	amount: float,
	bill_no: str = None,
	boq_item: str = None,
	description: str = None
) -> dict:
	"""
	Create a proforma (draft) invoice.
	(Task 9.6: Proforma invoice generation)
	
	Args:
		project: Project name
		customer: Customer name
		amount: Invoice amount
		bill_no: Optional Bill No
		boq_item: Optional BOQ Item
		description: Optional description
		
	Returns:
		dict with created invoice info
	"""
	# Get company from project
	company = frappe.db.get_value("Project", project, "company")
	if not company:
		company = frappe.defaults.get_user_default("Company")
	
	# Get default income account
	income_account = frappe.db.get_value("Company", company, "default_income_account")
	
	# Build description
	if not description:
		description = "Proforma Invoice"
		if boq_item:
			description = frappe.db.get_value("BOQ Item", boq_item, "description") or description
		elif bill_no:
			description = frappe.db.get_value("BOQ Bill", bill_no, "description") or f"Bill: {bill_no}"
	
	# Create draft invoice
	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = customer
	invoice.company = company
	invoice.project = project
	invoice.posting_date = today()
	invoice.due_date = today()
	invoice.custom_is_proforma = 1  # Mark as proforma
	
	# Add dimensions if available
	if hasattr(invoice, "custom_bill_number") and bill_no:
		invoice.custom_bill_number = bill_no
	
	# Add item with accounting dimensions (project, bill_no, boq_item)
	invoice.append("items", {
		"item_name": description[:140],
		"description": description,
		"qty": 1,
		"rate": flt(amount),
		"income_account": income_account,
		"project": project,  # Set project on item level for accounting dimension
		"boq_item": boq_item,  # Set boq_item on item level for accounting dimension
		"bill_no": bill_no  # Set bill_no on item level for accounting dimension
	})
	
	invoice.flags.ignore_permissions = True
	invoice.insert()  # Keep in draft
	
	return {
		"name": invoice.name,
		"grand_total": invoice.grand_total,
		"status": "Draft",
		"is_proforma": True
	}


@frappe.whitelist()
def create_payment_certificate_from_proforma(proforma_invoice: str, accepted_amount: float, remarks: str = None) -> dict:
	"""
	Create Payment Certificate from a proforma invoice.
	
	Args:
		proforma_invoice: Proforma invoice name
		accepted_amount: Accepted amount
		remarks: Optional remarks
		
	Returns:
		dict with created Payment Certificate info
	"""
	proforma = frappe.get_doc("Sales Invoice", proforma_invoice)
	
	if proforma.docstatus != 0:
		frappe.throw(_("Proforma Invoice must be in Draft status"))
	
	pc = frappe.new_doc("Payment Certificate")
	pc.project = proforma.project
	pc.customer = proforma.customer
	pc.proforma_invoice = proforma_invoice
	pc.proforma_amount = proforma.grand_total
	pc.accepted_amount = flt(accepted_amount)
	pc.remarks = remarks
	
	# Get bill_no and boq_item from proforma invoice items
	if proforma.items:
		first_item = proforma.items[0]
		# Try to get bill_no from item level first, then from invoice level
		if hasattr(first_item, "bill_no") and first_item.bill_no:
			pc.bill_no = first_item.bill_no
		elif hasattr(proforma, "custom_bill_number") and proforma.custom_bill_number:
			pc.bill_no = proforma.custom_bill_number
		
		# Get boq_item from item level
		if hasattr(first_item, "boq_item") and first_item.boq_item:
			pc.boq_item = first_item.boq_item
	
	pc.insert()
	
	return {
		"name": pc.name,
		"project": pc.project,
		"proforma_amount": pc.proforma_amount,
		"accepted_amount": pc.accepted_amount,
		"variance": pc.variance,
		"bill_no": pc.bill_no,
		"boq_item": pc.boq_item
	}


@frappe.whitelist()
def get_payment_certificate_summary(project: str) -> dict:
	"""
	Get payment certificate summary for a project.
	
	Args:
		project: Project name
		
	Returns:
		dict with summary statistics
	"""
	summary = frappe.db.sql("""
		SELECT 
			COUNT(*) as total_count,
			SUM(CASE WHEN status = 'Draft' THEN 1 ELSE 0 END) as draft_count,
			SUM(CASE WHEN status = 'Submitted' THEN 1 ELSE 0 END) as submitted_count,
			SUM(CASE WHEN status = 'Invoiced' THEN 1 ELSE 0 END) as invoiced_count,
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
		"draft_count": summary.draft_count or 0,
		"submitted_count": summary.submitted_count or 0,
		"invoiced_count": summary.invoiced_count or 0,
		"paid_count": summary.paid_count or 0,
		"total_proforma": flt(summary.total_proforma),
		"total_accepted": flt(summary.total_accepted),
		"total_variance": flt(summary.total_variance),
		"total_received": flt(summary.total_received)
	}

