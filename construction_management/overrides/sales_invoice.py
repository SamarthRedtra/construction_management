# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt, today


def validate(doc, method):
	"""Server-side validation and automatic deductions"""
	if doc.project and doc.docstatus == 0:
		apply_automatic_deductions(doc)


def apply_automatic_deductions(doc):
	"""Automatically apply retention and advance deductions if enabled"""
	from construction_management.api.boq_invoice import get_deduction_details, get_or_create_retention_item, get_or_create_advance_item
	
	details = get_deduction_details(doc.project, doc.items, invoice_name=doc.name)
	
	if not details.get("enable_progressive_boq"):
		return
		
	# Common defaults for deduction items
	default_income_account = frappe.db.get_value("Company", doc.company, "default_income_account")
	default_cost_center = frappe.db.get_value("Company", doc.company, "cost_center")
	
	# 1. Handle Retention Deduction
	if details.get("suggested_retention") > 0:
		retention_item = "RETENTION-DEDUCTION"
		get_or_create_retention_item() # Ensure it exists
		
		# Find existing or add new
		found = False
		for item in doc.items:
			if item.item_code == retention_item:
				item.rate = -flt(details["suggested_retention"])
				item.amount = -flt(details["suggested_retention"])
				item.qty = 1
				item.description = f"Retention deduction ({details['retention_percentage']}%)"
				item.project = doc.project
				found = True
				break
		
		if not found:
			doc.append("items", {
				"item_code": retention_item,
				"qty": 1,
				"rate": -flt(details["suggested_retention"]),
				"amount": -flt(details["suggested_retention"]),
				"description": f"Retention deduction ({details['retention_percentage']}%)",
				"project": doc.project,
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
		for item in doc.items:
			if item.item_code == advance_item:
				item.rate = -flt(details["suggested_advance"])
				item.amount = -flt(details["suggested_advance"])
				item.qty = 1
				item.description = "Deduction from advance payment"
				item.project = doc.project
				found = True
				break
		
		if not found:
			doc.append("items", {
				"item_code": advance_item,
				"qty": 1,
				"rate": -flt(details["suggested_advance"]),
				"amount": -flt(details["suggested_advance"]),
				"description": "Deduction from advance payment",
				"project": doc.project,
				"income_account": default_income_account,
				"cost_center": default_cost_center,
				"uom": "Nos",
				"conversion_factor": 1.0,
				"item_name": "Advance Deduction"
			})

	# Recalculate totals to handle the new items
	doc.run_method("calculate_taxes_and_totals")


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
	
	# Create retention entry if applicable
	if doc.get("custom_retention_amount") and flt(doc.custom_retention_amount) > 0:
		create_retention_entry(doc)
	
	# Update project completion percentage
	if doc.project:
		from construction_management.api.project_completion import update_project_completion
		try:
			update_project_completion(doc.project)
		except Exception as e:
			frappe.log_error(f"Error updating project completion: {str(e)}")


def on_update(doc, method):
	"""Handle status changes on update"""
	if doc.get("custom_is_advanced") and doc.status == "Paid" and doc.docstatus == 1:
		print("sshshhs")
		create_boq_advance_payment_from_invoice(doc)


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


def on_cancel(doc, method):
	"""Create reversing ledger entries on invoice cancel"""
	for item in doc.items:
		if item.get("boq_item"):
			create_boq_reversal_entry(doc, item)
			update_boq_item_after_invoice(item.boq_item)
	
	# Cancel retention entry if applicable
	if doc.get("custom_retention_amount"):
		cancel_retention_entry(doc)
	
	# Update project completion percentage
	if doc.project:
		from construction_management.api.project_completion import update_project_completion
		try:
			update_project_completion(doc.project)
		except Exception as e:
			frappe.log_error(f"Error updating project completion: {str(e)}")


def create_retention_entry(invoice):
	"""Create Journal Entry for retention amount: Debit Retention, Credit Customer"""
	retention_account = invoice.get("custom_retention_account")
	if not retention_account:
		# Fallback to BOQ Settings
		retention_account = frappe.db.get_value("BOQ Settings", invoice.company, "retention_account")
		
	if not retention_account:
		frappe.msgprint(_("Retention Account not found in BOQ Settings for company {0}. Skipping Journal Entry.").format(invoice.company))
		return

	# Debit: Retention Account, Credit: Customer
	jv = frappe.new_doc("Journal Entry")
	jv.posting_date = invoice.posting_date
	jv.company = invoice.company
	jv.user_remark = f"Retention for Sales Invoice {invoice.name}"
	
	jv.append("accounts", {
		"account": retention_account,
		"debit_in_account_currency": flt(invoice.custom_retention_amount),
		"project": invoice.project
	})
	
	jv.append("accounts", {
		"account": invoice.debit_to, # Customer account
		"credit_in_account_currency": flt(invoice.custom_retention_amount),
		"party_type": "Customer",
		"party": invoice.customer,
		"project": invoice.project,
		"reference_type": "Sales Invoice",
		"reference_name": invoice.name
	})
	
	jv.flags.ignore_permissions = True
	jv.insert()
	jv.submit()
	frappe.msgprint(_("Retention Journal Entry {0} created").format(jv.name))

def cancel_retention_entry(invoice):
	"""Cancel linked retention Journal Entry"""
	jv_names = frappe.db.get_all("Journal Entry Account", filters={
		"reference_type": "Sales Invoice",
		"reference_name": invoice.name,
		"party": invoice.customer,
		"credit_in_account_currency": [">", 0],
		"docstatus": 1
	}, pluck="parent")
	
	for jv_name in jv_names:
		jv = frappe.get_doc("Journal Entry", jv_name)
		jv.cancel()
		frappe.msgprint(_("Retention Journal Entry {0} cancelled").format(jv_name))


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

	# Case 3: Invoice linked directly to Sales Order (Direct Conversion)
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
	# - If this invoice belongs to a PI/PC/SO chain but ledger row is missing, do not create a duplicate; log instead.
	if invoice.custom_payment_certificate or invoice.get("custom_proforma_invoice") or any(it.get("sales_order") for it in invoice.items):
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
	For orphan SIs (no PI/PC), delete the ledger entry entirely.
	
	Args:
		invoice: Sales Invoice document
		item: Sales Invoice Item
	"""
	from construction_management.api.boq_ledger import recalculate_ledger_for_item
	
	boq_item = item.boq_item
	
	# Check if this is an orphan SI (created outside PI/PC flow)
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
			# Delete the ledger entry for orphan SI
			# Set flag to allow deletion during Sales Invoice cancellation
			frappe.flags.allow_boq_ledger_deletion = True
			try:
				frappe.delete_doc("BOQ Progress Ledger", ledger_entry, force=1, ignore_permissions=True)
				frappe.logger().info(f"Deleted orphan SI ledger entry for BOQ Item {boq_item} from invoice {invoice.name}")
			finally:
				# Always clear the flag after deletion attempt
				frappe.flags.allow_boq_ledger_deletion = False
		else:
			# Clear TI fields for linked SI (PI/PC flow)
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
			frappe.logger().info(f"Updated ledger row for BOQ Item {boq_item} after cancelling invoice {invoice.name}")
		
		recalculate_ledger_for_item(boq_item)


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
