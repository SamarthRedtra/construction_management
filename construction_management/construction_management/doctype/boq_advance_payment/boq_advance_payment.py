# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BOQAdvancePayment(Document):
	def validate(self):
		self.validate_amount()
		self.validate_bill_item_context()
		self.calculate_unallocated()
	
	def validate_amount(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be greater than zero"))
	
	def validate_bill_item_context(self):
		"""Validate bill_no and boq_item belong to the project"""
		if self.bill_no:
			bill_project = frappe.db.get_value("BOQ Bill", self.bill_no, "project")
			if bill_project != self.project:
				frappe.throw(_("Bill {0} does not belong to Project {1}").format(
					self.bill_no, self.project
				))
		
		if self.boq_item:
			item_bill = frappe.db.get_value("BOQ Item", self.boq_item, "parent_bill")
			if self.bill_no and item_bill != self.bill_no:
				frappe.throw(_("BOQ Item {0} does not belong to Bill {1}").format(
					self.boq_item, self.bill_no
				))
	
	def calculate_unallocated(self):
		"""Calculate unallocated amount"""
		self.unallocated_amount = flt(self.amount) - flt(self.allocated_amount)
	
	def on_submit(self):
		self.status = "Active"
		self.db_set("unallocated_amount", flt(self.amount) - flt(self.allocated_amount))
	
	def on_cancel(self):
		self.db_set("status", "Cancelled")
	
	def allocate_to_invoice(self, invoice: str, allocation_amount: float):
		"""
		Allocate advance amount to an invoice.
		
		Args:
			invoice: Sales Invoice name
			allocation_amount: Amount to allocate
		"""
		allocation_amount = flt(allocation_amount)
		
		if allocation_amount <= 0:
			frappe.throw(_("Allocation amount must be greater than zero"))
		
		if allocation_amount > flt(self.unallocated_amount):
			frappe.throw(_("Allocation amount {0} exceeds unallocated amount {1}").format(
				allocation_amount, self.unallocated_amount
			))
		
		# Update allocated amount
		new_allocated = flt(self.allocated_amount) + allocation_amount
		new_unallocated = flt(self.amount) - new_allocated
		
		self.db_set({
			"allocated_amount": new_allocated,
			"unallocated_amount": new_unallocated,
			"linked_invoice": invoice
		})
		
		# Update status
		if new_unallocated <= 0:
			self.db_set("status", "Fully Utilized")
		else:
			self.db_set("status", "Partially Utilized")
		
		return {
			"allocated": new_allocated,
			"unallocated": new_unallocated
		}


# ============================================
# API Functions for Advance Management
# ============================================

@frappe.whitelist()
def get_bill_item_advances(boq_item: str) -> list:
	"""
	Get all advances for a specific BOQ Item.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		List of advance records
	"""
	advances = frappe.db.sql("""
		SELECT 
			name, project, bill_no, boq_item, date, 
			amount, allocated_amount, unallocated_amount, 
			status, reference, linked_invoice
		FROM `tabBOQ Advance Payment`
		WHERE boq_item = %s AND docstatus = 1
		ORDER BY date DESC
	""", boq_item, as_dict=True)
	
	return advances


@frappe.whitelist()
def get_available_advances(boq_item: str = None, bill_no: str = None, project: str = None) -> list:
	"""
	Get advances with unallocated amounts for allocation to invoices.
	Can filter by boq_item, bill_no, or project (in that priority order).
	
	Args:
		boq_item: Optional BOQ Item name
		bill_no: Optional Bill No
		project: Optional Project name
		
	Returns:
		List of advances with unallocated amounts
	"""
	filters = ["docstatus = 1", "unallocated_amount > 0", "status != 'Cancelled'"]
	params = []
	
	if boq_item:
		filters.append("boq_item = %s")
		params.append(boq_item)
	elif bill_no:
		filters.append("bill_no = %s")
		params.append(bill_no)
	elif project:
		filters.append("project = %s")
		params.append(project)
	else:
		return []
	
	advances = frappe.db.sql("""
		SELECT 
			name, project, bill_no, boq_item, date, 
			amount, allocated_amount, unallocated_amount,
			reference
		FROM `tabBOQ Advance Payment`
		WHERE {filters}
		ORDER BY date ASC
	""".format(filters=" AND ".join(filters)), tuple(params), as_dict=True)
	
	return advances


@frappe.whitelist()
def get_project_advances(project: str) -> dict:
	"""
	Get aggregated advance summary for a project.
	
	Args:
		project: Project name
		
	Returns:
		dict with total_advances, allocated, unallocated, by_bill summary
	"""
	# Get totals
	totals = frappe.db.sql("""
		SELECT 
			COALESCE(SUM(amount), 0) as total_advances,
			COALESCE(SUM(allocated_amount), 0) as allocated,
			COALESCE(SUM(unallocated_amount), 0) as unallocated
		FROM `tabBOQ Advance Payment`
		WHERE project = %s AND docstatus = 1 AND status != 'Cancelled'
	""", project, as_dict=True)[0]
	
	# Get by bill summary
	by_bill = frappe.db.sql("""
		SELECT 
			COALESCE(bill_no, 'Unassigned') as bill_no,
			SUM(amount) as total_advances,
			SUM(allocated_amount) as allocated,
			SUM(unallocated_amount) as unallocated,
			COUNT(*) as count
		FROM `tabBOQ Advance Payment`
		WHERE project = %s AND docstatus = 1 AND status != 'Cancelled'
		GROUP BY bill_no
		ORDER BY bill_no
	""", project, as_dict=True)
	
	return {
		"total_advances": flt(totals.get("total_advances")),
		"allocated": flt(totals.get("allocated")),
		"unallocated": flt(totals.get("unallocated")),
		"by_bill": by_bill
	}


@frappe.whitelist()
def get_bill_advances(bill_no: str) -> dict:
	"""
	Get aggregated advance summary for a specific bill.
	
	Args:
		bill_no: Bill No name
		
	Returns:
		dict with total, allocated, unallocated
	"""
	totals = frappe.db.sql("""
		SELECT 
			COALESCE(SUM(amount), 0) as total_advances,
			COALESCE(SUM(allocated_amount), 0) as allocated,
			COALESCE(SUM(unallocated_amount), 0) as unallocated
		FROM `tabBOQ Advance Payment`
		WHERE bill_no = %s AND docstatus = 1 AND status != 'Cancelled'
	""", bill_no, as_dict=True)[0]
	
	return {
		"total_advances": flt(totals.get("total_advances")),
		"allocated": flt(totals.get("allocated")),
		"unallocated": flt(totals.get("unallocated"))
	}


@frappe.whitelist()
def allocate_advance(advance: str, invoice: str, amount: float) -> dict:
	"""
	Allocate an advance payment to a sales invoice.
	
	Args:
		advance: BOQ Advance Payment name
		invoice: Sales Invoice name
		amount: Amount to allocate
		
	Returns:
		dict with allocation result
	"""
	if not frappe.db.exists("BOQ Advance Payment", advance):
		frappe.throw(_("Advance {0} not found").format(advance))
	
	if not frappe.db.exists("Sales Invoice", invoice):
		frappe.throw(_("Invoice {0} not found").format(invoice))
	
	adv_doc = frappe.get_doc("BOQ Advance Payment", advance)
	
	if adv_doc.docstatus != 1:
		frappe.throw(_("Advance must be submitted before allocation"))
	
	result = adv_doc.allocate_to_invoice(invoice, flt(amount))
	
	# Create allocation record in Sales Invoice if custom field exists
	try:
		inv = frappe.get_doc("Sales Invoice", invoice)
		if hasattr(inv, "custom_advance_allocated"):
			current_allocated = flt(inv.custom_advance_allocated)
			inv.db_set("custom_advance_allocated", current_allocated + flt(amount))
	except Exception:
		pass
	
	frappe.db.commit()
	
	return result
