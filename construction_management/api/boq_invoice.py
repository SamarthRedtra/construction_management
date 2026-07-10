# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt, today, getdate
from construction_management.api.boq_ledger import create_ledger_entry, recalculate_ledger_for_item
from construction_management.api.boq_tree import get_boq_kpi, get_retention_summary as _get_retention_summary
from erpnext.controllers.accounts_controller import get_default_taxes_and_charges


def has_invoice_permission() -> bool:
	"""
	Check if current user has permission to create invoices.
	
	Returns:
		bool: True if user has required role
	"""
	allowed_roles = ["Project Manager", "Quantity Surveyor", "System Manager"]
	user_roles = frappe.get_roles()
	return any(role in user_roles for role in allowed_roles)


def _set_direct_billing_mode(invoice, is_proforma: int = 0):
	"""Tag direct BOQ invoices with billing mode when field exists."""
	if is_proforma:
		return
	if frappe.db.has_column("Sales Invoice", "custom_billing_mode"):
		invoice.custom_billing_mode = "Direct BOQ"


@frappe.whitelist()
def get_pending_proformas_for_item(boq_item: str) -> list:
	"""
	Get pending Sales Orders for a specific BOQ item.
	Returns Sales Orders that are submitted but don't have a Payment Certificate yet.
	"""
	orders = frappe.db.sql("""
		SELECT 
			so.name,
			so.transaction_date as posting_date,
			soi.base_amount as amount,
			so.customer,
			so.project,
			so.status
		FROM `tabSales Order` so
		INNER JOIN `tabSales Order Item` soi ON soi.parent = so.name
		WHERE soi.boq_item = %(boq_item)s
		AND so.docstatus = 1
		AND NOT EXISTS (
			SELECT 1 FROM `tabPayment Certificate Item` pci
			WHERE pci.parentfield = 'items'
			AND pci.boq_item = soi.boq_item
			AND EXISTS (
				SELECT 1 FROM `tabPayment Certificate` pc
				WHERE pc.name = pci.parent
				AND pc.sales_order = so.name
				AND pc.docstatus != 2
			)
		)
		ORDER BY so.transaction_date DESC
	""", {"boq_item": boq_item}, as_dict=True)
	
	for so in orders:
		so["age_days"] = (getdate(today()) - getdate(so.posting_date)).days if so.posting_date else 0
		so["grand_total"] = so.amount # UI compatibility
		
	return orders


def has_boq_write_permission() -> bool:
	"""
	Check if current user has permission to modify BOQ data.
	
	Returns:
		bool: True if user has required role
	"""
	allowed_roles = ["Project Manager", "Quantity Surveyor", "System Manager"]
	user_roles = frappe.get_roles()
	return any(role in user_roles for role in allowed_roles)


