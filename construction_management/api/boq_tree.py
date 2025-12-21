# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_boq_tree_data(project: str) -> dict:
	"""
	Get complete BOQ tree structure with calculated values for a project.
	
	Args:
		project: Project name
		
	Returns:
		dict with kpi and bills data
	"""
	# Check if progressive BOQ is enabled
	if not is_progressive_boq_enabled(project):
		return {"error": "Progressive BOQ is not enabled for this project"}
	
	# Get Project BOQ
	project_boq = frappe.db.get_value(
		"Project BOQ",
		{"project": project},
		["name", "boq_name", "status", "total_boq_value"],
		as_dict=True
	)
	
	if not project_boq:
		return {"kpi": None, "bills": [], "project_boq": None, "has_boq": False}
	
	# Get KPI data
	kpi = get_boq_kpi(project)
	
	# Get bills with items
	bills = get_bills_with_items(project_boq.name)
	
	return {
		"project_boq": project_boq,
		"kpi": kpi,
		"bills": bills,
		"has_boq": True
	}


@frappe.whitelist()
def get_boq_kpi(project: str) -> dict:
	"""
	Get KPI summary for project BOQ including cost breakdown, advance, and retention.
	
	Args:
		project: Project name
		
	Returns:
		dict with total_boq_value, total_billed, total_collected, pending, cost breakdown, advance, and retention
	"""
	# Get Project BOQ total
	total_boq_value = frappe.db.get_value(
		"Project BOQ",
		{"project": project},
		"total_boq_value"
	) or 0
	
	# Get total billed from ledger
	total_billed = frappe.db.sql("""
		SELECT COALESCE(SUM(amount), 0) as total
		FROM `tabBOQ Progress Ledger`
		WHERE project = %s AND source = 'Invoice'
	""", project)[0][0] or 0
	
	# Get total collected from paid invoices
	total_collected = frappe.db.sql("""
		SELECT COALESCE(SUM(si.grand_total), 0) as total
		FROM `tabSales Invoice` si
		WHERE si.project = %s 
		AND si.docstatus = 1
		AND si.status = 'Paid'
		AND EXISTS (
			SELECT 1 FROM `tabSales Invoice Item` sii 
			WHERE sii.parent = si.name AND sii.boq_item IS NOT NULL
		)
	""", project)[0][0] or 0
	
	# Get cost breakdown from Daily Progress Records
	cost_breakdown = frappe.db.sql("""
		SELECT 
			COALESCE(SUM(labour_cost), 0) as labour,
			COALESCE(SUM(material_cost), 0) as material,
			COALESCE(SUM(asset_cost), 0) as asset,
			COALESCE(SUM(subcontract_cost), 0) as subcontract,
			COALESCE(SUM(expense_cost), 0) as expense,
			COALESCE(SUM(total_cost), 0) as total
		FROM `tabDaily Progress Record`
		WHERE project = %s
	""", project, as_dict=True)[0]
	
	# Get advance payment summary
	advance_summary = get_advance_summary(project)
	
	# Get retention summary
	retention_summary = get_retention_summary(project)
	
	return {
		"total_boq_value": flt(total_boq_value),
		"total_billed": flt(total_billed),
		"total_collected": flt(total_collected),
		"pending": flt(total_billed) - flt(total_collected),
		"total_labour_cost": flt(cost_breakdown.labour),
		"total_material_cost": flt(cost_breakdown.material),
		"total_asset_cost": flt(cost_breakdown.asset),
		"total_subcontract_cost": flt(cost_breakdown.subcontract),
		"total_expense_cost": flt(cost_breakdown.expense),
		"total_cost": flt(cost_breakdown.total),
		# Advance tracking
		"advance_collected": flt(advance_summary.get("total_collected", 0)),
		"advance_utilized": flt(advance_summary.get("total_utilized", 0)),
		"advance_balance": flt(advance_summary.get("balance", 0)),
		# Retention tracking
		"retention_held": flt(retention_summary.get("total_retained", 0)),
		"retention_released": flt(retention_summary.get("total_released", 0)),
		"retention_balance": flt(retention_summary.get("retention_balance", 0))
	}


def get_advance_summary(project: str) -> dict:
	"""Get advance payment summary for a project"""
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
	
	total_utilized = flt(total_deducted[0].total) if total_deducted else 0
	
	return {
		"total_collected": total_collected,
		"total_utilized": total_utilized,
		"balance": total_collected - total_utilized
	}


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
	
	# Get retention released
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


def get_bills_with_items(project_boq: str) -> list:
	"""Get all bills with their items for a Project BOQ"""
	bills = frappe.get_all(
		"BOQ Bill",
		filters={"project_boq": project_boq},
		fields=["name", "bill_no", "sequence", "description", "total_qty", "total_amount"],
		order_by="sequence, bill_no"
	)
	
	for bill in bills:
		bill["items"] = get_boq_items(bill.name)
		# Calculate bill totals from items
		bill["totals"] = calculate_bill_totals(bill["items"])
	
	return bills


