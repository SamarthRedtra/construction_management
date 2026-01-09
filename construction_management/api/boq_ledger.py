# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt, today


@frappe.whitelist()
def get_previous_qty(boq_item: str) -> float:
	"""
	Get sum of ledger qty from completed transactions (submitted invoices, PCs).
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		float: Previous quantity from submitted documents
	"""
	# Sum all ledger entries from submitted documents
	# BOQ Progress Ledger is not submittable, so we check the source type
	# 'Invoice' entries come from submitted Sales Invoices
	# 'Proforma Reversal' entries are from cancelled proformas
	result = frappe.db.sql("""
		SELECT COALESCE(SUM(qty), 0) as total
		FROM `tabBOQ Progress Ledger`
		WHERE boq_item = %s
		AND source IN ('Invoice', 'Proforma', 'Proforma Reversal', 'Adjustment', 'Reversal')
		AND posting_date <= CURDATE()
	""", boq_item)
	
	return flt(result[0][0]) if result else 0


@frappe.whitelist()
def get_previous_amount(boq_item: str) -> float:
	"""
	Get sum of ledger amount from completed transactions.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		float: Previous amount from submitted documents
	"""
	# Sum all ledger entries
	result = frappe.db.sql("""
		SELECT COALESCE(SUM(amount), 0) as total
		FROM `tabBOQ Progress Ledger`
		WHERE boq_item = %s
		AND source IN ('Invoice', 'Proforma', 'Proforma Reversal', 'Adjustment', 'Reversal')
		AND posting_date <= CURDATE()
	""", boq_item)
	
	return flt(result[0][0]) if result else 0


@frappe.whitelist()
def get_to_date_qty(boq_item: str) -> float:
	"""
	Get sum of all ledger qty up to current date.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		float: To-date quantity
	"""
	result = frappe.db.sql("""
		SELECT COALESCE(SUM(qty), 0) as total
		FROM `tabBOQ Progress Ledger`
		WHERE boq_item = %s
		AND posting_date <= %s
	""", (boq_item, today()))
	
	return flt(result[0][0]) if result else 0


@frappe.whitelist()
def get_to_date_amount(boq_item: str) -> float:
	"""
	Get sum of all ledger amount up to current date.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		float: To-date amount
	"""
	result = frappe.db.sql("""
		SELECT COALESCE(SUM(amount), 0) as total
		FROM `tabBOQ Progress Ledger`
		WHERE boq_item = %s
		AND posting_date <= %s
	""", (boq_item, today()))
	
	return flt(result[0][0]) if result else 0


@frappe.whitelist()
def get_cost_to_date(boq_item: str) -> float:
	"""
	Get sum of all DPR costs for a BOQ Item.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		float: Total cost to date
	"""
	# Requirement 2: Real-Time Costing via GL Entries
	# Calculate cost from GL entries linked to DPRs of this item
	# This ensures we track "Financial Cost" (GL) rather than just "Operational Cost" (DPR estimates)
	
	posting_date = today()
	base_cost = frappe.db.sql("""
		SELECT SUM(gle.debit - gle.credit)
		FROM `tabGL Entry` gle
		JOIN `tabDaily Progress Record` dpr ON (
			dpr.stock_entries LIKE CONCAT('%%', gle.voucher_no, '%%') OR 
			dpr.journal_entries LIKE CONCAT('%%', gle.voucher_no, '%%')
		)
		WHERE dpr.boq_item = %s
		AND gle.is_cancelled = 0
		AND gle.project = dpr.project
		AND gle.posting_date <= %s
		AND gle.account IN (
			SELECT name FROM `tabAccount` 
			WHERE root_type = 'Expense' 
			OR account_type = 'Work In Progress'
		)
	""", (boq_item, posting_date))

	purchase_gl_cost = frappe.db.sql("""
		SELECT SUM(gle.debit - gle.credit)
		FROM `tabGL Entry` gle
		WHERE gle.voucher_type = 'Purchase Invoice'
		AND gle.voucher_no IN (
			SELECT pii.parent
			FROM `tabPurchase Invoice Item` pii
			JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
			WHERE pii.boq_item = %s
			AND pi.docstatus = 1
		)
		AND gle.is_cancelled = 0
		AND gle.posting_date <= %s
		AND gle.account IN (
			SELECT name FROM `tabAccount`
			WHERE root_type = 'Expense'
			OR account_type = 'Work In Progress'
		)
	""", (boq_item, posting_date))

	purchase_receipt_cost = frappe.db.sql("""
		SELECT SUM(gle.debit - gle.credit)
		FROM `tabGL Entry` gle
		WHERE gle.voucher_type = 'Purchase Receipt'
		AND gle.voucher_no IN (
			SELECT pri.parent
			FROM `tabPurchase Receipt Item` pri
			JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
			WHERE pri.boq_item = %s
			AND pr.docstatus = 1
		)
		AND gle.is_cancelled = 0
		AND gle.posting_date <= %s
		AND gle.account IN (
			SELECT name FROM `tabAccount`
			WHERE root_type = 'Expense'
			OR account_type = 'Work In Progress'
		)
	""", (boq_item, posting_date))

	total = flt(base_cost[0][0] if base_cost and base_cost[0][0] else 0) + \
		flt(purchase_gl_cost[0][0] if purchase_gl_cost and purchase_gl_cost[0][0] else 0) + \
		flt(purchase_receipt_cost[0][0] if purchase_receipt_cost and purchase_receipt_cost[0][0] else 0)

	return total


