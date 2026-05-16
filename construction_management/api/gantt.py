# Copyright (c) 2024, Construction Management
# License: MIT

"""
Gantt Chart API for BOQ Tasks
Provides data for Gantt chart visualization and task date updates.
(Tasks 7.1-7.5: Gantt Chart on BOQ Level)
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, date_diff, add_days


@frappe.whitelist()
def get_boq_gantt_data(project: str = None, project_boq: str = None) -> list:
	"""
	Get BOQ tasks with dates for Gantt chart visualization.
	Shows BOQ Items that have linked tasks with dates, or have custom task fields set.
	(Property 9: Gantt Task Filtering)
	
	Args:
		project: Project name
		project_boq: Optional Project BOQ name for filtering
		
	Returns:
		List of tasks with Gantt-compatible data structure
	"""
	params = []
	
	# Check if custom fields exist
	has_is_task = frappe.db.exists("Custom Field", {"dt": "BOQ Item", "fieldname": "is_task"})
	has_start_date = frappe.db.exists("Custom Field", {"dt": "BOQ Item", "fieldname": "start_date"})
	
	# Build query based on available fields
	if has_is_task and has_start_date:
		# Use custom task fields
		filters = ["bi.is_task = 1", "bi.start_date IS NOT NULL"]
	else:
		# Fallback: use linked_task with Task dates
		filters = ["bi.linked_task IS NOT NULL", "t.exp_start_date IS NOT NULL"]
	
	if project_boq:
		filters.append("bb.project_boq = %s")
		params.append(project_boq)
	elif project:
		filters.append("pb.project = %s")
		params.append(project)
	else:
		return []
	
	# Build SELECT fields based on available columns
	select_fields = """
		bi.name as id,
		bi.item_code,
		bi.description as name,
		bi.total_qty,
		bi.to_date_qty,
		bi.parent_bill,
		bb.bill_no,
		COALESCE(bb.sequence, 0) as bill_sequence,
		bi.linked_task
	"""
	
	if has_start_date:
		select_fields += ", bi.start_date, bi.end_date"
	
	# Add completed_qty if exists
	has_completed_qty = frappe.db.exists("Custom Field", {"dt": "BOQ Item", "fieldname": "completed_qty"})
	if has_completed_qty:
		select_fields += ", bi.completed_qty"
	
	tasks = frappe.db.sql("""
		SELECT 
			{select_fields},
			COALESCE(t.progress, 0) as task_progress,
			t.exp_start_date as task_start,
			t.exp_end_date as task_end
		FROM `tabBOQ Item` bi
		JOIN `tabBOQ Bill` bb ON bb.name = bi.parent_bill
		JOIN `tabProject BOQ` pb ON pb.name = bb.project_boq
		LEFT JOIN `tabTask` t ON t.name = bi.linked_task
		WHERE {filters}
		ORDER BY bb.sequence, bi.name
	""".format(select_fields=select_fields, filters=" AND ".join(filters)), tuple(params), as_dict=True)
	
	# Format for Gantt library
	gantt_tasks = []
	for task in tasks:
		# Calculate progress - use to_date_qty/total_qty or completed_qty/total_qty or Task progress
		total_qty = flt(task.get('total_qty', 0))
		completed_qty = flt(task.get('completed_qty') or task.get('to_date_qty') or 0)
		
		if total_qty > 0 and completed_qty > 0:
			calculated_progress = min(100, (completed_qty / total_qty) * 100)
		else:
			# Fallback to Task progress
			calculated_progress = flt(task.get('task_progress', 0))
		
		# Determine start/end dates - use BOQ Item fields or Task fields
		start_date = task.get('start_date') or task.get('task_start')
		end_date = task.get('end_date') or task.get('task_end')
		
		if not start_date:
			continue  # Skip items without valid start date
		
		# Default end date to start + 1 day if not set
		if not end_date:
			end_date = add_days(start_date, 1)
		
		task_name = task.get('name', '') or task.get('item_code', 'Unknown')
		display_name = f"[{task.bill_no}] {task.item_code}: {task_name[:50]}..." if len(task_name) > 50 else f"[{task.bill_no}] {task.item_code}: {task_name}"
		
		gantt_tasks.append({
			"id": task.id,
			"name": display_name,
			"start": str(start_date),
			"end": str(end_date),
			"progress": calculated_progress,
			"dependencies": "",  # Can be extended for task dependencies
			"custom_class": get_task_class(calculated_progress),
			"bill_no": task.bill_no,
			"item_code": task.item_code,
			"parent_bill": task.parent_bill,
			"linked_task": task.get('linked_task')
		})
	
	return gantt_tasks


@frappe.whitelist()
def get_boq_gantt_hierarchy(project: str = None, project_boq: str = None) -> list:
	"""
	Get BOQ tasks with parent-child hierarchy for nested Gantt display.
	(Task 6.3: Display child tasks as sub-bars)
	
	Args:
		project: Project name
		project_boq: Optional Project BOQ name
		
	Returns:
		List of tasks with hierarchy structure
	"""
	params = []
	
	# Check if custom fields exist
	has_is_task = frappe.db.exists("Custom Field", {"dt": "BOQ Item", "fieldname": "is_task"})
	has_start_date = frappe.db.exists("Custom Field", {"dt": "BOQ Item", "fieldname": "start_date"})
	
	# Build filters based on available fields
	if has_is_task and has_start_date:
		filters = ["bi.is_task = 1", "bi.start_date IS NOT NULL"]
	else:
		# Fallback: use linked_task with Task dates
		filters = ["bi.linked_task IS NOT NULL", "t.exp_start_date IS NOT NULL"]
	
	if project_boq:
		filters.append("bb.project_boq = %s")
		params.append(project_boq)
	elif project:
		filters.append("pb.project = %s")
		params.append(project)
	else:
		return []
	
	# Build SELECT based on available fields
	select_fields = """
		bi.name as id,
		bi.item_code,
		bi.description,
		bi.total_qty,
		bi.to_date_qty,
		bi.parent_bill,
		bb.bill_no,
		COALESCE(bb.sequence, 0) as bill_seq,
		bi.linked_task
	"""
	
	if has_start_date:
		select_fields += ", bi.start_date, bi.end_date"
	
	# Get all BOQ items (parents and children based on bill structure)
	items = frappe.db.sql("""
		SELECT 
			{select_fields},
			t.exp_start_date as task_start,
			t.exp_end_date as task_end,
			COALESCE(t.progress, 0) as task_progress
		FROM `tabBOQ Item` bi
		JOIN `tabBOQ Bill` bb ON bb.name = bi.parent_bill
		JOIN `tabProject BOQ` pb ON pb.name = bb.project_boq
		LEFT JOIN `tabTask` t ON t.name = bi.linked_task
		WHERE {filters}
		ORDER BY bb.sequence, bi.name
	""".format(select_fields=select_fields, filters=" AND ".join(filters)), tuple(params), as_dict=True)
	
	# Group by bill for hierarchy
	by_bill = {}
	for item in items:
		# Determine dates
		start_date = item.get('start_date') or item.get('task_start')
		end_date = item.get('end_date') or item.get('task_end')
		
		if not start_date:
			continue
		
		if not end_date:
			end_date = add_days(start_date, 1)
		
		bill_key = item.parent_bill
		if bill_key not in by_bill:
			by_bill[bill_key] = {
				"id": f"bill_{bill_key}",
				"name": f"Bill: {item.bill_no}",
				"is_parent": True,
				"children": [],
				"start": None,
				"end": None
			}
		
		# Calculate progress
		total_qty = flt(item.get('total_qty', 0))
		completed_qty = flt(item.get('to_date_qty', 0))
		
		if total_qty > 0 and completed_qty > 0:
			progress = min(100, (completed_qty / total_qty) * 100)
		else:
			progress = flt(item.get('task_progress', 0))
		
		desc = item.description or item.item_code or 'Item'
		child = {
			"id": item.id,
			"name": f"{item.item_code}: {desc[:40]}..." if len(desc) > 40 else f"{item.item_code}: {desc}",
			"start": str(start_date),
			"end": str(end_date),
			"progress": progress,
			"parent": f"bill_{bill_key}",
			"custom_class": get_task_class(progress)
		}
		by_bill[bill_key]["children"].append(child)
		
		# Update parent date range
		if by_bill[bill_key]["start"] is None or getdate(start_date) < getdate(by_bill[bill_key]["start"]):
			by_bill[bill_key]["start"] = str(start_date)
		if by_bill[bill_key]["end"] is None or getdate(end_date) > getdate(by_bill[bill_key]["end"]):
			by_bill[bill_key]["end"] = str(end_date)
	
	# Flatten for Gantt library (parents first, then children)
	result = []
	for bill_key, bill_data in by_bill.items():
		# Add parent (bill summary row)
		result.append({
			"id": bill_data["id"],
			"name": bill_data["name"],
			"start": bill_data["start"],
			"end": bill_data["end"],
			"progress": 0,
			"dependencies": "",
			"custom_class": "gantt-bill-bar"
		})
		# Add children
		for child in bill_data["children"]:
			result.append(child)
	
	return result


@frappe.whitelist()
def update_task_dates(boq_item: str, start_date: str, end_date: str) -> dict:
	"""
	Update BOQ Item dates (called when dragging task in Gantt).
	(Task 7.5: Implement task date update on drag)
	
	Args:
		boq_item: BOQ Item name
		start_date: New start date
		end_date: New end date
		
	Returns:
		dict with updated task info
	"""
	if not frappe.db.exists("BOQ Item", boq_item):
		frappe.throw(_("BOQ Item {0} not found").format(boq_item))
	
	doc = frappe.get_doc("BOQ Item", boq_item)
	
	# Check if custom fields exist
	has_start_date = frappe.db.exists("Custom Field", {"dt": "BOQ Item", "fieldname": "start_date"})
	
	old_start = doc.get('start_date') if has_start_date else None
	old_end = doc.get('end_date') if has_start_date else None
	
	# Update BOQ Item dates if custom fields exist
	if has_start_date:
		doc.start_date = getdate(start_date)
		doc.end_date = getdate(end_date)
		doc.save()
	
	# If linked to a Task, update that too (always update Task)
	if doc.linked_task:
		try:
			task = frappe.get_doc("Task", doc.linked_task)
			task.exp_start_date = getdate(start_date)
			task.exp_end_date = getdate(end_date)
			task.save()
		except Exception as e:
			frappe.log_error(f"Error updating linked task: {str(e)}")
	
	return {
		"name": doc.name,
		"item_code": doc.item_code,
		"old_start": str(old_start) if old_start else None,
		"old_end": str(old_end) if old_end else None,
		"new_start": start_date,
		"new_end": end_date,
		"linked_task": doc.linked_task
	}


@frappe.whitelist()
def get_project_boq_summary(project: str) -> dict:
	"""
	Get summary of all Project BOQs for Gantt chart selection.
	
	Args:
		project: Project name
		
	Returns:
		dict with BOQs and task counts
	"""
	# Check if custom fields exist
	has_is_task = frappe.db.exists("Custom Field", {"dt": "BOQ Item", "fieldname": "is_task"})
	has_start_date = frappe.db.exists("Custom Field", {"dt": "BOQ Item", "fieldname": "start_date"})
	
	if has_is_task and has_start_date:
		# Use custom fields
		boqs = frappe.db.sql("""
			SELECT 
				pb.name,
				pb.customer,
				pb.status,
				COUNT(DISTINCT bb.name) as bill_count,
				COUNT(DISTINCT CASE WHEN bi.is_task = 1 AND bi.start_date IS NOT NULL THEN bi.name END) as task_count,
				MIN(bi.start_date) as earliest_start,
				MAX(COALESCE(bi.end_date, bi.start_date)) as latest_end
			FROM `tabProject BOQ` pb
			LEFT JOIN `tabBOQ Bill` bb ON bb.project_boq = pb.name
			LEFT JOIN `tabBOQ Item` bi ON bi.parent_bill = bb.name
			WHERE pb.project = %s
			GROUP BY pb.name
		""", project, as_dict=True)
	else:
		# Fallback: count linked tasks
		boqs = frappe.db.sql("""
			SELECT 
				pb.name,
				pb.customer,
				pb.status,
				COUNT(DISTINCT bb.name) as bill_count,
				COUNT(DISTINCT CASE WHEN bi.linked_task IS NOT NULL AND t.exp_start_date IS NOT NULL THEN bi.name END) as task_count,
				MIN(t.exp_start_date) as earliest_start,
				MAX(COALESCE(t.exp_end_date, t.exp_start_date)) as latest_end
			FROM `tabProject BOQ` pb
			LEFT JOIN `tabBOQ Bill` bb ON bb.project_boq = pb.name
			LEFT JOIN `tabBOQ Item` bi ON bi.parent_bill = bb.name
			LEFT JOIN `tabTask` t ON t.name = bi.linked_task
			WHERE pb.project = %s
			GROUP BY pb.name
		""", project, as_dict=True)
	
	return {
		"project": project,
		"boqs": boqs,
		"total_tasks": sum(b.task_count or 0 for b in boqs)
	}


def get_task_class(progress: float) -> str:
	"""Get CSS class based on progress percentage"""
	if progress >= 100:
		return "gantt-completed"
	elif progress >= 75:
		return "gantt-near-complete"
	elif progress >= 50:
		return "gantt-half-done"
	elif progress >= 25:
		return "gantt-started"
	else:
		return "gantt-not-started"


@frappe.whitelist()
def get_task_progress_timeline(boq_item: str) -> dict:
	"""
	Fetch all tasks for a specific BOQ Item and cross-reference them with their
	Task Progress Log entries to return timeline data for the frontend calendar view.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		dict with tasks and their timeline of progress
	"""
	from construction_management.api.boq_tasks import get_boq_item_tasks_tree

	tree_data = get_boq_item_tasks_tree(boq_item)
	tasks = _flatten_task_tree(tree_data.get("tasks") or [])

	task_names = [t.get("name") for t in tasks if t.get("name")]
	if not task_names:
		return {"tasks": [], "logs": [], "boq_item": tree_data.get("boq_item") or {}}

	logs = frappe.get_all(
		"Task Progress Log",
		filters={"boq_item": boq_item, "task": ["in", task_names]},
		fields=["task", "date", "qty_updated", "progress_percent", "remarks", "user"],
		order_by="date asc",
	)

	for t in tasks:
		if not t.get("is_group"):
			t["completed_qty"] = frappe.db.get_value("Task", t["name"], "completed_qty") or 0.0

	boq_item_doc = tree_data.get("boq_item") or frappe.get_doc("BOQ Item", boq_item).as_dict()
	rollup = _get_boq_daily_rollup(logs)

	return {
		"tasks": tasks,
		"logs": logs,
		"boq_item": boq_item_doc,
		"daily_rollup": rollup,
	}


def _flatten_task_tree(nodes: list, result: list = None) -> list:
	"""Flatten nested task tree nodes into a single list."""
	if result is None:
		result = []

	for node in nodes or []:
		result.append({
			"name": node.get("name"),
			"subject": node.get("subject"),
			"status": node.get("status"),
			"progress": node.get("progress"),
			"completed_qty": node.get("completed_qty"),
			"expected_area": node.get("expected_area"),
			"is_group": node.get("is_group"),
			"exp_start_date": node.get("exp_start_date"),
			"exp_end_date": node.get("exp_end_date"),
		})
		_flatten_task_tree(node.get("children") or [], result)

	return result


def _get_boq_daily_rollup(logs: list) -> list:
	"""Aggregate sub-task logs by date for BOQ-level Gantt summary."""
	by_date = {}
	for log in logs or []:
		date_key = str(log.get("date"))
		if not date_key:
			continue
		entry = by_date.setdefault(date_key, {
			"date": date_key,
			"qty_updated": 0.0,
			"progress_percent": 0.0,
			"task_count": 0,
		})
		entry["qty_updated"] += flt(log.get("qty_updated"))
		entry["progress_percent"] = max(entry["progress_percent"], flt(log.get("progress_percent")))
		entry["task_count"] += 1

	return sorted(by_date.values(), key=lambda row: row["date"])
