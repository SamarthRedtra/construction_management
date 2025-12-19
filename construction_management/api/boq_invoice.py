# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt, today


@frappe.whitelist()
def create_invoice_from_boq_item(project: str, boq_item: str, current_qty: float) -> dict:
	"""
	Create a Sales Invoice from a BOQ Item with the specified current quantity.
	
	Args:
		project: Project name
		boq_item: BOQ Item name
		current_qty: Quantity to bill
		
	Returns:
		dict with invoice details
	"""
	current_qty = flt(current_qty)
	
	# Validate
	if current_qty <= 0:
		frappe.throw(_("Quantity must be greater than zero"))
	
	# Get BOQ Item
	item = frappe.get_doc("BOQ Item", boq_item)
	
	# Validate balance
	from construction_management.api.boq_ledger import get_to_date_qty
	to_date_qty = get_to_date_qty(boq_item)
	balance_qty = flt(item.total_qty) - flt(to_date_qty)
	
	if current_qty > balance_qty:
		frappe.throw(
			_("Quantity ({0}) exceeds available balance ({1})").format(
				current_qty, balance_qty
			),
			title=_("Over-Billing Error")
		)
	
	# Calculate amount
	current_amount = flt(current_qty) * flt(item.rate)
	
	# Get project details for customer
	project_doc = frappe.get_doc("Project", project)
	customer = project_doc.customer if hasattr(project_doc, 'customer') and project_doc.customer else None
	
	if not customer:
		frappe.throw(_("Project must have a customer assigned to create invoice"))
	
	# Ensure linked_item exists - create if not
	if not item.linked_item:
		item.create_linked_item()
		item.reload()
	
	# Get the item_code to use - prefer linked_item, fallback to item_code
	invoice_item_code = item.linked_item or item.item_code
	
	# Validate item exists in ERPNext
	if not invoice_item_code or not frappe.db.exists("Item", invoice_item_code):
		frappe.throw(
			_("No valid Item found for BOQ Item {0}. Please ensure the linked item exists.").format(boq_item),
			title=_("Item Not Found")
		)
	
	# Create Sales Invoice
	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = customer
	invoice.project = project
	invoice.posting_date = today()
	invoice.due_date = today()
	
	# Add item - use linked_item for item_code
	invoice.append("items", {
		"item_code": invoice_item_code,
		"item_name": item.description[:140] if item.description else "BOQ Item",
		"description": item.description,
		"qty": current_qty,
		"rate": item.rate,
		"amount": current_amount,
		"uom": item.unit,
		"boq_item": boq_item,
		"bill_no": item.parent_bill
	})
	
	invoice.insert()
	
	# Update BOQ Item current_qty
	item.current_qty = 0  # Reset after creating invoice
	item.save()
	
	return {
		"invoice": invoice.name,
		"customer": customer,
		"qty": current_qty,
		"amount": current_amount,
		"status": "Draft"
	}