def get_boq_items(bill_name: str) -> list:
	"""Get all BOQ items for a bill with calculated values"""
	items = frappe.get_all(
		"BOQ Item",
		filters={"parent_bill": bill_name},
		fields=[
			"name", "item_code", "description", "unit",
			"total_qty", "rate", "total_amount",
			"billing_status"
		],
		order_by="idx"
	)
	
	for item in items:
		# Get ledger-based values
		ledger_values = get_item_ledger_values(item.name)
		item.update(ledger_values)
		
		# Get cost values
		cost_values = get_item_cost_values(item.name)
		item.update(cost_values)
	
	return items


def get_item_ledger_values(boq_item: str) -> dict:
	"""Get Previous, Current, To-Date, Balance values from ledger"""
	from construction_management.api.boq_ledger import (
		get_previous_qty, get_previous_amount,
		get_to_date_qty, get_to_date_amount
	)
	
	# Get BOQ Item details
	item = frappe.get_doc("BOQ Item", boq_item)
	
	prev_qty = get_previous_qty(boq_item)
	prev_amount = get_previous_amount(boq_item)
	to_date_qty = get_to_date_qty(boq_item)
	to_date_amount = get_to_date_amount(boq_item)
	
	# Current is the difference (items being billed now but not yet submitted)
	current_qty = flt(item.current_qty) if hasattr(item, 'current_qty') else 0
	current_amount = flt(current_qty) * flt(item.rate)
	
	# Balance
	balance_qty = flt(item.total_qty) - flt(to_date_qty) - flt(current_qty)
	balance_amount = flt(item.total_amount) - flt(to_date_amount) - flt(current_amount)
	
	return {
		"qty": {
			"total": flt(item.total_qty),
			"prev": flt(prev_qty),
			"current": flt(current_qty),
			"to_date": flt(to_date_qty),
			"balance": flt(balance_qty)
		},
		"amount": {
			"rate": flt(item.rate),
			"total": flt(item.total_amount),
			"prev": flt(prev_amount),
			"current": flt(current_amount),
			"to_date": flt(to_date_amount),
			"balance": flt(balance_amount)
		}
	}


def get_item_cost_values(boq_item: str) -> dict:
	"""Get cost to date and margin for BOQ item"""
	from construction_management.api.boq_ledger import get_cost_to_date
	
	cost_to_date = get_cost_to_date(boq_item)
	
	# Get to_date_amount for margin calculation
	to_date_amount = frappe.db.sql("""
		SELECT COALESCE(SUM(amount), 0)
		FROM `tabBOQ Progress Ledger`
		WHERE boq_item = %s
	""", boq_item)[0][0] or 0
	
	margin = flt(to_date_amount) - flt(cost_to_date)
	
	return {
		"cost_to_date": flt(cost_to_date),
		"margin": flt(margin)
	}


def calculate_bill_totals(items: list) -> dict:
	"""Calculate aggregated totals for a bill from its items"""
	totals = {
		"qty": {"total": 0, "prev": 0, "current": 0, "to_date": 0, "balance": 0},
		"amount": {"total": 0, "prev": 0, "current": 0, "to_date": 0, "balance": 0},
		"cost_to_date": 0,
		"margin": 0
	}
	
	for item in items:
		if "qty" in item:
			for key in totals["qty"]:
				totals["qty"][key] += flt(item["qty"].get(key, 0))
		if "amount" in item:
			for key in totals["amount"]:
				if key != "rate":  # Don't sum rates
					totals["amount"][key] += flt(item["amount"].get(key, 0))
		totals["cost_to_date"] += flt(item.get("cost_to_date", 0))
		totals["margin"] += flt(item.get("margin", 0))
	
	return totals


@frappe.whitelist()
def update_boq_item_current(boq_item: str, current_qty: float) -> dict:
	"""
	Update current qty for a BOQ item and recalculate values.
	
	Args:
		boq_item: BOQ Item name
		current_qty: New current quantity
		
	Returns:
		dict with updated values
	"""
	current_qty = flt(current_qty)
	
	# Validate
	item = frappe.get_doc("BOQ Item", boq_item)
	
	# Check if BOQ is approved and locked
	project_boq = frappe.get_doc("Project BOQ", item.project_boq)
	if project_boq.status == "Approved":
		# Allow current_qty updates even on approved BOQ (for billing)
		pass
	
	# Check balance
	from construction_management.api.boq_ledger import get_to_date_qty
	to_date_qty = get_to_date_qty(boq_item)
	balance_qty = flt(item.total_qty) - flt(to_date_qty)
	
	if current_qty > balance_qty:
		frappe.throw(
			_("Current quantity ({0}) exceeds available balance ({1})").format(
				current_qty, balance_qty
			),
			title=_("Over-Billing Error")
		)
	
	if current_qty < 0:
		frappe.throw(_("Current quantity cannot be negative"))
	
	# Update the item
	item.current_qty = current_qty
	item.save()
	
	# Return updated values
	return get_item_ledger_values(boq_item)


