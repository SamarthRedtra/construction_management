# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt, today, getdate


@frappe.whitelist()
def create_invoice_from_boq_item(project: str, boq_item: str, current_qty: float, 
                                  apply_retention: int = 1, advance_deduction: float = 0,
                                  is_proforma: int = 0) -> dict:
	"""
	Create a Sales Invoice from a BOQ Item with the specified current quantity.
	
	Args:
		project: Project name
		boq_item: BOQ Item name
		current_qty: Quantity to bill
		apply_retention: Whether to apply retention (1=yes, 0=no)
		advance_deduction: Amount to deduct from advance
		is_proforma: Whether to create as proforma invoice (1=yes, 0=no)
		
	Returns:
		dict with invoice details
	"""
	current_qty = flt(current_qty)
	apply_retention = int(apply_retention)
	advance_deduction = flt(advance_deduction)
	is_proforma = int(is_proforma)
	
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
	
	# Get project details for customer and retention
	project_doc = frappe.get_doc("Project", project)
	customer = project_doc.customer if hasattr(project_doc, 'customer') and project_doc.customer else None
	retention_percentage = flt(project_doc.retention_percentage) if hasattr(project_doc, 'retention_percentage') else 0
	
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
	
	# Set proforma flag if requested
	if is_proforma:
		invoice.custom_is_proforma = 1
	
	# Add item - use linked_item for item_code with accounting dimensions
	invoice.append("items", {
		"item_code": invoice_item_code,
		"item_name": item.description[:140] if item.description else "BOQ Item",
		"description": item.description,
		"qty": current_qty,
		"rate": item.rate,
		"amount": current_amount,
		"uom": item.unit,
		"boq_item": boq_item,
		"bill_no": item.parent_bill,
		"project": project  # Set project on item level for accounting dimension
	})
	
	# Calculate retention
	retention_amount = 0
	if apply_retention and retention_percentage > 0 and not is_proforma:
		retention_amount = flt(current_amount * retention_percentage / 100, 2)
		# Add retention as a negative line item (deduction)
		if retention_amount > 0:
			# Get or create retention item
			retention_item = get_or_create_retention_item()
			invoice.append("items", {
				"item_code": retention_item,
				"item_name": f"Retention ({retention_percentage}%)",
				"description": f"Retention deduction at {retention_percentage}%",
				"qty": 1,
				"rate": -retention_amount,
				"amount": -retention_amount,
				"project": project  # Set project on item level
			})
	
	# Handle advance deduction
	if advance_deduction > 0 and not is_proforma:
		# Validate advance balance
		advance_balance = get_advance_balance(project)
		if advance_deduction > advance_balance:
			frappe.throw(
				_("Advance deduction ({0}) exceeds available advance balance ({1})").format(
					advance_deduction, advance_balance
				),
				title=_("Advance Deduction Error")
			)
		
		# Add advance deduction as negative line item
		advance_item = get_or_create_advance_item()
		invoice.append("items", {
			"item_code": advance_item,
			"item_name": "Advance Deduction",
			"description": "Deduction from advance payment",
			"qty": 1,
			"rate": -advance_deduction,
			"amount": -advance_deduction,
			"project": project  # Set project on item level
		})
	
	invoice.insert()
	
	# Update BOQ Item current_qty
	item.current_qty = 0  # Reset after creating invoice
	item.save()
	
	# Calculate net amount
	net_amount = current_amount - retention_amount - advance_deduction
	
	return {
		"invoice": invoice.name,
		"customer": customer,
		"qty": current_qty,
		"gross_amount": current_amount,
		"retention_amount": retention_amount,
		"advance_deduction": advance_deduction,
		"net_amount": net_amount,
		"status": "Draft",
		"is_proforma": is_proforma
	}


@frappe.whitelist()
def create_invoice_from_multiple_items(project: str, items: list, 
                                        apply_retention: int = 1, advance_deduction: float = 0) -> dict:
	"""
	Create a single Sales Invoice from multiple BOQ Items.
	
	Args:
		project: Project name
		items: List of dicts with boq_item and current_qty
		apply_retention: Whether to apply retention (1=yes, 0=no)
		advance_deduction: Amount to deduct from advance
		
	Returns:
		dict with invoice details
	"""
	if isinstance(items, str):
		import json
		items = json.loads(items)
	
	if not items:
		frappe.throw(_("No items provided"))
	
	apply_retention = int(apply_retention)
	advance_deduction = flt(advance_deduction)
	
	# Get project details
	project_doc = frappe.get_doc("Project", project)
	customer = project_doc.customer if hasattr(project_doc, 'customer') and project_doc.customer else None
	retention_percentage = flt(project_doc.retention_percentage) if hasattr(project_doc, 'retention_percentage') else 0
	
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
			"bill_no": item.parent_bill,
			"project": project  # Set project on item level for accounting dimension
		})
	
	if not invoice.items:
		frappe.throw(_("No valid items to invoice"))
	
	# Calculate retention
	retention_amount = 0
	if apply_retention and retention_percentage > 0:
		retention_amount = flt(total_amount * retention_percentage / 100, 2)
		if retention_amount > 0:
			retention_item = get_or_create_retention_item()
			invoice.append("items", {
				"item_code": retention_item,
				"item_name": f"Retention ({retention_percentage}%)",
				"description": f"Retention deduction at {retention_percentage}%",
				"qty": 1,
				"rate": -retention_amount,
				"amount": -retention_amount,
				"project": project  # Set project on item level
			})
	
	# Handle advance deduction
	if advance_deduction > 0:
		advance_balance = get_advance_balance(project)
		if advance_deduction > advance_balance:
			frappe.throw(
				_("Advance deduction ({0}) exceeds available advance balance ({1})").format(
					advance_deduction, advance_balance
				),
				title=_("Advance Deduction Error")
			)
		
		advance_item = get_or_create_advance_item()
		invoice.append("items", {
			"item_code": advance_item,
			"item_name": "Advance Deduction",
			"description": "Deduction from advance payment",
			"qty": 1,
			"rate": -advance_deduction,
			"amount": -advance_deduction,
			"project": project  # Set project on item level
		})
	
	invoice.insert()
	
	# Reset current_qty on all BOQ Items
	for item_data in items:
		if flt(item_data.get("current_qty", 0)) > 0:
			frappe.db.set_value("BOQ Item", item_data.get("boq_item"), "current_qty", 0)
	
	net_amount = total_amount - retention_amount - advance_deduction
	
	return {
		"invoice": invoice.name,
		"customer": customer,
		"item_count": len([i for i in invoice.items if flt(i.rate) > 0]),
		"gross_amount": total_amount,
		"retention_amount": retention_amount,
		"advance_deduction": advance_deduction,
		"net_amount": net_amount,
		"status": "Draft"
	}