def get_project_boq_for_item(boq_item_name: str) -> str:
	"""
	Get project_boq from BOQ Item's parent hierarchy.
	
	Traverses: BOQ Item → BOQ Bill → Project BOQ
	
	Args:
		boq_item_name: Name of the BOQ Item
		
	Returns:
		Project BOQ name if found, None if hierarchy is incomplete
		
	Requirements: 5.2, 6.1
	"""
	if not boq_item_name:
		return None
	
	# First try to get project_boq directly from BOQ Item (it's a fetched field)
	project_boq = frappe.db.get_value("BOQ Item", boq_item_name, "project_boq")
	if project_boq:
		return project_boq
	
	# If not set, traverse the hierarchy: BOQ Item → BOQ Bill → Project BOQ
	parent_bill = frappe.db.get_value("BOQ Item", boq_item_name, "parent_bill")
	if not parent_bill:
		return None
	
	project_boq = frappe.db.get_value("BOQ Bill", parent_bill, "project_boq")
	return project_boq


def validate_ledger_entry_fields(
	boq_item: str,
	project: str,
	project_boq: str,
	bill_no: str,
	posting_date: str,
	source: str,
	qty: float,
	amount: float
) -> dict:
	"""
	Validate all mandatory fields for ledger entry creation.
	
	Args:
		All required fields for BOQ Progress Ledger
		
	Returns:
		dict with status and error_message if validation fails
		
	Requirements: 6.2
	"""
	errors = []
	
	if not boq_item:
		errors.append("BOQ Item is required")
	elif not frappe.db.exists("BOQ Item", boq_item):
		errors.append(f"BOQ Item '{boq_item}' does not exist")
	
	if not project:
		errors.append("Project is required")
	elif not frappe.db.exists("Project", project):
		errors.append(f"Project '{project}' does not exist")
	
	if not project_boq:
		errors.append("Project BOQ is required")
	elif not frappe.db.exists("Project BOQ", project_boq):
		errors.append(f"Project BOQ '{project_boq}' does not exist")
	
	if not bill_no:
		errors.append("Bill No is required")
	elif not frappe.db.exists("BOQ Bill", bill_no):
		errors.append(f"BOQ Bill '{bill_no}' does not exist")
	
	if not posting_date:
		errors.append("Posting Date is required")
	
	valid_sources = ["Invoice", "Proforma", "Proforma Reversal", "Adjustment", "Reversal"]
	if not source:
		errors.append("Source is required")
	elif source not in valid_sources:
		errors.append(f"Source must be one of: {', '.join(valid_sources)}")
	
	if qty is None:
		errors.append("Qty is required")
	
	if amount is None:
		errors.append("Amount is required")
	
	if errors:
		return {"status": "error", "error_message": "; ".join(errors)}
	
	return {"status": "success"}


