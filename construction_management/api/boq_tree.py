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
		dict with total_boq_value, total_billed, total_collected (combined), 
		invoice_collected, advance_collected, pending, cost breakdown, and retention
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
	
	# Get total collected from paid invoices (Invoice Collected)
	invoice_collected = frappe.db.sql("""
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
	advance_collected = flt(advance_summary.get("total_collected", 0))
	
	# Get retention summary
	retention_summary = get_retention_summary(project)
	
	# Total Collected = Advance Collected + Invoice Collected
	total_collected = flt(advance_collected) + flt(invoice_collected)
	
	return {
		"total_boq_value": flt(total_boq_value),
		"total_billed": flt(total_billed),
		# Combined total collected (advance + invoice)
		"total_collected": flt(total_collected),
		# Breakdown of collected amounts
		"invoice_collected": flt(invoice_collected),
		"advance_collected": flt(advance_collected),
		"pending": flt(total_billed) - flt(invoice_collected),
		"total_labour_cost": flt(cost_breakdown.labour),
		"total_material_cost": flt(cost_breakdown.material),
		"total_asset_cost": flt(cost_breakdown.asset),
		"total_subcontract_cost": flt(cost_breakdown.subcontract),
		"total_expense_cost": flt(cost_breakdown.expense),
		"total_cost": flt(cost_breakdown.total),
		# Advance tracking (detailed)
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
		# Get advance amount for this bill (Task 9.3)
		bill["advance_amount"] = get_bill_advance_amount(bill.name)
	
	return bills


def get_bill_advance_amount(bill_no: str) -> float:
	"""Get total advance amount for a bill"""
	result = frappe.db.sql("""
		SELECT COALESCE(SUM(amount), 0) as total
		FROM `tabBOQ Advance Payment`
		WHERE bill_no = %s AND docstatus = 1
	""", bill_no)
	return flt(result[0][0]) if result else 0


def get_boq_items(bill_name: str) -> list:
	"""Get all BOQ items for a bill with calculated values including revenue breakdown and profitability"""
	items = frappe.get_all(
		"BOQ Item",
		filters={"parent_bill": bill_name},
		fields=[
			"name", "item_code", "description", "unit",
			"total_qty", "rate", "total_amount",
			"billing_status",
			"estimated_material_cost", "estimated_labour_cost",
			"estimated_subcontract_cost", "estimated_asset_cost",
			"estimated_other_cost", "total_estimated_cost",
			"estimated_gp", "estimated_gp_percent",
			"cost_to_date", "margin",
			"labour_cost", "material_cost", "subcontract_cost",
			"asset_cost", "expense_cost"
		],
		order_by="idx"
	)
	
	for item in items:
		# Get ledger-based values
		ledger_values = get_item_ledger_values(item.name)
		item.update(ledger_values)
		
		# Get actual cost breakdown from BOQ Item fields
		actual_costs = {
			"material": flt(item.get("material_cost", 0)),
			"labour": flt(item.get("labour_cost", 0)),
			"subcontract": flt(item.get("subcontract_cost", 0)),
			"asset": flt(item.get("asset_cost", 0)),
			"other": flt(item.get("expense_cost", 0)),
			"total": flt(item.get("cost_to_date", 0))
		}
		item["actual_costs"] = actual_costs
		
		# Add estimated costs structure
		item["estimated_costs"] = {
			"material": flt(item.get("estimated_material_cost", 0)),
			"labour": flt(item.get("estimated_labour_cost", 0)),
			"subcontract": flt(item.get("estimated_subcontract_cost", 0)),
			"asset": flt(item.get("estimated_asset_cost", 0)),
			"other": flt(item.get("estimated_other_cost", 0)),
			"total": flt(item.get("total_estimated_cost", 0))
		}
		
		# Get revenue breakdown (PI, PC, Tax Invoice, Variance, Balance)
		revenue_breakdown = get_boq_item_revenue_breakdown_internal(item.name, item["total_amount"])
		item["revenue"] = revenue_breakdown
		
		# Calculate profitability (GP and GP%)
		# Revenue for GP calculation
		# Per Requirement 6: Use BOQ Ledger Value (Total Sales Value)
		# This includes Net Proformas + Invoices, as per the correct Ledger logic
		revenue_for_gp = flt(item.get("to_date_amount", 0))
		# If no cost yet, use collected Sales Invoice amount as GP basis (user request)
		# Fallback to ledger to_date_amount if no SI value
		tax_invoice_revenue = flt(revenue_breakdown.get("tax_invoice", 0))
		if flt(actual_costs.get("total", 0)) <= 0 and tax_invoice_revenue > 0:
			revenue_for_gp = tax_invoice_revenue
		actual_cost = flt(actual_costs.get("total", 0))
		
		gp = revenue_for_gp - actual_cost
		gp_percent = (gp / revenue_for_gp * 100) if revenue_for_gp > 0 else 0
		
		item["profitability"] = {
			"gp": flt(gp),
			"gp_percent": flt(gp_percent, 2),
			# Include breakdown for transparency if needed
			"revenue_basis": revenue_for_gp,
			"cost_basis": actual_cost,
			"estimated_gp": flt(item.get("estimated_gp", 0)),
			"estimated_gp_percent": flt(item.get("estimated_gp_percent", 0))
		}
		
		# Get advance payments for this item (Task 9.4)
		item["advance_amount"] = get_item_advance_amount(item.name)
		
		# Get retention amount (pro-rata from invoice)
		item["retention_amount"] = get_item_retention_amount(item.name)
	
	return items


def get_item_advance_amount(boq_item: str) -> float:
	"""Get total advance amount collected for a specific BOQ item"""
	result = frappe.db.sql("""
		SELECT COALESCE(SUM(advance_deduction), 0) as total
		FROM `tabBOQ Progress Ledger`
		WHERE boq_item = %s AND docstatus = 1
	""", boq_item)
	return flt(result[0][0]) if result else 0


def get_item_actual_costs(boq_item: str) -> dict:
	"""Get actual cost breakdown from Daily Progress Records and GL for a BOQ item"""
	# Get operational costs from DPR (Labour, Material)
	dpr_costs = frappe.db.sql("""
		SELECT 
			COALESCE(SUM(labour_cost), 0) as labour,
			COALESCE(SUM(material_cost), 0) as material
		FROM `tabDaily Progress Record`
		WHERE boq_item = %s AND docstatus = 1
	""", boq_item, as_dict=True)[0]

	# Get financial costs from GL (Subcontract, Asset, Other)
	subcontract_cost = get_gl_subcontract_cost(boq_item)
	asset_cost = get_gl_asset_cost(boq_item)
	other_cost = get_gl_other_cost(boq_item)
	
	total_cost = (
		flt(dpr_costs.material) + 
		flt(dpr_costs.labour) + 
		flt(subcontract_cost) + 
		flt(asset_cost) + 
		flt(other_cost)
	)

	return {
		"material": flt(dpr_costs.material),
		"labour": flt(dpr_costs.labour),
		"asset": flt(asset_cost),
		"subcontract": flt(subcontract_cost),
		"other": flt(other_cost),
		"total": flt(total_cost)
	}


def get_gl_subcontract_cost(boq_item: str) -> float:
	"""Get total subcontracting cost from GL (Purchase Receipts/Invoices)"""
	# Subcontract costs are usually booked under Expense accounts in PR/PI
	# We filter by voucher types that book actual expenses
	return frappe.db.sql("""
		SELECT COALESCE(SUM(gle.debit - gle.credit), 0)
		FROM `tabGL Entry` gle
		WHERE gle.account IN (
			SELECT name FROM `tabAccount` 
			WHERE account_type IN ('Expense Account', 'Cost of Goods Sold', 'Service')
			OR root_type = 'Expense'
		)
		AND gle.voucher_type IN ('Purchase Receipt', 'Purchase Invoice')
		AND gle.is_cancelled = 0
		AND EXISTS (
			SELECT 1 FROM `tabPurchase Receipt Item` pri 
			WHERE pri.parent = gle.voucher_no AND pri.boq_item = %s
		) OR EXISTS (
			SELECT 1 FROM `tabPurchase Invoice Item` pii
			WHERE pii.parent = gle.voucher_no AND pii.boq_item = %s
		)
	""", (boq_item, boq_item))[0][0]


def get_gl_asset_cost(boq_item: str) -> float:
	"""Get asset depreciation/allocation cost from GL"""
	return frappe.db.sql("""
		SELECT COALESCE(SUM(gle.debit - gle.credit), 0)
		FROM `tabGL Entry` gle
		WHERE (
			EXISTS (
				SELECT 1 FROM `tabDaily Progress Record` dpr 
				WHERE dpr.journal_entries LIKE CONCAT('%%', gle.voucher_no, '%%')
				AND dpr.boq_item = %s
			)
		)
		AND gle.account IN (
			SELECT name FROM `tabAccount` WHERE account_type = 'Depreciation'
		)
		AND gle.is_cancelled = 0
	""", boq_item)[0][0]


def get_gl_other_cost(boq_item: str) -> float:
	"""Get other expense costs from GL (Journals, Expenses)"""
	return frappe.db.sql("""
		SELECT COALESCE(SUM(gle.debit - gle.credit), 0)
		FROM `tabGL Entry` gle
		WHERE (
			EXISTS (
				SELECT 1 FROM `tabDaily Progress Record` dpr 
				WHERE dpr.journal_entries LIKE CONCAT('%%', gle.voucher_no, '%%')
				AND dpr.boq_item = %s
			)
			OR
			gle.voucher_type = 'Journal Entry' AND gle.voucher_no IN (
			    SELECT parent FROM `tabJournal Entry Account` 
				WHERE project IS NOT NULL -- Simplified check, ideally check linking
			)
		)
		AND gle.account IN (
			SELECT name FROM `tabAccount` 
			WHERE root_type = 'Expense' 
			AND account_type NOT IN ('Depreciation', 'Cost of Goods Sold')
		)
		AND gle.is_cancelled = 0
		AND gle.voucher_type = 'Journal Entry' 
		-- Add stricter linking logic if possible
	""", boq_item)[0][0]


@frappe.whitelist()
def get_boq_item_advances(boq_item: str) -> list:
	"""Get detailed advance payments list for a BOQ item"""
	return frappe.get_all(
		"BOQ Advance Payment",
		filters={"boq_item": boq_item, "docstatus": 1},
		fields=["name", "date", "amount", "status", "reference", "remarks"],
		order_by="date desc"
	)


def get_boq_item_revenue_breakdown_internal(boq_item: str, boq_total: float) -> dict:
	"""
	Internal function to get revenue breakdown for a BOQ item.
	Used by get_boq_items to avoid repeated API calls.
	"""
	# Get Proforma Invoice totals
	proforma_total = frappe.db.sql("""
		SELECT COALESCE(SUM(pii.amount), 0) as total
		FROM `tabProforma Invoice Item` pii
		JOIN `tabProforma Invoice` pi ON pi.name = pii.parent
		WHERE pii.boq_item = %s AND pi.docstatus = 1
	""", boq_item)[0][0] or 0
	
	# Get Payment Certificate totals and variance
	pc_data = frappe.db.sql("""
		SELECT 
			COALESCE(SUM(pc.accepted_amount), 0) as pc_total,
			COALESCE(SUM(pc.variance), 0) as variance_total
		FROM `tabPayment Certificate` pc
		WHERE pc.boq_item = %s AND pc.docstatus = 1
	""", boq_item, as_dict=True)[0]
	
	pc_total = flt(pc_data.pc_total) if pc_data else 0
	variance_total = flt(pc_data.variance_total) if pc_data else 0
	
	# Get Tax Invoice totals
	tax_invoice_total = frappe.db.sql("""
		SELECT COALESCE(SUM(sii.amount), 0) as total
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE sii.boq_item = %s AND si.docstatus = 1
	""", boq_item)[0][0] or 0
	
	# Balance = BOQ Total - Proforma Total (NOT PC Total)
	balance = flt(boq_total) - flt(proforma_total)
	
	return {
		"proforma": flt(proforma_total),
		"pc": flt(pc_total),
		"tax_invoice": flt(tax_invoice_total),
		"variance": flt(variance_total),
		"total": flt(proforma_total),  # Total billed = PI total
		"balance": flt(balance)
	}


def get_item_ledger_values(boq_item: str) -> dict:
	"""Get Previous, Current, To-Date, Balance values from ledger with fallback to invoice data"""
	from construction_management.api.boq_ledger import (
		get_previous_qty, get_previous_amount,
		get_to_date_qty, get_to_date_amount
	)
	
	# Get BOQ Item details
	item = frappe.get_doc("BOQ Item", boq_item)
	
	# User Request: Show value from last proforma invoiced BOQ ledger entries (Snapshot)
	# Instead of summing all entries, we fetch the latest ledger entry and use its prev/curr/accumulated snapshot.
	last_entry = frappe.db.get_value(
		"BOQ Progress Ledger",
		{"boq_item": boq_item},
		[
			"prev_qty", "current_qty", "accumulated_qty",
			"prev_amount", "current_amount", "accumulated_amount"
		],
		order_by="posting_date desc, creation desc",
		as_dict=True
	)
	
	if last_entry:
		prev_qty = flt(last_entry.get('prev_qty'))
		current_qty = flt(last_entry.get('current_qty'))
		to_date_qty = flt(last_entry.get('accumulated_qty'))
		
		prev_amount = flt(last_entry.get('prev_amount'))
		current_amount = flt(last_entry.get('current_amount'))
		to_date_amount = flt(last_entry.get('accumulated_amount'))
	else:
		prev_qty = get_previous_qty(boq_item)
		prev_amount = get_previous_amount(boq_item)
		
		# If no ledger entry exists, current comes from pending (unsaved) qty
		current_qty = flt(item.current_qty) if hasattr(item, 'current_qty') else 0
		current_amount = flt(current_qty) * flt(item.rate)
		
		to_date_qty = prev_qty + current_qty
		to_date_amount = prev_amount + current_amount
	
	# If no ledger entries exist, try to get values from Proforma Invoice items
	if to_date_qty == 0 and to_date_amount == 0 and not last_entry:
		invoice_totals = frappe.db.sql("""
			SELECT 
				COALESCE(SUM(pii.qty), 0) as qty,
				COALESCE(SUM(pii.amount), 0) as amount
			FROM `tabProforma Invoice Item` pii
			INNER JOIN `tabProforma Invoice` pi ON pi.name = pii.parent
			WHERE pii.boq_item = %s
			AND pi.docstatus = 1
		""", boq_item, as_dict=True)
		
		if invoice_totals and invoice_totals[0]:
			# All invoiced amounts are "previous" since they're already submitted
			prev_qty = flt(invoice_totals[0].qty)
			prev_amount = flt(invoice_totals[0].amount)
			to_date_qty = prev_qty + current_qty
			to_date_amount = prev_amount + current_amount
	
	# Balance
	balance_qty = flt(item.total_qty) - flt(to_date_qty)
	balance_amount = flt(item.total_amount) - flt(to_date_amount)
	
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
	"""Calculate aggregated totals for a bill from its items including revenue breakdown and profitability"""
	totals = {
		"qty": {"total": 0, "prev": 0, "current": 0, "to_date": 0, "balance": 0},
		"amount": {"total": 0, "prev": 0, "current": 0, "to_date": 0, "balance": 0},
		"cost_to_date": 0,
		"margin": 0,
		"estimated_costs": {
			"material": 0, "labour": 0, "subcontract": 0, 
			"asset": 0, "other": 0, "total": 0
		},
		"actual_costs": {
			"material": 0, "labour": 0, "subcontract": 0,
			"asset": 0, "other": 0, "total": 0
		},
		"revenue": {
			"proforma": 0, "pc": 0, "tax_invoice": 0,
			"variance": 0, "total": 0, "balance": 0
		},
		"profitability": {
			"gp": 0, "gp_percent": 0,
			"estimated_gp": 0, "estimated_gp_percent": 0
		},
		"retention_amount": 0,
		"advance_amount": 0
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
		
		# Aggregate estimated costs
		if "estimated_costs" in item:
			for key in totals["estimated_costs"]:
				totals["estimated_costs"][key] += flt(item["estimated_costs"].get(key, 0))
		
		# Aggregate actual costs
		if "actual_costs" in item:
			for key in totals["actual_costs"]:
				totals["actual_costs"][key] += flt(item["actual_costs"].get(key, 0))
		
		# Aggregate revenue breakdown
		if "revenue" in item:
			for key in totals["revenue"]:
				totals["revenue"][key] += flt(item["revenue"].get(key, 0))
		
		# Aggregate profitability
		if "profitability" in item:
			totals["profitability"]["gp"] += flt(item["profitability"].get("gp", 0))
			totals["profitability"]["estimated_gp"] += flt(item["profitability"].get("estimated_gp", 0))
			
		totals["retention_amount"] += flt(item.get("retention_amount", 0))
		totals["advance_amount"] += flt(item.get("advance_amount", 0))
	
	# Calculate bill-level GP%
	revenue_for_gp = flt(totals["revenue"]["tax_invoice"]) or flt(totals["revenue"]["pc"])
	if revenue_for_gp > 0:
		totals["profitability"]["gp_percent"] = flt(totals["profitability"]["gp"] / revenue_for_gp * 100, 2)
	
	# Calculate total estimated GP
	total_estimated_revenue = totals["amount"]["total"]
	total_estimated_cost = totals["estimated_costs"]["total"]
	totals["profitability"]["estimated_gp"] = total_estimated_revenue - total_estimated_cost
	if total_estimated_revenue > 0:
		totals["profitability"]["estimated_gp_percent"] = flt(totals["profitability"]["estimated_gp"] / total_estimated_revenue * 100, 2)
		
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
		# Check if overbilling is allowed
		if not project_boq.allow_overbilling:
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


@frappe.whitelist()
def get_boq_item_cost_progress(boq_item: str) -> dict:
	"""
	Get cost progress comparing estimated vs incurred costs for a BOQ item.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		dict with progress percentage, breakup by category, and variance
	"""
	item = frappe.get_doc("BOQ Item", boq_item)
	return item.get_cost_progress()


@frappe.whitelist()
def get_boq_item_revenue_breakdown(boq_item: str) -> dict:
	"""
	Get revenue breakdown for a BOQ item showing PI, PC, Tax Invoice, Variance, and Balance.
	
	Key Logic:
	- Balance = BOQ Total - Sum of Proforma Invoice amounts (NOT PC amounts)
	- Variance = Sum of (PI Amount - PC Amount) for each PI-PC pair
	- Variance represents loss when PC < PI
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		dict with:
		- proforma_total: Sum of all Proforma Invoice amounts
		- pc_total: Sum of all Payment Certificate accepted amounts
		- tax_invoice_total: Sum of all Tax Invoice amounts
		- variance_total: Sum of all variances (PI - PC)
		- total_billed: Same as proforma_total (what was billed)
		- balance: BOQ Total - proforma_total
	
	Requirements: 3.3, 3.5
	"""
	# Get BOQ Item details
	item = frappe.db.get_value(
		"BOQ Item", boq_item, 
		["total_amount", "total_qty", "rate"], 
		as_dict=True
	)
	
	if not item:
		return {
			"proforma_total": 0,
			"pc_total": 0,
			"tax_invoice_total": 0,
			"variance_total": 0,
			"total_billed": 0,
			"balance": 0
		}
	
	boq_total = flt(item.total_amount)
	
	
	if not item:
		return {
			"proforma_total": 0,
			"pc_total": 0,
			"tax_invoice_total": 0,
			"variance_total": 0,
			"total_billed": 0,
			"balance": 0
		}
	
	boq_total = flt(item.total_amount)
	
	# Get Proforma Invoice totals for this BOQ item
	proforma_total = frappe.db.sql("""
		SELECT COALESCE(SUM(pii.amount), 0) as total
		FROM `tabProforma Invoice Item` pii
		JOIN `tabProforma Invoice` pi ON pi.name = pii.parent
		WHERE pii.boq_item = %s AND pi.docstatus = 1
	""", boq_item)[0][0] or 0
	
	# Get Payment Certificate totals and variance
	pc_data = frappe.db.sql("""
		SELECT 
			COALESCE(SUM(pc.accepted_amount), 0) as pc_total,
			COALESCE(SUM(pc.variance), 0) as variance_total
		FROM `tabPayment Certificate` pc
		WHERE pc.boq_item = %s AND pc.docstatus = 1
	""", boq_item, as_dict=True)[0]
	
	pc_total = flt(pc_data.pc_total) if pc_data else 0
	variance_total = flt(pc_data.variance_total) if pc_data else 0
	
	# Get Tax Invoice totals
	tax_invoice_total = frappe.db.sql("""
		SELECT COALESCE(SUM(sii.amount), 0) as total
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE sii.boq_item = %s AND si.docstatus = 1
	""", boq_item)[0][0] or 0
	
	# Balance = BOQ Total - Proforma Total
	balance = boq_total - proforma_total
	
	return {
		"proforma_total": flt(proforma_total),
		"pc_total": flt(pc_total),
		"tax_invoice_total": flt(tax_invoice_total),
		"variance_total": flt(variance_total),
		"total_billed": flt(proforma_total),
		"balance": flt(balance)
	}

def get_item_retention_amount(boq_item: str) -> float:
	"""
	Calculate retention amount attributed to this BOQ item.
	Use BOQ Progress Ledger retention_amount totals.
	"""
	total_retention = frappe.db.sql("""
		SELECT COALESCE(SUM(retention_amount), 0)
		FROM `tabBOQ Progress Ledger`
		WHERE boq_item = %s AND docstatus = 1
	""", boq_item)[0][0] or 0
	return flt(total_retention)
	



@frappe.whitelist()
def get_boq_item_transactions(boq_item: str) -> list:
	"""
	Get all transactions (PI, PC, Tax Invoice) for a BOQ item.
	
	Returns a unified list of all billing transactions for expandable row display.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		List of transactions with:
		- doctype: "Proforma Invoice" | "Payment Certificate" | "Sales Invoice"
		- name: Document name
		- date: Posting date
		- qty: Quantity billed
		- amount: Amount
		- status: Document status
		- variance: Variance amount (for PC only)
		- pc_amount: Accepted amount (for PC only)
	
	Requirements: 2.2, 2.3
	"""
	transactions = []
	
	# Get Proforma Invoices
	proforma_items = frappe.db.sql("""
		SELECT 
			'Proforma Invoice' as doctype,
			pi.name,
			pi.posting_date as date,
			pii.qty,
			pii.amount,
			pi.status,
			NULL as variance,
			NULL as pc_amount
		FROM `tabProforma Invoice Item` pii
		JOIN `tabProforma Invoice` pi ON pi.name = pii.parent
		WHERE pii.boq_item = %s AND pi.docstatus != 2
		ORDER BY pi.posting_date DESC
	""", boq_item, as_dict=True)
	
	transactions.extend(proforma_items)
	
	# Get Payment Certificates
	payment_certs = frappe.db.sql("""
		SELECT 
			'Payment Certificate' as doctype,
			pc.name,
			pc.posting_date as date,
			NULL as qty,
			pc.proforma_amount as amount,
			pc.status,
			pc.variance,
			pc.accepted_amount as pc_amount
		FROM `tabPayment Certificate` pc
		WHERE pc.boq_item = %s AND pc.docstatus != 2
		ORDER BY pc.posting_date DESC
	""", boq_item, as_dict=True)
	
	transactions.extend(payment_certs)
	
	# Get Sales Invoices (Tax Invoices)
	sales_invoices = frappe.db.sql("""
		SELECT 
			'Sales Invoice' as doctype,
			si.name,
			si.posting_date as date,
			sii.qty,
			sii.amount,
			si.status,
			NULL as variance,
			NULL as pc_amount
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE sii.boq_item = %s AND si.docstatus != 2
		ORDER BY si.posting_date DESC
	""", boq_item, as_dict=True)
	
	transactions.extend(sales_invoices)
	
	# Sort all transactions by date (most recent first)
	transactions.sort(key=lambda x: x.get('date') or '', reverse=True)
	
	return transactions


@frappe.whitelist()
def get_boq_item_with_transactions(boq_item: str) -> dict:
	"""
	Get BOQ item details along with all transactions for popup display.
	
	Returns item details (description, unit, rate, qty/value breakdown) and
	all transactions (PI, PC, Tax Invoice) in a single API call.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		dict with:
		- item: Item details including qty and amount breakdown
		- transactions: List of all transactions with project_boq
	
	Requirements: 1.1, 1.2, 1.3, 3.4
	"""
	# Get BOQ Item details
	item_doc = frappe.get_doc("BOQ Item", boq_item)
	
	# Get ledger-based values
	ledger_values = get_item_ledger_values(boq_item)
	
	# Get revenue breakdown
	revenue = get_boq_item_revenue_breakdown_internal(boq_item, flt(item_doc.total_amount))
	
	# Get estimated and actual costs
	estimated_costs = {
		"material": flt(item_doc.estimated_material_cost),
		"labour": flt(item_doc.estimated_labour_cost),
		"asset": flt(item_doc.estimated_asset_cost),
		"subcontract": flt(item_doc.estimated_subcontract_cost),
		"other": flt(item_doc.estimated_other_cost),
		"total": flt(item_doc.total_estimated_cost)
	}
	
	# Build item data
	item_data = {
		"name": item_doc.name,
		"item_code": item_doc.item_code,
		"description": item_doc.description,
		"unit": item_doc.unit,
		"project": item_doc.project,
		"project_boq": item_doc.project_boq,
		"parent_bill": item_doc.parent_bill,
		"billing_status": item_doc.billing_status,
		"qty": ledger_values.get("qty", {}),
		"amount": ledger_values.get("amount", {}),
		"revenue": revenue,
		"estimated_costs": estimated_costs,
		"actual_costs": ledger_values.get("actual_costs", {})
	}
	
	# Get transactions with project_boq included
	transactions = get_boq_item_transactions_with_ledger(boq_item)
	
	return {
		"item": item_data,
		"transactions": transactions
	}


def get_boq_item_transactions_with_ledger(boq_item: str) -> list:
	"""
	Get all transactions for a BOQ item including ledger entries with project_boq.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		List of transactions with complete ledger data including project_boq
		
	Requirements: 3.4
	"""
	transactions = []
	
	# Get BOQ Progress Ledger entries (includes project_boq)
	ledger_entries = frappe.db.sql("""
		SELECT 
			reference_doctype,
			reference_name,
			posting_date as date,
			creation,
			qty,
			amount,
			source,
			project_boq,
			proforma_invoice,
			proforma_amount,
			payment_certificate,
			certified_amount,
			tax_invoice,
			tax_invoice_amount,
			remarks
		FROM `tabBOQ Progress Ledger`
		WHERE boq_item = %s
		ORDER BY posting_date ASC, creation ASC
	""", boq_item, as_dict=True)
	
	# Group by Proforma Invoice (Billing Cycle)
	billing_cycles = {}
	independent_entries = []
	
	# Pre-fetch status of all referenced Proforma Invoices to filter revisions
	pi_names = set(entry.proforma_invoice for entry in ledger_entries if entry.proforma_invoice)
	cancelled_pis = set()
	if pi_names:
		cancelled_pis = set(frappe.db.sql("""
			SELECT name FROM `tabProforma Invoice` 
			WHERE name IN %s AND docstatus = 2
		""", (list(pi_names),), as_list=1)[0] if pi_names else [])

	# 1. Resolve Orphan Entries (Try to find PI for independent entries)
	orphan_entries = [e for e in ledger_entries if not e.proforma_invoice]
	
	# Cache for resolved PIs
	resolved_pis = {}
	
	# Helper to find PI from Sales Invoice
	si_names = [e.reference_name for e in orphan_entries if e.reference_doctype == 'Sales Invoice']
	if si_names:
		# Check if SI is linked to a PC which has a PI
		si_links = frappe.db.sql("""
			SELECT si.name, pc.proforma_invoice
			FROM `tabSales Invoice` si
			LEFT JOIN `tabPayment Certificate` pc ON pc.tax_invoice = si.name
			WHERE si.name IN %s AND pc.proforma_invoice IS NOT NULL
		""", (si_names,), as_dict=True)
		for link in si_links:
			resolved_pis[link.name] = link.proforma_invoice
			
	# Helper to find PI from Payment Certificate
	pc_names = [e.reference_name for e in orphan_entries if e.reference_doctype == 'Payment Certificate']
	if pc_names:
		pc_links = frappe.db.sql("""
			SELECT name, proforma_invoice
			FROM `tabPayment Certificate`
			WHERE name IN %s AND proforma_invoice IS NOT NULL
		""", (pc_names,), as_dict=True)
		for link in pc_links:
			resolved_pis[link.name] = link.proforma_invoice

	for entry in ledger_entries:
		# Try to resolve PI if missing
		if not entry.proforma_invoice and entry.reference_name in resolved_pis:
			entry.proforma_invoice = resolved_pis[entry.reference_name]

		# Exclude entries related to cancelled PIs
		if entry.proforma_invoice and entry.proforma_invoice in cancelled_pis:
			continue

		if entry.proforma_invoice:
			if entry.proforma_invoice not in billing_cycles:
				billing_cycles[entry.proforma_invoice] = []
			billing_cycles[entry.proforma_invoice].append(entry)
		else:
			# If it's a "Sales Invoice" but we couldn't resolve a PI, 
			# it might be a direct invoice. Treat it as independent.
			independent_entries.append(entry)
	
	processed_transactions = []
	
	# Process Billing Cycles (PI -> PC -> TI)
	for pi_name, entries in billing_cycles.items():
		# Find the "Winner" entry for this cycle (TI > PC > PI > Other)
		# Because we want to show ONE line representing the final state
		winner = None
		
		# Sort inputs by hierarchy of maturity
		# We look for the entry that represents the furthest stage
		ti_entry = next((e for e in entries if e.tax_invoice), None)
		pc_entry = next((e for e in entries if e.payment_certificate and not e.tax_invoice), None)
		pi_entry = next((e for e in entries if e.reference_doctype == 'Proforma Invoice'), None)
		
		if ti_entry:
			winner = ti_entry
			# Ensure we use the TI amount/qty
			# Ledger "amount" column normally holds the delta or actual value for that transaction
			# But for the consolidated view, we want the magnitude of the stage
			# If the ledger logic inserts entries cumulatively (PI then TI), the TI entry usually holds the *Difference*? 
			# OR does it hold the full value?
			# Standard Ledger Design: Rows are deltas. 
			# User's Request: "PI created 3000... Tax Invoice 2500... Show 2500".
			# This implies we should take the absolute value from the Document fields in the ledger, not necessarily the ledger amount column?
			# The ledger columns: `proforma_amount`, `certified_amount`, `tax_invoice_amount`.
			winner.amount = flt(winner.tax_invoice_amount)
			# Qty logic: usually strictly tracked. Let's assume TI Qty is final.
			# If ledger entry has `current_qty` (from our select earlier which we removed, let's trust `qty` if it is full magnitude)
			# Actually, if ledger tracks deltas, `qty` might be 0 for TI if it didn't change from PI.
			# We should probably use the explicit columns if available, or fall back to PI info.
			# Let's trust the explicit amount columns which seem to be snapshots.
		elif pc_entry:
			winner = pc_entry
			winner.amount = flt(winner.certified_amount)
		elif pi_entry:
			winner = pi_entry
			winner.amount = flt(winner.proforma_amount)
		else:
			# Fallback to the last entry
			winner = entries[-1]
			
		if winner:
			# Normalize Fields for View
			winner.proforma = winner.proforma_invoice
			winner.pc = winner.payment_certificate
			winner.tax = winner.tax_invoice
			
			# Determine status
			if winner.tax_invoice:
				winner.status = "Invoiced" # Or fetch status
				winner.doctype = "Sales Invoice"
				winner.name = winner.tax_invoice
			elif winner.payment_certificate:
				winner.status = "Certified"
				winner.doctype = "Payment Certificate"
				winner.name = winner.payment_certificate
			else:
				try:
					winner.status = frappe.db.get_value("Proforma Invoice", winner.proforma_invoice, "status")
				except:
					winner.status = "Draft"
				winner.doctype = "Proforma Invoice"
				winner.name = winner.proforma_invoice
			
			processed_transactions.append(winner)
	
	# Add independent entries (e.g. manual adjustments)
	for entry in independent_entries:
		processed_transactions.append(entry)
	
	# Sort by Date
	processed_transactions.sort(key=lambda x: (x.date or '', x.creation or '')) # Date Ascending
	
	# Re-calculate Running Totals
	running_qty = 0.0
	running_amount = 0.0
	
	final_transactions = []
	
	for tx in processed_transactions:
		# Calculate Previous (Available before this tx)
		tx.prev_qty = running_qty
		tx.prev_amt = running_amount # Field name 'prev amt' requested? Maps to 'prev_amount' usually.
		# User requested "prev amt" (space/underscore is ambiguous in text, adhering to snake_case for API)
		tx.prev_amount = running_amount
		
		# Current
		# Use the amount determined from the "Winner" logic
		current_q = flt(tx.qty) # This might be risky if ledger is delta. 
		# If `qty` is delta/difference, summing works. 
		# If user wants "Snapshot" value:
		# Re-read: "PI value 10000... PI is 3000... TI is 2500... Show 2500".
		# This implies the row represents the Billing Event Magnitude.
		# So `current_amount` = 2500.
		# `accumulated` = `prev` + `current`.
		
		# However, `qty` in the ledger row:
		# If PI had 3. TI has 3. Ledger for TI might have qty=0 (no change).
		# We likely want the Absolute Quantity of the event.
		# We don't have explicit `proforma_qty` columns in the select.
		# But `accumulated_qty` in DB was snapshot.
		# Let's rely on the fact that for specific Documents (PI, PC), normally `qty` IS the billed qty for that doc.
		
		# For robustness:
		# If it's a TI/PC row, `qty` might be 0 or delta.
		# Let's assume for now `qty` field holds the distinct quantity billed in this cycle.
		
		tx.current_qty = flt(tx.qty) 
		tx.current_amount = flt(tx.amount)
		
		# Accumulated
		running_qty += tx.current_qty
		running_amount += tx.current_amount
		
		tx.accumulated_qty = running_qty # "accu qty"
		tx.accumulated_amount = running_amount # "accu amt"
		
		# Variance
		if tx.proforma_amount and tx.certified_amount:
			tx.variance = flt(tx.proforma_amount) - flt(tx.certified_amount)
		else:
			tx.variance = 0
			
		# Mappings for specific requested keys if strictly needed by frontend
		# "prev qty", "curr aty", "accu qty" etc are likely labels in UI, but API keys usually snake_case
		# We'll stick to standard snake_case keys which the UI likely maps from.
		
		final_transactions.append(tx)
		
	# Reverse sort for display (Newest First) if that's the convention, 
	# but user example: prev 0 -> 3000. Next prev 3000 -> ...
	# This implies Chronological order for calculation, but Display order?
	# "showing the BOQ ledger entries... visibility I want to be minimized"
	# Usually ledgers are shown Newest Top.
	# But the calculation description flows Top->Down (0->3000).
	# I will return Chronological (Oldest First) or adhere to what the previous code did (Desc)?
	# Previous code ordered DESC.
	# If I order DESC, "Previous" usually refers to "Before this occurred".
	# The user's example is clearly Chronological (0 -> 3000).
	# If I return DESC, the first row shown (latest) will have proper Pref/Accu values.
	final_transactions.reverse()
	
	return final_transactions
