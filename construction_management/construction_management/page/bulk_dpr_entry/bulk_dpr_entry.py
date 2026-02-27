import frappe
from frappe import _
from frappe.utils import flt
import json
from construction_management.api.boq_tree import get_item_ledger_values

from construction_management.api.dpr_utils import (
	get_employees_with_rates,
	get_assets_with_rates,
	get_item_valuation_rate,
	_create_dpr_internal
)

@frappe.whitelist()
def get_initial_data(project: str, date: str = None, start: int = 0, page_length: int = 20, company: str = None) -> dict:
	"""
	Fetch initial data for Bulk DPR Entry page.
	"""
	if not date:
		date = frappe.utils.today()
	
	start = int(start or 0)
	page_length = int(page_length or 20)

	if not project:
		return {
			"project": None,
			"boq_items": [],
			"sites": [],
			"employees": get_employees_with_rates(),
			"materials": [],
			"assets": [],
			"overhead_accounts": get_overhead_accounts(company),
			"existing_dprs": [],
			"total_dprs": 0,
			"day_totals": {"labour_cost": 0, "material_cost": 0, "asset_cost": 0, "overhead_cost": 0, "total_cost": 0}
		}

	project_company = frappe.db.get_value("Project", project, "company")
	if company and project_company and project_company != company:
		return {
			"project": None,
			"boq_items": [],
			"sites": [],
			"employees": get_employees_with_rates(),
			"materials": [],
			"assets": [],
			"overhead_accounts": get_overhead_accounts(company),
			"existing_dprs": [],
			"total_dprs": 0,
			"day_totals": {"labour_cost": 0, "material_cost": 0, "asset_cost": 0, "overhead_cost": 0, "total_cost": 0}
		}

	existing_dprs_data = get_existing_dprs(project, date, start, page_length, company)
	
	total_costs = frappe.db.get_value(
		"Daily Progress Record", 
		filters={"project": project, "date": date, "docstatus": ["<", 2]},
		fieldname=[
			{"SUM": "labour_cost", "as": "labour_cost"},
			{"SUM": "material_cost", "as": "material_cost"},
			{"SUM": "asset_cost", "as": "asset_cost"},
			{"SUM": "overhead_cost", "as": "overhead_cost"},
			{"SUM": "total_cost", "as": "total_cost"}
		],
		as_dict=True
	)

	return {
		"project": frappe.get_doc("Project", project).as_dict(),
		"boq_items": get_boq_items_with_balance(project),
		"sites": get_project_sites(project),
		"employees": get_employees_with_rates(),
		"materials": get_materials(project),
		"assets": get_assets_with_rates(project, date),
		"overhead_accounts": get_overhead_accounts(),
		"existing_dprs": existing_dprs_data["dprs"],
		"total_dprs": existing_dprs_data["total"],
		"day_totals": total_costs
	}

def get_boq_items_with_balance(project: str) -> list:
	"""
	Get all BOQ items for the project with their current balance quantity.
	"""
	# Get all BOQ items for the project
	items = frappe.get_all(
		"BOQ Item",
		filters={"project": project},
		fields=["name", "item_code", "description", "unit", "total_qty"],
		order_by="idx"
	)

	result = []
	for item in items:
		# Calculate balance using existing logic
		ledger_vals = get_item_ledger_values(item.name)
		balance = ledger_vals.get("qty", {}).get("balance", 0)
		
		item["balance"] = balance
		result.append(item)
	
	return result

def get_project_sites(project: str) -> list:
	return frappe.get_all(
        "Project Sites", 
        filters={"project": project}, 
        fields=["name", "site_name"]
    )

def get_employees() -> list:
	return frappe.get_all(
        "Employee", 
        filters={"status": "Active"}, 
        fields=["name", "employee_name", "designation"]
    )

def get_overhead_accounts(company: str = None) -> list:
	filters = {
		"root_type": ["in", ["Expense"]],
		"is_group": 0
	}
	if company:
		filters["company"] = company
	return frappe.get_all(
		"Account",
		filters=filters,
		fields=["name", "account_name"]
	)