@frappe.whitelist()
def create_invoice_from_selected_bills(project: str, bill_names: list, 
                                        apply_retention: int = 1, advance_deduction: float = 0,
                                        is_proforma: int = 0) -> dict:
	"""
	Create a single Sales Invoice from all items with current_qty > 0 in selected bills.
	
	Args:
		project: Project name
		bill_names: List of BOQ Bill names to include
		apply_retention: Whether to apply retention (1=yes, 0=no)
		advance_deduction: Amount to deduct from advance
		is_proforma: Whether to create as proforma invoice (1=yes, 0=no)
		
	Returns:
		dict with invoice details
	"""
	if isinstance(bill_names, str):
		import json
		bill_names = json.loads(bill_names)
	
	if not bill_names:
		frappe.throw(_("No bills selected"))
	
	apply_retention = int(apply_retention)
	advance_deduction = flt(advance_deduction)
	is_proforma = int(is_proforma)
	
	# Get project details
	project_doc = frappe.get_doc("Project", project)
	customer = project_doc.customer if hasattr(project_doc, 'customer') and project_doc.customer else None
	retention_percentage = flt(project_doc.retention_percentage) if hasattr(project_doc, 'retention_percentage') else 0
	
	if not customer:
		frappe.throw(_("Project must have a customer assigned to create invoice"))
	
	# Get all BOQ Items with current_qty > 0 from selected bills
	items_to_bill = frappe.db.sql("""
		SELECT 
			bi.name as boq_item,
			bi.description,
			bi.unit,
			bi.rate,
			bi.total_qty,
			bi.current_qty,
			bi.linked_item,
			bi.item_code,
			bi.parent_bill,
			bb.bill_no
		FROM `tabBOQ Item` bi
		JOIN `tabBOQ Bill` bb ON bb.name = bi.parent_bill
		WHERE bi.parent_bill IN %s
		AND bi.current_qty > 0
		ORDER BY bb.bill_no, bi.name
	""", (tuple(bill_names),), as_dict=True)
	
	if not items_to_bill:
		frappe.throw(_("No items with current quantity found in selected bills"))
	
	# Create Sales Invoice
	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = customer
	invoice.project = project
	invoice.posting_date = today()
	invoice.due_date = today()
	
	# Set proforma flag if requested
	if is_proforma:
		invoice.custom_is_proforma = 1
	
	total_amount = 0
	items_added = 0
	bills_included = set()
	
	for item_data in items_to_bill:
		current_qty = flt(item_data.current_qty)
		
		if current_qty <= 0:
			continue
		
		# Validate balance
		from construction_management.api.boq_ledger import get_to_date_qty
		to_date_qty = get_to_date_qty(item_data.boq_item)
		balance_qty = flt(item_data.total_qty) - flt(to_date_qty)
		
		if current_qty > balance_qty:
			frappe.throw(
				_("Quantity ({0}) exceeds available balance ({1}) for item in {2}: {3}").format(
					current_qty, balance_qty, item_data.bill_no, item_data.description[:50]
				),
				title=_("Over-Billing Error")
			)
		
		current_amount = flt(current_qty) * flt(item_data.rate)
		total_amount += current_amount
		
		# Get the item_code to use - prefer linked_item, fallback to item_code
		invoice_item_code = item_data.linked_item or item_data.item_code
		
		# Ensure linked_item exists - create if not
		if not invoice_item_code:
			item_doc = frappe.get_doc("BOQ Item", item_data.boq_item)
			item_doc.create_linked_item()
			item_doc.reload()
			invoice_item_code = item_doc.linked_item
		
		# Skip if no valid item
		if not invoice_item_code or not frappe.db.exists("Item", invoice_item_code):
			frappe.msgprint(
				_("Skipping BOQ Item in {0}: {1} - no valid linked Item found").format(
					item_data.bill_no, item_data.description[:50]
				),
				indicator="orange"
			)
			continue
		
		# Add item to invoice
		invoice.append("items", {
			"item_code": invoice_item_code,
			"item_name": item_data.description[:140] if item_data.description else "BOQ Item",
			"description": f"[{item_data.bill_no}] {item_data.description}",
			"qty": current_qty,
			"rate": item_data.rate,
			"amount": current_amount,
			"uom": item_data.unit,
			"boq_item": item_data.boq_item,
			"bill_no": item_data.parent_bill,
			"project": project
		})
		
		items_added += 1
		bills_included.add(item_data.bill_no)
	
	if not invoice.items:
		frappe.throw(_("No valid items to invoice"))
	
	# Calculate retention
	retention_amount = 0
	if apply_retention and retention_percentage > 0 and not is_proforma:
		retention_amount = flt(total_amount * retention_percentage / 100, 2)
		if retention_amount > 0:
			retention_item = get_or_create_retention_item()
			invoice.append("items", {
				"item_code": retention_item,
				"item_name": f"Retention ({retention_percentage}%)",
				"description": f"Retention deduction at {retention_percentage}%",
				"qty": 1,
				"rate": -retention_amount,
				"amount": -retention_amount,
				"project": project
			})
	
	# Handle advance deduction
	if advance_deduction > 0 and not is_proforma:
		advance_balance = get_advance_balance(project)
		if advance_deduction > advance_balance:
			frappe.throw(
				_("Advance deduction ({0}) exceeds available advance balance ({1})").format(
					advance_deduction, advance_balance
				),
				title=_("Advance Deduction Error")
			)
		
		advance_item = get_or_create_advance_item()
		invoice.append("items", {
			"item_code": advance_item,
			"item_name": "Advance Deduction",
			"description": "Deduction from advance payment",
			"qty": 1,
			"rate": -advance_deduction,
			"amount": -advance_deduction,
			"project": project
		})
	
	invoice.insert()
	
	# Reset current_qty on all BOQ Items that were billed
	for item_data in items_to_bill:
		if flt(item_data.current_qty) > 0:
			frappe.db.set_value("BOQ Item", item_data.boq_item, "current_qty", 0)
	
	net_amount = total_amount - retention_amount - advance_deduction
	
	return {
		"invoice": invoice.name,
		"customer": customer,
		"item_count": items_added,
		"bills_included": list(bills_included),
		"gross_amount": total_amount,
		"retention_amount": retention_amount,
		"advance_deduction": advance_deduction,
		"net_amount": net_amount,
		"status": "Draft",
		"is_proforma": is_proforma
	}


