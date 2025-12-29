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
def get_item_valuation_rate(item_code: str, warehouse: str = None) -> dict:
	"""
	Get the valuation rate for an item.
	
	Args:
		item_code: Item code
		warehouse: Warehouse (optional)
		
	Returns:
		Dict with valuation_rate
	"""
	rate = 0
	if warehouse:
		rate = frappe.db.get_value(
			"Bin",
			{"item_code": item_code, "warehouse": warehouse},
			"valuation_rate"
		)
	
	if not rate:
		# Fallback to item's valuation rate
		rate = frappe.db.get_value("Item", item_code, "valuation_rate")
	
	if not rate:
		# Fallback to standard rate
		rate = frappe.db.get_value("Item", item_code, "standard_rate")
	
	return {"valuation_rate": flt(rate)}


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
	"""Get single asset with its hourly rate for a project"""
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
		"value_per_hour",
		order_by="effective_from desc"
	)
	
	return {
		"name": asset_doc.name,
		"asset_name": asset_doc.asset_name,
		"rate_per_hour": flt(rate) if rate else 0,
		"rate_per_day": flt(rate) * 8 if rate else 0  # For backward compatibility
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
	"""Get all assets with their hourly rates for a project"""
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
			"value_per_hour",
			order_by="effective_from desc"
		)
		asset["rate_per_hour"] = flt(rate) if rate else 0
		asset["rate_per_day"] = flt(rate) * 8 if rate else 0  # For backward compatibility
	
	return assets


@frappe.whitelist()
def get_project_dprs(project: str) -> list:
	"""
	Get all Daily Progress Records for a project with summary info.
	Includes quantity totals for DPR summary display.
	(Task 3.3: Display Quantities in DPR Totals)
	
	Args:
		project: Project name
		
	Returns:
		List of DPRs with details including quantities
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
			dpr.remarks,
			COALESCE(dpr.total_labour_hours, 0) as total_labour_hours,
			COALESCE(dpr.total_material_qty, 0) as total_material_qty,
			COALESCE(dpr.total_asset_hours, 0) as total_asset_hours,
			COALESCE(dpr.total_subcontract_qty, 0) as total_subcontract_qty,
			COALESCE(dpr.total_expense_count, 0) as total_expense_count
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


@frappe.whitelist()
def get_project_warehouses(project: str) -> list:
	"""
	Get warehouses linked to a specific project.
	
	Args:
		project: Project name
		
	Returns:
		List of warehouses with custom_project = project
	"""
	warehouses = frappe.get_all(
		"Warehouse",
		filters={"custom_project": project},
		fields=["name", "warehouse_name", "is_group", "parent_warehouse"]
	)
	return warehouses


@frappe.whitelist()
def get_warehouse_items_with_stock(warehouse: str, project: str = None) -> list:
	"""
	Get items with available stock in a warehouse.
	
	Property 10: Only items with actual_qty > 0 in the project's site_location 
	warehouse SHALL be available for selection.
	
	Args:
		warehouse: Warehouse name (optional if project provided)
		project: Project name (to get site_location warehouse)
		
	Returns:
		List of items with actual_qty > 0
	"""
	# If project provided, get site_location warehouse
	if project and not warehouse:
		warehouse = frappe.db.get_value("Project", project, "site_location")
	
	if not warehouse:
		return []
	
	items = frappe.db.sql("""
		SELECT 
			b.item_code,
			i.item_name,
			i.stock_uom,
			b.actual_qty,
			b.valuation_rate
		FROM `tabBin` b
		JOIN `tabItem` i ON i.name = b.item_code
		WHERE b.warehouse = %s
		AND b.actual_qty > 0
		ORDER BY i.item_name
	""", warehouse, as_dict=True)
	
	return items


@frappe.whitelist()
def validate_material_stock(warehouse: str, item_code: str, qty: float, project: str = None) -> dict:
	"""
	Validate if sufficient stock is available for a material.
	
	Property 11: The requested quantity SHALL NOT exceed the available stock 
	in the site_location warehouse.
	
	Args:
		warehouse: Warehouse name (optional if project provided)
		item_code: Item code
		qty: Requested quantity
		project: Project name (to get site_location warehouse)
		
	Returns:
		dict with is_valid, available_qty, message
	"""
	qty = flt(qty)
	
	# If project provided, get site_location warehouse
	if project and not warehouse:
		warehouse = frappe.db.get_value("Project", project, "site_location")
	
	if not warehouse:
		return {
			"is_valid": False,
			"available_qty": 0,
			"requested_qty": qty,
			"message": _("No warehouse specified")
		}
	
	available_qty = frappe.db.get_value(
		"Bin",
		{"warehouse": warehouse, "item_code": item_code},
		"actual_qty"
	) or 0
	
	is_valid = flt(available_qty) >= qty
	
	return {
		"is_valid": is_valid,
		"available_qty": flt(available_qty),
		"requested_qty": qty,
		"message": "" if is_valid else _("Insufficient stock. Available: {0}, Requested: {1}").format(
			flt(available_qty), qty
		)
	}


@frappe.whitelist()
def get_warehouse_items_query(doctype, txt, searchfield, start, page_len, filters):
	"""
	Query function for item selection filtered by warehouse stock.
	Used in DPR Material child table to show only items with stock.
	
	Property 10: Only items with actual_qty > 0 SHALL be available for selection.
	
	Args:
		doctype: Item
		txt: Search text
		searchfield: Field to search
		start: Start index
		page_len: Page length
		filters: Must contain 'warehouse' or 'project'
		
	Returns:
		List of items with stock in the warehouse
	"""
	warehouse = filters.get("warehouse")
	project = filters.get("project")
	
	# If project provided, get site_location warehouse
	if project and not warehouse:
		warehouse = frappe.db.get_value("Project", project, "site_location")
	
	if not warehouse:
		return []
	
	return frappe.db.sql("""
		SELECT 
			b.item_code,
			i.item_name,
			b.actual_qty,
			b.valuation_rate
		FROM `tabBin` b
		JOIN `tabItem` i ON i.name = b.item_code
		WHERE b.warehouse = %(warehouse)s
		AND b.actual_qty > 0
		AND (
			b.item_code LIKE %(txt)s
			OR i.item_name LIKE %(txt)s
		)
		ORDER BY i.item_name
		LIMIT %(start)s, %(page_len)s
	""", {
		"warehouse": warehouse,
		"txt": "%%%s%%" % txt,
		"start": start,
		"page_len": page_len
	})