@frappe.whitelist()
def create_invoice_from_multiple_items(project: str, items: list) -> dict:
	"""
	Create a single Sales Invoice from multiple BOQ Items.
	
	Args:
		project: Project name
		items: List of dicts with boq_item and current_qty
		
	Returns:
		dict with invoice details
	"""
	if isinstance(items, str):
		import json
		items = json.loads(items)
	
	if not items:
		frappe.throw(_("No items provided"))
	
	# Get project details
	project_doc = frappe.get_doc("Project", project)
	customer = project_doc.customer if hasattr(project_doc, 'customer') and project_doc.customer else None
	
	if not customer:
		frappe.throw(_("Project must have a customer assigned to create invoice"))
	
	# Create Sales Invoice
	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = customer
	invoice.project = project
	invoice.posting_date = today()
	invoice.due_date = today()
	
	total_amount = 0
	
	for item_data in items:
		boq_item_name = item_data.get("boq_item")
		current_qty = flt(item_data.get("current_qty", 0))
		
		if current_qty <= 0:
			continue
		
		# Get BOQ Item
		item = frappe.get_doc("BOQ Item", boq_item_name)
		
		# Validate balance
		from construction_management.api.boq_ledger import get_to_date_qty
		to_date_qty = get_to_date_qty(boq_item_name)
		balance_qty = flt(item.total_qty) - flt(to_date_qty)
		
		if current_qty > balance_qty:
			frappe.throw(
				_("Quantity ({0}) exceeds available balance ({1}) for item {2}").format(
					current_qty, balance_qty, item.description[:50]
				),
				title=_("Over-Billing Error")
			)
		
		current_amount = flt(current_qty) * flt(item.rate)
		total_amount += current_amount
		
		# Ensure linked_item exists - create if not
		if not item.linked_item:
			item.create_linked_item()
			item.reload()
		
		# Get the item_code to use - prefer linked_item, fallback to item_code
		invoice_item_code = item.linked_item or item.item_code
		
		# Skip if no valid item
		if not invoice_item_code or not frappe.db.exists("Item", invoice_item_code):
			frappe.msgprint(
				_("Skipping BOQ Item {0} - no valid linked Item found").format(item.description[:50]),
				indicator="orange"
			)
			continue
		
		# Add item to invoice
		invoice.append("items", {
			"item_code": invoice_item_code,
			"item_name": item.description[:140] if item.description else "BOQ Item",
			"description": item.description,
			"qty": current_qty,
			"rate": item.rate,
			"amount": current_amount,
			"uom": item.unit,
			"boq_item": boq_item_name,
			"bill_no": item.parent_bill
		})
	
	if not invoice.items:
		frappe.throw(_("No valid items to invoice"))
	
	invoice.insert()
	
	# Reset current_qty on all BOQ Items
	for item_data in items:
		if flt(item_data.get("current_qty", 0)) > 0:
			frappe.db.set_value("BOQ Item", item_data.get("boq_item"), "current_qty", 0)
	
	return {
		"invoice": invoice.name,
		"customer": customer,
		"item_count": len(invoice.items),
		"total_amount": total_amount,
		"status": "Draft"
	}


@frappe.whitelist()
def get_boq_invoice_history(boq_item: str) -> dict:
	"""
	Get invoice history for a BOQ Item (Child Payment Plan).
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		dict with invoice summary and details including unit, rate, pay_cert
	"""
	# Get BOQ Item details for unit
	boq_item_doc = frappe.get_doc("BOQ Item", boq_item)
	
	# Get all invoices for this BOQ Item
	invoices = frappe.db.sql("""
		SELECT 
			si.name,
			si.posting_date,
			si.status,
			si.grand_total,
			si.outstanding_amount,
			sii.qty,
			sii.rate,
			sii.amount,
			sii.uom as unit
		FROM `tabSales Invoice` si
		JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		WHERE sii.boq_item = %s
		AND si.docstatus = 1
		ORDER BY si.posting_date DESC
	""", boq_item, as_dict=True)
	
	# Add pay_cert (payment certificate) info - check if invoice is linked to any payment
	for inv in invoices:
		# Check for payment entries linked to this invoice
		payment_entry = frappe.db.get_value(
			"Payment Entry Reference",
			{"reference_name": inv.name, "reference_doctype": "Sales Invoice"},
			"parent"
		)
		inv["pay_cert"] = payment_entry if payment_entry else None
		
		# Use BOQ Item unit if not set on invoice item
		if not inv.get("unit"):
			inv["unit"] = boq_item_doc.unit
	
	# Calculate summary
	total_invoiced = sum(flt(inv.amount) for inv in invoices)
	total_collected = sum(flt(inv.amount) for inv in invoices if inv.status == "Paid")
	total_outstanding = sum(flt(inv.outstanding_amount) for inv in invoices)
	
	return {
		"summary": {
			"invoice_count": len(invoices),
			"total_invoiced": total_invoiced,
			"total_collected": total_collected,
			"pending": total_invoiced - total_collected
		},
		"invoices": invoices
	}