@frappe.whitelist()
def get_bills_with_billable_items(project: str) -> list:
	"""
	Get all bills that have items with current_qty > 0 (ready to bill).
	
	Args:
		project: Project name
		
	Returns:
		list of bills with billable item counts and amounts
	"""
	bills = frappe.db.sql("""
		SELECT 
			bb.name,
			bb.bill_no,
			bb.description,
			COUNT(bi.name) as item_count,
			SUM(bi.current_qty) as total_qty,
			SUM(bi.current_qty * bi.rate) as total_amount
		FROM `tabBOQ Bill` bb
		JOIN `tabBOQ Item` bi ON bi.parent_bill = bb.name
		WHERE bb.project = %s
		AND bi.current_qty > 0
		GROUP BY bb.name, bb.bill_no, bb.description
		ORDER BY bb.bill_no
	""", project, as_dict=True)
	
	return bills


@frappe.whitelist()
def get_boq_invoice_history(boq_item: str) -> dict:
	"""
	Get invoice history for a BOQ Item (Child Payment Plan) with progressive billing details.
	Includes proforma invoices, payment certificates, and tax invoices tracking.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		dict with invoice summary, ledger entries, payment certificates with prev/curr/accumulated values
	"""
	# Get BOQ Item details
	boq_item_doc = frappe.get_doc("BOQ Item", boq_item)
	
	# Get all ledger entries for this BOQ Item (ordered by posting_date ASC for progressive tracking)
	ledger_entries = frappe.db.sql("""
		SELECT 
			pl.name,
			pl.posting_date,
			pl.source,
			pl.reference_doctype,
			pl.reference_name,
			pl.qty as transaction_qty,
			pl.amount as transaction_amount,
			pl.prev_qty,
			pl.prev_amount,
			pl.current_qty,
			pl.current_amount,
			pl.accumulated_qty,
			pl.accumulated_amount,
			pl.remarks,
			si.status as invoice_status,
			si.docstatus as invoice_docstatus,
			si.outstanding_amount,
			si.custom_is_proforma as is_proforma
		FROM `tabBOQ Progress Ledger` pl
		LEFT JOIN `tabSales Invoice` si 
			ON pl.reference_name = si.name 
			AND pl.reference_doctype = 'Sales Invoice'
			AND si.docstatus != 2
		WHERE pl.boq_item = %s
		ORDER BY pl.posting_date ASC, pl.creation ASC
	""", boq_item, as_dict=True)
	
	# Add payment certificate info and format data
	filtered_entries = []
	acc_qty = 0
	acc_amount = 0
	for entry in ledger_entries:
		# Skip cancelled invoices explicitly
		if entry.reference_doctype == "Sales Invoice" and entry.invoice_docstatus == 2:
			continue
		
		# Check for payment entries linked to this invoice
		if entry.reference_doctype == "Sales Invoice" and entry.reference_name:
			payment_entry = frappe.db.get_value(
				"Payment Entry Reference",
				{"reference_name": entry.reference_name, "reference_doctype": "Sales Invoice"},
				"parent"
			)
			entry["pay_cert"] = payment_entry if payment_entry else None
		else:
			entry["pay_cert"] = None
		
		# Add unit and rate from BOQ Item
		entry["unit"] = boq_item_doc.unit
		entry["rate"] = boq_item_doc.rate
		
		# Recompute progressive accumulated values excluding cancelled invoices
		acc_qty += flt(entry.current_qty)
		acc_amount += flt(entry.current_amount)
		entry["accumulated_qty"] = acc_qty
		entry["accumulated_amount"] = acc_amount
		
		filtered_entries.append(entry)
	
	# Get all invoices for summary calculation
	invoices = frappe.db.sql("""
		SELECT 
			si.name,
			si.status,
			si.custom_is_proforma as is_proforma,
			sii.amount
		FROM `tabSales Invoice` si
		JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		WHERE sii.boq_item = %s
		AND si.docstatus = 1
	""", boq_item, as_dict=True)
	
	# Calculate summary
	total_invoiced = sum(flt(inv.amount) for inv in invoices)
	total_collected = sum(flt(inv.amount) for inv in invoices if inv.status == "Paid")
	
	# Get BOQ Item totals for balance calculation
	total_qty = flt(boq_item_doc.total_qty)
	total_amount = flt(boq_item_doc.total_qty) * flt(boq_item_doc.rate)
	
	# Get latest accumulated values
	latest_accumulated_qty = flt(filtered_entries[-1].accumulated_qty) if filtered_entries else 0
	latest_accumulated_amount = flt(filtered_entries[-1].accumulated_amount) if filtered_entries else 0
	
	# Get payment certificates for this BOQ Item
	payment_certificates = frappe.db.sql("""
		SELECT 
			pc.name,
			pc.posting_date,
			pc.proforma_invoice,
			pc.proforma_amount,
			pc.accepted_amount,
			pc.variance,
			pc.tax_invoice,
			pc.status,
			pc.payment_received,
			pc.invoice_status
		FROM `tabPayment Certificate` pc
		WHERE pc.boq_item = %s
		AND pc.docstatus != 2
		ORDER BY pc.posting_date DESC
	""", boq_item, as_dict=True)
	
	# Get pending proformas (proforma invoices without payment certificate)
	pending_proformas = frappe.db.sql("""
		SELECT 
			si.name,
			si.posting_date,
			si.grand_total,
			si.customer,
			DATEDIFF(CURDATE(), si.posting_date) as age_days
		FROM `tabSales Invoice` si
		JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		WHERE sii.boq_item = %s
		AND si.docstatus = 0
		AND si.custom_is_proforma = 1
		AND NOT EXISTS (
			SELECT 1 FROM `tabPayment Certificate` pc 
			WHERE pc.proforma_invoice = si.name 
			AND pc.docstatus != 2
		)
		ORDER BY si.posting_date DESC
	""", boq_item, as_dict=True)
	
	# Calculate payment certificate summary
	pc_summary = {
		"total_proforma": sum(flt(pc.proforma_amount) for pc in payment_certificates),
		"total_accepted": sum(flt(pc.accepted_amount) for pc in payment_certificates),
		"total_variance": sum(flt(pc.variance) for pc in payment_certificates),
		"total_received": sum(flt(pc.payment_received) for pc in payment_certificates),
		"pending_proforma_count": len(pending_proformas),
		"pending_proforma_amount": sum(flt(p.grand_total) for p in pending_proformas)
	}
	
	return {
		"boq_item": {
			"name": boq_item_doc.name,
			"description": boq_item_doc.description,
			"unit": boq_item_doc.unit,
			"rate": boq_item_doc.rate,
			"total_qty": total_qty,
			"total_amount": total_amount
		},
		"summary": {
			"invoice_count": len(invoices),
			"total_invoiced": total_invoiced,
			"total_collected": total_collected,
			"pending": total_invoiced - total_collected,
			"accumulated_qty": latest_accumulated_qty,
			"accumulated_amount": latest_accumulated_amount,
			"balance_qty": total_qty - latest_accumulated_qty,
			"balance_amount": total_amount - latest_accumulated_amount
		},
		"ledger_entries": filtered_entries,
		"payment_certificates": payment_certificates,
		"pending_proformas": pending_proformas,
		"pc_summary": pc_summary
	}



