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
		self.validate_type_based_fields()
		self.validate_amounts()
		self.validate_proforma_invoice()
		self.validate_purchase_receipt()
		self.calculate_variance()
		self.validate_duplicate()
	
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
	
	def validate_proforma_invoice(self):
		"""Validate proforma invoice exists and is submitted (Sales type only)"""
		if self.type != "Sales" or not self.proforma_invoice:
			return
			
		proforma = frappe.db.get_value(
			"Proforma Invoice", 
			self.proforma_invoice, 
			["docstatus", "amount", "net_amount", "customer", "project"],
			as_dict=True
		)
		
		if not proforma:
			frappe.throw(_("Proforma Invoice {0} not found").format(self.proforma_invoice))
		
		# Proforma should be submitted (docstatus = 1)
		if proforma.docstatus != 1:
			frappe.throw(_("Proforma Invoice must be submitted"))
		
		# Set proforma amount from invoice if not set (use net_amount after retention)
		if not self.proforma_amount:
			self.proforma_amount = flt(proforma.net_amount) or flt(proforma.amount)
		
		# Auto-populate accepted_amount if not set
		if not self.accepted_amount:
			self.accepted_amount = flt(self.proforma_amount)
		
		# Auto-populate customer from proforma if not set
		if not self.customer and proforma.customer:
			self.customer = proforma.customer
		
		# Auto-populate project from proforma if not set
		if not self.project and proforma.project:
			self.project = proforma.project
	
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
		original_amount = flt(self.proforma_amount) if self.type == "Sales" else flt(self.pr_amount)
		self.variance = original_amount - flt(self.accepted_amount)
		
		if original_amount > 0:
			self.variance_percent = (flt(self.variance) / original_amount) * 100
		else:
			self.variance_percent = 0
	
	def validate_duplicate(self):
		"""Prevent creating multiple Payment Certificates for same proforma/PR"""
		if self.type == "Sales" and self.proforma_invoice:
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
		3. Cancel/close proforma invoice
		
		For Purchase type:
		1. Create Purchase Invoice with accepted amount
		2. Update BOQ Progress Ledger
		"""
		self.status = "Submitted"
		
		if self.type == "Sales":
			self.create_tax_invoice()
			self.update_boq_progress_ledger()
			self.close_proforma_invoice()
		else:  # Purchase
			self.create_purchase_invoice()
			self.update_boq_progress_ledger()
		
		self.db_set("status", "Invoiced")
	
	def on_cancel(self):
		"""Cancel linked invoice if not paid"""
		self.db_set("status", "Cancelled")
		
		if self.type == "Sales" and self.tax_invoice:
			tax_inv = frappe.get_doc("Sales Invoice", self.tax_invoice)
			if tax_inv.docstatus == 1 and flt(tax_inv.outstanding_amount) == flt(tax_inv.grand_total):
				# Only cancel if no payment received
				tax_inv.cancel()
				frappe.msgprint(_("Tax Invoice {0} cancelled").format(self.tax_invoice))
			elif flt(tax_inv.outstanding_amount) < flt(tax_inv.grand_total):
				frappe.throw(_("Cannot cancel - Tax Invoice has received payments"))
		
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
		If there's variance (PI > PC), add a discount line item.
		(Property 10: Tax Invoice Generation)
		Requirements: 3.2
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
		invoice.custom_proforma_invoice = self.proforma_invoice
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
		
		# Add main item with PROFORMA amount (original billed amount)
		# This ensures BOQ balance is calculated correctly
		invoice.append("items", {
			"item_name": item_desc[:140],
			"description": item_desc,
			"qty": 1,
			"rate": flt(self.proforma_amount),  # Use proforma amount, not accepted
			"income_account": income_account,
			"project": self.project,
			"boq_item": self.boq_item,
			"bill_no": self.bill_no
		})
		
		# If there's variance (loss), add a discount line
		# Variance = PI - PC, positive means customer paid less
		if flt(self.variance) > 0:
			# Add discount line to reduce invoice to accepted amount
			invoice.append("items", {
				"item_name": "Variance Discount",
				"description": f"Variance adjustment (PI: {self.proforma_amount}, PC: {self.accepted_amount})",
				"qty": 1,
				"rate": -flt(self.variance),  # Negative to reduce total
				"income_account": income_account,
				"project": self.project,
				"boq_item": self.boq_item,
				"bill_no": self.bill_no
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
		Property 6: Purchase Payment Certificate Submission
		Requirements: 6.3, 7.4
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
		
		# Link to Purchase Receipt if available
		if self.purchase_receipt:
			pi.purchase_receipt = self.purchase_receipt
		
		# Link to Purchase Order if available
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
		
		# If there's variance (PR > PC), add a discount line
		if flt(self.variance) > 0:
			pi.append("items", {
				"item_name": "Variance Discount",
				"description": f"Variance adjustment (PR: {self.pr_amount}, PC: {self.accepted_amount})",
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
		(Property 11: Ledger Update with Accepted Amount)
		"""
		if not self.boq_item:
			return
		
		# Check if BOQ Progress Ledger exists
		if not frappe.db.exists("DocType", "BOQ Progress Ledger"):
			return
		
		from construction_management.api.boq_ledger import create_ledger_entry, recalculate_ledger_for_item
		
		try:
			# Prefer updating the original Proforma ledger row to keep a single chain (PI -> PC -> TI)
			ledger_entry = None
			
			if self.proforma_invoice:
				ledger_entry = frappe.db.get_value(
					"BOQ Progress Ledger",
					{
						"boq_item": self.boq_item,
						"proforma_invoice": self.proforma_invoice
					},
					"name"
				)
				
				if not ledger_entry:
					ledger_entry = frappe.db.get_value(
						"BOQ Progress Ledger",
						{
							"boq_item": self.boq_item,
							"reference_doctype": "Proforma Invoice",
							"reference_name": self.proforma_invoice
						},
						"name"
					)
			
			if ledger_entry:
				frappe.db.set_value(
					"BOQ Progress Ledger",
					ledger_entry,
					{
						"payment_certificate": self.name,
						"certified_amount": flt(self.accepted_amount),
						"tax_invoice": self.tax_invoice,
						"tax_invoice_amount": flt(self.tax_invoice_amount) if self.tax_invoice else 0,
						"proforma_invoice": self.proforma_invoice,
						"proforma_amount": flt(self.proforma_amount) or flt(self.accepted_amount),
						"posting_date": self.posting_date
					},
					update_modified=False
				)
			else:
				# Safety net: rebuild the missing ledger row from the Proforma context
				qty = 0
				amount = flt(self.proforma_amount) or flt(self.accepted_amount)
				
				if self.proforma_invoice:
					proforma_item = frappe.db.get_value(
						"Proforma Invoice Item",
						{
							"parent": self.proforma_invoice,
							"boq_item": self.boq_item
						},
						["qty", "amount"],
						as_dict=True
					)
					if proforma_item:
						qty = flt(proforma_item.qty)
						amount = flt(proforma_item.amount)
				
				create_ledger_entry(
					boq_item=self.boq_item,
					qty=qty,
					amount=amount,
					source="Proforma",
					reference_doctype="Proforma Invoice" if self.proforma_invoice else None,
					reference_name=self.proforma_invoice,
					posting_date=self.posting_date,
					remarks=f"Auto-created from Payment Certificate {self.name}",
					proforma_invoice=self.proforma_invoice,
					proforma_amount=amount,
					payment_certificate=self.name,
					certified_amount=flt(self.accepted_amount),
					tax_invoice=self.tax_invoice,
					tax_invoice_amount=flt(self.tax_invoice_amount) if self.tax_invoice else 0
				)
			
			# Refresh progressive values so the chain stays balanced
			recalculate_ledger_for_item(self.boq_item)
		except Exception as e:
			frappe.log_error(f"Error creating BOQ Progress Ledger: {str(e)}")

	def revert_boq_progress_ledger(self):
		"""
		Undo Payment Certificate impact on BOQ Progress Ledger (single-row lifecycle).
		"""
		if not self.boq_item:
			return
		if not frappe.db.exists("DocType", "BOQ Progress Ledger"):
			return
		
		from construction_management.api.boq_ledger import recalculate_ledger_for_item
		
		# Prefer targeting by proforma -> PC linkage, then fallback to PC or TI
		ledger_entry = None
		if self.proforma_invoice:
			ledger_entry = frappe.db.get_value(
				"BOQ Progress Ledger",
				{
					"boq_item": self.boq_item,
					"proforma_invoice": self.proforma_invoice
				},
				"name"
			)
		
		if not ledger_entry:
			ledger_entry = frappe.db.get_value(
				"BOQ Progress Ledger",
				{
					"boq_item": self.boq_item,
					"payment_certificate": self.name
				},
				"name"
			)
		
		if not ledger_entry and self.tax_invoice:
			ledger_entry = frappe.db.get_value(
				"BOQ Progress Ledger",
				{
					"boq_item": self.boq_item,
					"tax_invoice": self.tax_invoice
				},
				"name"
			)
		
		if ledger_entry:
			frappe.db.set_value(
				"BOQ Progress Ledger",
				ledger_entry,
				{
					"payment_certificate": None,
					"certified_amount": 0,
					"tax_invoice": None,
					"tax_invoice_amount": 0,
					"remarks": f"Payment Certificate {self.name} cancelled",
					"source": "Proforma" if self.proforma_invoice else "Adjustment"
				},
				update_modified=False
			)
			recalculate_ledger_for_item(self.boq_item)
	
	def close_proforma_invoice(self):
		"""Mark proforma invoice as converted to tax invoice"""
		if self.proforma_invoice:
			try:
				# Update the Proforma Invoice status and link to PC and Tax Invoice
				proforma = frappe.get_doc("Proforma Invoice", self.proforma_invoice)
				
				# Update proforma with links
				proforma.db_set({
					"payment_certificate": self.name,
					"tax_invoice": self.tax_invoice,
					"converted_date": today(),
					"status": "Converted"
				})
				
				# Add comment for audit trail
				proforma.add_comment(
					"Comment",
					text=f"Converted to Tax Invoice {self.tax_invoice} via Payment Certificate {self.name}"
				)
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
def create_payment_certificate_from_proforma(proforma_invoice: str, accepted_amount: float = None, remarks: str = None) -> dict:
	"""
	Create Payment Certificate from a proforma invoice.
	
	Args:
		proforma_invoice: Proforma invoice name
		accepted_amount: Accepted amount (auto-populated from proforma if not provided)
		remarks: Optional remarks
		
	Returns:
		dict with created Payment Certificate info
	"""
	proforma = frappe.get_doc("Proforma Invoice", proforma_invoice)
	
	if proforma.docstatus != 1:
		frappe.throw(_("Proforma Invoice must be submitted"))
	
	# Check if PC already exists for this proforma
	existing_pc = frappe.db.exists("Payment Certificate", {
		"proforma_invoice": proforma_invoice,
		"docstatus": ["!=", 2]
	})
	if existing_pc:
		frappe.throw(_("Payment Certificate {0} already exists for this Proforma Invoice").format(existing_pc))
	
	# Auto-populate accepted_amount from proforma if not provided
	proforma_amount = flt(proforma.net_amount) or flt(proforma.amount)
	if accepted_amount is None:
		accepted_amount = proforma_amount
	
	# Validate accepted_amount doesn't exceed proforma amount
	if flt(accepted_amount) > proforma_amount:
		frappe.throw(
			_("Accepted amount ({0}) cannot exceed proforma amount ({1})").format(
				accepted_amount, proforma_amount
			)
		)
	
	pc = frappe.new_doc("Payment Certificate")
	pc.type = "Sales"
	pc.project = proforma.project
	pc.customer = proforma.customer
	pc.proforma_invoice = proforma_invoice
	pc.proforma_amount = proforma_amount
	pc.accepted_amount = flt(accepted_amount)
	pc.remarks = remarks
	
	# Auto-fetch bill_no and boq_item from proforma invoice items
	if proforma.items:
		for item in proforma.items:
			if hasattr(item, "bill_no") and item.bill_no and not pc.bill_no:
				pc.bill_no = item.bill_no
			if hasattr(item, "boq_item") and item.boq_item and not pc.boq_item:
				pc.boq_item = item.boq_item
	
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

