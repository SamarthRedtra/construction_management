# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt, today


def before_insert(doc, method):
	"""Auto-set BOQ dimensions on Sales Invoice Items"""
	for item in doc.items:
		if item.get("boq_item"):
			# Fetch BOQ Item details
			boq_item = frappe.get_doc("BOQ Item", item.boq_item)
			
			# Set dimensions
			item.bill_no = boq_item.parent_bill
			
			# Ensure boq_item is set (it should already be)
			if not item.boq_item:
				item.boq_item = boq_item.name


def on_submit(doc, method):
	"""Create ledger entries for BOQ items on invoice submit"""
	for item in doc.items:
		if item.get("boq_item"):
			create_boq_ledger_entry(doc, item)
			update_boq_item_after_invoice(item.boq_item)
	
	# Update project completion percentage
	if doc.project:
		from construction_management.api.project_completion import update_project_completion
		try:
			update_project_completion(doc.project)
		except Exception as e:
			frappe.log_error(f"Error updating project completion: {str(e)}")


def on_cancel(doc, method):
	"""Create reversing ledger entries on invoice cancel"""
	for item in doc.items:
		if item.get("boq_item"):
			create_boq_reversal_entry(doc, item)
			update_boq_item_after_invoice(item.boq_item)
	
	# Update project completion percentage
	if doc.project:
		from construction_management.api.project_completion import update_project_completion
		try:
			update_project_completion(doc.project)
		except Exception as e:
			frappe.log_error(f"Error updating project completion: {str(e)}")


def create_boq_ledger_entry(invoice, item):
	"""
	Create a BOQ Progress Ledger entry for an invoice item.
	
	Args:
		invoice: Sales Invoice document
		item: Sales Invoice Item
	"""
	from construction_management.construction_management.doctype.boq_progress_ledger.boq_progress_ledger import BOQProgressLedger
	
	# Get BOQ Item details
	boq_item = frappe.get_doc("BOQ Item", item.boq_item)
	
	BOQProgressLedger.create_entry(
		project=boq_item.project,
		project_boq=boq_item.project_boq,
		bill_no=boq_item.parent_bill,
		boq_item=item.boq_item,
		posting_date=invoice.posting_date or today(),
		qty=flt(item.qty),
		amount=flt(item.amount),
		source="Invoice",
		reference_doctype="Sales Invoice",
		reference_name=invoice.name,
		remarks=f"Invoice {invoice.name}"
	)
	
	frappe.logger().info(f"Created ledger entry for BOQ Item {item.boq_item} from invoice {invoice.name}")


def create_boq_reversal_entry(invoice, item):
	"""
	Create a reversing BOQ Progress Ledger entry for a cancelled invoice.
	
	Args:
		invoice: Sales Invoice document
		item: Sales Invoice Item
	"""
	from construction_management.construction_management.doctype.boq_progress_ledger.boq_progress_ledger import BOQProgressLedger
	
	# Get BOQ Item details
	boq_item = frappe.get_doc("BOQ Item", item.boq_item)
	
	BOQProgressLedger.create_entry(
		project=boq_item.project,
		project_boq=boq_item.project_boq,
		bill_no=boq_item.parent_bill,
		boq_item=item.boq_item,
		posting_date=today(),
		qty=-flt(item.qty),  # Negative for reversal
		amount=-flt(item.amount),  # Negative for reversal
		source="Reversal",
		reference_doctype="Sales Invoice",
		reference_name=invoice.name,
		remarks=f"Reversal of Invoice {invoice.name}"
	)
	
	frappe.logger().info(f"Created reversal entry for BOQ Item {item.boq_item} from cancelled invoice {invoice.name}")


def update_boq_item_after_invoice(boq_item_name):
	"""
	Update BOQ Item calculated fields after invoice submit/cancel.
	
	Args:
		boq_item_name: BOQ Item name
	"""
	boq_item = frappe.get_doc("BOQ Item", boq_item_name)
	
	# Reset current_qty after invoicing
	boq_item.current_qty = 0
	
	# Recalculate amounts (this will fetch from ledger)
	boq_item.calculate_amounts()
	boq_item.update_billing_status()
	boq_item.db_update()
	
	# Update parent bill totals
	if boq_item.parent_bill:
		bill = frappe.get_doc("BOQ Bill", boq_item.parent_bill)
		bill.calculate_totals()
		bill.db_update()
	
	# Update Project BOQ totals
	if boq_item.project_boq:
		project_boq = frappe.get_doc("Project BOQ", boq_item.project_boq)
		project_boq.calculate_totals()
		project_boq.db_update()