def get_or_create_retention_item():
	"""Get or create a service item for retention deductions"""
	item_code = "RETENTION-DEDUCTION"
	
	if not frappe.db.exists("Item", item_code):
		item = frappe.new_doc("Item")
		item.item_code = item_code
		item.item_name = "Retention Deduction"
		item.item_group = "Services"
		item.stock_uom = "Nos"
		item.is_stock_item = 0
		item.is_sales_item = 1
		item.description = "Retention amount deducted from progressive billing invoices"
		item.insert(ignore_permissions=True)
	
	return item_code


def get_or_create_advance_item():
	"""Get or create a service item for advance deductions"""
	item_code = "ADVANCE-DEDUCTION"
	
	if not frappe.db.exists("Item", item_code):
		item = frappe.new_doc("Item")
		item.item_code = item_code
		item.item_name = "Advance Deduction"
		item.item_group = "Services"
		item.stock_uom = "Nos"
		item.is_stock_item = 0
		item.is_sales_item = 1
		item.description = "Advance payment deducted from progressive billing invoices"
		item.insert(ignore_permissions=True)
	
	return item_code


def get_advance_balance(project: str) -> float:
	"""Get the available advance balance for a project"""
	# Get total advances collected
	total_advances = frappe.db.sql("""
		SELECT COALESCE(SUM(amount), 0) as total
		FROM `tabBOQ Advance Payment`
		WHERE project = %s AND docstatus = 1
	""", project, as_dict=True)
	
	total_collected = flt(total_advances[0].total) if total_advances else 0
	
	# Get total advances already deducted (from invoice items)
	total_deducted = frappe.db.sql("""
		SELECT COALESCE(SUM(ABS(sii.amount)), 0) as total
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.project = %s 
		AND si.docstatus = 1
		AND sii.item_code = 'ADVANCE-DEDUCTION'
	""", project, as_dict=True)
	
	total_used = flt(total_deducted[0].total) if total_deducted else 0
	
	return total_collected - total_used


@frappe.whitelist()
def get_retention_summary(project: str) -> dict:
	"""Get retention summary for a project"""
	# Get total retention deducted
	total_retention = frappe.db.sql("""
		SELECT COALESCE(SUM(ABS(sii.amount)), 0) as total
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.project = %s 
		AND si.docstatus = 1
		AND sii.item_code = 'RETENTION-DEDUCTION'
	""", project, as_dict=True)
	
	total_retained = flt(total_retention[0].total) if total_retention else 0
	
	# Get retention released (if any retention release invoices exist)
	total_released = frappe.db.sql("""
		SELECT COALESCE(SUM(sii.amount), 0) as total
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.project = %s 
		AND si.docstatus = 1
		AND sii.item_code = 'RETENTION-RELEASE'
	""", project, as_dict=True)
	
	released = flt(total_released[0].total) if total_released else 0
	
	return {
		"total_retained": total_retained,
		"total_released": released,
		"retention_balance": total_retained - released
	}


@frappe.whitelist()
def release_retention(project: str, amount: float = None) -> dict:
	"""
	Create an invoice to release accumulated retention.
	
	Args:
		project: Project name
		amount: Amount to release (if None, releases full balance)
		
	Returns:
		dict with invoice details
	"""
	retention_summary = get_retention_summary(project)
	retention_balance = retention_summary.get("retention_balance", 0)
	
	if retention_balance <= 0:
		frappe.throw(_("No retention balance available to release"))
	
	release_amount = flt(amount) if amount else retention_balance
	
	if release_amount > retention_balance:
		frappe.throw(
			_("Release amount ({0}) exceeds retention balance ({1})").format(
				release_amount, retention_balance
			)
		)
	
	# Get project details
	project_doc = frappe.get_doc("Project", project)
	customer = project_doc.customer if hasattr(project_doc, 'customer') and project_doc.customer else None
	
	if not customer:
		frappe.throw(_("Project must have a customer assigned"))
	
	# Get or create retention release item
	release_item = get_or_create_retention_release_item()
	
	# Create invoice
	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = customer
	invoice.project = project
	invoice.posting_date = today()
	invoice.due_date = today()
	
	invoice.append("items", {
		"item_code": release_item,
		"item_name": "Retention Release",
		"description": "Release of accumulated retention",
		"qty": 1,
		"rate": release_amount,
		"amount": release_amount
	})
	
	invoice.insert()
	
	return {
		"invoice": invoice.name,
		"amount": release_amount,
		"status": "Draft"
	}


def get_or_create_retention_release_item():
	"""Get or create a service item for retention release"""
	item_code = "RETENTION-RELEASE"
	
	if not frappe.db.exists("Item", item_code):
		item = frappe.new_doc("Item")
		item.item_code = item_code
		item.item_name = "Retention Release"
		item.item_group = "Services"
		item.stock_uom = "Nos"
		item.is_stock_item = 0
		item.is_sales_item = 1
		item.description = "Release of accumulated retention from progressive billing"
		item.insert(ignore_permissions=True)
	
	return item_code



@frappe.whitelist()
def generate_consolidated_invoice(project: str, invoice_type: str = "till_date", 
                                   month: str = None, year: int = None) -> dict:
	"""
	Generate a consolidated invoice report for a project.
	
	Args:
		project: Project name
		invoice_type: "till_date" or "monthly"
		month: Month number (1-12) for monthly invoice
		year: Year for monthly invoice
		
	Returns:
		dict with consolidated invoice data
	"""
	from construction_management.api.boq_tree import get_boq_tree_data, get_boq_kpi
	
	# Get project details
	project_doc = frappe.get_doc("Project", project)
	customer = project_doc.customer if hasattr(project_doc, 'customer') and project_doc.customer else None
	retention_percentage = flt(project_doc.retention_percentage) if hasattr(project_doc, 'retention_percentage') else 0
	
	# Get BOQ tree data
	tree_data = get_boq_tree_data(project)
	kpi = get_boq_kpi(project)
	
	if not tree_data.get("bills"):
		frappe.throw(_("No BOQ data found for this project"))
	
	# Build consolidated invoice data
	invoice_data = {
		"project": project,
		"project_name": project_doc.project_name,
		"customer": customer,
		"customer_name": frappe.db.get_value("Customer", customer, "customer_name") if customer else None,
		"invoice_type": invoice_type,
		"date": today(),
		"retention_percentage": retention_percentage,
		"bills": [],
		"summary": {}
	}
	
	# Process based on invoice type
	if invoice_type == "monthly" and month and year:
		invoice_data["period"] = f"{get_month_name(int(month))} {year}"
		invoice_data["month"] = int(month)
		invoice_data["year"] = int(year)
		bills_data = get_monthly_invoice_data(project, int(month), int(year), tree_data["bills"])
	else:
		invoice_data["period"] = "Till Date"
		bills_data = get_till_date_invoice_data(tree_data["bills"])
	
	invoice_data["bills"] = bills_data["bills"]
	
	# Calculate totals
	gross_total = bills_data["gross_total"]
	retention_amount = flt(gross_total * retention_percentage / 100, 2) if retention_percentage > 0 else 0
	net_total = gross_total - retention_amount
	
	invoice_data["summary"] = {
		"gross_total": gross_total,
		"retention_percentage": retention_percentage,
		"retention_amount": retention_amount,
		"net_total": net_total,
		"total_boq_value": kpi.get("total_boq_value", 0),
		"total_billed_to_date": kpi.get("total_billed", 0),
		"balance_to_bill": kpi.get("total_boq_value", 0) - kpi.get("total_billed", 0)
	}
	
	return invoice_data