def create_ledger_entry(
	boq_item: str,
	qty: float,
	amount: float,
	source: str,
	reference_doctype: str = None,
	reference_name: str = None,
	posting_date: str = None,
	remarks: str = None,
	validate: bool = True,
	**kwargs
) -> str:
	"""
	Create a BOQ Progress Ledger entry with progressive tracking (prev/curr/accumulated).
	
	This is the centralized function for creating ledger entries.
	
	Args:
		boq_item: BOQ Item name
		qty: Quantity
		amount: Amount
		source: Source type (Invoice/Proforma/Proforma Reversal/Adjustment/Reversal)
		reference_doctype: Reference DocType
		reference_name: Reference document name
		posting_date: Posting date (defaults to today)
		remarks: Optional remarks
		validate: Whether to validate fields before creation
		**kwargs: Additional fields to set on the ledger entry
		
	Returns:
		str: Created ledger entry name
		
	Raises:
		frappe.ValidationError: If validation fails
		
	Requirements: 6.1, 6.2, 6.3
	"""
	# Get BOQ Item details
	item = frappe.get_doc("BOQ Item", boq_item)
	
	# Get project_boq from hierarchy if not on item
	project_boq = item.project_boq or get_project_boq_for_item(boq_item)
	if not project_boq:
		frappe.throw(
			_("Cannot find Project BOQ for BOQ Item {0}. Please ensure the BOQ Item has a valid parent bill linked to a Project BOQ.").format(boq_item),
			title=_("Missing Project BOQ")
		)
	
	# Validate mandatory fields
	if validate:
		validation_result = validate_ledger_entry_fields(
			boq_item=boq_item,
			project=item.project,
			project_boq=project_boq,
			bill_no=item.parent_bill,
			posting_date=posting_date or today(),
			source=source,
			qty=qty,
			amount=amount
		)
		
		if validation_result["status"] == "error":
			frappe.log_error(
				f"Ledger entry validation failed for BOQ Item {boq_item}: {validation_result['error_message']}",
				"BOQ Ledger Validation Error"
			)
			frappe.throw(
				_(validation_result["error_message"]),
				title=_("Validation Error")
			)
	
	# Get previous accumulated values (sum of all previous ledger entries)
	prev_totals = frappe.db.sql("""
		SELECT 
			COALESCE(SUM(qty), 0) as prev_qty,
			COALESCE(SUM(amount), 0) as prev_amount
		FROM `tabBOQ Progress Ledger`
		WHERE boq_item = %s
	""", boq_item, as_dict=True)[0]
	
	prev_qty = flt(prev_totals.prev_qty)
	prev_amount = flt(prev_totals.prev_amount)
	current_qty = flt(qty)
	current_amount = flt(amount)
	accumulated_qty = prev_qty + current_qty
	accumulated_amount = prev_amount + current_amount
	
	try:
		ledger = frappe.new_doc("BOQ Progress Ledger")
		ledger.project = item.project
		ledger.project_boq = project_boq
		ledger.bill_no = item.parent_bill
		ledger.boq_item = boq_item
		ledger.posting_date = posting_date or today()
		ledger.qty = current_qty
		ledger.amount = current_amount
		ledger.source = source
		ledger.reference_doctype = reference_doctype
		ledger.reference_name = reference_name
		ledger.remarks = remarks
		
		# Set progressive tracking fields
		ledger.prev_qty = prev_qty
		ledger.prev_amount = prev_amount
		ledger.current_qty = current_qty
		ledger.current_amount = current_amount
		ledger.accumulated_qty = accumulated_qty
		ledger.accumulated_amount = accumulated_amount
		
		# Set additional fields from kwargs
		for key, value in kwargs.items():
			if hasattr(ledger, key):
				setattr(ledger, key, value)
		
		ledger.insert(ignore_permissions=True)
		
		frappe.logger().info(
			f"Created BOQ Progress Ledger {ledger.name} for BOQ Item {boq_item}, "
			f"source={source}, qty={current_qty}, amount={current_amount}"
		)
		
		return ledger.name
		
	except Exception as e:
		frappe.log_error(
			f"Error creating ledger entry for BOQ Item {boq_item}: {str(e)}",
			"BOQ Ledger Creation Error"
		)
		raise