def has_boq_read_permission() -> bool:
	"""
	Check if current user has permission to read BOQ data.
	
	Returns:
		bool: True if user has required role
	"""
	allowed_roles = ["Project Manager", "Quantity Surveyor", "System Manager", "Projects User", "Construction Manager"]
	user_roles = frappe.get_roles()
	return any(role in user_roles for role in allowed_roles)


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
	# Permission check - require Project Manager, Quantity Surveyor, or System Manager
	if not has_invoice_permission():
		frappe.throw(
			_("You don't have permission to create invoices. Required role: Project Manager, Quantity Surveyor, or System Manager"),
			frappe.PermissionError
		)
	
	current_qty = flt(current_qty)
	apply_retention = int(apply_retention)
	advance_deduction = flt(advance_deduction)
	is_proforma = int(is_proforma)
	
	# Validate
	if current_qty <= 0:
		frappe.throw(_("Quantity must be greater than zero"))
	
	# Get BOQ Item
	item = frappe.get_doc("BOQ Item", boq_item)
	
	if boq_item_skips_advance(boq_item):
		advance_deduction = 0
	
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
	else:
		_set_direct_billing_mode(invoice, is_proforma)
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
	
	# Populate taxes
	if not invoice.get("taxes_and_charges"):
		company_curr = frappe.get_cached_value("Project", project, "company")
		default_tax = get_default_taxes_and_charges("Sales Taxes and Charges Template", company=company_curr)
		
		if default_tax and default_tax.get("taxes_and_charges"):
			invoice.taxes_and_charges = default_tax["taxes_and_charges"]
			if not invoice.get("taxes"):
				for tax in default_tax.get("taxes", []):
					invoice.append("taxes", tax)
	
	if not invoice.get("taxes") and not invoice.get("taxes_and_charges"):
		customer_taxes = frappe.db.get_value("Customer", customer, "taxes_and_charges")
		if customer_taxes:
			invoice.taxes_and_charges = customer_taxes
			invoice.run_method("set_taxes")
	
	invoice.run_method("calculate_taxes_and_totals")

	
	try:
		invoice.insert()
		
		# Update BOQ Item current_qty
		item.current_qty = 0  # Reset after creating invoice
		item.save()
		
		# Commit the transaction
		frappe.db.commit()
		# Also set flag to prevent any later rollback
		frappe.flags.commit = True
		
		frappe.logger().info(
			f"Created Sales Invoice {invoice.name} from BOQ Item {boq_item}, "
			f"qty={current_qty}, amount={current_amount}, is_proforma={is_proforma}"
		)
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			message=f"Error creating invoice from BOQ Item {boq_item}: {str(e)}",
			title="Invoice Creation Error"
		)
		frappe.throw(_("Failed to create invoice: {0}").format(str(e)))
	
	# Calculate net amount
	net_amount = current_amount - retention_amount - advance_deduction
	
	return {
		"status": "success",
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
	# Permission check
	if not has_invoice_permission():
		frappe.throw(
			_("You don't have permission to create invoices. Required role: Project Manager, Quantity Surveyor, or System Manager"),
			frappe.PermissionError
		)
	
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
	_set_direct_billing_mode(invoice, 0)
	
	total_amount = 0
	boq_item_amounts = {}
	
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
		boq_item_amounts[boq_item_name] = flt(boq_item_amounts.get(boq_item_name, 0)) + current_amount
		
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
	
	advance_deduction = resolve_advance_deduction_for_boq_items(
		advance_deduction, boq_item_amounts, project
	)
	
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
	
	# Populate taxes
	if not invoice.get("taxes_and_charges"):
		company_curr = frappe.get_cached_value("Project", project, "company")
		default_tax = get_default_taxes_and_charges("Sales Taxes and Charges Template", company=company_curr)
		
		if default_tax and default_tax.get("taxes_and_charges"):
			invoice.taxes_and_charges = default_tax["taxes_and_charges"]
			if not invoice.get("taxes"):
				for tax in default_tax.get("taxes", []):
					invoice.append("taxes", tax)
	
	if not invoice.get("taxes") and not invoice.get("taxes_and_charges"):
		customer_taxes = frappe.db.get_value("Customer", customer, "taxes_and_charges")
		if customer_taxes:
			invoice.taxes_and_charges = customer_taxes
			invoice.run_method("set_taxes")
	
	invoice.run_method("calculate_taxes_and_totals")

	
	try:
		invoice.insert()
		
		# Reset current_qty on all BOQ Items
		for item_data in items:
			if flt(item_data.get("current_qty", 0)) > 0:
				frappe.db.set_value("BOQ Item", item_data.get("boq_item"), "current_qty", 0)
		
		# Commit the transaction
		frappe.db.commit()
		frappe.flags.commit = True
		
		frappe.logger().info(
			f"Created Sales Invoice {invoice.name} from multiple BOQ Items, "
			f"item_count={len([i for i in invoice.items if flt(i.rate) > 0])}, total={total_amount}"
		)
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			message=f"Error creating invoice from multiple items for project {project}: {str(e)}",
			title="Invoice Creation Error"
		)
		frappe.throw(_("Failed to create invoice: {0}").format(str(e)))
	
	net_amount = total_amount - retention_amount - advance_deduction
	
	return {
		"status": "success",
		"invoice": invoice.name,
		"customer": customer,
		"item_count": len([i for i in invoice.items if flt(i.rate) > 0]),
		"gross_amount": total_amount,
		"retention_amount": retention_amount,
		"advance_deduction": advance_deduction,
		"net_amount": net_amount,
		"doc_status": "Draft"
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
	boq_item_amounts = {}
	
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
		boq_item_amounts[item_data.boq_item] = (
			flt(boq_item_amounts.get(item_data.boq_item, 0)) + current_amount
		)
		
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
	
	advance_deduction = resolve_advance_deduction_for_boq_items(
		advance_deduction, boq_item_amounts, project
	)
	
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
	
	# Populate taxes
	if not invoice.get("taxes_and_charges"):
		company_doc = frappe.get_cached_value("Project", project, "company")
		default_tax = get_default_taxes_and_charges("Sales Taxes and Charges Template", company=company_doc)
		
		if default_tax and default_tax.get("taxes_and_charges"):
			invoice.taxes_and_charges = default_tax["taxes_and_charges"]
			if not invoice.get("taxes"):
				for tax in default_tax.get("taxes", []):
					invoice.append("taxes", tax)
	
	if not invoice.get("taxes") and not invoice.get("taxes_and_charges"):
		customer_taxes = frappe.db.get_value("Customer", customer, "taxes_and_charges")
		if customer_taxes:
			invoice.taxes_and_charges = customer_taxes
			invoice.run_method("set_taxes")
			
	invoice.run_method("calculate_taxes_and_totals")
	
	try:
		invoice.insert()
		
		# Reset current_qty on all BOQ Items that were billed
		for item_data in items_to_bill:
			if flt(item_data.current_qty) > 0:
				frappe.db.set_value("BOQ Item", item_data.boq_item, "current_qty", 0)
		
		# Commit the transaction
		frappe.db.commit()
		frappe.flags.commit = True
		
		frappe.logger().info(
			f"Created Sales Invoice {invoice.name} from selected bills, "
			f"items={items_added}, bills={list(bills_included)}, amount={total_amount}"
		)
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			message=f"Error creating invoice from selected bills for project {project}: {str(e)}",
			title="Invoice Creation Error"
		)
		frappe.throw(_("Failed to create invoice: {0}").format(str(e)))
	
	net_amount = total_amount - retention_amount - advance_deduction
	
	return {
		"status": "success",
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
def rebuild_orphan_si_ledgers(project: str = None, si: str = None):
	"""
	Backfill BOQ Progress Ledger entries for Sales Invoices created outside PI/PC flow.
	- Considers Sales Invoices with boq_item set, docstatus=1, custom_is_proforma=0,
	- custom_payment_certificate is empty, custom_proforma_invoice is empty.
	- Skips if a ledger entry already exists for the SI/boq_item combo.
	Recalculates progressive values per BOQ item after inserts.
	"""
	filters = {"docstatus": 1}
	if frappe.db.has_column("Sales Invoice", "custom_is_proforma"):
		filters["custom_is_proforma"] = 0
		
	if project:
		filters["project"] = project
	if si:
		filters["name"] = si
	
	fields = ["name", "posting_date", "project"]
	if frappe.db.has_column("Sales Invoice", "custom_payment_certificate"):
		fields.append("custom_payment_certificate")
	if frappe.db.has_column("Sales Invoice", "custom_proforma_invoice"):
		fields.append("custom_proforma_invoice")
	
	sis = frappe.get_all(
		"Sales Invoice",
		filters=filters,
		fields=fields
	)
	
	count_created = 0
	for inv in sis:
		# Skip if linked to PC/PI
		if inv.get("custom_payment_certificate") or inv.get("custom_proforma_invoice"):
			continue
		
		si_doc = frappe.get_doc("Sales Invoice", inv.name)
		for item in si_doc.items:
			boq_item = item.get("boq_item")
			if not boq_item:
				continue
			
			# Duplicate guard
			existing = frappe.db.get_value(
				"BOQ Progress Ledger",
				{
					"boq_item": boq_item,
					"reference_doctype": "Sales Invoice",
					"reference_name": inv.name
				},
				"name"
			)
			if existing:
				continue
			
			# Bill No fallback
			bill_no = item.get("bill_no") or frappe.db.get_value("BOQ Item", boq_item, "parent_bill")
			
			create_ledger_entry(
				boq_item=boq_item,
				qty=flt(item.qty),
				amount=flt(item.amount),
				source="Invoice",
				reference_doctype="Sales Invoice",
				reference_name=inv.name,
				posting_date=si_doc.posting_date,
				remarks=f"Invoice {inv.name} (orphan backfill)",
				bill_no=bill_no,
				tax_invoice=inv.name,
				tax_invoice_amount=flt(item.amount)
			)
			
			# Recalc per BOQ item
			recalculate_ledger_for_item(boq_item)
			count_created += 1
	
	return {
		"status": "success",
		"created": count_created
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
def get_boq_invoice_history(boq_item: str, grouped_view: int = 0) -> dict:
	"""
	Get invoice history for a BOQ Item with progressive billing details.
	Includes Sales Orders, Payment Certificates, and Tax Invoices tracking.
	"""
	# Get BOQ Item details
	boq_item_doc = frappe.get_doc("BOQ Item", boq_item)
	
	# Get all ledger entries for this BOQ Item
	ledger_entries = frappe.db.sql("""
		SELECT 
			pl.name,
			pl.posting_date,
			pl.creation,
			pl.source,
			pl.reference_doctype,
			pl.reference_name,
			pl.payment_certificate,
			pl.certified_amount,
			pl.tax_invoice,
			pl.tax_invoice_amount,
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
	
	filtered_entries = []
	acc_qty = 0
	acc_amount = 0
	for entry in ledger_entries:
		if entry.reference_doctype == "Sales Invoice" and entry.invoice_docstatus == 2:
			continue
		
		# Add unit and rate from BOQ Item
		entry["unit"] = boq_item_doc.unit
		entry["rate"] = boq_item_doc.rate
		
		# Recompute progressive accumulated values
		acc_qty += flt(entry.current_qty)
		acc_amount += flt(entry.current_amount)
		entry["accumulated_qty"] = acc_qty
		entry["accumulated_amount"] = acc_amount
		
		filtered_entries.append(entry)
	
	# Get Sales Orders (at item level for this BOQ Item)
	sales_orders = frappe.db.sql("""
		SELECT 
			so.name,
			so.transaction_date as posting_date,
			soi.base_amount as amount,
			so.status,
			soi.qty,
			soi.base_amount as item_amount
		FROM `tabSales Order` so
		JOIN `tabSales Order Item` soi ON soi.parent = so.name
		WHERE soi.boq_item = %s
		AND so.docstatus = 1
		ORDER BY so.transaction_date DESC
	""", boq_item, as_dict=True)
	
	# Get Payment Certificates (at item level for this BOQ Item)
	payment_certificates = frappe.db.sql("""
		SELECT 
			pc.name,
			pc.posting_date,
			pci.accepted_amount,
			pci.amount as proforma_amount,
			pci.variance,
			pc.status,
			pc.sales_order,
			pc.tax_invoice
		FROM `tabPayment Certificate` pc
		JOIN `tabPayment Certificate Item` pci ON pci.parent = pc.name
		WHERE pci.boq_item = %s
		AND pc.docstatus != 2
		ORDER BY pc.posting_date DESC
	""", boq_item, as_dict=True)
	
	# Pending Sales Orders
	pending_orders = []
	for so in sales_orders:
		if not any(pc.sales_order == so.name for pc in payment_certificates):
			# Calculate age in days
			so["age_days"] = (getdate(today()) - getdate(so.posting_date)).days
			pending_orders.append(so)
	
	# Calculate summary
	latest_accumulated_qty = acc_qty
	latest_accumulated_amount = acc_amount
	total_qty = flt(boq_item_doc.total_qty)
	total_amount = total_qty * flt(boq_item_doc.rate)
	
	pc_summary = {
		"total_proforma": sum(flt(so.amount) for so in sales_orders),
		"total_accepted": sum(flt(pc.accepted_amount) for pc in payment_certificates),
		"total_variance": sum(flt(pc.variance) for pc in payment_certificates),
		"total_received": sum(flt(frappe.db.get_value("Payment Certificate", pc.name, "payment_received")) for pc in payment_certificates),
		"pending_proforma_count": len(pending_orders),
		"pending_proforma_amount": sum(flt(so.amount) for so in pending_orders)
	}
	
	response = {
		"boq_item": {
			"name": boq_item_doc.name,
			"description": boq_item_doc.description,
			"unit": boq_item_doc.unit,
			"rate": boq_item_doc.rate,
			"total_qty": total_qty,
			"total_amount": total_amount
		},
		"summary": {
			"accumulated_qty": latest_accumulated_qty,
			"accumulated_amount": latest_accumulated_amount,
			"balance_qty": total_qty - latest_accumulated_qty,
			"balance_amount": total_amount - latest_accumulated_amount
		},
		"ledger_entries": filtered_entries,
		"payment_certificates": payment_certificates,
		"pending_proformas": pending_orders, # frontend compat
		"pc_summary": pc_summary,
		"view_mode": "grouped" if grouped_view else "raw"
	}
	
	if grouped_view:
		from construction_management.api.transaction_grouping import (
			group_transactions_by_billing_cycle, 
			get_grouped_transaction_summary
		)
		try:
			grouped_transactions = group_transactions_by_billing_cycle(filtered_entries, payment_certificates)
			grouping_summary = get_grouped_transaction_summary(grouped_transactions)
			response.update({
				"grouped_transactions": grouped_transactions,
				"grouping_summary": grouping_summary
			})
		except Exception as e:
			frappe.log_error(f"Grouping failed: {str(e)}")
			response["view_mode"] = "raw"
			
	return response
	
	# Add grouped transaction view if requested
	if grouped_view:
		from construction_management.api.transaction_grouping import (
			group_transactions_by_billing_cycle, 
			get_grouped_transaction_summary
		)
		
		try:
			# Group transactions by billing cycle
			grouped_transactions = group_transactions_by_billing_cycle(filtered_entries, payment_certificates)
			grouping_summary = get_grouped_transaction_summary(grouped_transactions)
			
			response.update({
				"grouped_transactions": grouped_transactions,
				"grouping_summary": grouping_summary,
				"view_mode": "grouped"
			})
		except Exception as e:
			# Fallback to raw view if grouping fails
			frappe.log_error(f"Transaction grouping failed for BOQ Item {boq_item}: {str(e)}", 
							"Transaction Grouping Error")
			response["view_mode"] = "raw"
			response["grouping_error"] = str(e)
	else:
		response["view_mode"] = "raw"
	
	return response


def _append_orphan_sales_invoices(boq_item, filtered_entries, boq_item_doc):
	"""
	Add Sales Invoices without PI/PC linkage to the history for visibility.
	Only include SIs that have neither custom_payment_certificate nor custom_proforma_invoice.
	"""
	# Collect existing reference names to avoid duplicates
	existing_refs = {e.reference_name for e in filtered_entries if e.reference_name}
	
	conditions = ["sii.boq_item = %s", "si.docstatus = 1"]
	
	if frappe.db.has_column("Sales Invoice", "custom_is_proforma"):
		conditions.append("si.custom_is_proforma = 0")
	
	if frappe.db.has_column("Sales Invoice", "custom_payment_certificate"):
		conditions.append("IFNULL(si.custom_payment_certificate, '') = ''")
		
	if frappe.db.has_column("Sales Invoice", "custom_proforma_invoice"):
		conditions.append("IFNULL(si.custom_proforma_invoice, '') = ''")
		
	where_clause = " AND ".join(conditions)
	
	orphan_si = frappe.db.sql(f"""
		SELECT si.name, si.posting_date, sii.qty, sii.amount
		FROM `tabSales Invoice` si
		JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		WHERE {where_clause}
	""", boq_item, as_dict=True)
	
	acc_qty = flt(filtered_entries[-1].accumulated_qty) if filtered_entries else 0
	acc_amount = flt(filtered_entries[-1].accumulated_amount) if filtered_entries else 0
	
	for inv in orphan_si:
		if inv.name in existing_refs:
			continue
		current_qty = flt(inv.qty)
		current_amount = flt(inv.amount)
		entry = frappe._dict({
			"name": f"ORPHAN-{inv.name}",
			"posting_date": inv.posting_date,
			"creation": inv.posting_date,
			"source": "Invoice",
			"reference_doctype": "Sales Invoice",
			"reference_name": inv.name,
			"qty": current_qty,
			"amount": current_amount,
			"prev_qty": acc_qty,
			"prev_amount": acc_amount,
			"current_qty": current_qty,
			"current_amount": current_amount,
			"accumulated_qty": acc_qty + current_qty,
			"accumulated_amount": acc_amount + current_amount,
			"unit": boq_item_doc.unit,
			"rate": boq_item_doc.rate,
			"invoice_status": "Submitted",
			"invoice_docstatus": 1,
			"is_proforma": 0,
			"tax_invoice": inv.name,
			"tax_invoice_amount": current_amount
		})
		filtered_entries.append(entry)
		acc_qty += current_qty
		acc_amount += current_amount



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
		item.is_purchase_item = 1
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
		item.is_purchase_item = 1
		item.description = "Advance payment deducted from progressive billing invoices"
		item.insert(ignore_permissions=True)
	
	return item_code


def _get_invoiced_advance_total(project: str) -> float:
	"""Sum net advance billed on submitted advance Sales Invoices for a project."""
	if not frappe.db.has_column("Sales Invoice", "custom_is_advanced"):
		return 0

	result = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(base_net_total), 0) AS total
		FROM `tabSales Invoice`
		WHERE project = %s
			AND docstatus = 1
			AND IFNULL(custom_is_advanced, 0) = 1
		""",
		project,
		as_dict=True,
	)
	return flt(result[0].total) if result else 0


def get_advance_balance(project: str) -> float:
	"""Get the available advance balance for a project"""
	paid_pool = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(amount), 0) AS total
		FROM `tabBOQ Advance Payment`
		WHERE project = %s AND docstatus = 1
		""",
		project,
		as_dict=True,
	)

	paid_collected = flt(paid_pool[0].total) if paid_pool else 0
	invoiced_advance = _get_invoiced_advance_total(project)
	total_collected = max(paid_collected, invoiced_advance)

	# Get total advances already deducted (from invoice items)
	# Include Draft (0) as well as Submitted (1) invoices
	total_deducted = frappe.db.sql("""
		SELECT COALESCE(SUM(ABS(sii.amount)), 0) as total
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.project = %s 
		AND si.docstatus IN (0, 1)
		AND sii.item_code = 'ADVANCE-DEDUCTION'
	""", project, as_dict=True)
	
	total_used = flt(total_deducted[0].total) if total_deducted else 0
	
	remaining_advance = total_collected - total_used

	# User's previous logic effectively capped the POOL by the percentage, which causes issues.
	# The requirement "percentage will be calculated on total of invoice" is handled in get_deduction_details.
	# get_advance_balance should return the AVAILABLE POOL.
	# Thus, we ignore the percentage here or return the full remaining amount.
	return remaining_advance


def get_boq_items_skip_advance(boq_item_names: list[str]) -> set[str]:
	"""Return BOQ item names where skip_advance_deduction is enabled."""
	if not boq_item_names:
		return set()
	names = list({name for name in boq_item_names if name})
	if not names:
		return set()
	return set(
		frappe.get_all(
			"BOQ Item",
			filters={"name": ["in", names], "skip_advance_deduction": 1},
			pluck="name",
		)
	)


def boq_item_skips_advance(boq_item: str) -> bool:
	if not boq_item:
		return False
	return bool(frappe.db.get_value("BOQ Item", boq_item, "skip_advance_deduction"))


def resolve_advance_deduction_for_boq_items(
	advance_deduction: float,
	boq_item_amounts: dict[str, float],
	project: str,
) -> float:
	"""Zero or cap advance when BOQ items skip advance deduction."""
	advance_deduction = flt(advance_deduction)
	if advance_deduction <= 0 or not boq_item_amounts:
		return 0

	skip_set = get_boq_items_skip_advance(list(boq_item_amounts.keys()))
	if skip_set and len(skip_set) == len(boq_item_amounts):
		return 0

	eligible_amount = sum(
		flt(amt) for boq, amt in boq_item_amounts.items() if boq not in skip_set
	)
	if eligible_amount <= 0:
		return 0

	project_doc = frappe.get_doc("Project", project)
	advance_pct = flt(getattr(project_doc, "advance_deduction", 0))
	max_from_pct = (
		flt(eligible_amount * advance_pct / 100, 2) if advance_pct else eligible_amount
	)
	return flt(min(advance_deduction, max_from_pct, get_advance_balance(project)), 2)


@frappe.whitelist()
def get_deduction_details(
	project: str,
	items: str | list | None = None,
	invoice_name: str | None = None,
	sales_order_name: str | None = None,
	sales_order_names: str | list | None = None,
) -> dict:
	"""
	Calculate available retention and advance deduction details for a project/invoice.
	
	Args:
		project: Project name
		items: List of invoice items with amounts (optional)
		invoice_name: Name of current invoice to exclude from balance (optional)
		sales_order_name: Draft SO name — advance lines on this order are added back to the pool for recalculation (optional)
		sales_order_names: List of SO names — same add-back for combined SO invoicing (optional)
		
	Returns:
		dict with retention_percentage, available_advance, suggested_retention, suggested_advance,
		total_billable_amount, available_boq_balance (project BOQ value minus billed BOQ lines, ex-VAT)
	"""
	if isinstance(items, str):
		import json
		items = json.loads(items)
		
	project_doc = frappe.get_doc("Project", project)
	retention_percentage = flt(project_doc.retention_percentage) if hasattr(project_doc, 'retention_percentage') else 0
	advance_percentage = flt(project_doc.advance_deduction) if hasattr(project_doc, 'advance_deduction') else 0
	enable_progressive_boq = getattr(project_doc, "enable_progressive_boq", 0)
	
	total_gross_amount = 0
	total_net_amount = 0
	skip_advance_boq_items = []
	total_net_amount_for_advance = 0
	
	if items:
		# Fetch variance item from BOQ Settings
		boq_settings = frappe.get_cached_doc("BOQ Settings", project_doc.company)
		variance_item = getattr(boq_settings, "varience_item", None)
		
		# Gross Amount: Exclude Variance (since Variance reduces total, ignoring it gives Gross)
		total_gross_amount = sum(flt(item.get("amount", 0)) for item in items 
			if not item.get("item_code") in ["RETENTION-DEDUCTION", "ADVANCE-DEDUCTION", variance_item])
			
		# Net Amount: Include Variance deduction (so Gross - Variance)
		total_net_amount = sum(flt(item.get("amount", 0)) for item in items 
			if not item.get("item_code") in ["RETENTION-DEDUCTION", "ADVANCE-DEDUCTION"])

		boq_names = [item.get("boq_item") for item in items if item.get("boq_item")]
		if boq_names:
			skip_set = get_boq_items_skip_advance(boq_names)
			skip_advance_boq_items = list(skip_set)
			if skip_set:
				total_net_amount_for_advance = sum(
					flt(item.get("amount", 0))
					for item in items
					if item.get("item_code") not in ["RETENTION-DEDUCTION", "ADVANCE-DEDUCTION"]
					and item.get("boq_item") not in skip_set
				)
			else:
				total_net_amount_for_advance = total_net_amount
		else:
			total_net_amount_for_advance = total_net_amount
	else:
		total_net_amount_for_advance = total_net_amount
	
	# Retention is usually on Gross Amount
	suggested_retention = flt(total_gross_amount * retention_percentage / 100, 2)
	
	available_advance = get_advance_balance(project)
	
	# If invoice_name is provided, it means we are recalculating for an existing (possibly Draft) invoice.
	# The get_advance_balance(project) now includes Drafts, so it already subtracted this invoice's deductions.
	# We should add them back for THIS invoice's "available" calculation so it doesn't double-subtract.
	if invoice_name:
		current_deductions = frappe.db.sql("""
			SELECT COALESCE(SUM(ABS(sii.amount)), 0) as total
			FROM `tabSales Invoice Item` sii
			WHERE sii.parent = %s AND sii.item_code = 'ADVANCE-DEDUCTION'
		""", invoice_name, as_dict=True)
		available_advance += flt(current_deductions[0].total) if current_deductions else 0

	if sales_order_name:
		sales_order_names = sales_order_names or [sales_order_name]
	if isinstance(sales_order_names, str):
		import json
		sales_order_names = json.loads(sales_order_names)

	for so_name in sales_order_names or []:
		so_adv = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(ABS(soi.amount)), 0) AS total
			FROM `tabSales Order Item` soi
			WHERE soi.parent = %s AND soi.item_code = 'ADVANCE-DEDUCTION'
			""",
			so_name,
			as_dict=True,
		)
		available_advance += flt(so_adv[0].total) if so_adv else 0
	
	# Suggested advance based on percentage cap
	# Calculate suggested advance deduction based on NET Amount (Gross - Variance)
	suggested_advance_deduction = flt(total_net_amount_for_advance * advance_percentage / 100, 2)
	
	suggested_advance = min(available_advance, suggested_advance_deduction)
	
	# Ensure items exist
	get_or_create_retention_item()
	get_or_create_advance_item()

	kpi = get_boq_kpi(project)
	available_boq_balance = flt(kpi.get("total_boq_value", 0)) - flt(kpi.get("total_billed", 0))
	
	return {
		"retention_percentage": retention_percentage,
		"advance_percentage": advance_percentage,
		"available_advance": flt(available_advance),
		"suggested_retention": suggested_retention,
		"suggested_advance": suggested_advance,
		"total_billable_amount": total_gross_amount,
		"available_boq_balance": flt(available_boq_balance),
		"enable_progressive_boq": enable_progressive_boq,
		"skip_advance_boq_items": skip_advance_boq_items,
	}