def get_materials(project: str = None) -> list:
	"""
	Fetch materials. If project is provided, fetch items available in Project's Site Warehouse
	and include their current stock balance.
	"""
	filters = {"disabled": 0, "is_stock_item": 1}
	warehouse = None
	
	if project:
		warehouse = frappe.db.get_value("Project", project, "site_location")
	
	# If we have a warehouse, we can fetch items and their quantities from Bin
	if warehouse:
		# Fetch items with positive stock in the warehouse
		bin_items = frappe.get_all(
			"Bin",
			filters={"warehouse": warehouse, "actual_qty": [">", 0]},
			fields=["item_code", "actual_qty"]
		)
		
		if not bin_items:
			return []
			
		# Map item_code to qty
		qty_map = {d.item_code: d.actual_qty for d in bin_items}
		item_codes = list(qty_map.keys())
		
		# Fetch item details for these codes
		items = frappe.get_all(
			"Item", 
			filters={"name": ["in", item_codes], "disabled": 0}, 
			fields=["name", "item_name", "item_code", "stock_uom", "valuation_rate"]
		)
		
		# Attach balance and ensure valuation rate is captured
		for item in items:
			item["balance"] = qty_map.get(item.name, 0)
			if not item.get("valuation_rate"):
				item["valuation_rate"] = get_item_valuation_rate(item.name, warehouse).get("valuation_rate", 0)
			
		return items

	# If no project or no warehouse, return empty to enforce project warehouse stock
	return []

def get_existing_dprs(project: str, date: str, start: int = 0, page_length: int = 20, company: str = None) -> dict:
	"""
	Fetch existing DPRs with pagination.
	"""
	if company:
		project_company = frappe.db.get_value("Project", project, "company")
		if project_company and project_company != company:
			return {"dprs": [], "total": 0}

	filters = {"project": project, "date": date, "docstatus": ["<", 2]}
	
	total = frappe.db.count("Daily Progress Record", filters)
	
	dprs = frappe.get_all(
		"Daily Progress Record",
		filters=filters,
		fields=[
            "name", "boq_item", "project_sites as site", "remarks as comment", 
            "warehouse", "docstatus", "asset_cost", "labour_cost", 
			"material_cost", "overhead_cost", "expense_cost", "total_cost"
        ],
		start=start,
		page_length=page_length,
		order_by="creation desc"
	)
    
	processed_dprs = []
	for dpr in dprs:
		doc = frappe.get_doc("Daily Progress Record", dpr.name)
		
		# Ensure child tables have necessary fields for SimpleMultiselect
		# and other UI components
		
		processed_employees = []
		for emp in doc.employees:
			processed_employees.append({
				"name": emp.employee,
				"employee": emp.employee,
				"employee_name": frappe.db.get_value("Employee", emp.employee, "employee_name"),
				"hours": emp.hours,
				"rate_per_day": emp.rate_per_day,
				"amount": emp.amount
			})

		processed_materials = []
		for mat in doc.materials:
			processed_materials.append({
				"name": mat.item_code,
				"item_code": mat.item_code,
				"item_name": frappe.db.get_value("Item", mat.item_code, "item_name"),
				"qty": mat.qty,
				"rate": mat.rate,
				"amount": mat.amount,
				"description": "" # We don't have it in child table, but keep it for UI consistency
			})

		processed_overheads = []
		for ovh in doc.overheads:
			processed_overheads.append({
				"name": ovh.account,
				"account": ovh.account,
				"account_name": frappe.db.get_value("Account", ovh.account, "account_name"),
				"description": ovh.description,
				"amount": ovh.amount
			})

		processed_absent = []
		for ae in getattr(doc, "absent_employees", []):
			processed_absent.append({
				"name": ae.employee,
				"employee": ae.employee,
				"employee_name": frappe.db.get_value("Employee", ae.employee, "employee_name")
			})

		processed_dprs.append({
			"name": doc.name,
			"docstatus": doc.docstatus,
			"boq_item": doc.boq_item,
			"site": doc.project_sites,
			"area_covered": doc.area_covered if hasattr(doc, 'area_covered') else 0,
			"remarks": doc.remarks,
			"employees": processed_employees,
			"absent_employees": processed_absent,
			"materials": processed_materials,
			"overheads": processed_overheads,
			"labour_cost": doc.labour_cost,
			"material_cost": doc.material_cost,
			"asset_cost": doc.asset_cost,
			"overhead_cost": doc.overhead_cost,
			"expense_cost": doc.expense_cost,
			"total_cost": doc.total_cost
		})
        
	return {"dprs": processed_dprs, "total": total}

