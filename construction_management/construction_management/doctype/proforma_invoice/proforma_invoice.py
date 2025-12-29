# Copyright (c) 2024, Construction Management
# License: MIT

"""
Proforma Invoice DocType Controller

Manages proforma invoices as a separate document type from Sales Invoice.
Supports multiple BOQ Items per proforma invoice.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today


class ProformaInvoice(Document):
	def validate(self):
		self.validate_project()
		self.validate_items()
		self.calculate_totals()
		self.calculate_retention()
		self.set_description()
	
	def validate_project(self):
		"""Validate project exists and has customer"""
		if not self.project:
			return
		
		customer = frappe.db.get_value("Project", self.project, "customer")
		if customer:
			self.customer = customer
	
	def validate_items(self):
		"""Validate items belong to the project"""
		if not self.items:
			frappe.throw(_("At least one item is required"))
		
		for item in self.items:
			if item.boq_item:
				item_project = frappe.db.get_value("BOQ Item", item.boq_item, "project")
				if item_project and item_project != self.project:
					frappe.throw(
						_("BOQ Item {0} does not belong to Project {1}").format(
							item.boq_item, self.project
						)
					)
				
				# Auto-fetch bill_no if not set
				if not item.bill_no:
					item.bill_no = frappe.db.get_value("BOQ Item", item.boq_item, "parent_bill")
				
				# Calculate item amount
				if not item.rate:
					item.rate = flt(frappe.db.get_value("BOQ Item", item.boq_item, "rate"))
				
				item.amount = flt(item.qty) * flt(item.rate)
	
	def calculate_totals(self):
		"""Calculate total amount from items"""
		self.amount = sum(flt(item.amount) for item in self.items)
	
	def calculate_retention(self):
		"""Calculate retention amount based on project settings"""
		retention_pct = 0
		if self.project:
			retention_pct = flt(frappe.db.get_value("Project", self.project, "retention_percentage"))
		
		self.retention_amount = flt(self.amount) * (retention_pct / 100)
		self.net_amount = flt(self.amount) - flt(self.retention_amount)
	
	def set_description(self):
		"""Auto-set description from items if not provided"""
		if not self.description and self.items:
			if len(self.items) == 1:
				self.description = frappe.db.get_value("BOQ Item", self.items[0].boq_item, "description")
			else:
				self.description = f"Proforma Invoice for {len(self.items)} BOQ Items"
	
	def on_submit(self):
		"""
		On submit:
		1. Update status to Submitted
		2. Create BOQ Progress Ledger entries for each item
		3. Reset BOQ Item current_qty
		
		Requirements: 7.2
		"""
		self.db_set("status", "Submitted")
		self.create_ledger_entries()
		self.reset_boq_item_current_qty()
	
	def on_cancel(self):
		"""
		On cancel:
		1. Update status to Cancelled
		2. Create reversing ledger entries
		
		Requirements: 7.3
		"""
		# Check if already converted
		if self.payment_certificate or self.tax_invoice:
			frappe.throw(
				_("Cannot cancel Proforma Invoice that has been converted to Payment Certificate or Tax Invoice")
			)
		
		self.db_set("status", "Cancelled")
		self.create_reversing_ledger_entries()
	
	def create_ledger_entries(self):
		"""Create BOQ Progress Ledger entries for each item"""
		if not frappe.db.exists("DocType", "BOQ Progress Ledger"):
			return
		
		for item in self.items:
			if not item.boq_item:
				continue
			
			try:
				# Get previous accumulated values
				from construction_management.api.boq_ledger import get_to_date_qty, get_to_date_amount
				prev_qty = get_to_date_qty(item.boq_item)
				prev_amount = get_to_date_amount(item.boq_item)
				
				ledger = frappe.new_doc("BOQ Progress Ledger")
				ledger.boq_item = item.boq_item
				ledger.project = self.project
				ledger.bill_no = item.bill_no
				ledger.posting_date = self.posting_date
				ledger.reference_doctype = "Proforma Invoice"
				ledger.reference_name = self.name
				ledger.proforma_invoice = self.name
				ledger.proforma_amount = flt(item.amount)
				ledger.source = "Proforma Invoice"
				ledger.qty = flt(item.qty)
				ledger.amount = flt(item.amount)
				ledger.prev_qty = prev_qty
				ledger.prev_amount = prev_amount
				ledger.current_qty = flt(item.qty)
				ledger.current_amount = flt(item.amount)
				ledger.accumulated_qty = prev_qty + flt(item.qty)
				ledger.accumulated_amount = prev_amount + flt(item.amount)
				ledger.remarks = f"Proforma Invoice {self.name}"
				ledger.insert(ignore_permissions=True)
			except Exception as e:
				frappe.log_error(f"Error creating ledger for Proforma {self.name}, Item {item.boq_item}: {str(e)}")
	
	def create_reversing_ledger_entries(self):
		"""Create reversing BOQ Progress Ledger entries"""
		if not frappe.db.exists("DocType", "BOQ Progress Ledger"):
			return
		
		for item in self.items:
			if not item.boq_item:
				continue
			
			try:
				# Get current accumulated values
				from construction_management.api.boq_ledger import get_to_date_qty, get_to_date_amount
				prev_qty = get_to_date_qty(item.boq_item)
				prev_amount = get_to_date_amount(item.boq_item)
				
				ledger = frappe.new_doc("BOQ Progress Ledger")
				ledger.boq_item = item.boq_item
				ledger.project = self.project
				ledger.bill_no = item.bill_no
				ledger.posting_date = today()
				ledger.reference_doctype = "Proforma Invoice"
				ledger.reference_name = self.name
				ledger.source = "Proforma Invoice Cancellation"
				ledger.qty = -flt(item.qty)
				ledger.amount = -flt(item.amount)
				ledger.prev_qty = prev_qty
				ledger.prev_amount = prev_amount
				ledger.current_qty = -flt(item.qty)
				ledger.current_amount = -flt(item.amount)
				ledger.accumulated_qty = prev_qty - flt(item.qty)
				ledger.accumulated_amount = prev_amount - flt(item.amount)
				ledger.remarks = f"Cancellation of Proforma Invoice {self.name}"
				ledger.insert(ignore_permissions=True)
			except Exception as e:
				frappe.log_error(f"Error creating reversing ledger for Proforma {self.name}, Item {item.boq_item}: {str(e)}")
	
	def reset_boq_item_current_qty(self):
		"""Reset current_qty on BOQ Items after proforma creation"""
		for item in self.items:
			if item.boq_item:
				frappe.db.set_value("BOQ Item", item.boq_item, "current_qty", 0)
	
	def mark_as_converted(self, payment_certificate: str, tax_invoice: str = None):
		"""
		Mark proforma as converted when Payment Certificate is created.
		Requirements: 7.4
		"""
		self.db_set({
			"status": "Converted",
			"payment_certificate": payment_certificate,
			"tax_invoice": tax_invoice,
			"converted_date": today()
		})


# ============================================
# API Functions
# ============================================

@frappe.whitelist()
def get_pending_proformas(project: str = None, bill_no: str = None) -> list:
	"""
	Get proforma invoices without linked Payment Certificate.
	
	Args:
		project: Optional project filter
		bill_no: Optional bill filter
		
	Returns:
		List of pending proforma invoices
	"""
	filters = {"docstatus": 1, "status": "Submitted"}
	
	if project:
		filters["project"] = project
	
	proformas = frappe.get_all(
		"Proforma Invoice",
		filters=filters,
		fields=[
			"name", "project", "customer",
			"posting_date", "amount", "net_amount", "description",
			"DATEDIFF(CURDATE(), posting_date) as age_days"
		],
		order_by="posting_date desc"
	)
	
	# Add item count
	for p in proformas:
		p["item_count"] = frappe.db.count("Proforma Invoice Item", {"parent": p.name})
	
	return proformas


@frappe.whitelist()
def create_proforma_from_selected_items(
	project: str,
	items: str | list,
	apply_retention: int = 1,
	posting_date: str = None,
	remarks: str = None
) -> dict:
	"""
	Create Proforma Invoice from selected BOQ Items.
	
	Args:
		project: Project name
		items: List of dicts with boq_item and qty
		apply_retention: Whether to apply retention
		posting_date: Optional posting date
		remarks: Optional remarks
		
	Returns:
		dict with created proforma info
	"""
	import json
	
	if isinstance(items, str):
		items = json.loads(items)
	
	if not items:
		frappe.throw(_("No items provided"))
	
	proforma = frappe.new_doc("Proforma Invoice")
	proforma.project = project
	proforma.posting_date = posting_date or today()
	proforma.remarks = remarks
	
	total_amount = 0
	bills_included = set()
	
	for item_data in items:
		boq_item_name = item_data.get("boq_item")
		qty = flt(item_data.get("qty", 0))
		
		if qty <= 0:
			continue
		
		# Get BOQ Item details
		boq_item = frappe.get_doc("BOQ Item", boq_item_name)
		
		# Validate balance
		from construction_management.api.boq_ledger import get_to_date_qty
		to_date_qty = get_to_date_qty(boq_item_name)
		balance_qty = flt(boq_item.total_qty) - flt(to_date_qty)
		
		if qty > balance_qty:
			frappe.throw(
				_("Quantity ({0}) exceeds available balance ({1}) for item {2}").format(
					qty, balance_qty, boq_item.description[:50]
				),
				title=_("Over-Billing Error")
			)
		
		amount = flt(qty) * flt(boq_item.rate)
		total_amount += amount
		
		# Get bill_no
		bill_no = frappe.db.get_value("BOQ Bill", boq_item.parent_bill, "bill_no")
		bills_included.add(bill_no or boq_item.parent_bill)
		
		# Add item to proforma
		proforma.append("items", {
			"boq_item": boq_item_name,
			"bill_no": boq_item.parent_bill,
			"description": boq_item.description,
			"unit": boq_item.unit,
			"qty": qty,
			"rate": boq_item.rate,
			"amount": amount
		})
	
	if not proforma.items:
		frappe.throw(_("No valid items to invoice"))
	
	proforma.insert()
	
	return {
		"name": proforma.name,
		"project": proforma.project,
		"item_count": len(proforma.items),
		"bills_included": list(bills_included),
		"amount": proforma.amount,
		"retention_amount": proforma.retention_amount,
		"net_amount": proforma.net_amount,
		"status": "Draft"
	}


@frappe.whitelist()
def get_proforma_summary(project: str) -> dict:
	"""
	Get proforma invoice summary for a project.
	
	Args:
		project: Project name
		
	Returns:
		dict with summary statistics
	"""
	summary = frappe.db.sql("""
		SELECT 
			COUNT(*) as total_count,
			SUM(CASE WHEN status = 'Draft' THEN 1 ELSE 0 END) as draft_count,
			SUM(CASE WHEN status = 'Submitted' THEN 1 ELSE 0 END) as pending_count,
			SUM(CASE WHEN status = 'Converted' THEN 1 ELSE 0 END) as converted_count,
			SUM(CASE WHEN status = 'Cancelled' THEN 1 ELSE 0 END) as cancelled_count,
			COALESCE(SUM(CASE WHEN docstatus = 1 THEN amount ELSE 0 END), 0) as total_amount,
			COALESCE(SUM(CASE WHEN status = 'Submitted' THEN amount ELSE 0 END), 0) as pending_amount,
			COALESCE(SUM(CASE WHEN status = 'Converted' THEN amount ELSE 0 END), 0) as converted_amount
		FROM `tabProforma Invoice`
		WHERE project = %s
	""", project, as_dict=True)[0]
	
	return {
		"project": project,
		"total_count": summary.total_count or 0,
		"draft_count": summary.draft_count or 0,
		"pending_count": summary.pending_count or 0,
		"converted_count": summary.converted_count or 0,
		"cancelled_count": summary.cancelled_count or 0,
		"total_amount": flt(summary.total_amount),
		"pending_amount": flt(summary.pending_amount),
		"converted_amount": flt(summary.converted_amount)
	}