@frappe.whitelist()
def get_retention_summary(project: str) -> dict:
	"""Get retention summary for a project (includes opening JE balance on retention account)."""
	return _get_retention_summary(project)


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
	
	try:
		invoice.insert()
		frappe.db.commit()
		frappe.flags.commit = True
		
		frappe.logger().info(
			f"Created retention release invoice {invoice.name} for project {project}, amount={release_amount}"
		)
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			message=f"Error creating retention release invoice for project {project}: {str(e)}",
			title="Retention Release Error"
		)
		frappe.throw(_("Failed to create retention release invoice: {0}").format(str(e)))
	
	return {
		"status": "success",
		"invoice": invoice.name,
		"amount": release_amount,
		"doc_status": "Draft"
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
def recalculate_sales_order_boq_deductions(sales_order: str) -> dict:
	"""
	Remove existing RETENTION-DEDUCTION / ADVANCE-DEDUCTION rows and rebuild them from the current
	BOQ revenue lines, Project retention %, and advance pool — same rules as create_sales_order_from_selected_items.
	"""
	doc = frappe.get_doc("Sales Order", sales_order)
	if doc.docstatus != 0:
		frappe.throw(_("Only draft Sales Orders can recalculate deductions."))
	if not doc.get("project"):
		frappe.throw(_("Set Project before recalculating deductions."))

	project_doc = frappe.get_doc("Project", doc.project)
	boq_settings = (
		frappe.get_cached_doc("BOQ Settings", doc.company)
		if frappe.db.exists("BOQ Settings", doc.company)
		else None
	)
	variance_item = getattr(boq_settings, "varience_item", None) if boq_settings else None

	deduction_item_codes = {"RETENTION-DEDUCTION", "ADVANCE-DEDUCTION"}
	for row in list(doc.items):
		if row.item_code in deduction_item_codes:
			doc.remove(row)

	excluded_for_base = set(deduction_item_codes)
	if variance_item:
		excluded_for_base.add(variance_item)

	items_for_deductions = []
	advance_base_items = []

	for row in doc.items:
		if row.item_code in excluded_for_base:
			continue
		if not row.get("boq_item"):
			continue
		amt = flt(row.amount)
		if amt <= 0:
			continue

		items_for_deductions.append({"item_code": row.item_code, "amount": amt})
		boq_desc = row.description
		bill_no = row.bill_no
		if not boq_desc or not bill_no:
			bi = frappe.db.get_value(
				"BOQ Item", row.boq_item, ["description", "parent_bill"], as_dict=True
			)
			if bi:
				boq_desc = boq_desc or bi.description
				bill_no = bill_no or bi.parent_bill

		if not boq_item_skips_advance(row.boq_item):
			advance_base_items.append({
				"boq_item": row.boq_item,
				"bill_no": bill_no,
				"description": boq_desc or "",
				"amount": amt,
			})

		if project_doc.retention_percentage and flt(project_doc.retention_percentage) > 0:
			retention_amount = flt(amt * flt(project_doc.retention_percentage) / 100, 2)
			if retention_amount > 0:
				retention_item_code = get_or_create_retention_item()
				doc.append(
					"items",
					{
						"item_code": retention_item_code,
						"item_name": "Retention Deduction",
						"description": _("Retention deduction ({0}%) for: {1}").format(
							project_doc.retention_percentage, boq_desc or row.item_code
						),
						"qty": 1,
						"rate": -retention_amount,
						"amount": -retention_amount,
						"uom": row.uom or "Nos",
						"project": doc.project,
						"boq_item": row.boq_item,
						"bill_no": bill_no,
					},
				)

	if items_for_deductions:
		deduction_details = get_deduction_details(
			doc.project,
			items_for_deductions,
			sales_order_name=doc.name,
		)
		advance_pct = flt(deduction_details.get("advance_percentage", 0))
		available_advance = flt(deduction_details.get("available_advance", 0))
		if advance_pct > 0 and available_advance > 0 and advance_base_items:
			advance_item_code = get_or_create_advance_item()
			desired_advances = []
			total_desired = 0
			for entry in advance_base_items:
				desired = flt(entry["amount"] * advance_pct / 100, 2)
				if desired > 0:
					desired_advances.append((entry, desired))
					total_desired += desired

			if total_desired > 0:
				target_total = flt(min(available_advance, total_desired), 2)
				scale = target_total / total_desired if total_desired else 0
				running_total = 0
				last_index = len(desired_advances) - 1

				for idx, (entry, desired) in enumerate(desired_advances):
					if idx == last_index:
						advance_amount = flt(target_total - running_total, 2)
					else:
						advance_amount = flt(desired * scale, 2)
						running_total += advance_amount

					if advance_amount <= 0:
						continue

					doc.append(
						"items",
						{
							"item_code": advance_item_code,
							"item_name": "Advance Deduction",
							"description": _("Advance deduction ({0}%) for: {1}").format(
								advance_pct, entry["description"]
							),
							"qty": 1,
							"rate": -advance_amount,
							"amount": -advance_amount,
							"uom": "Nos",
							"project": doc.project,
							"boq_item": entry["boq_item"],
							"bill_no": entry["bill_no"],
						},
					)

	doc.run_method("calculate_taxes_and_totals")
	doc.save()

	return {"status": "ok", "message": _("Retention and advance lines were recalculated.")}


@frappe.whitelist()
def create_sales_order_from_selected_items(
	project: str,
	items: str | list,
	posting_date: str = None,
	remarks: str = None,
	auto_submit: int = 1
) -> dict:
	"""
	Create Sales Order from selected BOQ Items.
	
	Args:
		project: Project name
		items: List of dicts with boq_item and qty
		posting_date: Optional posting date
		remarks: Optional remarks
		auto_submit: Whether to auto-submit the order (1=yes, 0=no)
		
	Returns:
		dict with status, data or error_message
	"""
	import json
	
	try:
		if isinstance(items, str):
			items = json.loads(items)
		
		if not items:
			return {"status": "error", "error_message": _("No items provided")}
		
		auto_submit = int(auto_submit)
		
		# Get project details
		project_doc = frappe.get_doc("Project", project)
		customer = project_doc.customer
		
		if not customer:
			return {"status": "error", "error_message": _("Project must have a customer")}
		
		order = frappe.new_doc("Sales Order")
		order.project = project
		order.customer = customer
		order.transaction_date = posting_date or today()
		order.delivery_date = posting_date or today()
		order.remarks = remarks
		
		bills_included = set()
		items_for_deductions = []
		advance_base_items = []
		
		for item_data in items:
			boq_item_name = item_data.get("boq_item")
			qty = flt(item_data.get("qty", 0))
			
			if qty <= 0:
				continue
			
			# Get BOQ Item details
			boq_item = frappe.get_doc("BOQ Item", boq_item_name)
			
			# Ensure linked_item exists
			if not boq_item.linked_item:
				boq_item.create_linked_item()
				boq_item.reload()
			
			# Get percentage if provided
			percentage = flt(item_data.get("percentage", 0))

			# Add item to order
			order.append("items", {
				"item_code": boq_item.linked_item or boq_item.item_code,
				"description": boq_item.description,
				"qty": qty,
				"rate": boq_item.rate,
				"uom": boq_item.unit,
				"project": project,
				"boq_item": boq_item_name,
				"bill_no": boq_item.parent_bill,
				"custom_billing_percentage": percentage
			})
			
			amount = qty * flt(boq_item.rate)
			items_for_deductions.append({
				"item_code": boq_item.linked_item or boq_item.item_code,
				"amount": amount
			})
			if not boq_item_skips_advance(boq_item_name):
				advance_base_items.append({
					"boq_item": boq_item_name,
					"bill_no": boq_item.parent_bill,
					"description": boq_item.description,
					"amount": amount
				})
			
			# Calculate and add Retention Deduction
			if project_doc.retention_percentage:
				retention_amount = flt(amount * flt(project_doc.retention_percentage) / 100, 2)
				if retention_amount > 0:
					retention_item_code = get_or_create_retention_item()
					order.append("items", {
						"item_code": retention_item_code,
						"item_name": f"Retention Deduction",
						"description": f"Retention deduction ({project_doc.retention_percentage}%) for: {boq_item.description}",
						"qty": 1,
						"rate": -retention_amount,
						"uom": "Nos",
						"project": project,
						"boq_item": boq_item_name,
						"bill_no": boq_item.parent_bill
					})

			bill_no = frappe.db.get_value("BOQ Bill", boq_item.parent_bill, "bill_no")
			bills_included.add(bill_no or boq_item.parent_bill)
		
		deduction_details = get_deduction_details(project, items_for_deductions)
		advance_pct = flt(deduction_details.get("advance_percentage", 0))
		available_advance = flt(deduction_details.get("available_advance", 0))
		if advance_pct > 0 and available_advance > 0 and advance_base_items:
			advance_item_code = get_or_create_advance_item()
			desired_advances = []
			total_desired = 0
			for entry in advance_base_items:
				desired = flt(entry["amount"] * advance_pct / 100, 2)
				if desired > 0:
					desired_advances.append((entry, desired))
					total_desired += desired
			
			if total_desired > 0:
				target_total = flt(min(available_advance, total_desired), 2)
				scale = target_total / total_desired if total_desired else 0
				running_total = 0
				allocated_total = 0
				last_index = len(desired_advances) - 1
				
				for idx, (entry, desired) in enumerate(desired_advances):
					if idx == last_index:
						advance_amount = flt(target_total - running_total, 2)
					else:
						advance_amount = flt(desired * scale, 2)
						running_total += advance_amount
					
					if advance_amount <= 0:
						continue
					
					allocated_total += advance_amount
					order.append("items", {
						"item_code": advance_item_code,
						"item_name": "Advance Deduction",
						"description": f"Advance deduction ({advance_pct}%) for: {entry['description']}",
						"qty": 1,
						"rate": -advance_amount,
						"uom": "Nos",
						"project": project,
						"boq_item": entry["boq_item"],
						"bill_no": entry["bill_no"]
					})
				
				if allocated_total - target_total > 0.01:
					frappe.throw(_("Advance deduction allocation exceeds available advance."))
		
		if not order.items:
			return {"status": "error", "error_message": _("No valid items to order")}
		
		# Populate taxes
		if not order.get("taxes_and_charges"):
			company_curr = project_doc.company
			default_tax = get_default_taxes_and_charges("Sales Taxes and Charges Template", company=company_curr)
			
			if default_tax and default_tax.get("taxes_and_charges"):
				order.taxes_and_charges = default_tax["taxes_and_charges"]
				if not order.get("taxes"):
					for tax in default_tax.get("taxes", []):
						order.append("taxes", tax)
		
		if not order.get("taxes") and not order.get("taxes_and_charges"):
			try:
				customer_taxes = frappe.db.get_value("Customer", customer, "taxes_and_charges")
			except Exception as e:
				customer_taxes = None
			if customer_taxes:
					order.taxes_and_charges = customer_taxes
					order.run_method("set_taxes")
			
		
		order.run_method("calculate_taxes_and_totals")
		
		# Insert the order
		order.insert()
		
		# Auto-submit if requested
		# if auto_submit:
		# 	order.submit()
		
		frappe.db.commit()
		frappe.flags.commit = True
		
		return {
			"status": "success",
			"name": order.name,
			"project": order.project,
			"item_count": len(order.items),
			"bills_included": list(bills_included),
			"amount": order.base_grand_total,
			"docstatus": order.docstatus
		}
		
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(f"Error creating sales order: {str(e)}", "Sales Order API Error")
		return {"status": "error", "error_message": str(e)}


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


def calculate_variance(proforma_amount: float, pc_amount: float) -> float:
	"""
	Calculate variance between Proforma Invoice and Payment Certificate.
	
	Variance = PI Amount - PC Amount
	Positive variance = loss (customer paid less than billed)
	
	Args:
		proforma_amount: Proforma Invoice amount
		pc_amount: Payment Certificate accepted amount
		
	Returns:
		Variance amount (positive = loss)
	
	Requirements: 3.1
	"""
	return flt(proforma_amount) - flt(pc_amount)


def calculate_variance_percent(variance: float, proforma_amount: float) -> float:
	"""
	Calculate variance percentage.
	
	Variance% = (Variance / PI Amount) * 100
	
	Args:
		variance: Variance amount
		proforma_amount: Proforma Invoice amount
		
	Returns:
		Variance percentage
	"""
	if flt(proforma_amount) <= 0:
		return 0
	return flt(variance / proforma_amount * 100, 2)


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
	else:
		_set_direct_billing_mode(invoice, is_proforma)
	
	total_amount = 0
	items_added = 0
	bills_included = set()
	boq_item_amounts = {}
	
	for item_data in items:
		boq_item_name = item_data.get("boq_item")
		# Accept both "qty" and "current_qty" field names for backward compatibility
		current_qty = flt(item_data.get("current_qty") or item_data.get("qty", 0))
		
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
		boq_item_amounts[boq_item_name] = flt(boq_item_amounts.get(boq_item_name, 0)) + current_amount
		
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
	
	advance_deduction = resolve_advance_deduction_for_boq_items(
		advance_deduction, boq_item_amounts, project
	)
	
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
	
	try:
		invoice.insert()
		# Ensure the transaction is committed
		frappe.db.commit()
		# Also set flag to prevent any later rollback
		frappe.flags.commit = True
		frappe.logger().info(
			f"Created Sales Invoice {invoice.name} for project {project}, "
			f"items={items_added}, amount={total_amount}, is_proforma={is_proforma}"
		)
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			message=f"Error creating invoice for project {project}: {str(e)}",
			title="Invoice Creation Error"
		)
		return {
			"status": "error",
			"error_message": _("Failed to create invoice: {0}").format(str(e))
		}
	
	net_amount = total_amount - retention_amount - advance_deduction
	
	return {
		"status": "success",
		"invoice": invoice.name,
		"customer": customer,
		"item_count": items_added,
		"bills_included": list(bills_included),
		"gross_amount": total_amount,
		"retention_amount": retention_amount,
		"advance_deduction": advance_deduction,
		"net_amount": net_amount,
		"doc_status": "Draft",
		"is_proforma": is_proforma
	}