def get_till_date_invoice_data(bills: list) -> dict:
	"""Get invoice data for till date report"""
	result_bills = []
	gross_total = 0
	
	for bill in bills:
		bill_data = {
			"bill_no": bill.get("bill_no"),
			"description": bill.get("description"),
			"items": [],
			"subtotal": {
				"prev_amount": 0,
				"current_amount": 0,
				"to_date_amount": 0
			}
		}
		
		for item in bill.get("items", []):
			qty = item.get("qty", {})
			amount = item.get("amount", {})
			
			item_data = {
				"description": item.get("description"),
				"unit": item.get("unit"),
				"rate": amount.get("rate", 0),
				"qty": {
					"prev": qty.get("prev", 0),
					"current": qty.get("current", 0),
					"to_date": qty.get("to_date", 0)
				},
				"amount": {
					"prev": amount.get("prev", 0),
					"current": amount.get("current", 0),
					"to_date": amount.get("to_date", 0)
				}
			}
			
			bill_data["items"].append(item_data)
			bill_data["subtotal"]["prev_amount"] += flt(amount.get("prev", 0))
			bill_data["subtotal"]["current_amount"] += flt(amount.get("current", 0))
			bill_data["subtotal"]["to_date_amount"] += flt(amount.get("to_date", 0))
		
		gross_total += bill_data["subtotal"]["to_date_amount"]
		result_bills.append(bill_data)
	
	return {
		"bills": result_bills,
		"gross_total": gross_total
	}


def get_monthly_invoice_data(project: str, month: int, year: int, bills: list) -> dict:
	"""Get invoice data for a specific month"""
	from datetime import date
	import calendar
	
	# Get first and last day of month
	first_day = date(year, month, 1)
	last_day = date(year, month, calendar.monthrange(year, month)[1])
	
	result_bills = []
	gross_total = 0
	
	for bill in bills:
		bill_data = {
			"bill_no": bill.get("bill_no"),
			"description": bill.get("description"),
			"items": [],
			"subtotal": {
				"prev_amount": 0,
				"current_amount": 0,
				"to_date_amount": 0
			}
		}
		
		for item in bill.get("items", []):
			boq_item = item.get("name")
			
			# Get amounts from ledger for this month
			monthly_data = frappe.db.sql("""
				SELECT 
					COALESCE(SUM(CASE WHEN posting_date < %s THEN amount ELSE 0 END), 0) as prev_amount,
					COALESCE(SUM(CASE WHEN posting_date BETWEEN %s AND %s THEN amount ELSE 0 END), 0) as current_amount,
					COALESCE(SUM(CASE WHEN posting_date <= %s THEN amount ELSE 0 END), 0) as to_date_amount,
					COALESCE(SUM(CASE WHEN posting_date < %s THEN qty ELSE 0 END), 0) as prev_qty,
					COALESCE(SUM(CASE WHEN posting_date BETWEEN %s AND %s THEN qty ELSE 0 END), 0) as current_qty,
					COALESCE(SUM(CASE WHEN posting_date <= %s THEN qty ELSE 0 END), 0) as to_date_qty
				FROM `tabBOQ Progress Ledger`
				WHERE boq_item = %s AND source = 'Invoice'
			""", (first_day, first_day, last_day, last_day, first_day, first_day, last_day, last_day, boq_item), as_dict=True)[0]
			
			# Only include items with activity in this month
			if flt(monthly_data.current_amount) > 0 or flt(monthly_data.to_date_amount) > 0:
				amount = item.get("amount", {})
				
				item_data = {
					"description": item.get("description"),
					"unit": item.get("unit"),
					"rate": amount.get("rate", 0),
					"qty": {
						"prev": flt(monthly_data.prev_qty),
						"current": flt(monthly_data.current_qty),
						"to_date": flt(monthly_data.to_date_qty)
					},
					"amount": {
						"prev": flt(monthly_data.prev_amount),
						"current": flt(monthly_data.current_amount),
						"to_date": flt(monthly_data.to_date_amount)
					}
				}
				
				bill_data["items"].append(item_data)
				bill_data["subtotal"]["prev_amount"] += flt(monthly_data.prev_amount)
				bill_data["subtotal"]["current_amount"] += flt(monthly_data.current_amount)
				bill_data["subtotal"]["to_date_amount"] += flt(monthly_data.to_date_amount)
		
		# Only include bills with items
		if bill_data["items"]:
			gross_total += bill_data["subtotal"]["current_amount"]  # For monthly, use current month amount
			result_bills.append(bill_data)
	
	return {
		"bills": result_bills,
		"gross_total": gross_total
	}


def get_month_name(month: int) -> str:
	"""Get month name from number"""
	months = ["", "January", "February", "March", "April", "May", "June",
	          "July", "August", "September", "October", "November", "December"]
	return months[month] if 1 <= month <= 12 else ""


@frappe.whitelist()
def print_consolidated_invoice(project: str, invoice_type: str = "till_date",
                                month: str = None, year: int = None) -> str:
	"""
	Generate and return HTML for consolidated invoice print.
	
	Args:
		project: Project name
		invoice_type: "till_date" or "monthly"
		month: Month number for monthly invoice
		year: Year for monthly invoice
		
	Returns:
		HTML string for printing
	"""
	data = generate_consolidated_invoice(project, invoice_type, month, year)
	
	# Generate HTML
	html = get_consolidated_invoice_html(data)
	
	return html


