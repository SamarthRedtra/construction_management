# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_employee_daily_rate(employee: str) -> float:
	"""
	Get the daily rate for an employee.
	Uses cached lookup first, then falls back to calculation.
	
	Priority:
	1. Cache lookup (fastest)
	2. Salary Structure Assignment (base + variable)
	3. Salary Structure (sum of fixed earnings)
	4. Returns 0 (manual entry required)
	
	Args:
		employee: Employee name
		
	Returns:
		Daily rate (monthly salary / 30)
	"""
	from construction_management.api.employee_rate_cache import get_employee_rate_optimized
	
	result = get_employee_rate_optimized(employee)
	return flt(result.get("rate_per_day", 0))


@frappe.whitelist()
def get_item_valuation_rate(item_code: str, warehouse: str = None) -> float:
	"""
	Get the valuation rate for an item.
	
	Args:
		item_code: Item code
		warehouse: Warehouse (optional)
		
	Returns:
		Valuation rate
	"""
	if warehouse:
		rate = frappe.db.get_value(
			"Bin",
			{"item_code": item_code, "warehouse": warehouse},
			"valuation_rate"
		)
		if rate:
			return flt(rate)
	
	# Fallback to item's valuation rate
	return flt(frappe.db.get_value("Item", item_code, "valuation_rate"))


@frappe.whitelist()
def get_boq_items_for_project(project: str) -> list:
	"""
	Get all BOQ Items for a project.
	
	Args:
		project: Project name
		
	Returns:
		List of BOQ Items with bill_no
	"""
	items = frappe.db.sql("""
		SELECT 
			bi.name,
			bi.description,
			bi.parent_bill as bill_no,
			bb.bill_no as bill_number
		FROM `tabBOQ Item` bi
		JOIN `tabBOQ Bill` bb ON bb.name = bi.parent_bill
		WHERE bi.project = %s
		ORDER BY bb.sequence, bi.idx
	""", project, as_dict=True)
	
	return items


@frappe.whitelist()
def get_employees_with_rates() -> list:
	"""Get all active employees with their daily rates"""
	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "employee_name", "designation"]
	)
	
	for emp in employees:
		emp["rate_per_day"] = get_employee_daily_rate(emp.name)
	
	return employees


@frappe.whitelist()
def get_employee_with_rate(employee: str) -> dict:
	"""
	Get single employee with their daily rate.
	Uses optimized cache lookup with fallback to Salary Structure.
	
	Returns source field to indicate where rate came from:
	- "cache": From daily cache
	- "salary_structure_assignment": From SSA base+variable
	- "salary_structure": From SS fixed earnings
	- "manual_required": No rate found, manual entry needed
	"""
	from construction_management.api.employee_rate_cache import get_employee_rate_optimized
	return get_employee_rate_optimized(employee)


@frappe.whitelist()
def get_asset_with_rate(asset: str, project: str, date: str = None) -> dict:
	"""Get single asset with its daily rate for a project"""
	from frappe.utils import today
	
	asset_doc = frappe.get_doc("Asset", asset)
	
	# Try to get rate from Project Asset Billing
	rate = frappe.db.get_value(
		"Project Asset Billing",
		{
			"project": project,
			"asset": asset,
			"effective_from": ["<=", date or today()]
		},
		"value_per_day",
		order_by="effective_from desc"
	)
	
	return {
		"name": asset_doc.name,
		"asset_name": asset_doc.asset_name,
		"rate_per_day": flt(rate) if rate else 0
	}


@frappe.whitelist()
def get_item_details(item_code: str, price_list: str = None) -> dict:
	"""
	Get item details including:
	- item_price_rate: Rate from Item Price (for DPR display/costing)
	- valuation_rate: Rate from Item (for Stock Entry)
	
	Args:
		item_code: Item code
		price_list: Optional price list to check
		
	Returns:
		dict with item details and both rates
	"""
	item = frappe.get_doc("Item", item_code)
	
	item_price_rate = 0
	
	# Try to get rate from specified price list first
	if price_list:
		price = frappe.db.get_value(
			"Item Price",
			{"item_code": item_code, "price_list": price_list},
			"price_list_rate"
		)
		if price:
			item_price_rate = flt(price)
	
	# Fallback to buying price list
	if not item_price_rate:
		buying_price_list = frappe.db.get_single_value("Buying Settings", "buying_price_list")
		if buying_price_list:
			price = frappe.db.get_value(
				"Item Price",
				{"item_code": item_code, "price_list": buying_price_list},
				"price_list_rate"
			)
			if price:
				item_price_rate = flt(price)
	
	# Try standard buying price list
	if not item_price_rate:
		price = frappe.db.get_value(
			"Item Price",
			{"item_code": item_code, "buying": 1},
			"price_list_rate"
		)
		if price:
			item_price_rate = flt(price)
	
	# Get valuation rate from Item
	valuation_rate = flt(item.valuation_rate)
	
	# For display rate: prefer item_price_rate, fallback to valuation_rate
	display_rate = item_price_rate if item_price_rate > 0 else valuation_rate
	rate_source = "Item Price" if item_price_rate > 0 else "Valuation Rate"
	
	return {
		"item_code": item.name,
		"item_name": item.item_name,
		"stock_uom": item.stock_uom,
		"rate": display_rate,  # For DPR display/costing
		"item_price_rate": item_price_rate,  # From Item Price
		"valuation_rate": valuation_rate,  # For Stock Entry
		"rate_source": rate_source
	}


