# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt, today, getdate


@frappe.whitelist()
def create_invoice_from_boq_item(project: str, boq_item: str, current_qty: float, 
                                  apply_retention: int = 1, advance_deduction: float = 0) -> dict:
	"""
	Create a Sales Invoice from a BOQ Item with the specified current quantity.
	
	Args:
		project: Project name
		boq_item: BOQ Item name
		current_qty: Quantity to bill
		apply_retention: Whether to apply retention (1=yes, 0=no)
		advance_deduction: Amount to deduct from advance
		
	Returns:
		dict with invoice details
	"""
	current_qty = flt(current_qty)
	apply_retention = int(apply_retention)
	advance_deduction = flt(advance_deduction)
	
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
	
	# Calculate retention
	retention_amount = 0
	if apply_retention and retention_percentage > 0:
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
				"amount": -retention_amount
			})
	
	# Handle advance deduction
	if advance_deduction > 0:
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
			"amount": -advance_deduction
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
		"status": "Draft"
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
			"bill_no": item.parent_bill
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
				"amount": -retention_amount
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
			"amount": -advance_deduction
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