def get_consolidated_invoice_html(data: dict) -> str:
	"""Generate HTML for consolidated invoice"""
	
	# Build items table
	items_html = ""
	for bill in data.get("bills", []):
		# Bill header row
		items_html += f"""
		<tr class="bill-header">
			<td colspan="9"><strong>{bill.get('bill_no')}</strong> {bill.get('description') or ''}</td>
		</tr>
		"""
		
		# Item rows
		for item in bill.get("items", []):
			qty = item.get("qty", {})
			amount = item.get("amount", {})
			items_html += f"""
			<tr>
				<td>{item.get('description', '')}</td>
				<td class="text-center">{item.get('unit', '')}</td>
				<td class="text-right">{format_number(qty.get('prev', 0))}</td>
				<td class="text-right">{format_number(qty.get('current', 0))}</td>
				<td class="text-right">{format_number(qty.get('to_date', 0))}</td>
				<td class="text-right">{format_currency_value(amount.get('rate', 0))}</td>
				<td class="text-right">{format_currency_value(amount.get('prev', 0))}</td>
				<td class="text-right">{format_currency_value(amount.get('current', 0))}</td>
				<td class="text-right">{format_currency_value(amount.get('to_date', 0))}</td>
			</tr>
			"""
		
		# Bill subtotal
		subtotal = bill.get("subtotal", {})
		items_html += f"""
		<tr class="subtotal-row">
			<td colspan="6" class="text-right"><strong>Subtotal - {bill.get('bill_no')}</strong></td>
			<td class="text-right"><strong>{format_currency_value(subtotal.get('prev_amount', 0))}</strong></td>
			<td class="text-right"><strong>{format_currency_value(subtotal.get('current_amount', 0))}</strong></td>
			<td class="text-right"><strong>{format_currency_value(subtotal.get('to_date_amount', 0))}</strong></td>
		</tr>
		"""
	
	summary = data.get("summary", {})
	
	html = f"""
	<!DOCTYPE html>
	<html>
	<head>
		<title>Interim Payment Application - {data.get('project')}</title>
		<style>
			body {{ font-family: Arial, sans-serif; font-size: 12px; margin: 20px; }}
			.header {{ text-align: center; margin-bottom: 30px; }}
			.header h1 {{ margin: 0; font-size: 18px; }}
			.header h2 {{ margin: 5px 0; font-size: 14px; color: #666; }}
			.info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
			.info-box {{ border: 1px solid #ddd; padding: 10px; }}
			.info-box h3 {{ margin: 0 0 10px 0; font-size: 12px; color: #666; border-bottom: 1px solid #ddd; padding-bottom: 5px; }}
			table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
			th, td {{ border: 1px solid #ddd; padding: 6px 8px; font-size: 11px; }}
			th {{ background: #f5f5f5; font-weight: bold; }}
			.text-right {{ text-align: right; }}
			.text-center {{ text-align: center; }}
			.bill-header {{ background: #e8f4f8; }}
			.subtotal-row {{ background: #f9f9f9; }}
			.summary-table {{ width: 50%; margin-left: auto; }}
			.summary-table td {{ padding: 8px; }}
			.total-row {{ font-weight: bold; font-size: 13px; background: #f0f0f0; }}
			@media print {{
				body {{ margin: 0; }}
				.no-print {{ display: none; }}
			}}
		</style>
	</head>
	<body>
		<div class="header">
			<h1>INTERIM PAYMENT APPLICATION</h1>
			<h2>{data.get('period', 'Till Date')}</h2>
		</div>
		
		<div class="info-grid">
			<div class="info-box">
				<h3>Project Details</h3>
				<p><strong>Project:</strong> {data.get('project_name', data.get('project'))}</p>
				<p><strong>Date:</strong> {data.get('date')}</p>
			</div>
			<div class="info-box">
				<h3>Client Details</h3>
				<p><strong>Customer:</strong> {data.get('customer_name', data.get('customer', 'N/A'))}</p>
			</div>
		</div>
		
		<table>
			<thead>
				<tr>
					<th>Description</th>
					<th>Unit</th>
					<th>Prev Qty</th>
					<th>Curr Qty</th>
					<th>To-Date Qty</th>
					<th>Rate</th>
					<th>Prev Amount</th>
					<th>Curr Amount</th>
					<th>To-Date Amount</th>
				</tr>
			</thead>
			<tbody>
				{items_html}
			</tbody>
		</table>
		
		<table class="summary-table">
			<tr>
				<td>Gross Total</td>
				<td class="text-right">{format_currency_value(summary.get('gross_total', 0))}</td>
			</tr>
			{"<tr><td>Less: Retention (" + str(summary.get('retention_percentage', 0)) + "%)</td><td class='text-right'>(" + format_currency_value(summary.get('retention_amount', 0)) + ")</td></tr>" if summary.get('retention_amount', 0) > 0 else ""}
			<tr class="total-row">
				<td>Net Total</td>
				<td class="text-right">{format_currency_value(summary.get('net_total', 0))}</td>
			</tr>
		</table>
		
		<div style="margin-top: 40px;">
			<p><strong>Total BOQ Value:</strong> {format_currency_value(summary.get('total_boq_value', 0))}</p>
			<p><strong>Total Billed To Date:</strong> {format_currency_value(summary.get('total_billed_to_date', 0))}</p>
			<p><strong>Balance to Bill:</strong> {format_currency_value(summary.get('balance_to_bill', 0))}</p>
		</div>
	</body>
	</html>
	"""
	
	return html


def format_currency_value(value):
	"""Format value as currency"""
	return "{:,.2f}".format(flt(value))


def format_number(value):
	"""Format number with 3 decimal places"""
	return "{:,.3f}".format(flt(value))


# ============================================
# Advance Aggregation APIs (Task 9.1)
# ============================================

@frappe.whitelist()
def get_bill_item_advances(boq_item: str) -> dict:
	"""
	Get advance payments linked to a specific BOQ Item.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		dict with total_advances, allocated, unallocated, and list of advances
	"""
	advances = frappe.db.sql("""
		SELECT 
			name,
			date,
			amount,
			allocated_amount,
			unallocated_amount,
			status,
			reference,
			linked_invoice
		FROM `tabBOQ Advance Payment`
		WHERE boq_item = %s AND docstatus = 1
		ORDER BY date DESC
	""", boq_item, as_dict=True)
	
	total_amount = sum(flt(a.amount) for a in advances)
	total_allocated = sum(flt(a.allocated_amount) for a in advances)
	total_unallocated = sum(flt(a.unallocated_amount) for a in advances)
	
	return {
		"boq_item": boq_item,
		"total_advances": total_amount,
		"allocated": total_allocated,
		"unallocated": total_unallocated,
		"count": len(advances),
		"advances": advances
	}