@frappe.whitelist()
def create_pc_from_purchase_receipt(
	purchase_receipt: str,
	accepted_amount: float = None,
	bill_no: str = None,
	remarks: str = None
) -> dict:
	"""
	Create Payment Certificate from a Purchase Receipt.
	Property 5: Purchase Payment Certificate Creation
	Requirements: 6.2, 6.5
	
	Args:
		purchase_receipt: Purchase Receipt name
		accepted_amount: Optional accepted amount (defaults to PR grand_total)
		bill_no: Optional Bill No
		remarks: Optional remarks
		
	Returns:
		dict with created Payment Certificate info
	"""
	# Get Purchase Receipt
	pr = frappe.get_doc("Purchase Receipt", purchase_receipt)
	
	if pr.docstatus != 1:
		frappe.throw(_("Purchase Receipt must be submitted"))
	
	if not pr.project:
		frappe.throw(_("Purchase Receipt must have a Project assigned"))

	if accepted_amount is None:
		accepted_amount = pr.grand_total
	
	# Check if PC already exists for this PR
	existing = frappe.db.exists(
		"Payment Certificate",
		{
			"purchase_receipt": purchase_receipt,
			"docstatus": ["!=", 2]
		}
	)
	if existing:
		frappe.throw(
			_("Payment Certificate {0} already exists for this Purchase Receipt").format(existing)
		)
	
	# Create Payment Certificate
	pc = frappe.new_doc("Payment Certificate")
	pc.type = "Purchase"
	pc.project = pr.project
	pc.supplier = pr.supplier
	pc.purchase_receipt = purchase_receipt
	pc.pr_amount = flt(pr.grand_total)
	pc.accepted_amount = flt(accepted_amount)
	pc.posting_date = today()
	pc.remarks = remarks
	
	# Copy Bill No if provided
	if bill_no:
		pc.bill_no = bill_no
	elif hasattr(pr, 'custom_bill_no') and pr.custom_bill_no:
		pc.bill_no = pr.custom_bill_no
	
	# Populate Items table
	total_amount = 0
	for item in pr.items:
		# Filter by bill_no if it was specified in the creation dialog
		item_bill_no = item.get("custom_bill_no") or item.get("bill_no")
		item_boq_item = item.get("custom_boq_item") or item.get("boq_item")

		include = True
		if pc.bill_no and item_bill_no and item_bill_no != pc.bill_no:
			include = False

		if include:
			pc.append("items", {
				"boq_item": item_boq_item,
				"bill_no": item_bill_no,
				"description": item.description,
				"unit": item.uom,
				"qty": item.qty,
				"rate": item.rate,
				"amount": item.amount,
				"accepted_amount": item.amount # Default to full
			})
			total_amount += flt(item.amount)

	# If we have items, update pr_amount and accepted_amount to sum of items
	if pc.get("items"):
		pc.pr_amount = total_amount
		# If accepted_amount was passed as grand_total (default), use total_amount of matched items
		if flt(accepted_amount) == flt(pr.grand_total):
			pc.accepted_amount = total_amount
		else:
			# If user entered a custom accepted amount, we keep it
			pc.accepted_amount = flt(accepted_amount)

	# Try to get Purchase Order from PR items
	if pr.items:
		for item in pr.items:
			if item.purchase_order:
				pc.purchase_order = item.purchase_order
				break
	
	pc.insert()
	
	# Commit the transaction
	frappe.db.commit()
	frappe.flags.commit = True
	
	frappe.logger().info(
		f"Created Payment Certificate {pc.name} from Purchase Receipt {purchase_receipt}, "
		f"amount={accepted_amount}"
	)
	
	return {
		"status": "success",
		"name": pc.name,
		"project": pc.project,
		"supplier": pc.supplier,
		"pr_amount": pc.pr_amount,
		"accepted_amount": pc.accepted_amount,
		"variance": pc.variance,
		"bill_no": pc.bill_no,
		"boq_item": pc.boq_item
	}


