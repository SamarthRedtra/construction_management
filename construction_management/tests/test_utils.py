# Copyright (c) 2024, Construction Management
# License: MIT
# Test Utilities for Construction Management Tests

"""
Test Utilities for Construction Management Tests

This module provides common utility functions for creating test data
and cleaning up after tests.
"""

import frappe
from frappe.utils import flt, today, add_days, random_string


def create_test_project(project_name: str) -> str:
	"""
	Create a test project for testing purposes.
	
	Args:
		project_name: Name of the project to create
		
	Returns:
		Project name
	"""
	if frappe.db.exists("Project", project_name):
		return project_name
	
	project = frappe.new_doc("Project")
	project.project_name = project_name
	project.status = "Open"
	project.project_type = "Internal"
	project.expected_start_date = today()
	project.expected_end_date = add_days(today(), 365)
	project.insert(ignore_permissions=True)
	
	return project.name


def create_test_boq_structure(project: str, total_qty: float = 100, rate: float = 50) -> tuple:
	"""
	Create a test BOQ structure with BOQ, Bill, and Item.
	
	Args:
		project: Project name
		total_qty: Total quantity for BOQ item
		rate: Rate for BOQ item
		
	Returns:
		Tuple of (boq_name, bill_name, item_name)
	"""
	# Create BOQ
	boq = frappe.new_doc("BOQ")
	boq.project = project
	boq.boq_name = f"Test BOQ for {project}"
	boq.insert(ignore_permissions=True)
	
	# Create BOQ Bill
	bill = frappe.new_doc("BOQ Bill")
	bill.project = project
	bill.parent_boq = boq.name
	bill.bill_no = f"BILL-{random_string(5)}"
	bill.sequence = 1
	bill.insert(ignore_permissions=True)
	
	# Create BOQ Item
	item = frappe.new_doc("BOQ Item")
	item.project = project
	item.parent_bill = bill.name
	item.description = f"Test BOQ Item for {project}"
	item.total_qty = total_qty
	item.rate = rate
	item.amount = flt(total_qty) * flt(rate)
	item.insert(ignore_permissions=True)
	
	return boq.name, bill.name, item.name


def create_test_employee(employee_id: str, employee_name: str) -> str:
	"""
	Create a test employee for testing purposes.
	
	Args:
		employee_id: Employee ID
		employee_name: Employee name
		
	Returns:
		Employee name
	"""
	if frappe.db.exists("Employee", employee_id):
		return employee_id
	
	employee = frappe.new_doc("Employee")
	employee.employee = employee_id
	employee.employee_name = employee_name
	employee.first_name = employee_name.split()[0]
	employee.last_name = employee_name.split()[-1] if len(employee_name.split()) > 1 else ""
	employee.status = "Active"
	employee.date_of_joining = today()
	employee.insert(ignore_permissions=True)
	
	return employee.name


def create_test_item(item_code: str, item_name: str) -> str:
	"""
	Create a test item for testing purposes.
	
	Args:
		item_code: Item code
		item_name: Item name
		
	Returns:
		Item code
	"""
	if frappe.db.exists("Item", item_code):
		return item_code
	
	item = frappe.new_doc("Item")
	item.item_code = item_code
	item.item_name = item_name
	item.item_group = "All Item Groups"
	item.stock_uom = "Nos"
	item.is_stock_item = 1
	item.valuation_rate = 10
	item.standard_rate = 15
	item.insert(ignore_permissions=True)
	
	return item.name


def create_test_warehouse(warehouse_name: str, project: str = None) -> str:
	"""
	Create a test warehouse for testing purposes.
	
	Args:
		warehouse_name: Warehouse name
		project: Project to link warehouse to (optional)
		
	Returns:
		Warehouse name
	"""
	if frappe.db.exists("Warehouse", warehouse_name):
		return warehouse_name
	
	warehouse = frappe.new_doc("Warehouse")
	warehouse.warehouse_name = warehouse_name
	warehouse.is_group = 0
	if project:
		warehouse.custom_project = project
	warehouse.insert(ignore_permissions=True)
	
	return warehouse.name


def create_test_company(company_name: str, abbreviation: str = None) -> str:
	"""
	Create a test company for testing purposes.
	
	Args:
		company_name: Company name
		abbreviation: Company abbreviation (optional)
		
	Returns:
		Company name
	"""
	if frappe.db.exists("Company", company_name):
		return company_name
	
	company = frappe.new_doc("Company")
	company.company_name = company_name
	company.abbr = abbreviation or company_name[:3].upper()
	company.default_currency = "USD"
	company.country = "United States"
	company.insert(ignore_permissions=True)
	
	return company.name