@frappe.whitelist()
def get_workers_from_daily_roster(project: str, date: str) -> list:
	"""
	Fetch all workers from Daily Roster where project and date match.
	Returns list of {employee, employee_name, rate_per_day} for use in DPR labour section.
	"""
	if not project or not date:
		return []

	rosters = frappe.get_all(
		"Daily Roster",
		filters={"project": project, "date": date, "docstatus": ["<", 2]},
		fields=["name"]
	)

	employee_ids = set()
	for r in rosters:
		doc = frappe.get_doc("Daily Roster", r.name)
		for row in getattr(doc, "workers", []):
			if row.employee:
				employee_ids.add(row.employee)

	if not employee_ids:
		return []

	# Enrich with rate_per_day from get_employees_with_rates
	rates_map = {e["name"]: e.get("rate_per_day", 0) for e in get_employees_with_rates() if e["name"] in employee_ids}

	result = []
	for emp_id in employee_ids:
		emp_name = frappe.db.get_value("Employee", emp_id, "employee_name")
		result.append({
			"employee": emp_id,
			"employee_name": emp_name or emp_id,
			"rate_per_day": rates_map.get(emp_id, 0)
		})
	return result


@frappe.whitelist()
def cancel_bulk_dpr(names: list | str):
	if isinstance(names, str):
		names = json.loads(names)
	
	cancelled = []
	for name in names:
		doc = frappe.get_doc("Daily Progress Record", name)
		if doc.docstatus == 1:
			doc.cancel()
			cancelled.append(name)
	
	return cancelled