@frappe.whitelist()
def create_payment_certificate_from_sales_order(sales_order: str, accepted_amount: float = None, remarks: str = None) -> dict:
	"""Create Payment Certificate from a Sales Order with multiple items."""
	so = frappe.get_doc("Sales Order", sales_order)
	
	if so.docstatus != 1:
		frappe.throw(_("Sales Order must be submitted"))
	
	# Check if PC already exists for this SO
	existing_pc = frappe.db.exists("Payment Certificate", {
		"sales_order": sales_order,
		"docstatus": ["!=", 2]
	})
	if existing_pc:
		frappe.throw(_("Payment Certificate {0} already exists for this Sales Order").format(existing_pc))
	
	pc = frappe.new_doc("Payment Certificate")
	pc.type = "Sales"
	pc.project = so.project
	pc.customer = so.customer
	pc.sales_order = sales_order
	pc.remarks = remarks
	
	def get_latest_sales_invoice_for_so(so_name: str):
		latest = frappe.get_all(
			"Sales Invoice",
			filters={"custom_sales_order": so_name, "docstatus": 1},
			fields=["name"],
			order_by="posting_date desc, creation desc",
			limit=1
		)
		if latest:
			return frappe.get_doc("Sales Invoice", latest[0].name)
		return None
	
	def apply_si_deductions_to_items(pc_doc, si_doc, company_name):
		"""Map SI retention/advance deductions to PC items."""
		if not pc_doc.get("items"):
			return
		
		if not si_doc:
			for pc_item in pc_doc.items:
				pc_item.invoiced_amount = flt(pc_item.amount)
			return
		
		variance_item_code = None
		if company_name and frappe.db.exists("BOQ Settings", company_name):
			variance_item_code = frappe.db.get_value("BOQ Settings", company_name, "varience_item")
		
		gross_by_boq = {}
		total_gross = 0
		item_specific = {}
		global_deductions = {"retention": 0, "advance": 0}
		
		for item in si_doc.items:
			is_retention = item.item_code == "RETENTION-DEDUCTION"
			is_advance = item.item_code == "ADVANCE-DEDUCTION"
			is_variance = variance_item_code and item.item_code == variance_item_code
			
			if not (is_retention or is_advance or is_variance) and item.get("boq_item"):
				gross_by_boq[item.boq_item] = flt(gross_by_boq.get(item.boq_item)) + flt(item.amount)
				total_gross += flt(item.amount)
			elif is_retention or is_advance:
				target_boq_item = item.get("boq_item")
				val = flt(item.amount)
				if target_boq_item:
					item_specific.setdefault(target_boq_item, {"retention": 0, "advance": 0})
					if is_retention:
						item_specific[target_boq_item]["retention"] += val
					if is_advance:
						item_specific[target_boq_item]["advance"] += val
				else:
					if is_retention:
						global_deductions["retention"] += val
					if is_advance:
						global_deductions["advance"] += val
		
		for pc_item in pc_doc.items:
			boq_item = pc_item.boq_item
			gross_amount = flt(gross_by_boq.get(boq_item) or pc_item.amount)
			spec = item_specific.get(boq_item, {"retention": 0, "advance": 0})
			
			allocated_retention = 0
			allocated_advance = 0
			if total_gross > 0:
				share = gross_amount / total_gross
				allocated_retention = global_deductions["retention"] * share
				allocated_advance = global_deductions["advance"] * share
			
			retention_amount = abs(flt(spec["retention"] + allocated_retention))
			advance_amount = abs(flt(spec["advance"] + allocated_advance))
			
			pc_item.retention_amount = retention_amount
			pc_item.advance_amount = advance_amount
			pc_item.invoiced_amount = gross_amount - retention_amount - advance_amount

	def apply_so_additional_discount(pc_doc, so_doc):
		"""Distribute SO additional discount across PC items without adding negative rows."""
		if not pc_doc.get("items"):
			return
		
		discount_amount = flt(getattr(so_doc, "discount_amount", 0))
		if discount_amount <= 0:
			return
		
		total_amount = sum(flt(i.amount) for i in pc_doc.items)
		if total_amount <= 0:
			return
		
		remaining_discount = discount_amount
		for idx, pc_item in enumerate(pc_doc.items):
			if idx == len(pc_doc.items) - 1:
				share = remaining_discount
			else:
				share = flt(discount_amount * (flt(pc_item.amount) / total_amount), 2)
				remaining_discount -= share
			
			pc_item.accepted_amount = max(0, flt(pc_item.accepted_amount) - share)
		
		pc_doc.discount_type = "Amount"
		pc_doc.discount_amount = discount_amount
		apply_on = (getattr(so_doc, "apply_discount_on", "") or "").strip()
		if apply_on:
			pc_doc.select_discount_on = apply_on
	
	# Populate items from Sales Order
	if so.items:
		for item in so.items:
			# Skip deduction items created on Sales Order as PC calculates its own
			if item.item_code in ["RETENTION-DEDUCTION", "ADVANCE-DEDUCTION"]:
				continue
			
			pc.append("items", {
				"boq_item": item.get("boq_item"),
				"bill_no": item.get("bill_no"),
				"description": item.description,
				"unit": item.uom,
				"qty": item.qty,
				"rate": item.rate,
				"amount": item.amount,
				"accepted_amount": item.amount, # Default to full amount
				"sales_order_item": item.name
			})
	
	# Populate default taxes
	company = frappe.db.get_value("Project", so.project, "company")
	apply_si_deductions_to_items(pc, so, company)
	# apply_so_additional_discount(pc, so)
	default_tax = get_default_taxes_and_charges("Sales Taxes and Charges Template", company=company)
	if default_tax and default_tax.get("taxes_and_charges"):
		pc.taxes_and_charges = default_tax["taxes_and_charges"]
		for tax in default_tax.get("taxes", []):
			pc.append("taxes", tax)
	
	# Trigger totals calculation
	pc.calculate_totals()
	pc.calculate_retention()
	
	# Override if specific amount provided
	if accepted_amount is not None:
		pc.accepted_amount = flt(accepted_amount)
		# Recalculate retention if accepted amount is changed
		pc.calculate_retention()
	
	pc.insert()
	
	return {
		"name": pc.name,
		"project": pc.project,
		"proforma_amount": pc.proforma_amount,
		"accepted_amount": pc.accepted_amount,
		"variance": pc.variance
	}


