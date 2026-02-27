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
def get_bin_snapshot(warehouse: str, item_code: str) -> dict:
	"""
	Get warehouse stock snapshot for an item (on-hand, reserved, projected, valuation).
	"""
	if not warehouse or not item_code:
		return {}
	return frappe.db.get_value(
		"Bin",
		{"warehouse": warehouse, "item_code": item_code},
		["actual_qty", "reserved_qty", "projected_qty", "valuation_rate"],
		as_dict=True
	) or {}


@frappe.whitelist()
def get_site_location_stock(project: str) -> list:
	"""
	Return stock snapshot for the project's site_location warehouse.
	Fields: item_code, item_name, stock_uom, actual_qty, reserved_qty, projected_qty, valuation_rate.
	"""
	if not project:
		return []
	warehouse = frappe.db.get_value("Project", project, "site_location")
	if not warehouse:
		return []
	return frappe.db.sql("""
		SELECT 
			b.item_code,
			i.item_name,
			i.stock_uom,
			b.actual_qty,
			b.reserved_qty,
			b.projected_qty,
			b.valuation_rate
		FROM `tabBin` b
		JOIN `tabItem` i ON i.name = b.item_code
		WHERE b.warehouse = %s
		ORDER BY b.actual_qty DESC, i.item_name ASC
	""", warehouse, as_dict=True)