@frappe.whitelist()
def rebuild_ledger(project: str = None):
	"""
	Rebuild ledger entries from invoices for data integrity.
	
	Args:
		project: Optional project filter
	"""
	frappe.only_for("System Manager")
	
	filters = {}
	if project:
		filters["project"] = project
	
	# Get all BOQ Items
	boq_items = frappe.get_all(
		"BOQ Item",
		filters=filters,
		fields=["name", "project"]
	)
	
	for item in boq_items:
		# Get all invoices for this item
		invoices = frappe.db.sql("""
			SELECT si.name, si.posting_date, si.docstatus,
				   sii.qty, sii.amount
			FROM `tabSales Invoice` si
			JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
			WHERE sii.boq_item = %s
			AND si.docstatus = 1
		""", item.name, as_dict=True)
		
		# Check existing ledger entries
		existing = frappe.get_all(
			"BOQ Progress Ledger",
			filters={"boq_item": item.name},
			fields=["name", "reference_name", "qty", "amount"]
		)
		
		existing_refs = {e.reference_name: e for e in existing}
		
		# Create missing entries
		for inv in invoices:
			if inv.name not in existing_refs:
				create_ledger_entry(
					boq_item=item.name,
					qty=inv.qty,
					amount=inv.amount,
					source="Invoice",
					reference_doctype="Sales Invoice",
					reference_name=inv.name,
					posting_date=inv.posting_date,
					remarks="Rebuilt from invoice"
				)
				frappe.logger().info(f"Created ledger entry for {item.name} from {inv.name}")
	
	frappe.db.commit()
	frappe.msgprint(_("Ledger rebuild completed"))


@frappe.whitelist()
def recalculate_progressive_values(project: str = None, boq_item: str = None):
	"""
	Recalculate prev/curr/accumulated values for existing ledger entries.
	Useful for data migration or fixing inconsistencies.
	
	Args:
		project: Optional project filter
		boq_item: Optional specific BOQ Item
	"""
	frappe.only_for("System Manager")
	
	# Build filters
	filters = {}
	if project:
		filters["project"] = project
	if boq_item:
		filters["boq_item"] = boq_item
	
	# Get all BOQ Items to process
	if boq_item:
		boq_items = [{"name": boq_item}]
	else:
		boq_items = frappe.get_all("BOQ Item", filters=filters if project else {}, fields=["name"])
	
	updated_count = 0
	
	for item in boq_items:
		# Get all ledger entries for this BOQ Item ordered by date and creation
		entries = frappe.get_all(
			"BOQ Progress Ledger",
			filters={"boq_item": item["name"]},
			fields=["name", "qty", "amount"],
			order_by="posting_date ASC, creation ASC"
		)
		
		# Recalculate progressive values
		running_qty = 0
		running_amount = 0
		
		for entry in entries:
			prev_qty = running_qty
			prev_amount = running_amount
			current_qty = flt(entry.qty)
			current_amount = flt(entry.amount)
			running_qty += current_qty
			running_amount += current_amount
			
			# Update the entry
			frappe.db.set_value("BOQ Progress Ledger", entry.name, {
				"prev_qty": prev_qty,
				"prev_amount": prev_amount,
				"current_qty": current_qty,
				"current_amount": current_amount,
				"accumulated_qty": running_qty,
				"accumulated_amount": running_amount
			}, update_modified=False)
			
			updated_count += 1
	
	frappe.db.commit()
	frappe.msgprint(_("Recalculated progressive values for {0} ledger entries").format(updated_count))


def recalculate_ledger_for_item(boq_item):
	"""
	Helper to recalculate progressive values for a single BOQ item.
	Can be called from other doctypes without "System Manager" restriction.
	"""
	entries = frappe.get_all(
		"BOQ Progress Ledger",
		filters={"boq_item": boq_item},
		fields=["name", "qty", "amount", "certified_amount", "tax_invoice_amount", "source"],
		order_by="posting_date ASC, creation ASC"
	)
	
	running_qty = 0.0
	running_amount = 0.0
	
	for entry in entries:
		# Determine the "Active Amount" for this ledger row
		# If it's a consolidated row (PI->PC->TI), use the most mature amount available
		active_qty = flt(entry.qty) # Base qty
		
		# If we updated the row with PC/TI amounts, use those for calculation
		if entry.tax_invoice_amount:
			active_amount = flt(entry.tax_invoice_amount)
		elif entry.certified_amount:
			active_amount = flt(entry.certified_amount)
		else:
			active_amount = flt(entry.amount) # Base amount (defaults to PI)
		
		# Set context for this row
		prev_qty = running_qty
		prev_amount = running_amount
		
		# Update running totals
		running_qty += active_qty
		running_amount += active_amount
		
		# Update the ledger entry with corrected progressive values
		frappe.db.set_value("BOQ Progress Ledger", entry.name, {
			"prev_qty": prev_qty,
			"prev_amount": prev_amount,
			"current_qty": active_qty,
			"current_amount": active_amount,
			"accumulated_qty": running_qty,
			"accumulated_amount": running_amount
		}, update_modified=False)
	
	# Update BOQ Item statistics
	try:
		item_doc = frappe.get_doc("BOQ Item", boq_item)
		# limit what we calculate/update to avoid deep recursion if triggers are active
		item_doc.calculate_amounts()
		item_doc.db_update() # Use db_update to avoid triggering full validation/save hooks if not needed
	except Exception as e:
		frappe.log_error(f"Failed to update BOQ Item {boq_item} stats: {str(e)}", "BOQ Ledger Update")
	
	# After recalculating ledger for item, update Project Financials
	item_doc = frappe.db.get_value("BOQ Item", boq_item, "project", as_dict=True)
	if item_doc:
		update_project_financials(item_doc.project)