@frappe.whitelist()
def save_bulk_dpr(project: str, date: str, rows: list | str, submit: bool = False):
	if isinstance(rows, str):
		rows = json.loads(rows)
	
	if isinstance(submit, str):
		submit = json.loads(submit)
        
	project_doc = frappe.get_doc("Project", project)
	default_warehouse = project_doc.site_location
    
	if not default_warehouse:
		default_warehouse = frappe.db.get_value("Warehouse", {"warehouse_name": project})

	saved_names = []
	errors = []
    
	for row in rows:
		if not row.get("name") and not row.get("boq_item"):
			continue
            
		# Use the standardized internal function for creation/submission
		# This ensures consistency with the single DPR entry page
		
		# If updating existing
		if row.get("name"):
			doc = frappe.get_doc("Daily Progress Record", row.get("name"))
			# If it's already submitted, we might need a different handling or skip
			if doc.docstatus > 0:
				continue
		
		# Prepare data for _create_dpr_internal
		# It expects list of dicts for child tables
		
		# Collect all material and overhead remarks to append to main remarks
		# based on user request "put it on new line"
		material_details = []
		for mat in row.get("materials", []):
			if mat.get("description"):
				material_details.append(f"Material {mat.get('item_code')}: {mat.get('description')}")
		
		overhead_details = []
		for ovh in row.get("overheads", []):
			if ovh.get("description"):
				overhead_details.append(f"Overhead {ovh.get('account')}: {ovh.get('description')}")
		
		main_remarks = row.get("remarks") or ""
		if material_details:
			main_remarks += ("\n" if main_remarks else "") + "\n".join(material_details)
		if overhead_details:
			main_remarks += ("\n" if main_remarks else "") + "\n".join(overhead_details)

		dpr_data = {
			"project": project,
			"date": date,
			"boq_item": row.get("boq_item"),
			"project_sites": row.get("site"),
			"warehouse": default_warehouse,
			"remarks": main_remarks,
			"area_covered": row.get("area_covered"),
			"employees": row.get("employees", []),
			"absent_employees": row.get("absent_employees", []),
			"materials": row.get("materials", []),
			"overheads": row.get("overheads", []),
			"submit": submit
		}
		
		# _create_dpr_internal handles both new and existing? Let's check its code.
		# Ah, _create_dpr_internal always calls frappe.new_doc. 
		# So if updating, I should handle it.
		
		if row.get("name"):
			# Update logic (manual update since utils might not support update)
			doc = frappe.get_doc("Daily Progress Record", row.get("name"))
			doc.project = dpr_data["project"]
			doc.date = dpr_data["date"]
			if dpr_data.get("boq_item"):
				doc.boq_item = dpr_data["boq_item"]
				doc.bill_no = frappe.db.get_value("BOQ Item", dpr_data["boq_item"], "parent_bill")
			doc.project_sites = dpr_data["project_sites"]
			doc.warehouse = dpr_data["warehouse"]
			doc.remarks = dpr_data["remarks"]
			doc.area_covered = flt(dpr_data["area_covered"])
			
			doc.employees = []
			for emp in dpr_data["employees"]:
				hours = flt(emp.get("hours", 8))
				rate = flt(emp.get("rate_per_day", 0))
				amount = flt(emp.get("amount", 0)) or (rate * (hours / 8))
				doc.append("employees", {
					"employee": emp.get("employee"),
					"hours": hours,
					"rate_per_day": rate,
					"amount": amount
				})
			
			doc.materials = []
			for mat in dpr_data["materials"]:
				item_code = mat.get("item_code") or mat.get("name")
				rate = flt(mat.get("rate", 0))
				if not rate and item_code:
					rate = flt(get_item_valuation_rate(item_code, dpr_data["warehouse"]).get("valuation_rate", 0))
				qty = flt(mat.get("qty", 0))
				amount = flt(mat.get("amount", 0)) or (rate * qty)
				doc.append("materials", {
					"item_code": item_code,
					"warehouse": dpr_data["warehouse"],
					"qty": qty,
					"rate": rate,
					"amount": amount
				})
			
			doc.overheads = []
			for ovh in dpr_data["overheads"]:
				amount = flt(ovh.get("amount", 0)) or flt(ovh.get("qty", 0))
				doc.append("overheads", {
					"account": ovh.get("account"),
					"description": ovh.get("description", ""),
					"amount": amount
				})

			doc.absent_employees = []
			for ae in dpr_data.get("absent_employees", []):
				emp_id = ae.get("employee") or ae.get("name")
				if emp_id:
					doc.append("absent_employees", {"employee": emp_id})

			doc.save()
			if submit:
				try:
					doc.submit()
				except Exception as e:
					errors.append(f"{doc.name}: {str(e)}")
			saved_names.append(doc.name)
		else:
			# New DPR
			normalized_materials = []
			for mat in dpr_data["materials"]:
				item_code = mat.get("item_code") or mat.get("name")
				rate = flt(mat.get("rate", 0))
				if not rate and item_code:
					rate = flt(get_item_valuation_rate(item_code, dpr_data["warehouse"]).get("valuation_rate", 0))
				qty = flt(mat.get("qty", 0))
				amount = flt(mat.get("amount", 0)) or (rate * qty)
				normalized_materials.append({
					**mat,
					"item_code": item_code,
					"rate": rate,
					"qty": qty,
					"amount": amount
				})
			result = _create_dpr_internal(
				project=project,
				date=date,
				boq_item=dpr_data["boq_item"],
				project_sites=dpr_data["project_sites"],
				warehouse=dpr_data["warehouse"],
				remarks=dpr_data["remarks"],
				area_covered=dpr_data["area_covered"],
				employees=dpr_data["employees"],
				absent_employees=dpr_data.get("absent_employees", []),
				materials=normalized_materials,
				overheads=dpr_data["overheads"],
				submit=submit
			)
			if result.get("name"):
				saved_names.append(result["name"])
			if result.get("error"):
				errors.append(f"{result.get('name')}: {result.get('error')}")

	return {"saved_names": saved_names, "errors": errors}