def cleanup_test_data():
	"""
	Clean up test data created during tests.
	This function removes test records to prevent interference between tests.
	"""
	# Clean up test projects
	test_projects = frappe.get_all(
		"Project",
		filters={"project_name": ["like", "TEST-%"]},
		fields=["name"]
	)
	
	for project in test_projects:
		try:
			# Delete related BOQ Items first
			boq_items = frappe.get_all(
				"BOQ Item",
				filters={"project": project.name},
				fields=["name"]
			)
			for item in boq_items:
				frappe.delete_doc("BOQ Item", item.name, force=True)
			
			# Delete related BOQ Bills
			boq_bills = frappe.get_all(
				"BOQ Bill",
				filters={"project": project.name},
				fields=["name"]
			)
			for bill in boq_bills:
				frappe.delete_doc("BOQ Bill", bill.name, force=True)
			
			# Delete related BOQs
			boqs = frappe.get_all(
				"BOQ",
				filters={"project": project.name},
				fields=["name"]
			)
			for boq in boqs:
				frappe.delete_doc("BOQ", boq.name, force=True)
			
			# Delete project
			frappe.delete_doc("Project", project.name, force=True)
		except:
			pass
	
	# Clean up test employees
	test_employees = frappe.get_all(
		"Employee",
		filters={"employee": ["like", "TEST-EMP-%"]},
		fields=["name"]
	)
	
	for employee in test_employees:
		try:
			frappe.delete_doc("Employee", employee.name, force=True)
		except:
			pass
	
	# Clean up test items
	test_items = frappe.get_all(
		"Item",
		filters={"item_code": ["like", "TEST-%"]},
		fields=["name"]
	)
	
	for item in test_items:
		try:
			frappe.delete_doc("Item", item.name, force=True)
		except:
			pass
	
	# Clean up test warehouses
	test_warehouses = frappe.get_all(
		"Warehouse",
		filters={"warehouse_name": ["like", "TEST-%"]},
		fields=["name"]
	)
	
	for warehouse in test_warehouses:
		try:
			frappe.delete_doc("Warehouse", warehouse.name, force=True)
		except:
			pass
	
	# Clean up test companies
	test_companies = frappe.get_all(
		"Company",
		filters={"company_name": ["like", "TEST-COMP-%"]},
		fields=["name"]
	)
	
	for company in test_companies:
		try:
			frappe.delete_doc("Company", company.name, force=True)
		except:
			pass


def create_boq_item_with_estimates(bill: str, description: str, **estimates) -> str:
	"""
	Create a BOQ Item with estimated costs for testing.
	
	Args:
		bill: BOQ Bill name
		description: Item description
		**estimates: Estimated cost fields (material_cost, labour_cost, etc.)
		
	Returns:
		BOQ Item name
	"""
	# Get project from bill
	project = frappe.db.get_value("BOQ Bill", bill, "project")
	
	item = frappe.new_doc("BOQ Item")
	item.project = project
	item.parent_bill = bill
	item.description = description
	item.total_qty = 100
	item.rate = 50
	item.amount = 5000
	
	# Set estimated costs
	for field, value in estimates.items():
		if hasattr(item, f"estimated_{field}"):
			setattr(item, f"estimated_{field}", value)
	
	item.insert(ignore_permissions=True)
	return item.name


def create_test_bill(project: str, bill_no: str) -> str:
	"""
	Create a test BOQ Bill for testing.
	
	Args:
		project: Project name
		bill_no: Bill number
		
	Returns:
		BOQ Bill name
	"""
	# Create BOQ first if it doesn't exist
	boq_name = f"Test BOQ for {project}"
	if not frappe.db.exists("BOQ", {"project": project}):
		boq = frappe.new_doc("BOQ")
		boq.project = project
		boq.boq_name = boq_name
		boq.insert(ignore_permissions=True)
		boq_name = boq.name
	else:
		boq_name = frappe.db.get_value("BOQ", {"project": project}, "name")
	
	bill = frappe.new_doc("BOQ Bill")
	bill.project = project
	bill.parent_boq = boq_name
	bill.bill_no = bill_no
	bill.sequence = 1
	bill.insert(ignore_permissions=True)
	
	return bill.name