@frappe.whitelist()
def create_payment_certificate(proforma_invoice: str, posting_date: str = None, accepted_amount: float = None) -> str:
	"""
	Create Payment Certificate from Proforma or Sales Order.
	"""
	# Check if it's a Sales Order
	if frappe.db.exists("Sales Order", proforma_invoice):
		result = create_payment_certificate_from_sales_order(proforma_invoice, accepted_amount)
		return result.get("name")
		
	# Legacy Proforma Invoice Support
	proforma = frappe.get_doc("Proforma Invoice", proforma_invoice)
	
	if proforma.docstatus != 1:
		frappe.throw(_("Proforma Invoice must be submitted"))
	
	# Check if PC already exists
	existing = frappe.db.exists(
		"Payment Certificate",
		{
			"proforma_invoice": proforma_invoice,
			"docstatus": ["!=", 2]
		}
	)
	if existing:
		frappe.throw(
			_("Payment Certificate {0} already exists for this Proforma Invoice").format(existing)
		)
	
	proforma_amount = flt(proforma.net_amount) or flt(proforma.amount)
	
	if accepted_amount is None:
		accepted_amount = proforma_amount
	else:
		accepted_amount = flt(accepted_amount)
	
	pc = frappe.new_doc("Payment Certificate")
	pc.type = "Sales"
	pc.project = proforma.project
	pc.customer = proforma.customer
	pc.proforma_invoice = proforma_invoice
	pc.proforma_amount = proforma_amount
	pc.accepted_amount = accepted_amount
	pc.posting_date = getdate(posting_date) if posting_date else today()
	
	if proforma.items:
		for item in proforma.items:
			pc.append("items", {
				"boq_item": item.boq_item,
				"description": item.description,
				"unit": item.unit,
				"qty": item.qty,
				"rate": item.rate,
				"amount": item.amount,
				"accepted_amount": (flt(item.amount) / proforma_amount) * accepted_amount if proforma_amount > 0 else 0
			})
	
	pc.insert()
	return pc.name