@frappe.whitelist()
def get_bill_advances(bill_no: str) -> dict:
	"""
	Get advance payments linked to a specific Bill No.
	
	Args:
		bill_no: BOQ Bill name
		
	Returns:
		dict with total_advances, allocated, unallocated, and list of advances
	"""
	advances = frappe.db.sql("""
		SELECT 
			name,
			boq_item,
			date,
			amount,
			allocated_amount,
			unallocated_amount,
			status,
			reference,
			linked_invoice
		FROM `tabBOQ Advance Payment`
		WHERE bill_no = %s AND docstatus = 1
		ORDER BY date DESC
	""", bill_no, as_dict=True)
	
	total_amount = sum(flt(a.amount) for a in advances)
	total_allocated = sum(flt(a.allocated_amount) for a in advances)
	total_unallocated = sum(flt(a.unallocated_amount) for a in advances)
	
	return {
		"bill_no": bill_no,
		"total_advances": total_amount,
		"allocated": total_allocated,
		"unallocated": total_unallocated,
		"count": len(advances),
		"advances": advances
	}


@frappe.whitelist()
def get_available_advances(boq_item: str = None, bill_no: str = None, project: str = None) -> list:
	"""
	Get available (unallocated) advances for allocation to invoices.
	Can filter by BOQ Item, Bill No, or Project.
	
	Args:
		boq_item: Optional BOQ Item filter
		bill_no: Optional Bill No filter
		project: Optional Project filter
		
	Returns:
		List of advances with unallocated amounts
	"""
	conditions = ["docstatus = 1", "unallocated_amount > 0"]
	values = {}
	
	if boq_item:
		conditions.append("boq_item = %(boq_item)s")
		values["boq_item"] = boq_item
	elif bill_no:
		conditions.append("bill_no = %(bill_no)s")
		values["bill_no"] = bill_no
	elif project:
		conditions.append("project = %(project)s")
		values["project"] = project
	else:
		return []
	
	advances = frappe.db.sql("""
		SELECT 
			name,
			project,
			bill_no,
			boq_item,
			date,
			amount,
			allocated_amount,
			unallocated_amount,
			status,
			reference
		FROM `tabBOQ Advance Payment`
		WHERE {conditions}
		ORDER BY date ASC
	""".format(conditions=" AND ".join(conditions)), values, as_dict=True)
	
	return advances


@frappe.whitelist()
def get_project_advances(project: str) -> dict:
	"""
	Get aggregated advance payment summary for a project.
	Includes breakdown by bill and item.
	
	Args:
		project: Project name
		
	Returns:
		dict with project totals and breakdown by bill/item
	"""
	# Get all advances for project
	advances = frappe.db.sql("""
		SELECT 
			name,
			bill_no,
			boq_item,
			date,
			amount,
			allocated_amount,
			unallocated_amount,
			status,
			reference
		FROM `tabBOQ Advance Payment`
		WHERE project = %s AND docstatus = 1
		ORDER BY date DESC
	""", project, as_dict=True)
	
	# Calculate project totals
	total_amount = sum(flt(a.amount) for a in advances)
	total_allocated = sum(flt(a.allocated_amount) for a in advances)
	total_unallocated = sum(flt(a.unallocated_amount) for a in advances)
	
	# Group by bill
	by_bill = {}
	for adv in advances:
		bill = adv.bill_no or "Unassigned"
		if bill not in by_bill:
			by_bill[bill] = {
				"bill_no": bill,
				"total": 0,
				"allocated": 0,
				"unallocated": 0,
				"count": 0,
				"items": {}
			}
		by_bill[bill]["total"] += flt(adv.amount)
		by_bill[bill]["allocated"] += flt(adv.allocated_amount)
		by_bill[bill]["unallocated"] += flt(adv.unallocated_amount)
		by_bill[bill]["count"] += 1
		
		# Group by item within bill
		item = adv.boq_item or "Unassigned"
		if item not in by_bill[bill]["items"]:
			by_bill[bill]["items"][item] = {
				"boq_item": item,
				"total": 0,
				"allocated": 0,
				"unallocated": 0,
				"count": 0
			}
		by_bill[bill]["items"][item]["total"] += flt(adv.amount)
		by_bill[bill]["items"][item]["allocated"] += flt(adv.allocated_amount)
		by_bill[bill]["items"][item]["unallocated"] += flt(adv.unallocated_amount)
		by_bill[bill]["items"][item]["count"] += 1
	
	# Convert items dict to list for each bill
	for bill in by_bill.values():
		bill["items"] = list(bill["items"].values())
	
	return {
		"project": project,
		"summary": {
			"total_advances": total_amount,
			"allocated": total_allocated,
			"unallocated": total_unallocated,
			"count": len(advances)
		},
		"by_bill": list(by_bill.values()),
		"advances": advances
	}


@frappe.whitelist()
def allocate_advance_to_invoice(advance_name: str, invoice_name: str, amount: float = None) -> dict:
	"""
	Allocate an advance payment to a sales invoice.
	
	Args:
		advance_name: BOQ Advance Payment name
		invoice_name: Sales Invoice name
		amount: Amount to allocate (defaults to full unallocated amount)
		
	Returns:
		dict with allocation details
	"""
	advance = frappe.get_doc("BOQ Advance Payment", advance_name)
	
	if advance.docstatus != 1:
		frappe.throw(_("Advance payment must be submitted before allocation"))
	
	available = flt(advance.unallocated_amount)
	if available <= 0:
		frappe.throw(_("No unallocated amount available in this advance"))
	
	allocation_amount = flt(amount) if amount else available
	if allocation_amount > available:
		frappe.throw(_("Allocation amount ({0}) exceeds available amount ({1})").format(
			allocation_amount, available
		))
	
	# Update advance
	advance.allocated_amount = flt(advance.allocated_amount) + allocation_amount
	advance.unallocated_amount = flt(advance.amount) - flt(advance.allocated_amount)
	advance.linked_invoice = invoice_name
	
	if advance.unallocated_amount <= 0:
		advance.status = "Fully Utilized"
	else:
		advance.status = "Partially Utilized"
	
	advance.save()
	
	return {
		"advance": advance_name,
		"invoice": invoice_name,
		"allocated_amount": allocation_amount,
		"remaining_unallocated": advance.unallocated_amount,
		"status": advance.status
	}


