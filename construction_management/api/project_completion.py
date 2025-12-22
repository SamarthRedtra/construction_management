# Copyright (c) 2024, Construction Management
# License: MIT

"""
Project Completion API
Calculates project completion based on BOQ billing status
"""

import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def calculate_project_completion(project: str) -> dict:
	"""
	Calculate project completion percentage based on fully billed BOQ Bills.
	
	Logic: If there are N bills, each bill represents 100/N % of completion.
	A bill is considered complete when all its items are 100% billed.
	
	Args:
		project: Project name
		
	Returns:
		dict with completion details
	"""
	# Get Project BOQ
	project_boq = frappe.db.get_value("Project BOQ", {"project": project}, "name")
	
	if not project_boq:
		return {
			"completion_percentage": 0,
			"total_bills": 0,
			"completed_bills": 0,
			"bills": []
		}
	
	# Get all bills for this project
	bills = frappe.db.sql("""
		SELECT 
			bb.name,
			bb.bill_no,
			bb.description,
			COUNT(bi.name) as total_items,
			SUM(CASE WHEN bi.billing_status = 'Fully Billed' THEN 1 ELSE 0 END) as fully_billed_items,
			SUM(bi.total_amount) as total_amount,
			SUM(bi.to_date_amount) as billed_amount
		FROM `tabBOQ Bill` bb
		LEFT JOIN `tabBOQ Item` bi ON bi.parent_bill = bb.name
		WHERE bb.project_boq = %s
		GROUP BY bb.name
		ORDER BY bb.sequence, bb.creation
	""", project_boq, as_dict=True)
	
	total_bills = len(bills)
	completed_bills = 0
	bill_details = []
	
	for bill in bills:
		# A bill is complete when all items are fully billed
		is_complete = (bill.total_items > 0 and 
					   bill.fully_billed_items == bill.total_items)
		
		if is_complete:
			completed_bills += 1
		
		# Calculate bill-level completion percentage
		bill_completion = 0
		if bill.total_amount and bill.total_amount > 0:
			bill_completion = (flt(bill.billed_amount) / flt(bill.total_amount)) * 100
		
		bill_details.append({
			"name": bill.name,
			"bill_no": bill.bill_no,
			"description": bill.description,
			"total_items": bill.total_items or 0,
			"fully_billed_items": bill.fully_billed_items or 0,
			"total_amount": flt(bill.total_amount),
			"billed_amount": flt(bill.billed_amount),
			"is_complete": is_complete,
			"completion_percentage": round(bill_completion, 2)
		})
	
	# Calculate overall completion
	completion_percentage = 0
	if total_bills > 0:
		completion_percentage = (completed_bills / total_bills) * 100
	
	return {
		"completion_percentage": round(completion_percentage, 2),
		"total_bills": total_bills,
		"completed_bills": completed_bills,
		"bills": bill_details
	}


@frappe.whitelist()
def update_project_completion(project: str) -> dict:
	"""
	Update the project's percent_complete field based on BOQ billing.
	
	Args:
		project: Project name
		
	Returns:
		dict with updated completion percentage
	"""
	completion_data = calculate_project_completion(project)
	
	# Update project's percent_complete field
	frappe.db.set_value(
		"Project", 
		project, 
		"percent_complete", 
		completion_data["completion_percentage"]
	)
	
	return completion_data


def on_invoice_submit(doc, method):
	"""
	Hook to update project completion when a Sales Invoice is submitted.
	Called from hooks.py
	"""
	if doc.project:
		# Check if project has progressive BOQ enabled
		enable_boq = frappe.db.get_value("Project", doc.project, "enable_progressive_boq")
		if enable_boq:
			update_project_completion(doc.project)


def on_invoice_cancel(doc, method):
	"""
	Hook to update project completion when a Sales Invoice is cancelled.
	Called from hooks.py
	"""
	if doc.project:
		# Check if project has progressive BOQ enabled
		enable_boq = frappe.db.get_value("Project", doc.project, "enable_progressive_boq")
		if enable_boq:
			update_project_completion(doc.project)


@frappe.whitelist()
def get_project_completion_summary(project: str) -> dict:
	"""
	Get a comprehensive summary of project completion including
	billing, costs, and task progress.
	
	Args:
		project: Project name
		
	Returns:
		dict with comprehensive completion data
	"""
	# Get billing-based completion
	billing_completion = calculate_project_completion(project)
	
	# Get project details
	project_doc = frappe.get_doc("Project", project)
	
	# Get task-based completion (if tasks exist)
	task_completion = frappe.db.sql("""
		SELECT 
			COUNT(*) as total_tasks,
			SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) as completed_tasks,
			AVG(progress) as avg_progress
		FROM `tabTask`
		WHERE project = %s
	""", project, as_dict=True)[0]
	
	task_completion_pct = 0
	if task_completion.total_tasks and task_completion.total_tasks > 0:
		task_completion_pct = (task_completion.completed_tasks / task_completion.total_tasks) * 100
	
	# Get cost summary
	cost_summary = frappe.db.sql("""
		SELECT 
			COALESCE(SUM(total_cost), 0) as total_cost,
			COALESCE(SUM(labour_cost), 0) as labour_cost,
			COALESCE(SUM(material_cost), 0) as material_cost,
			COALESCE(SUM(asset_cost), 0) as asset_cost,
			COALESCE(SUM(subcontract_cost), 0) as subcontract_cost,
			COALESCE(SUM(expense_cost), 0) as expense_cost
		FROM `tabDaily Progress Record`
		WHERE project = %s AND docstatus = 1
	""", project, as_dict=True)[0]
	
	return {
		"project": project,
		"project_name": project_doc.project_name,
		"billing_completion": billing_completion,
		"task_completion": {
			"total_tasks": task_completion.total_tasks or 0,
			"completed_tasks": task_completion.completed_tasks or 0,
			"completion_percentage": round(task_completion_pct, 2),
			"avg_progress": round(flt(task_completion.avg_progress), 2)
		},
		"cost_summary": {
			"total_cost": flt(cost_summary.total_cost),
			"labour_cost": flt(cost_summary.labour_cost),
			"material_cost": flt(cost_summary.material_cost),
			"asset_cost": flt(cost_summary.asset_cost),
			"subcontract_cost": flt(cost_summary.subcontract_cost),
			"expense_cost": flt(cost_summary.expense_cost)
		},
		"overall_completion": billing_completion["completion_percentage"]
	}