@frappe.whitelist()
def create_bill_number(project: str, bill_no: str, description: str = None) -> dict:
	"""
	Create a new Bill Number for a project.
	
	Args:
		project: Project name
		bill_no: Bill number identifier
		description: Optional description
		
	Returns:
		dict with created bill details
	"""
	# Get or create Project BOQ
	project_boq = frappe.db.get_value("Project BOQ", {"project": project}, "name")
	
	if not project_boq:
		# Create Project BOQ first
		boq_doc = frappe.new_doc("Project BOQ")
		boq_doc.project = project
		boq_doc.boq_name = f"BOQ - {project}"
		boq_doc.status = "Draft"
		boq_doc.insert()
		project_boq = boq_doc.name
	
	# Get next sequence
	max_seq = frappe.db.sql("""
		SELECT COALESCE(MAX(sequence), 0) + 1
		FROM `tabBOQ Bill`
		WHERE project_boq = %s
	""", project_boq)[0][0]
	
	# Create Bill
	bill = frappe.new_doc("BOQ Bill")
	bill.project_boq = project_boq
	bill.bill_no = bill_no
	bill.sequence = max_seq
	bill.description = description
	bill.insert()
	
	return {
		"name": bill.name,
		"bill_no": bill.bill_no,
		"sequence": bill.sequence
	}


def is_progressive_boq_enabled(project: str) -> bool:
	"""Check if progressive BOQ is enabled for a project"""
	return frappe.db.get_value("Project", project, "enable_progressive_boq") or False


@frappe.whitelist()
def get_boq_item_cost_details(boq_item: str) -> dict:
	"""
	Get detailed cost breakdown for a BOQ item.
	Same breakdown as shown at project level for consistency.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		dict with cost breakdown and revenue details
	"""
	# Get BOQ Item
	item = frappe.get_doc("BOQ Item", boq_item)
	
	# Get cost breakdown from Daily Progress Records - same categories as project level
	cost_breakdown = frappe.db.sql("""
		SELECT 
			COALESCE(SUM(labour_cost), 0) as labour,
			COALESCE(SUM(material_cost), 0) as material,
			COALESCE(SUM(asset_cost), 0) as asset,
			COALESCE(SUM(subcontract_cost), 0) as subcontract,
			COALESCE(SUM(expense_cost), 0) as expense,
			COALESCE(SUM(overhead_cost), 0) as overhead,
			COALESCE(SUM(total_cost), 0) as total
		FROM `tabDaily Progress Record`
		WHERE boq_item = %s
	""", boq_item, as_dict=True)[0]
	
	# Get revenue from ledger
	from construction_management.api.boq_ledger import (
		get_previous_amount, get_to_date_amount
	)
	
	prev_amount = get_previous_amount(boq_item)
	to_date_amount = get_to_date_amount(boq_item)
	current_amount = flt(item.current_qty) * flt(item.rate)
	
	return {
		"cost": {
			"labour": flt(cost_breakdown.labour),
			"material": flt(cost_breakdown.material),
			"asset": flt(cost_breakdown.asset),
			"subcontract": flt(cost_breakdown.subcontract),
			"expense": flt(cost_breakdown.expense),
			"overhead": flt(cost_breakdown.overhead),
			"total": flt(cost_breakdown.total)
		},
		"revenue": {
			"prev": flt(prev_amount),
			"current": flt(current_amount),
			"to_date": flt(to_date_amount) + flt(current_amount),
			"total": flt(item.total_amount)
		}
	}


@frappe.whitelist()
def get_boq_item_cost_breakdown(boq_item: str) -> dict:
	"""
	Get detailed cost breakdown for a BOQ item with DPR details.
	Returns same structure as project-level costs for consistency.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		dict with detailed cost breakdown including DPR list
	"""
	# Get cost summary
	cost_summary = frappe.db.sql("""
		SELECT 
			COALESCE(SUM(labour_cost), 0) as labour,
			COALESCE(SUM(material_cost), 0) as material,
			COALESCE(SUM(asset_cost), 0) as asset,
			COALESCE(SUM(subcontract_cost), 0) as subcontract,
			COALESCE(SUM(expense_cost), 0) as expense,
			COALESCE(SUM(overhead_cost), 0) as overhead,
			COALESCE(SUM(total_cost), 0) as total
		FROM `tabDaily Progress Record`
		WHERE boq_item = %s AND docstatus = 1
	""", boq_item, as_dict=True)[0]
	
	# Get DPR list
	dprs = frappe.get_all(
		"Daily Progress Record",
		filters={"boq_item": boq_item, "docstatus": 1},
		fields=["name", "date", "labour_cost", "material_cost", "asset_cost", 
				"subcontract_cost", "expense_cost", "overhead_cost", "total_cost"],
		order_by="date desc"
	)
	
	return {
		"summary": {
			"labour": flt(cost_summary.labour),
			"material": flt(cost_summary.material),
			"asset": flt(cost_summary.asset),
			"subcontract": flt(cost_summary.subcontract),
			"expense": flt(cost_summary.expense),
			"overhead": flt(cost_summary.overhead),
			"total": flt(cost_summary.total)
		},
		"dprs": dprs
	}