@frappe.whitelist()
def get_asset_with_rate(asset: str, project: str, date: str = None) -> dict:
	"""Get single asset with its hourly rate for a project"""
	from frappe.utils import today
	
	asset_doc = frappe.get_doc("Asset", asset)
	
	# Try to get rate from Project Asset Billing
	rate = frappe.db.get_values(
		"Project Asset Billing",
		{
			"project": project,
			"asset": asset,
			"effective_from": ["<=", date or today()]
		},
		["value_per_hour", "value_per_day"],
		order_by="effective_from desc"
	)
	per_day_rate = rate[0][1] if rate and rate[0][1] else None
	per_hour_rate = rate[0][0] if rate and rate[0][0] else None
	return {
		"name": asset_doc.name,
		"asset_name": asset_doc.asset_name,
		"rate_per_hour": flt(per_hour_rate) if per_hour_rate else 0,
		"rate_per_day": flt(per_day_rate) if per_day_rate else 0
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
		rate = frappe.db.get_values(
			"Project Asset Billing",
			{
				"project": project,
				"asset": asset.name,
				"effective_from": ["<=", date or today()]
			},
			["value_per_hour", "value_per_day"],
			order_by="effective_from desc"
		)
		if rate:
			asset["rate_per_hour"] = flt(rate[0][0]) if rate[0][0] else 0
			asset["rate_per_day"] = flt(rate[0][1]) if rate[0][1] else 0
		else:
			asset["rate_per_hour"] = 0
			asset["rate_per_day"] = 0
	return assets


@frappe.whitelist()
def get_project_dprs(project: str = None, from_date: str = None, to_date: str = None) -> list:
	"""
	Get Daily Progress Records with optional project and date range filtering.
	Includes quantity totals for DPR summary display.
	"""
	conditions = []
	values = {}
	
	if project:
		conditions.append("dpr.project = %(project)s")
		values["project"] = project
		
	if from_date:
		conditions.append("dpr.date >= %(from_date)s")
		values["from_date"] = from_date
		
	if to_date:
		conditions.append("dpr.date <= %(to_date)s")
		values["to_date"] = to_date
		
	# Exclude cancelled DPRs
	conditions.append("dpr.docstatus != 2")

	where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
	
	dprs = frappe.db.sql(f"""
		SELECT 
			dpr.name,
			dpr.date,
			dpr.project,
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
		{where_clause}
		ORDER BY dpr.date DESC, dpr.creation DESC
	""", values, as_dict=True)
	
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
	bill_no: str = None,
	warehouse: str = None,
	project_sites: str = None,
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
	"""
	import json
	
	employees_list = json.loads(employees) if employees else []
	assets_list = json.loads(assets) if assets else []
	materials_list = json.loads(materials) if materials else []
	expenses_list = json.loads(expenses) if expenses else []
	overheads_list = json.loads(overheads) if overheads else []
	
	return _create_dpr_internal(
		project=project,
		date=date,
		boq_item=boq_item,
		bill_no=bill_no,
		project_sites=project_sites,
		warehouse=warehouse,
		remarks=remarks,
		subcontract_cost=subcontract_cost,
		employees=employees_list,
		assets=assets_list,
		materials=materials_list,
		expenses=expenses_list,
		overheads=overheads_list
	)


def _create_dpr_internal(
	project: str,
	date: str,
	boq_item: str,
	bill_no: str = None,
	project_sites: str = None,
	warehouse: str = None,
	remarks: str = None,
	subcontract_cost: float = 0,
	employees: list = None,
	absent_employees: list = None,
	assets: list = None,
	materials: list = None,
	expenses: list = None,
	overheads: list = None,
	area_covered: float = 0,
	consumed_qty: float = 0,
	balance_qty: float = 0,
	submit: int = 0
) -> dict:
	"""
	Internal helper to create a single DPR document passed pre-parsed lists.
	"""
	employees = employees or []
	assets = assets or []
	materials = materials or []
	expenses = expenses or []
	overheads = overheads or []
	
	# Calculate totals
	labour_cost = sum(flt(e.get("amount", 0)) for e in employees)
	asset_cost = sum(flt(a.get("amount", 0)) for a in assets)
	material_cost = sum(flt(m.get("amount", 0)) for m in materials)
	expense_cost = sum(flt(x.get("amount", 0)) for x in expenses)
	overhead_cost = sum(flt(o.get("amount", 0)) for o in overheads)
	
	# Create DPR
	dpr = frappe.new_doc("Daily Progress Record")
	dpr.naming_series = "DPR-.YYYY.-"
	dpr.project = project
	dpr.boq_item = boq_item
	dpr.bill_no = bill_no or frappe.db.get_value("BOQ Item", boq_item, "parent_bill")
	final_warehouse = warehouse 
	if final_warehouse:
		dpr.warehouse = final_warehouse
	if project_sites:
		dpr.project_sites = project_sites
	
	dpr.date = date
	dpr.labour_cost = labour_cost
	dpr.material_cost = material_cost
	dpr.asset_cost = asset_cost
	dpr.subcontract_cost = flt(subcontract_cost)
	dpr.expense_cost = expense_cost
	dpr.overhead_cost = overhead_cost
	dpr.remarks = remarks
	
	# Additional fields for enhanced tracking (if they exist)
	for field in ["area_covered", "consumed_qty", "balance_qty"]:
		if hasattr(dpr, field):
			val = locals().get(field)
			if val:
				setattr(dpr, field, flt(val))
	
	# Add employees
	for emp in employees:
		dpr.append("employees", {
			"employee": emp.get("employee"),
			"hours": flt(emp.get("hours", 8)),
			"rate_per_day": flt(emp.get("rate_per_day", 0)),
			"amount": flt(emp.get("amount", 0))
		})

	# Add absent employees (reference only, no cost)
	if hasattr(dpr, "absent_employees"):
		for ae in (absent_employees or []):
			emp_id = ae.get("employee") or ae.get("name")
			if emp_id:
				dpr.append("absent_employees", {"employee": emp_id})

	# Add assets
	for asset in assets:
		dpr.append("assets", {
			"asset": asset.get("asset"),
			"hours": flt(asset.get("hours", 8)),
			"rate_per_day": flt(asset.get("rate_per_day", 0)),
			"rate_per_hour": flt(asset.get("rate_per_hour", 0)),
			"amount": flt(asset.get("amount", 0))
		})
	
	# Add materials
	for mat in materials:
		dpr.append("materials", {
			"item_code": mat.get("item_code"),
			"warehouse": mat.get("warehouse") or final_warehouse,
			"project_sites":project_sites,
			"qty": flt(mat.get("qty", 0)),
			"rate": flt(mat.get("rate", 0)),
			"amount": flt(mat.get("amount", 0))
		})
	
	# Add expenses
	for exp in expenses:
		dpr.append("expenses", {
			"expense_type": exp.get("expense_type"),
			"description": exp.get("description", ""),
			"amount": flt(exp.get("amount", 0))
		})
	
	# Add overheads
	for ovh in overheads:
		dpr.append("overheads", {
			"account": ovh.get("account"),
			"description": ovh.get("description", ""),
			"amount": flt(ovh.get("amount", 0))
		})
	
	dpr.insert()
	
	error = None
	if submit:
		save_point = f"before_submit_{dpr.name.replace('-', '_')}"
		try:
			frappe.db.savepoint(save_point)
			dpr.submit()
		except Exception as e:
			frappe.db.rollback(save_point=save_point)
			error = str(e)
			# Explicitly reset docstatus to 0 in case the object state was modified
			dpr.docstatus = 0 
	
	return {
		"name": dpr.name,
		"total_cost": dpr.total_cost,
		"error": error
	}


@frappe.whitelist()
def create_bulk_dpr_enhanced(project: str, date: str, data: str, submit: int = 0) -> dict:
	"""
	Enhanced bulk create Daily Progress Records with full child table support.
	Uses the standard creation logic iteratively.
	"""
	import json
	
	records_data = json.loads(data) if isinstance(data, str) else data
	created_names = []
	errors = []
	
	for idx, dpr_data in enumerate(records_data):
		try:
			if not dpr_data.get("boq_item"):
				errors.append(_("Row {0}: BOQ Item is required").format(idx + 1))
				continue
			
			# Call the shared internal function
			result = _create_dpr_internal(
				project=project,
				date=date,
				boq_item=dpr_data.get("boq_item"),
				bill_no=dpr_data.get("bill_no"),
				project_sites=dpr_data.get("project_sites"),
				remarks=dpr_data.get("remarks"),
				subcontract_cost=flt(dpr_data.get("subcontract_cost")),
				area_covered=flt(dpr_data.get("area_covered")),
				consumed_qty=flt(dpr_data.get("consumed_qty")),
				balance_qty=flt(dpr_data.get("balance_qty")),
				employees=dpr_data.get("employees", []),
				assets=dpr_data.get("assets", []),
				materials=dpr_data.get("materials", []),
				expenses=dpr_data.get("expenses", []),
				overheads=dpr_data.get("overheads", []),
				submit=submit
			)
			
			created_names.append(result["name"])
			if result.get("error"):
				errors.append(_("Row {0} ({1}): Saved as Draft but failed to submit: {2}").format(
					idx + 1, result["name"], result["error"]
				))
			
		except Exception as e:
			frappe.log_error(f"Enhanced Bulk DPR Error Row {idx+1}: {str(e)}")
			errors.append(_("Row {0}: {1}").format(idx + 1, str(e)))
			
	return {
		"created_count": len(created_names),
		"created_names": created_names,
		"errors": errors
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
			CONCAT(i.item_name, ' | Stock: ', FORMAT(b.actual_qty, 2), ' | Value: ', FORMAT(b.valuation_rate, 2)) as item_name,
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


@frappe.whitelist()
def get_warehouse_items_with_stock(warehouse: str) -> list:
	"""
	Returns list of items with actual_qty > 0 in a specific warehouse.
	"""
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
		WHERE b.warehouse = %s
		AND b.actual_qty > 0
		ORDER BY i.item_name
	""", warehouse, as_dict=True)


@frappe.whitelist()
def validate_material_stock(warehouse: str, item_code: str, qty: float) -> dict:
	"""
	Whitelisted API for real-time stock validation.
	Used by the frontend to show warnings during DPR entry.
	
	Returns:
		dict: { "is_valid": bool, "message": str }
	"""
	if not warehouse or not item_code:
		return {"is_valid": True}
	
	actual_qty = frappe.db.get_value(
		"Bin",
		{"warehouse": warehouse, "item_code": item_code},
		"actual_qty"
	) or 0
	
	requested_qty = flt(qty)
	
	if flt(actual_qty) < requested_qty:
		return {
			"is_valid": False,
			"message": _("Insufficient stock for {0} in {1}. Available: {2}, Requested: {3}").format(
				item_code, warehouse, flt(actual_qty), requested_qty
			)
		}
	
	return {"is_valid": True}
@frappe.whitelist()
def get_project_sites_list(project: str) -> list:
	"""Get all sites for a project"""
	return frappe.get_all(
		"Project Sites",
		filters={"project": project},
		fields=["name"]
	)
