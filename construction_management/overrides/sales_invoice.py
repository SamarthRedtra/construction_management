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
	Create or Update a BOQ Progress Ledger entry for an invoice item.
	Updates existing PC/PI ledger entry if found to maintain single-row-per-cycle.
	
	Args:
		invoice: Sales Invoice document
		item: Sales Invoice Item
	"""
	from construction_management.api.boq_ledger import create_ledger_entry, recalculate_ledger_for_item
	
	boq_item = item.boq_item
	
	# Try to find an existing ledger entry to update
	# Case 1: Invoice linked to Payment Certificate (Standard Flow)
	ledger_entry = None
	if invoice.custom_payment_certificate:
		ledger_entry = frappe.db.get_value("BOQ Progress Ledger", {
			"payment_certificate": invoice.custom_payment_certificate,
			"boq_item": boq_item,
		}, "name")
	
	# Case 2: Invoice linked directly to Proforma Invoice (Direct Conversion)
	if not ledger_entry and invoice.get("custom_proforma_invoice"):
		ledger_entry = frappe.db.get_value("BOQ Progress Ledger", {
			"proforma_invoice": invoice.custom_proforma_invoice,
			"boq_item": boq_item,
		}, "name")
		
	if ledger_entry:
		# Update existing entry with Tax Invoice details
		frappe.db.set_value(
			"BOQ Progress Ledger",
			ledger_entry,
			{
				"tax_invoice": invoice.name,
				"tax_invoice_amount": flt(item.amount),
				"source": "Invoice" # Mark source as Invoice now that TI exists
			},
			update_modified=False
		)
		
		recalculate_ledger_for_item(boq_item)
		return

	# Case 2: Proforma to Invoice Direct Conversion (Rare but possible)
	# Check for linked PI if custom field exists or via item link?
	# Assuming standard flow PI -> PC -> TI.
	
	# If no existing entry found:
	# - If this invoice belongs to a PI/PC chain but ledger row is missing, do not create a duplicate; log instead.
	if invoice.custom_payment_certificate or invoice.get("custom_proforma_invoice"):
		frappe.logger().warning(
			f"Missing ledger row for BOQ Item {boq_item} on invoice {invoice.name}; skipping creation to avoid duplication."
		)
		return
	
	# - Otherwise (direct invoice not tied to PI/PC), create a new ledger entry if not already existing
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
		frappe.logger().info(f"Ledger entry already exists for {invoice.name} / {boq_item}, skipping duplicate.")
		return
	
	create_ledger_entry(
		boq_item=boq_item,
		qty=flt(item.qty),
		amount=flt(item.amount),
		source="Invoice",
		reference_doctype="Sales Invoice",
		reference_name=invoice.name,
		posting_date=invoice.posting_date or today(),
		remarks=f"Invoice {invoice.name}",
		tax_invoice=invoice.name,
		tax_invoice_amount=flt(item.amount)
	)
	
	recalculate_ledger_for_item(boq_item)
	frappe.logger().info(f"Created ledger entry for BOQ Item {item.boq_item} from invoice {invoice.name}")


def create_boq_reversal_entry(invoice, item):
	"""
	Undo Tax Invoice impact on the existing BOQ Progress Ledger row.
	
	Args:
		invoice: Sales Invoice document
		item: Sales Invoice Item
	"""
	from construction_management.api.boq_ledger import recalculate_ledger_for_item
	
	boq_item = item.boq_item
	
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
		frappe.db.set_value(
			"BOQ Progress Ledger",
			ledger_entry,
			{
				"tax_invoice": None,
				"tax_invoice_amount": 0,
				"remarks": f"Reversal of Invoice {invoice.name}",
				"source": "Proforma" if invoice.get("custom_proforma_invoice") else "Adjustment"
			},
			update_modified=False
		)
		recalculate_ledger_for_item(boq_item)
		frappe.logger().info(f"Updated ledger row for BOQ Item {boq_item} after cancelling invoice {invoice.name}")


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