@frappe.whitelist()
def get_assets_with_rates(project: str, date: str = None) -> list:
	"""Get all assets with their daily rates for a project"""
	from frappe.utils import today
	
	assets = frappe.get_all(
		"Asset",
		filters={"status": ["in", ["Submitted", "Partially Depreciated"]]},
		fields=["name", "asset_name", "status"]
	)
	
	for asset in assets:
		# Try to get rate from Project Asset Billing
		rate = frappe.db.get_value(
			"Project Asset Billing",
			{
				"project": project,
				"asset": asset.name,
				"effective_from": ["<=", date or today()]
			},
			"value_per_day",
			order_by="effective_from desc"
		)
		asset["rate_per_day"] = flt(rate) if rate else 0
	
	return assets


@frappe.whitelist()
def get_project_dprs(project: str) -> list:
	"""
	Get all Daily Progress Records for a project with summary info.
	
	Args:
		project: Project name
		
	Returns:
		List of DPRs with details
	"""
	dprs = frappe.db.sql("""
		SELECT 
			dpr.name,
			dpr.date,
			dpr.boq_item,
			bi.description as boq_item_description,
			bb.bill_no,
			dpr.labour_cost,
			dpr.material_cost,
			dpr.asset_cost,
			dpr.subcontract_cost,
			dpr.expense_cost,
			dpr.overhead_cost,
			dpr.total_cost,
			dpr.docstatus,
			dpr.remarks
		FROM `tabDaily Progress Record` dpr
		LEFT JOIN `tabBOQ Item` bi ON bi.name = dpr.boq_item
		LEFT JOIN `tabBOQ Bill` bb ON bb.name = bi.parent_bill
		WHERE dpr.project = %s
		ORDER BY dpr.date DESC, dpr.creation DESC
	""", project, as_dict=True)
	
	# Add status label
	for dpr in dprs:
		if dpr.docstatus == 0:
			dpr['status'] = 'Draft'
		elif dpr.docstatus == 1:
			dpr['status'] = 'Submitted'
		else:
			dpr['status'] = 'Cancelled'
	
	return dprs


@frappe.whitelist()
def create_dpr_with_details(
	project: str,
	boq_item: str,
	date: str,
	employees: str = None,
	assets: str = None,
	materials: str = None,
	expenses: str = None,
	overheads: str = None,
	subcontract_cost: float = 0,
	remarks: str = None
) -> dict:
	"""
	Create a DPR with employee, asset, material, expense, and overhead details.
	
	Args:
		project: Project name
		boq_item: BOQ Item name
		date: DPR date
		employees: JSON string of employee list [{employee, hours, rate_per_day, amount}]
		assets: JSON string of asset list [{asset, hours, rate_per_day, amount}]
		materials: JSON string of material list [{item_code, warehouse, qty, rate, amount}]
		expenses: JSON string of expense list [{expense_type, description, amount}]
		overheads: JSON string of overhead list [{account, description, amount}]
		subcontract_cost: Subcontract cost
		remarks: Optional remarks
		
	Returns:
		dict with created DPR details
	"""
	import json
	
	employees_list = json.loads(employees) if employees else []
	assets_list = json.loads(assets) if assets else []
	materials_list = json.loads(materials) if materials else []
	expenses_list = json.loads(expenses) if expenses else []
	overheads_list = json.loads(overheads) if overheads else []
	
	# Calculate totals
	labour_cost = sum(flt(e.get("amount", 0)) for e in employees_list)
	asset_cost = sum(flt(a.get("amount", 0)) for a in assets_list)
	material_cost = sum(flt(m.get("amount", 0)) for m in materials_list)
	expense_cost = sum(flt(x.get("amount", 0)) for x in expenses_list)
	overhead_cost = sum(flt(o.get("amount", 0)) for o in overheads_list)
	
	# Create DPR
	dpr = frappe.new_doc("Daily Progress Record")
	dpr.project = project
	dpr.boq_item = boq_item
	dpr.date = date
	dpr.labour_cost = labour_cost
	dpr.material_cost = material_cost
	dpr.asset_cost = asset_cost
	dpr.subcontract_cost = flt(subcontract_cost)
	dpr.expense_cost = expense_cost
	dpr.overhead_cost = overhead_cost
	dpr.remarks = remarks
	
	# Add employees
	for emp in employees_list:
		dpr.append("employees", {
			"employee": emp.get("employee"),
			"hours": flt(emp.get("hours", 8)),
			"rate_per_day": flt(emp.get("rate_per_day", 0)),
			"amount": flt(emp.get("amount", 0))
		})
	
	# Add assets
	for asset in assets_list:
		dpr.append("assets", {
			"asset": asset.get("asset"),
			"hours": flt(asset.get("hours", 8)),
			"rate_per_day": flt(asset.get("rate_per_day", 0)),
			"amount": flt(asset.get("amount", 0))
		})
	
	# Add materials
	for mat in materials_list:
		dpr.append("materials", {
			"item_code": mat.get("item_code"),
			"warehouse": mat.get("warehouse"),
			"qty": flt(mat.get("qty", 0)),
			"rate": flt(mat.get("rate", 0)),
			"amount": flt(mat.get("amount", 0))
		})
	
	# Add expenses
	for exp in expenses_list:
		dpr.append("expenses", {
			"expense_type": exp.get("expense_type"),
			"description": exp.get("description", ""),
			"amount": flt(exp.get("amount", 0))
		})
	
	# Add overheads
	for ovh in overheads_list:
		dpr.append("overheads", {
			"account": ovh.get("account"),
			"description": ovh.get("description", ""),
			"amount": flt(ovh.get("amount", 0))
		})
	
	dpr.insert()
	
	return {
		"name": dpr.name,
		"total_cost": dpr.total_cost
	}
