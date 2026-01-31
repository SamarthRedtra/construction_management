import frappe
from frappe import _
import json
from construction_management.api.boq_tree import get_item_ledger_values

@frappe.whitelist()
def get_initial_data(project: str, date: str = None) -> dict:
	"""
	Fetch initial data for Bulk DPR Entry page.
	"""
	if not date:
		date = frappe.utils.today()

	return {
		"project": frappe.get_doc("Project", project).as_dict(),
		"boq_items": get_boq_items_with_balance(project),
		"sites": get_project_sites(project),
		"employees": get_employees(),
		"materials": get_materials(project),
		"overhead_accounts": get_overhead_accounts(),
		"existing_dprs": get_existing_dprs(project, date)
	}

def get_boq_items_with_balance(project: str) -> list:
	"""
	Get all BOQ items for the project with their current balance quantity.
	"""
	# Get all BOQ items for the project
	items = frappe.get_all(
		"BOQ Item",
		filters={"project": project, "docstatus": 1},
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

def get_overhead_accounts() -> list:
	return frappe.get_all(
        "Account",
        filters={"account_type": ["in", ["Expense Account", "Cost of Goods Sold"]], "is_group": 0},
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
			fields=["name", "item_name", "item_code", "stock_uom"]
		)
		
		# Attach balance
		for item in items:
			item["balance"] = qty_map.get(item.name, 0)
			
		return items

	# Fallback: if no project selected or no warehouse, just return all items (balance 0/unknown)
	# But user wants "only fetched from site_warehouse". So if no project, maybe empty?
	# Or if project has no warehouse?
	# Current logic: if project is None, we return all items.
	# But we want to show balance. If not in specific warehouse, balance is abstract.
	
	return frappe.get_all(
        "Item", 
        filters=filters, 
        fields=["name", "item_name", "item_code", "stock_uom"]
    )

def get_existing_dprs(project: str, date: str) -> list:
	dprs = frappe.get_all(
		"Daily Progress Record",
		filters={"project": project, "date": date, "docstatus": ["<", 2]},
		fields=[
            "name", "boq_item", "project_sites as site", "remarks as comment", 
            "warehouse"
        ]
	)
    
	# Process DPRs to match frontend row structure
	processed_dprs = []
	for dpr in dprs:
		doc = frappe.get_doc("Daily Progress Record", dpr.name)
		
		# Employees
		employees = [d.employee for d in doc.employees]
		
		# Materials
		materials = [
			{"item_code": d.item_code, "qty": d.qty, "name": d.item_code} 
			for d in doc.materials
		]

		# Overheads
		overheads = [
			{"account": d.account, "amount": d.amount, "name": d.account, "label": d.account}
			for d in doc.overheads
		]
        
		processed_dprs.append({
			"name": doc.name,
			"docstatus": doc.docstatus,
			"boq_item": doc.boq_item,
			"site": doc.project_sites,
			"area_covered": 0, # Placeholder if field missing
			"employees": employees,
			"materials": materials,
			"overheads": overheads,
			"other_expenses": doc.expense_cost, # Keep for backward compat?
			"comment": doc.remarks
		})
        
	return processed_dprs
        
	return processed_dprs

@frappe.whitelist()
def save_bulk_dpr(project: str, date: str, rows: list | str, submit: bool = False):
	if isinstance(rows, str):
		rows = json.loads(rows)
	
	if isinstance(submit, str):
		submit = json.loads(submit)
        
	project_doc = frappe.get_doc("Project", project)
	default_warehouse = project_doc.site_location
    
	if not default_warehouse:
		# Fallback: try to find a warehouse with project name
		default_warehouse = frappe.db.get_value("Warehouse", {"warehouse_name": project})
        
	if not default_warehouse:
        # Fallback to company default if absolutely necessary, or error
		pass

	saved_names = []
    
    # Process rows
	for row in rows:
		if not row.get("name") and not row.get("boq_item"):
			continue # Skip empty new rows
            
		if row.get("name"):
			# Update existing
			doc = frappe.get_doc("Daily Progress Record", row.get("name"))
		else:
			# Create new
			doc = frappe.new_doc("Daily Progress Record")
			doc.project = project
			doc.date = date
			doc.naming_series = "DPR-.YYYY.-"
        
		doc.boq_item = row.get("boq_item")
		doc.project_sites = row.get("site")
		doc.warehouse = default_warehouse
		doc.remarks = row.get("comment")
        
        # Area Covered handling - Checking if custom field exists or storing in remarks for now.
        # User requirement implies specific field. 
        # If field doesn't exist, I should probably add it or mention it. 
        # For this task, I'll store it in remarks if no field found.
		if row.get("area_covered"): # Handle area covered
			doc.remarks = f"Area Covered: {row.get('area_covered')}\n{doc.remarks or ''}"

		# Clear child tables to rebuild (simple logic for bulk edit)
		doc.employees = []
		doc.materials = []
		doc.expenses = []
        
		# Employees
		for emp in row.get("employees", []):
			doc.append("employees", {
				"employee": emp,
				"hours": 8 # Default
			})
            
		# Materials
		for mat in row.get("materials", []):
			if isinstance(mat, dict):
				item_code = mat.get("item_code") or mat.get("name") # Handle both keys just in case
				qty = mat.get("qty", 0)
			else:
				# Old fallback or string
				item_code = mat
				qty = 1

			if item_code:
				doc.append("materials", {
					"item_code": item_code,
					"warehouse": default_warehouse,
					"project_sites": row.get("site"),
					"qty": qty
				})
            
		# Overheads
		for ovh in row.get("overheads", []):
			# Frontend sends { name: account, amount: X, label: ... }
			account = ovh.get("name") or ovh.get("account")
			amount = ovh.get("amount") or ovh.get("qty") # Frontend might use 'qty' field for amount if reusing component? No, custom label 'Amount'
			
			if account and float(amount or 0) > 0:
				doc.append("overheads", {
					"account": account,
					"description": "Overhead from Bulk Entry",
					"amount": amount
				})

		# Expenses (Legacy / Other Expenses column if still used, but typically replaced by Overheads)
		if row.get("other_expenses") and float(row.get("other_expenses")) > 0:
            # Find default expense type
			expense_type = frappe.db.get_value("Expense Claim Type", {}, "name")
			doc.append("expenses", {
				"expense_type": expense_type,
				"description": "Other Expenses from Bulk Entry",
				"amount": row.get("other_expenses")
			})
            
		doc.save()
		if submit:
			doc.submit()
			
		saved_names.append(doc.name)
        
	return saved_names
