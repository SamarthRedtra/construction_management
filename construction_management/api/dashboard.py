# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt, today, add_days


@frappe.whitelist()
def get_project_dashboard(project=None):
	"""Get comprehensive project dashboard data"""
	user = frappe.session.user
	filters = {}
	
	if project:
		filters["project"] = project
	
	# Get projects user has access to
	projects = frappe.get_all("Construction Project", 
		filters=filters if project else {},
		fields=["name", "project_name", "status", "percent_complete", 
				"estimated_cost", "actual_cost", "start_date", "expected_end_date"]
	)
	
	if not projects:
		return {"projects": [], "summary": {}}
	
	project_names = [p.name for p in projects]
	
	# Summary counts
	summary = {
		"total_projects": len(projects),
		"active_projects": len([p for p in projects if p.status == "In Progress"]),
		"pending_mars": frappe.db.count("Material Approval Request", {
			"project": ["in", project_names],
			"status": ["in", ["Submitted", "Under Review"]]
		}),
		"open_ncrs": frappe.db.count("Non Conformance Report", {
			"project": ["in", project_names],
			"status": ["not in", ["Closed"]]
		}),
		"pending_irs": frappe.db.count("Inspection Request", {
			"project": ["in", project_names],
			"status": ["in", ["Submitted", "Scheduled"]]
		}),
		"overdue_tasks": frappe.db.count("Construction Task", {
			"project": ["in", project_names],
			"status": ["not in", ["Completed", "Cancelled"]],
			"due_date": ["<", today()]
		}),
		"total_estimated": sum(flt(p.estimated_cost) for p in projects),
		"total_actual": sum(flt(p.actual_cost) for p in projects)
	}
	
	# Recent activities
	recent_activities = get_recent_activities(project_names)
	
	# Upcoming deadlines
	upcoming_deadlines = get_upcoming_deadlines(project_names)
	
	return {
		"projects": projects,
		"summary": summary,
		"recent_activities": recent_activities,
		"upcoming_deadlines": upcoming_deadlines
	}


def get_recent_activities(project_names, limit=10):
	"""Get recent activities across all doctypes"""
	activities = []
	
	# Recent MARs
	mars = frappe.get_all("Material Approval Request",
		filters={"project": ["in", project_names]},
		fields=["name", "mar_title", "status", "modified", "project"],
		order_by="modified desc",
		limit=5
	)
	for mar in mars:
		activities.append({
			"type": "MAR",
			"name": mar.name,
			"title": mar.mar_title,
			"status": mar.status,
			"project": mar.project,
			"date": mar.modified
		})
	
	# Recent NCRs
	ncrs = frappe.get_all("Non Conformance Report",
		filters={"project": ["in", project_names]},
		fields=["name", "ncr_title", "status", "modified", "project"],
		order_by="modified desc",
		limit=5
	)
	for ncr in ncrs:
		activities.append({
			"type": "NCR",
			"name": ncr.name,
			"title": ncr.ncr_title,
			"status": ncr.status,
			"project": ncr.project,
			"date": ncr.modified
		})
	
	# Sort by date and limit
	activities.sort(key=lambda x: x["date"], reverse=True)
	return activities[:limit]


def get_upcoming_deadlines(project_names, days=7):
	"""Get upcoming deadlines"""
	deadline_date = add_days(today(), days)
	
	deadlines = []
	
	# Tasks due soon
	tasks = frappe.get_all("Construction Task",
		filters={
			"project": ["in", project_names],
			"status": ["not in", ["Completed", "Cancelled"]],
			"due_date": ["<=", deadline_date],
			"due_date": [">=", today()]
		},
		fields=["name", "subject", "due_date", "priority", "project"]
	)
	for task in tasks:
		deadlines.append({
			"type": "Task",
			"name": task.name,
			"title": task.subject,
			"date": task.due_date,
			"priority": task.priority,
			"project": task.project
		})
	
	# IRs scheduled
	irs = frappe.get_all("Inspection Request",
		filters={
			"project": ["in", project_names],
			"status": "Scheduled",
			"scheduled_date": ["<=", deadline_date],
			"scheduled_date": [">=", today()]
		},
		fields=["name", "ir_title", "scheduled_date", "project"]
	)
	for ir in irs:
		deadlines.append({
			"type": "Inspection",
			"name": ir.name,
			"title": ir.ir_title,
			"date": ir.scheduled_date,
			"project": ir.project
		})
	
	deadlines.sort(key=lambda x: x["date"])
	return deadlines


@frappe.whitelist()
def get_financial_summary(project=None):
	"""Get financial summary for projects"""
	filters = {}
	if project:
		filters["project"] = project
	
	# BOQ totals
	boqs = frappe.get_all("BOQ",
		filters=filters,
		fields=["name", "project", "grand_total", "status"]
	)
	
	# IPC totals
	ipcs = frappe.get_all("Interim Payment Certificate",
		filters=filters,
		fields=["name", "project", "gross_amount_current", "net_payable_current", "status"]
	)
	
	# Bid comparison
	bids = frappe.get_all("Bid",
		filters={**filters, "status": ["in", ["Submitted", "Shortlisted", "Awarded"]]},
		fields=["name", "project", "contractor", "grand_total", "status"]
	)
	
	return {
		"boq_total": sum(flt(b.grand_total) for b in boqs),
		"certified_amount": sum(flt(i.gross_amount_current) for i in ipcs),
		"paid_amount": sum(
			flt(i.net_payable_current) 
			for i in ipcs 
			if i.status == "Paid"
		),
		"bid_count": len(bids),
		"lowest_bid": min([b.grand_total for b in bids]) if bids else 0,
		"boqs": boqs,
		"ipcs": ipcs,
		"bids": bids
	}


@frappe.whitelist()
def get_progress_chart_data(project):
	"""Get data for progress charts"""
	# DPR completion over time
	dprs = frappe.get_all("Daily Progress Report",
		filters={"project": project},
		fields=["report_date", "overall_completion_percent"],
		order_by="report_date"
	)
	
	# IPC amounts over time
	ipcs = frappe.get_all("Interim Payment Certificate",
		filters={"project": project},
		fields=["ipc_number", "gross_amount_current", "valuation_period_end"],
		order_by="ipc_number"
	)
	
	return {
		"progress_data": [
			{"date": str(d.report_date), "completion": d.overall_completion_percent}
			for d in dprs
		],
		"payment_data": [
			{"ipc": i.ipc_number, "amount": i.gross_amount_current, "date": str(i.valuation_period_end)}
			for i in ipcs
		]
	}