def update_project_financials(project):
	"""
	Update Project-level financial summaries from BOQ Ledger and BOQ Items.
	"""
	# 1. Revenue & Financials from Ledger
	ledger_totals = frappe.db.sql("""
		SELECT 
			COALESCE(SUM(current_amount), 0) as total_revenue,
			COALESCE(SUM(retention_amount), 0) as total_retention_retained,
			COALESCE(SUM(advance_deduction), 0) as total_advance_utilized
			FROM `tabBOQ Progress Ledger`
		WHERE project = %s AND docstatus = 1
	""", project, as_dict=True)
	
	total_revenue = flt(ledger_totals[0].total_revenue) if ledger_totals else 0.0
	total_retention_retained = flt(ledger_totals[0].total_retention_retained) if ledger_totals else 0.0
	total_advance_utilized = flt(ledger_totals[0].total_advance_utilized) if ledger_totals else 0.0
	
	# 2. Estimates from Project BOQ (Approved)
	boq_totals = frappe.db.sql("""
		SELECT 
			COALESCE(SUM(total_boq_value), 0) as total_boq_value
		FROM `tabProject BOQ`
		WHERE project = %s AND status = 'Approved'
	""", project, as_dict=True)
	
	total_boq_value = flt(boq_totals[0].total_boq_value) if boq_totals else 0.0
	
	# Fetch total estimated cost from all BOQ Items
	estimated_totals = frappe.db.sql("""
		SELECT COALESCE(SUM(total_estimated_cost), 0)
		FROM `tabBOQ Item`
		WHERE project = %s
	""", project)
	total_estimated_cost = flt(estimated_totals[0][0]) if estimated_totals else 0.0
	
	# 3. Actual Costs from BOQ Items
	actual_cost = frappe.db.sql("""
		SELECT COALESCE(SUM(cost_to_date), 0)
		FROM `tabBOQ Item`
		WHERE project = %s
	""", project)
	total_actual_cost = flt(actual_cost[0][0]) if actual_cost else 0.0
	
	# 4. Advance Given (Placeholder)
	# TODO: Implement accurate advance tracking logic based on user's workflow
	total_advance_given = 0.0
	
	# 5. Calculations
	total_estimated_gp = total_boq_value - total_estimated_cost
	project_gp_percent = (total_estimated_gp / total_boq_value * 100) if total_boq_value else 0.0
	
	total_retention_released = 0.0 # Implement if tracked
	total_retention_balance = total_retention_retained - total_retention_released
	
	total_advance_available = total_advance_given - total_advance_utilized
	
	project_net_receivable = total_revenue - total_retention_retained - total_advance_utilized
	
	# Update Project
	frappe.db.set_value("Project", project, {
		"total_revenue": total_revenue,
		"total_estimated_cost": total_estimated_cost,
		"total_actual_cost": total_actual_cost,
		"total_estimated_gp": total_estimated_gp,
		"project_gp_percentage": project_gp_percent,
		"total_retention_retained": total_retention_retained,
		"total_retention_released": total_retention_released,
		"total_retention_balance": total_retention_balance,
		"total_advance_given": total_advance_given,
		"total_advance_utilized": total_advance_utilized,
		"total_advance_available": total_advance_available,
		"project_net_receivable": project_net_receivable
	})