@frappe.whitelist()
def get_proforma_management_data(project: str) -> dict:
	"""
	Get all Proforma Invoices for a project with their PC status and available actions.
	Requirements: 3.1
	
	Args:
		project: Project name
		
	Returns:
		dict with proformas grouped by status
	"""
	# Get all proforma invoices for the project
	proformas = frappe.db.sql("""
		SELECT 
			si.name,
			si.posting_date,
			si.grand_total,
			si.customer,
			si.customer_name,
			pc.name as payment_certificate,
			pc.status as pc_status,
			pc.accepted_amount,
			pc.variance,
			pc.tax_invoice,
			DATEDIFF(CURDATE(), si.posting_date) as age_days
		FROM `tabSales Invoice` si
		LEFT JOIN `tabPayment Certificate` pc ON pc.proforma_invoice = si.name AND pc.docstatus != 2
		WHERE si.project = %s
		AND si.custom_is_proforma = 1
		AND si.docstatus = 0
		ORDER BY si.posting_date DESC
	""", project, as_dict=True)
	
	# Group by status and add action
	pending = []
	draft_pc = []
	submitted_pc = []
	invoiced = []
	
	for p in proformas:
		action = get_action_for_proforma(p)
		p["action"] = action
		
		if not p.payment_certificate:
			pending.append(p)
		elif p.pc_status == "Draft":
			draft_pc.append(p)
		elif p.pc_status == "Submitted":
			submitted_pc.append(p)
		elif p.pc_status in ["Invoiced", "Paid"]:
			invoiced.append(p)
		else:
			pending.append(p)
	
	return {
		"pending": pending,
		"draft_pc": draft_pc,
		"submitted_pc": submitted_pc,
		"invoiced": invoiced,
		"total_count": len(proformas),
		"pending_count": len(pending),
		"draft_pc_count": len(draft_pc),
		"submitted_pc_count": len(submitted_pc),
		"invoiced_count": len(invoiced)
	}


def get_action_for_proforma(proforma: dict) -> str:
	"""
	Determine available action for a proforma invoice.
	Property 3: Action Button Visibility Based on Status
	Requirements: 3.2, 3.3, 3.4
	
	Args:
		proforma: Proforma invoice dict with PC info
		
	Returns:
		Action string: "create_pc", "submit_pc", "view_details"
	"""
	if not proforma.get("payment_certificate"):
		return "create_pc"
	
	pc_status = proforma.get("pc_status")
	
	if pc_status == "Draft":
		return "submit_pc"
	elif pc_status in ["Submitted", "Invoiced", "Paid"]:
		return "view_details"
	else:
		return "create_pc"


SO_DEDUCTION_ITEM_CODES = frozenset({"RETENTION-DEDUCTION", "ADVANCE-DEDUCTION"})


def _parse_name_list(values) -> list[str]:
	import json

	if not values:
		return []
	if isinstance(values, str):
		values = json.loads(values)
	if isinstance(values, (list, tuple)):
		return [str(v).strip() for v in values if str(v).strip()]
	return [str(values).strip()]


def _get_so_item_pending_amount(so_item) -> float:
	return flt(flt(so_item.amount) - flt(so_item.billed_amt))