@frappe.whitelist()
def get_billable_items_by_bill(project: str) -> list:
	"""
	Get all billable items grouped by bill with their details.
	This is used for the enhanced Generate Invoice dialog that allows
	selecting individual BOQ items.
	
	Args:
		project: Project name
		
	Returns:
		list of bills with their billable items
	"""
	# Get all bills with billable items
	bills_data = frappe.db.sql("""
		SELECT 
			bb.name as bill_name,
			bb.bill_no,
			bb.description as bill_description
		FROM `tabBOQ Bill` bb
		WHERE bb.project = %s
		AND EXISTS (
			SELECT 1 FROM `tabBOQ Item` bi 
			WHERE bi.parent_bill = bb.name 
			AND bi.current_qty > 0
		)
		ORDER BY bb.bill_no
	""", project, as_dict=True)
	
	result = []
	
	for bill in bills_data:
		# Get billable items for this bill
		items = frappe.db.sql("""
			SELECT 
				bi.name as boq_item,
				bi.item_code,
				bi.description,
				bi.unit,
				bi.rate,
				bi.total_qty,
				bi.current_qty,
				bi.current_qty * bi.rate as current_amount,
				bi.balance_qty,
				bi.balance_amount,
				bi.billing_status
			FROM `tabBOQ Item` bi
			WHERE bi.parent_bill = %s
			AND bi.current_qty > 0
			ORDER BY bi.name
		""", bill.bill_name, as_dict=True)
		
		if items:
			bill_total = sum(flt(item.current_amount) for item in items)
			result.append({
				"bill_name": bill.bill_name,
				"bill_no": bill.bill_no,
				"bill_description": bill.bill_description,
				"items": items,
				"item_count": len(items),
				"total_amount": bill_total
			})
	
	return result


@frappe.whitelist()
def get_all_bills_with_items(project: str) -> list:
	"""
	Get ALL bills and ALL BOQ items for a project (regardless of current_qty).
	Shows items with balance_qty > 0 that can still be billed.
	
	Args:
		project: Project name
		
	Returns:
		list of all bills with their items that have balance to bill
	"""
	# Get all bills for the project
	bills_data = frappe.db.sql("""
		SELECT 
			bb.name as bill_name,
			bb.bill_no,
			bb.description as bill_description
		FROM `tabBOQ Bill` bb
		WHERE bb.project = %s
		ORDER BY bb.bill_no
	""", project, as_dict=True)
	
	result = []
	
	for bill in bills_data:
		# Get ALL items for this bill that have balance to bill
		items = frappe.db.sql("""
			SELECT 
				bi.name as boq_item,
				bi.item_code,
				bi.description,
				bi.unit,
				bi.rate,
				bi.total_qty,
				bi.to_date_qty,
				bi.balance_qty,
				bi.balance_amount,
				bi.billing_status
			FROM `tabBOQ Item` bi
			WHERE bi.parent_bill = %s
			AND bi.balance_qty > 0
			ORDER BY bi.name
		""", bill.bill_name, as_dict=True)
		
		if items:
			bill_balance = sum(flt(item.balance_amount) for item in items)
			result.append({
				"bill_name": bill.bill_name,
				"bill_no": bill.bill_no,
				"bill_description": bill.bill_description,
				"items": items,
				"item_count": len(items),
				"total_balance": bill_balance
			})
	
	return result


@frappe.whitelist()
def create_invoice_from_selected_items(project: str, items: str | list, 
                                        apply_retention: int = 1, 
                                        advance_deduction: float = 0,
                                        is_proforma: int = 0) -> dict:
	"""
	Create a Sales Invoice from selected BOQ Items with custom quantities.
	
	Args:
		project: Project name
		items: List of dicts with boq_item, qty, and amount
		apply_retention: Whether to apply retention (1=yes, 0=no)
		advance_deduction: Amount to deduct from advance
		is_proforma: Whether to create as proforma invoice (1=yes, 0=no)
		
	Returns:
		dict with invoice details
	"""
	import json
	
	if isinstance(items, str):
		items = json.loads(items)
	
	if not items:
		frappe.throw(_("No items provided"))
	
	apply_retention = int(apply_retention)
	advance_deduction = flt(advance_deduction)
	is_proforma = int(is_proforma)
	
	# Get project details
	project_doc = frappe.get_doc("Project", project)
	customer = project_doc.customer if hasattr(project_doc, 'customer') and project_doc.customer else None
	retention_percentage = flt(project_doc.retention_percentage) if hasattr(project_doc, 'retention_percentage') else 0
	
	if not customer:
		frappe.throw(_("Project must have a customer assigned to create invoice"))
	
	# Create Sales Invoice
	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = customer
	invoice.project = project
	invoice.posting_date = today()
	invoice.due_date = today()
	
	# Set proforma flag if requested
	if is_proforma:
		invoice.custom_is_proforma = 1
	
	total_amount = 0
	items_added = 0
	bills_included = set()
	
	for item_data in items:
		boq_item_name = item_data.get("boq_item")
		current_qty = flt(item_data.get("qty", 0))
		
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
		
		# Get bill_no for reference
		bill_no = frappe.db.get_value("BOQ Bill", item.parent_bill, "bill_no")
		
		# Add item to invoice
		invoice.append("items", {
			"item_code": invoice_item_code,
			"item_name": item.description[:140] if item.description else "BOQ Item",
			"description": f"[{bill_no}] {item.description}" if bill_no else item.description,
			"qty": current_qty,
			"rate": item.rate,
			"amount": current_amount,
			"uom": item.unit,
			"boq_item": boq_item_name,
			"bill_no": item.parent_bill,
			"project": project
		})
		
		items_added += 1
		bills_included.add(bill_no or item.parent_bill)
		
		# Update BOQ Item current_qty to the invoiced amount
		frappe.db.set_value("BOQ Item", boq_item_name, "current_qty", 0)
	
	if not invoice.items:
		frappe.throw(_("No valid items to invoice"))
	
	# Calculate retention
	retention_amount = 0
	if apply_retention and retention_percentage > 0 and not is_proforma:
		retention_amount = flt(total_amount * retention_percentage / 100, 2)
		if retention_amount > 0:
			retention_item = get_or_create_retention_item()
			invoice.append("items", {
				"item_code": retention_item,
				"item_name": f"Retention ({retention_percentage}%)",
				"description": f"Retention deduction at {retention_percentage}%",
				"qty": 1,
				"rate": -retention_amount,
				"amount": -retention_amount,
				"project": project
			})
	
	# Handle advance deduction
	if advance_deduction > 0 and not is_proforma:
		advance_balance = get_advance_balance(project)
		if advance_deduction > advance_balance:
			frappe.throw(
				_("Advance deduction ({0}) exceeds available advance balance ({1})").format(
					advance_deduction, advance_balance
				),
				title=_("Advance Deduction Error")
			)
		
		advance_item = get_or_create_advance_item()
		invoice.append("items", {
			"item_code": advance_item,
			"item_name": "Advance Deduction",
			"description": "Deduction from advance payment",
			"qty": 1,
			"rate": -advance_deduction,
			"amount": -advance_deduction,
			"project": project
		})
	
	invoice.insert()
	
	net_amount = total_amount - retention_amount - advance_deduction
	
	return {
		"invoice": invoice.name,
		"customer": customer,
		"item_count": items_added,
		"bills_included": list(bills_included),
		"gross_amount": total_amount,
		"retention_amount": retention_amount,
		"advance_deduction": advance_deduction,
		"net_amount": net_amount,
		"status": "Draft",
		"is_proforma": is_proforma
	}
