# Copyright (c) 2024, Construction Management
# License: MIT

"""
Resource Planner API
Handles resource allocation, calendar views, and availability checks
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, add_days, date_diff, today


@frappe.whitelist()
def get_project_sites(doctype, txt, searchfield, start, page_len, filters):
	"""
	Get warehouses linked to a project for site field.
	(Task 6.1: Resource Planner site field linked to Warehouse)
	"""
	project = filters.get("project")
	if not project:
		return []
	
	return frappe.db.sql("""
		SELECT name, warehouse_name
		FROM `tabWarehouse`
		WHERE custom_project = %s
		AND is_group = 0
		AND (name LIKE %s OR warehouse_name LIKE %s)
		ORDER BY warehouse_name
		LIMIT %s, %s
	""", (project, f"%{txt}%", f"%{txt}%", start, page_len))


@frappe.whitelist()
def get_bills_for_project(doctype, txt, searchfield, start, page_len, filters):
	"""Get BOQ Bills for a project (for Link field query)"""
	project = filters.get("project")
	if not project:
		return []
	
	return frappe.db.sql("""
		SELECT bb.name, bb.bill_no, bb.description
		FROM `tabBOQ Bill` bb
		JOIN `tabProject BOQ` pb ON pb.name = bb.project_boq
		WHERE pb.project = %s
		AND (bb.name LIKE %s OR bb.bill_no LIKE %s)
		ORDER BY bb.sequence
		LIMIT %s, %s
	""", (project, f"%{txt}%", f"%{txt}%", start, page_len))


@frappe.whitelist()
def get_boq_items_for_bill(doctype, txt, searchfield, start, page_len, filters):
	"""Get BOQ Items for a bill (for Link field query)"""
	bill_no = filters.get("bill_no")
	if not bill_no:
		return []
	
	return frappe.db.sql("""
		SELECT name, item_code, description
		FROM `tabBOQ Item`
		WHERE parent_bill = %s
		AND (name LIKE %s OR item_code LIKE %s OR description LIKE %s)
		ORDER BY idx
		LIMIT %s, %s
	""", (bill_no, f"%{txt}%", f"%{txt}%", f"%{txt}%", start, page_len))


@frappe.whitelist()
def get_resource_calendar_data(project: str = None, start_date: str = None, end_date: str = None) -> list:
	"""
	Get resource planner data for calendar view.
	
	Args:
		project: Optional project filter
		start_date: Calendar start date
		end_date: Calendar end date
		
	Returns:
		List of calendar events
	"""
	filters = {}
	if project:
		filters["project"] = project
	
	if start_date and end_date:
		# Get resources that overlap with the date range
		resources = frappe.db.sql("""
			SELECT 
				rp.name,
				rp.project,
				rp.bill_no,
				rp.boq_item,
				rp.employee,
				rp.employee_name,
				rp.designation,
				rp.start_date,
				rp.end_date,
				rp.hours_per_day,
				rp.total_hours,
				rp.notes,
				p.project_name
			FROM `tabResource Planner` rp
			LEFT JOIN `tabProject` p ON p.name = rp.project
			WHERE rp.start_date <= %s AND rp.end_date >= %s
			{project_filter}
			ORDER BY rp.start_date, rp.employee_name
		""".format(
			project_filter="AND rp.project = %(project)s" if project else ""
		), {
			"start_date": end_date,
			"end_date": start_date,
			"project": project
		}, as_dict=True)
	else:
		resources = frappe.get_all(
			"Resource Planner",
			filters=filters,
			fields=[
				"name", "project", "bill_no", "boq_item", "employee",
				"employee_name", "designation", "start_date", "end_date",
				"hours_per_day", "total_hours", "notes"
			],
			order_by="start_date, employee_name"
		)
	
	# Convert to calendar events
	events = []
	colors = [
		"#5e64ff", "#28a745", "#ffc107", "#dc3545", "#17a2b8",
		"#6f42c1", "#fd7e14", "#20c997", "#e83e8c", "#6c757d"
	]
	
	employee_colors = {}
	color_idx = 0
	
	for resource in resources:
		# Assign consistent color per employee
		if resource.employee not in employee_colors:
			employee_colors[resource.employee] = colors[color_idx % len(colors)]
			color_idx += 1
		
		events.append({
			"id": resource.name,
			"title": f"{resource.employee_name or resource.employee}",
			"start": str(resource.start_date),
			"end": str(add_days(resource.end_date, 1)),  # FullCalendar end is exclusive
			"color": employee_colors[resource.employee],
			"extendedProps": {
				"name": resource.name,
				"project": resource.project,
				"project_name": resource.get("project_name", resource.project),
				"bill_no": resource.bill_no,
				"boq_item": resource.boq_item,
				"employee": resource.employee,
				"employee_name": resource.employee_name,
				"designation": resource.designation,
				"hours_per_day": resource.hours_per_day,
				"total_hours": resource.total_hours,
				"notes": resource.notes
			}
		})
	
	return events


@frappe.whitelist()
def get_employee_availability(employee: str, start_date: str, end_date: str) -> dict:
	"""
	Check employee availability for a date range.
	
	Args:
		employee: Employee name
		start_date: Start date
		end_date: End date
		
	Returns:
		dict with availability info
	"""
	# Get existing assignments
	assignments = frappe.db.sql("""
		SELECT 
			name, project, bill_no, start_date, end_date, hours_per_day
		FROM `tabResource Planner`
		WHERE employee = %s
		AND start_date <= %s AND end_date >= %s
		ORDER BY start_date
	""", (employee, end_date, start_date), as_dict=True)
	
	# Calculate busy days
	busy_days = set()
	for assignment in assignments:
		current = getdate(assignment.start_date)
		end = getdate(assignment.end_date)
		while current <= end:
			busy_days.add(str(current))
			current = add_days(current, 1)
	
	# Calculate available days in range
	total_days = date_diff(end_date, start_date) + 1
	busy_count = 0
	current = getdate(start_date)
	end = getdate(end_date)
	while current <= end:
		if str(current) in busy_days:
			busy_count += 1
		current = add_days(current, 1)
	
	available_days = total_days - busy_count
	
	return {
		"employee": employee,
		"start_date": start_date,
		"end_date": end_date,
		"total_days": total_days,
		"busy_days": busy_count,
		"available_days": available_days,
		"is_available": busy_count == 0,
		"assignments": assignments
	}


@frappe.whitelist()
def get_project_resource_summary(project: str, employee: str = None, start_date: str = None, end_date: str = None, page: int = 1, page_size: int = 10) -> dict:
	"""
	Get resource allocation summary for a project with filters and pagination.
	
	Args:
		project: Project name
		employee: Optional employee filter
		start_date: Optional start date filter
		end_date: Optional end date filter
		page: Page number (default 1)
		page_size: Items per page (default 10)
		
	Returns:
		dict with resource summary
	"""
	page = int(page) if page else 1
	page_size = int(page_size) if page_size else 10
	offset = (page - 1) * page_size
	
	# Build filters
	filters = ["rp.project = %(project)s"]
	params = {"project": project, "offset": offset, "page_size": page_size}
	
	if employee:
		filters.append("rp.employee = %(employee)s")
		params["employee"] = employee
	
	if start_date:
		filters.append("rp.start_date >= %(start_date)s")
		params["start_date"] = start_date
	
	if end_date:
		filters.append("rp.end_date <= %(end_date)s")
		params["end_date"] = end_date
	
	where_clause = " AND ".join(filters)
	
	# Get total count
	total_count = frappe.db.sql("""
		SELECT COUNT(DISTINCT rp.employee)
		FROM `tabResource Planner` rp
		WHERE {where_clause}
	""".format(where_clause=where_clause), params)[0][0] or 0
	
	# Get all resource allocations with pagination by employee
	resources = frappe.db.sql("""
		SELECT 
			rp.employee,
			rp.employee_name,
			rp.designation,
			rp.bill_no,
			bb.bill_no as bill_number,
			rp.boq_item,
			bi.description as boq_description,
			rp.start_date,
			rp.end_date,
			rp.hours_per_day,
			rp.total_hours,
			rp.name
		FROM `tabResource Planner` rp
		LEFT JOIN `tabBOQ Bill` bb ON bb.name = rp.bill_no
		LEFT JOIN `tabBOQ Item` bi ON bi.name = rp.boq_item
		WHERE {where_clause}
		ORDER BY rp.start_date DESC, rp.employee_name
	""".format(where_clause=where_clause), params, as_dict=True)
	
	# Group by employee
	by_employee = {}
	for r in resources:
		if r.employee not in by_employee:
			by_employee[r.employee] = {
				"employee": r.employee,
				"employee_name": r.employee_name,
				"designation": r.designation,
				"total_hours": 0,
				"assignments": []
			}
		by_employee[r.employee]["total_hours"] += flt(r.total_hours)
		by_employee[r.employee]["assignments"].append({
			"name": r.name,
			"bill_no": r.bill_number,
			"boq_item": r.boq_item,
			"boq_description": r.boq_description,
			"start_date": str(r.start_date),
			"end_date": str(r.end_date),
			"hours_per_day": r.hours_per_day,
			"total_hours": r.total_hours
		})
	
	# Apply pagination to employees list
	employee_list = list(by_employee.values())
	paginated_employees = employee_list[offset:offset + page_size]
	
	# Calculate totals (from all, not just paginated)
	total_hours = sum(e["total_hours"] for e in employee_list)
	total_employees = len(employee_list)
	
	return {
		"project": project,
		"total_employees": total_employees,
		"total_hours": total_hours,
		"by_employee": paginated_employees,
		"all_resources": resources,
		"pagination": {
			"page": page,
			"page_size": page_size,
			"total_count": total_employees,
			"total_pages": (total_employees + page_size - 1) // page_size if page_size > 0 else 1,
			"has_next": page * page_size < total_employees,
			"has_prev": page > 1
		}
	}


@frappe.whitelist()
def create_resource_allocation(
	project: str,
	employee: str,
	start_date: str,
	end_date: str,
	bill_no: str = None,
	boq_item: str = None,
	hours_per_day: float = 8,
	notes: str = None
) -> dict:
	"""
	Create a new resource allocation.
	
	Args:
		project: Project name
		employee: Employee name
		start_date: Start date
		end_date: End date
		bill_no: Optional BOQ Bill
		boq_item: Optional BOQ Item
		hours_per_day: Hours per day (default 8)
		notes: Optional notes
		
	Returns:
		dict with created resource planner details
	"""
	rp = frappe.new_doc("Resource Planner")
	rp.project = project
	rp.employee = employee
	rp.start_date = start_date
	rp.end_date = end_date
	rp.bill_no = bill_no
	rp.boq_item = boq_item
	rp.hours_per_day = flt(hours_per_day) or 8
	rp.notes = notes
	
	rp.insert()
	
	return {
		"name": rp.name,
		"employee": rp.employee,
		"employee_name": rp.employee_name,
		"start_date": str(rp.start_date),
		"end_date": str(rp.end_date),
		"total_hours": rp.total_hours
	}


@frappe.whitelist()
def create_multiple_resource_allocations(
	project: str,
	employees: str,
	start_date: str,
	end_date: str,
	bill_no: str = None,
	boq_item: str = None,
	hours_per_day: float = 8,
	notes: str = None
) -> dict:
	"""
	Create resource allocations for multiple employees at once.
	
	Args:
		project: Project name
		employees: JSON string of employee names list
		start_date: Start date
		end_date: End date
		bill_no: Optional BOQ Bill
		boq_item: Optional BOQ Item
		hours_per_day: Hours per day (default 8)
		notes: Optional notes
		
	Returns:
		dict with count and created resource planner details
	"""
	import json
	
	# Parse employees from JSON string
	if isinstance(employees, str):
		employees = json.loads(employees)
	
	created = []
	errors = []
	
	for employee in employees:
		try:
			rp = frappe.new_doc("Resource Planner")
			rp.project = project
			rp.employee = employee
			rp.start_date = start_date
			rp.end_date = end_date
			rp.bill_no = bill_no
			rp.boq_item = boq_item
			rp.hours_per_day = flt(hours_per_day) or 8
			rp.notes = notes
			
			rp.insert()
			
			created.append({
				"name": rp.name,
				"employee": rp.employee,
				"employee_name": rp.employee_name
			})
		except Exception as e:
			errors.append({
				"employee": employee,
				"error": str(e)
			})
	
	return {
		"count": len(created),
		"created": created,
		"errors": errors
	}


@frappe.whitelist()
def update_resource_allocation(
	name: str,
	start_date: str = None,
	end_date: str = None,
	hours_per_day: float = None,
	notes: str = None
) -> dict:
	"""
	Update an existing resource allocation.
	
	Args:
		name: Resource Planner name
		start_date: New start date
		end_date: New end date
		hours_per_day: New hours per day
		notes: New notes
		
	Returns:
		dict with updated details
	"""
	rp = frappe.get_doc("Resource Planner", name)
	
	if start_date:
		rp.start_date = start_date
	if end_date:
		rp.end_date = end_date
	if hours_per_day is not None:
		rp.hours_per_day = flt(hours_per_day)
	if notes is not None:
		rp.notes = notes
	
	rp.save()
	
	return {
		"name": rp.name,
		"start_date": str(rp.start_date),
		"end_date": str(rp.end_date),
		"total_hours": rp.total_hours
	}


@frappe.whitelist()
def delete_resource_allocation(name: str) -> dict:
	"""
	Delete a resource allocation.
	
	Args:
		name: Resource Planner name
		
	Returns:
		dict with success status
	"""
	frappe.delete_doc("Resource Planner", name)
	return {"success": True}


@frappe.whitelist()
def get_available_employees(project: str, start_date: str, end_date: str) -> list:
	"""
	Get list of employees available for a date range.
	
	Args:
		project: Project name (for context)
		start_date: Start date
		end_date: End date
		
	Returns:
		List of available employees with their availability status
	"""
	# Get all active employees
	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "employee_name", "designation", "department"]
	)
	
	# Check availability for each
	for emp in employees:
		availability = get_employee_availability(emp.name, start_date, end_date)
		emp["is_available"] = availability["is_available"]
		emp["busy_days"] = availability["busy_days"]
		emp["available_days"] = availability["available_days"]
		emp["assignments"] = availability["assignments"]
	
	# Sort: available first, then by name
	employees.sort(key=lambda x: (not x["is_available"], x["employee_name"]))
	
	return employees