def _get_so_item_pending_qty(so_item, so_doc) -> float:
	if so_doc.get("has_unit_price_items") and flt(so_item.qty) == 0:
		return flt(so_item.qty)
	if flt(so_item.qty) and flt(so_item.billed_amt):
		billed_qty = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(qty), 0)
			FROM `tabSales Invoice Item` sii
			INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE si.docstatus = 1 AND sii.so_detail = %s
			""",
			so_item.name,
		)[0][0] or 0
		return flt(so_item.qty) - flt(billed_qty)
	return flt(so_item.qty) - flt(so_item.returned_qty)


def _so_has_submitted_payment_certificate(so_name: str) -> bool:
	return bool(
		frappe.db.exists(
			"Payment Certificate",
			{"sales_order": so_name, "docstatus": 1},
		)
	)


def get_pending_so_revenue_lines(so_doc) -> list[dict]:
	"""Return unbilled BOQ revenue lines from a submitted Sales Order."""
	lines = []
	for so_item in so_doc.items:
		if so_item.item_code in SO_DEDUCTION_ITEM_CODES:
			continue
		if not so_item.get("boq_item"):
			continue

		pending_amount = _get_so_item_pending_amount(so_item)
		if pending_amount <= 0:
			continue

		pending_qty = _get_so_item_pending_qty(so_item, so_doc)
		rate = flt(so_item.rate)
		if not rate and pending_qty:
			rate = flt(pending_amount / pending_qty)

		lines.append(
			{
				"item_code": so_item.item_code,
				"description": so_item.description,
				"qty": pending_qty,
				"rate": rate,
				"amount": pending_amount,
				"accepted_amount": pending_amount,
				"boq_item": so_item.boq_item,
				"bill_no": so_item.bill_no,
				"sales_order": so_doc.name,
				"so_detail": so_item.name,
			}
		)
	return lines


def append_per_item_revenue_and_deductions(
	invoice,
	line_items: list[dict],
	deduction_details: dict,
	*,
	company: str,
	project: str,
	income_account: str | None = None,
	cost_center: str | None = None,
	include_variance: bool = False,
):
	"""Append revenue lines and proportional retention/advance deductions to a Sales Invoice."""
	settings = frappe.get_cached_doc("BOQ Settings", company)
	income_account = income_account or frappe.db.get_value("Company", company, "default_income_account")
	cost_center = cost_center or invoice.cost_center or frappe.db.get_value("Company", company, "cost_center")

	suggested_retention = flt(deduction_details.get("suggested_retention"))
	suggested_advance = flt(deduction_details.get("suggested_advance"))
	retention_pct = flt(deduction_details.get("retention_percentage"))
	total_proforma = sum(flt(row.get("amount")) for row in line_items)

	skip_advance_set = get_boq_items_skip_advance(
		[row.get("boq_item") for row in line_items if row.get("boq_item")]
	)
	eligible_accepted = sum(
		flt(row.get("accepted_amount"))
		for row in line_items
		if row.get("boq_item") and row.get("boq_item") not in skip_advance_set
	)

	variance_item_code = settings.varience_item
	retention_item_code = "RETENTION-DEDUCTION"
	advance_item_code = "ADVANCE-DEDUCTION"

	get_or_create_retention_item()
	get_or_create_advance_item()

	for row in line_items:
		invoice.append(
			"items",
			{
				"item_code": row.get("item_code") or "Service",
				"description": row.get("description"),
				"qty": flt(row.get("qty")),
				"rate": flt(row.get("rate")),
				"amount": flt(row.get("amount")),
				"income_account": income_account,
				"project": project,
				"boq_item": row.get("boq_item"),
				"bill_no": row.get("bill_no"),
				"sales_order": row.get("sales_order"),
				"so_detail": row.get("so_detail"),
				"cost_center": cost_center,
			},
		)

		if include_variance:
			item_variance = flt(row.get("amount")) - flt(row.get("accepted_amount"))
			if item_variance > 0:
				if not variance_item_code:
					frappe.throw(
						_("Please set 'Varience Deduction Item' in BOQ Settings matching company {0}").format(
							company
						)
					)
				invoice.append(
					"items",
					{
						"item_code": variance_item_code,
						"item_name": "Variance Deduction",
						"description": f"Variance adjustment for: {row.get('description') or row.get('boq_item')}",
						"qty": 1,
						"rate": -item_variance,
						"amount": -item_variance,
						"income_account": income_account,
						"project": project,
						"boq_item": row.get("boq_item"),
						"bill_no": row.get("bill_no"),
						"cost_center": cost_center,
					},
				)

		if suggested_retention > 0 and total_proforma > 0:
			share = flt(row.get("amount")) / total_proforma
			item_retention = flt(suggested_retention * share, 2)
			if item_retention > 0:
				invoice.append(
					"items",
					{
						"item_code": retention_item_code,
						"item_name": "Retention Deduction",
						"description": f"Retention deduction ({retention_pct}%) for: {row.get('description') or row.get('boq_item')}",
						"qty": 1,
						"rate": -item_retention,
						"amount": -item_retention,
						"income_account": income_account,
						"project": project,
						"boq_item": row.get("boq_item"),
						"bill_no": row.get("bill_no"),
						"cost_center": cost_center,
					},
				)

		if (
			suggested_advance > 0
			and eligible_accepted > 0
			and row.get("boq_item")
			and not boq_item_skips_advance(row.get("boq_item"))
		):
			share = flt(row.get("accepted_amount")) / eligible_accepted
			item_advance = flt(suggested_advance * share, 2)
			if item_advance > 0:
				invoice.append(
					"items",
					{
						"item_code": advance_item_code,
						"item_name": "Advance Deduction",
						"description": f"Deduction from advance payment for: {row.get('description') or row.get('boq_item')}",
						"qty": 1,
						"rate": -item_advance,
						"amount": -item_advance,
						"income_account": income_account,
						"project": project,
						"boq_item": row.get("boq_item"),
						"bill_no": row.get("bill_no"),
						"cost_center": cost_center,
					},
				)


@frappe.whitelist()
def get_billable_sales_orders_for_invoice(project: str) -> list:
	"""Sales Orders with unbilled BOQ revenue lines, excluding submitted Payment Certificates."""
	if not project:
		return []

	filters = {"docstatus": 1, "project": project}
	sos = frappe.get_all(
		"Sales Order",
		filters=filters,
		fields=[
			"name",
			"project",
			"customer",
			"customer_name",
			"company",
			"base_grand_total",
			"transaction_date as posting_date",
			"taxes_and_charges",
		],
		order_by="transaction_date desc",
	)

	billable = []
	for so_row in sos:
		if _so_has_submitted_payment_certificate(so_row.name):
			continue

		so_doc = frappe.get_doc("Sales Order", so_row.name)
		pending_lines = get_pending_so_revenue_lines(so_doc)
		if not pending_lines:
			continue

		pending_amount = sum(flt(line.get("amount")) for line in pending_lines)
		invoiced_amount = flt(so_row.base_grand_total) - pending_amount

		billable.append(
			{
				"name": so_row.name,
				"project": so_row.project,
				"customer": so_row.customer,
				"customer_name": so_row.customer_name,
				"company": so_row.company,
				"posting_date": so_row.posting_date,
				"amount": flt(so_row.base_grand_total),
				"pending_amount": pending_amount,
				"invoiced_amount": max(invoiced_amount, 0),
				"has_invoice": 1 if invoiced_amount > 0 else 0,
				"taxes_and_charges": so_row.taxes_and_charges,
				"boq_items": list({line.get("boq_item") for line in pending_lines if line.get("boq_item")}),
			}
		)

	return billable


def _validate_combined_sales_orders(project: str, sales_orders: list[str]) -> list:
	if not sales_orders:
		frappe.throw(_("Select at least one Sales Order"))

	so_docs = []
	reference = None
	tax_templates = set()

	for so_name in sales_orders:
		if not frappe.db.exists("Sales Order", so_name):
			frappe.throw(_("Sales Order {0} does not exist").format(so_name))

		so_doc = frappe.get_doc("Sales Order", so_name)
		if so_doc.docstatus != 1:
			frappe.throw(_("Sales Order {0} must be submitted").format(so_name))
		if so_doc.project != project:
			frappe.throw(_("Sales Order {0} does not belong to project {1}").format(so_name, project))
		if _so_has_submitted_payment_certificate(so_name):
			frappe.throw(
				_("Sales Order {0} already has a submitted Payment Certificate").format(so_name)
			)

		pending_lines = get_pending_so_revenue_lines(so_doc)
		if not pending_lines:
			frappe.throw(_("Sales Order {0} has no unbilled BOQ lines").format(so_name))

		if reference is None:
			reference = {
				"customer": so_doc.customer,
				"company": so_doc.company,
				"project": so_doc.project,
				"currency": so_doc.currency,
				"conversion_rate": so_doc.conversion_rate,
				"selling_price_list": so_doc.selling_price_list,
			}
		else:
			if so_doc.customer != reference["customer"]:
				frappe.throw(_("All selected Sales Orders must have the same customer"))
			if so_doc.company != reference["company"]:
				frappe.throw(_("All selected Sales Orders must belong to the same company"))

		if so_doc.taxes_and_charges:
			tax_templates.add(so_doc.taxes_and_charges)

		so_docs.append(so_doc)

	if len(tax_templates) > 1:
		frappe.throw(_("All selected Sales Orders must use the same tax template"))

	return so_docs


@frappe.whitelist()
def make_combined_sales_invoice_from_selected_sales_orders(sales_orders) -> dict:
	"""Create combined draft Sales Invoice from selected SO names (project derived from SOs)."""
	sales_order_names = _parse_name_list(sales_orders)
	if not sales_order_names:
		frappe.throw(_("Select at least one Sales Order"))

	rows = frappe.get_all(
		"Sales Order",
		filters={"name": ["in", sales_order_names], "docstatus": 1},
		fields=["name", "project"],
	)
	if len(rows) != len(sales_order_names):
		frappe.throw(_("All selected Sales Orders must be submitted"))

	projects = {row.project for row in rows if row.project}
	if not projects:
		frappe.throw(_("Selected Sales Orders must have a Project"))
	if len(projects) > 1:
		frappe.throw(_("All selected Sales Orders must belong to the same project"))

	return make_combined_sales_invoice_from_sales_orders(projects.pop(), sales_order_names)


@frappe.whitelist()
def make_combined_sales_invoice_from_sales_orders(project: str, sales_orders) -> dict:
	"""Create one draft Sales Invoice from multiple submitted Sales Orders."""
	if not has_invoice_permission():
		frappe.throw(_("You do not have permission to create invoices"), frappe.PermissionError)

	sales_order_names = _parse_name_list(sales_orders)
	so_docs = _validate_combined_sales_orders(project, sales_order_names)

	revenue_lines = []
	for so_doc in so_docs:
		revenue_lines.extend(get_pending_so_revenue_lines(so_doc))

	if not revenue_lines:
		frappe.throw(_("No billable lines found on selected Sales Orders"))

	first_so = so_docs[0]
	company = first_so.company
	customer = first_so.customer

	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = customer
	invoice.company = company
	invoice.project = project
	invoice.posting_date = today()
	invoice.due_date = today()
	invoice.currency = first_so.currency
	invoice.conversion_rate = first_so.conversion_rate or 1
	invoice.selling_price_list = first_so.selling_price_list
	invoice.cost_center = frappe.db.get_value("Company", company, "cost_center")

	if frappe.db.has_column("Sales Invoice", "custom_billing_mode"):
		invoice.custom_billing_mode = "Sales Order"
	if frappe.db.has_column("Sales Invoice", "custom_source_sales_orders"):
		invoice.custom_source_sales_orders = ", ".join(sales_order_names)
	if frappe.db.has_column("Sales Invoice", "custom_is_proforma"):
		invoice.custom_is_proforma = 0

	deduction_details = get_deduction_details(
		project,
		revenue_lines,
		sales_order_names=sales_order_names,
	)
	append_per_item_revenue_and_deductions(
		invoice,
		revenue_lines,
		deduction_details,
		company=company,
		project=project,
		cost_center=invoice.cost_center,
		include_variance=False,
	)

	tax_template = next((so.taxes_and_charges for so in so_docs if so.taxes_and_charges), None)
	if tax_template:
		invoice.taxes_and_charges = tax_template
	elif not invoice.get("taxes"):
		default_tax = get_default_taxes_and_charges("Sales Taxes and Charges Template", company=company)
		if default_tax and default_tax.get("taxes_and_charges"):
			invoice.taxes_and_charges = default_tax["taxes_and_charges"]
			for tax in default_tax.get("taxes", []):
				invoice.append("taxes", tax)

	if not invoice.get("taxes") and not invoice.get("taxes_and_charges"):
		invoice.run_method("set_taxes_and_charges")

	invoice.run_method("calculate_taxes_and_totals")
	invoice.flags.ignore_permissions = True
	invoice.insert()

	return {"sales_invoice": invoice.name, "sales_orders": sales_order_names}
