# Copyright (c) 2024, Construction Management
# License: MIT

"""
Overtime Cost Allocator

Allocates overtime costs from Salary Slips to projects.

Properties validated:
- Property 19: Overtime Extraction and Allocation
- Property 20: Multi-Project Overtime Proration

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today, get_first_day, get_last_day
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class OvertimeAllocation:
	"""Overtime allocation result"""
	project: str
	amount: float
	hours: float
	percentage: float


def extract_overtime(salary_slip: str) -> float:
	"""
	Extract overtime amount from a Salary Slip.
	
	Property 19: For any submitted Salary Slip with overtime_amount > 0,
	the overtime SHALL be extracted.
	
	Requirements: 10.1
	
	Args:
		salary_slip: Salary Slip name
		
	Returns:
		Overtime amount
	"""
	# Get overtime from salary slip earnings
	overtime_amount = frappe.db.sql("""
		SELECT COALESCE(SUM(sd.amount), 0) as overtime
		FROM `tabSalary Detail` sd
		JOIN `tabSalary Component` sc ON sc.name = sd.salary_component
		WHERE sd.parent = %s
		AND sd.parentfield = 'earnings'
		AND (
			sc.name LIKE '%%Overtime%%'
			OR sc.name LIKE '%%OT%%'
			OR sc.salary_component_abbr LIKE '%%OT%%'
		)
	""", salary_slip)[0][0]
	
	return flt(overtime_amount)


def get_project_hours(employee: str, start_date: str, end_date: str) -> Dict[str, float]:
	"""
	Get hours worked per project for an employee in a period.
	
	Requirements: 10.2
	
	Args:
		employee: Employee name
		start_date: Period start date
		end_date: Period end date
		
	Returns:
		Dict mapping project to hours worked
	"""
	# Get hours from DPR entries
	dpr_hours = frappe.db.sql("""
		SELECT 
			dpr.project,
			COALESCE(SUM(de.hours), 0) as hours
		FROM `tabDaily Progress Record` dpr
		JOIN `tabDPR Employee` de ON de.parent = dpr.name
		WHERE de.employee = %s
		AND dpr.date BETWEEN %s AND %s
		AND dpr.docstatus = 1
		GROUP BY dpr.project
	""", (employee, start_date, end_date), as_dict=True)
	
	project_hours = {}
	for row in dpr_hours:
		if row.project:
			project_hours[row.project] = flt(row.hours)
	
	# Also check Timesheet if available
	if frappe.db.exists("DocType", "Timesheet"):
		timesheet_hours = frappe.db.sql("""
			SELECT 
				td.project,
				COALESCE(SUM(td.hours), 0) as hours
			FROM `tabTimesheet` ts
			JOIN `tabTimesheet Detail` td ON td.parent = ts.name
			WHERE ts.employee = %s
			AND td.from_time >= %s
			AND td.to_time <= %s
			AND ts.docstatus = 1
			GROUP BY td.project
		""", (employee, start_date, end_date), as_dict=True)
		
		for row in timesheet_hours:
			if row.project:
				project_hours[row.project] = project_hours.get(row.project, 0) + flt(row.hours)
	
	return project_hours


def allocate_overtime(
	employee: str, 
	overtime_amount: float, 
	start_date: str, 
	end_date: str,
	salary_slip: str = None
) -> List[OvertimeAllocation]:
	"""
	Allocate overtime to projects based on hours worked.
	
	Property 19: Overtime SHALL be allocated to the employee's assigned project(s)
	as a Project Expense with category "Overtime".
	
	Property 20: For any employee working on multiple projects, overtime SHALL be
	prorated such that project_overtime = total_overtime × (project_hours / total_hours)
	
	Requirements: 10.2, 10.3, 10.5
	
	Args:
		employee: Employee name
		overtime_amount: Total overtime amount
		start_date: Period start date
		end_date: Period end date
		salary_slip: Optional salary slip reference
		
	Returns:
		List of OvertimeAllocation objects
	"""
	if flt(overtime_amount) <= 0:
		return []
	
	# Get hours per project
	project_hours = get_project_hours(employee, start_date, end_date)
	
	if not project_hours:
		# No project hours found, try to get default project from employee
		default_project = frappe.db.get_value("Employee", employee, "project")
		if default_project:
			project_hours = {default_project: 1}  # Assign 100% to default project
		else:
			return []  # No project to allocate to
	
	# Calculate total hours
	total_hours = sum(project_hours.values())
	
	if total_hours <= 0:
		return []
	
	# Allocate overtime proportionally
	allocations = []
	for project, hours in project_hours.items():
		percentage = (hours / total_hours) * 100
		amount = flt(overtime_amount) * (hours / total_hours)
		
		allocation = OvertimeAllocation(
			project=project,
			amount=amount,
			hours=hours,
			percentage=percentage
		)
		allocations.append(allocation)
		
		# Create project expense entry
		create_project_expense(
			project=project,
			amount=amount,
			category="Overtime",
			employee=employee,
			salary_slip=salary_slip,
			posting_date=end_date
		)
	
	return allocations


def create_project_expense(
	project: str,
	amount: float,
	category: str,
	employee: str = None,
	salary_slip: str = None,
	posting_date: str = None
) -> Optional[str]:
	"""
	Create a Project Expense entry for overtime.
	
	Requirements: 10.3, 10.4
	
	Args:
		project: Project name
		amount: Expense amount
		category: Expense category (e.g., "Overtime")
		employee: Employee name
		salary_slip: Salary Slip reference
		posting_date: Posting date
		
	Returns:
		Created expense name or None
	"""
	if flt(amount) <= 0:
		return None
	
	# Check if Project Expense doctype exists
	# If not, we'll create a Journal Entry instead
	if frappe.db.exists("DocType", "Project Expense"):
		try:
			expense = frappe.new_doc("Project Expense")
			expense.project = project
			expense.expense_date = posting_date or today()
			expense.expense_type = category
			expense.amount = flt(amount)
			expense.description = f"Overtime allocation from Salary Slip {salary_slip}" if salary_slip else f"Overtime for {employee}"
			
			if hasattr(expense, "employee"):
				expense.employee = employee
			if hasattr(expense, "salary_slip"):
				expense.salary_slip = salary_slip
			
			expense.insert(ignore_permissions=True)
			return expense.name
		except Exception as e:
			frappe.log_error(f"Error creating Project Expense: {str(e)}")
	
	# Fallback: Update project's estimated_costing
	try:
		current_cost = flt(frappe.db.get_value("Project", project, "estimated_costing"))
		frappe.db.set_value("Project", project, "estimated_costing", current_cost + flt(amount))
		
		# Add comment for audit trail
		frappe.get_doc("Project", project).add_comment(
			"Comment",
			text=f"Overtime cost {frappe.format_value(amount, {'fieldtype': 'Currency'})} allocated from {salary_slip or employee}"
		)
		
		return f"Project:{project}"
	except Exception as e:
		frappe.log_error(f"Error updating project cost: {str(e)}")
		return None


@frappe.whitelist()
def process_salary_slip_overtime(salary_slip: str) -> dict:
	"""
	Process overtime from a submitted Salary Slip.
	
	Called from Salary Slip on_submit hook.
	
	Args:
		salary_slip: Salary Slip name
		
	Returns:
		dict with allocation results
	"""
	ss = frappe.get_doc("Salary Slip", salary_slip)
	
	if ss.docstatus != 1:
		return {"error": "Salary Slip must be submitted"}
	
	# Extract overtime
	overtime_amount = extract_overtime(salary_slip)
	
	if flt(overtime_amount) <= 0:
		return {"message": "No overtime found", "overtime_amount": 0}
	
	# Allocate to projects
	allocations = allocate_overtime(
		employee=ss.employee,
		overtime_amount=overtime_amount,
		start_date=ss.start_date,
		end_date=ss.end_date,
		salary_slip=salary_slip
	)
	
	return {
		"overtime_amount": overtime_amount,
		"allocations": [
			{
				"project": a.project,
				"amount": a.amount,
				"hours": a.hours,
				"percentage": a.percentage
			}
			for a in allocations
		]
	}


@frappe.whitelist()
def get_employee_overtime_summary(employee: str, from_date: str = None, to_date: str = None) -> dict:
	"""
	Get overtime summary for an employee.
	
	Args:
		employee: Employee name
		from_date: Optional start date
		to_date: Optional end date
		
	Returns:
		dict with overtime summary
	"""
	conditions = ["ss.employee = %s", "ss.docstatus = 1"]
	params = [employee]
	
	if from_date:
		conditions.append("ss.start_date >= %s")
		params.append(from_date)
	
	if to_date:
		conditions.append("ss.end_date <= %s")
		params.append(to_date)
	
	# Get salary slips with overtime
	salary_slips = frappe.db.sql("""
		SELECT 
			ss.name,
			ss.start_date,
			ss.end_date,
			ss.gross_pay
		FROM `tabSalary Slip` ss
		WHERE {conditions}
		ORDER BY ss.start_date DESC
	""".format(conditions=" AND ".join(conditions)), tuple(params), as_dict=True)
	
	total_overtime = 0
	slip_details = []
	
	for ss in salary_slips:
		overtime = extract_overtime(ss.name)
		if overtime > 0:
			total_overtime += overtime
			slip_details.append({
				"salary_slip": ss.name,
				"period": f"{ss.start_date} to {ss.end_date}",
				"overtime_amount": overtime
			})
	
	return {
		"employee": employee,
		"total_overtime": total_overtime,
		"salary_slips": slip_details
	}
