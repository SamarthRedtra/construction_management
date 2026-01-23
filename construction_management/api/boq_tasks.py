# Copyright (c) 2024, Construction Management
# License: MIT

"""
BOQ Task Management API
Handles task creation, tree view, and status updates for BOQ Items
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today


@frappe.whitelist()
def create_boq_item_with_task(
	parent_bill: str,
	description: str,
	unit: str,
	total_qty: float,
	rate: float,
	item_code: str = None,
	label: str = None,
	is_task: int = 0,
	start_date: str = None,
	end_date: str = None,
	estimated_material_cost: float = 0,
	estimated_labour_cost: float = 0,
	estimated_subcontract_cost: float = 0,
	estimated_asset_cost: float = 0,
	estimated_other_cost: float = 0,
	total_estimated_cost: float = 0,
	estimated_material_cost_per_unit: float = 0,
	estimated_labour_cost_per_unit: float = 0,
	estimated_subcontract_cost_per_unit: float = 0,
	estimated_asset_cost_per_unit: float = 0,
	estimated_other_cost_per_unit: float = 0,
	materials: str | list = None
) -> dict:
	"""
	Create a BOQ Item and optionally create a linked Group Task.
	
	Args:
		parent_bill: BOQ Bill name
		description: BOQ Item description
		unit: Unit of measurement
		total_qty: Total quantity
		rate: Rate per unit
		item_code: Optional item code
		label: Optional label
		is_task: Whether to create a linked task (1 or 0)
		start_date: Optional task start date
		end_date: Optional task end date
		estimated_material_cost: Estimated material cost
		estimated_labour_cost: Estimated labour cost
		estimated_subcontract_cost: Estimated subcontract cost
		estimated_asset_cost: Estimated asset cost
		estimated_other_cost: Estimated other costs
		total_estimated_cost: Total estimated cost (when using Total Cost Only mode)
		materials: List of material items [{item_code, qty, rate}]
		
	Returns:
		dict with boq_item and task names
	"""
	import json
	
	# Parse materials if string
	if materials and isinstance(materials, str):
		materials = json.loads(materials)
	
	# Get project from bill
	project = frappe.db.get_value("BOQ Bill", parent_bill, "project")
	
	# Create BOQ Item
	boq_item = frappe.new_doc("BOQ Item")
	boq_item.parent_bill = parent_bill
	boq_item.item_code = item_code
	boq_item.label = label
	boq_item.description = description
	boq_item.unit = unit
	boq_item.total_qty = flt(total_qty)
	boq_item.rate = flt(rate)
	
	# Set unit costs
	boq_item.estimated_material_cost_per_unit = flt(estimated_material_cost_per_unit)
	boq_item.estimated_labour_cost_per_unit = flt(estimated_labour_cost_per_unit)
	boq_item.estimated_subcontract_cost_per_unit = flt(estimated_subcontract_cost_per_unit)
	boq_item.estimated_asset_cost_per_unit = flt(estimated_asset_cost_per_unit)
	boq_item.estimated_other_cost_per_unit = flt(estimated_other_cost_per_unit)
	
	# Add materials if provided and field exists
	if materials and hasattr(boq_item, 'materials'):
		for mat in materials:
			if mat.get("item_code") and flt(mat.get("qty")) > 0:
				boq_item.append("materials", {
					"item_code": mat.get("item_code"),
					"qty": flt(mat.get("qty")),
					"rate": flt(mat.get("rate", 0)),
					"amount": flt(mat.get("qty")) * flt(mat.get("rate", 0))
				})
	
	# Set estimated costs
	# If total_estimated_cost is provided (Total Cost Only mode), use it
	# Otherwise use the breakdown values
	if flt(total_estimated_cost) > 0:
		boq_item.total_estimated_cost = flt(total_estimated_cost)
		# Clear breakdown fields when using total cost only
		boq_item.estimated_material_cost = 0
		boq_item.estimated_labour_cost = 0
		boq_item.estimated_subcontract_cost = 0
		boq_item.estimated_asset_cost = 0
		boq_item.estimated_other_cost = 0
	else:
		boq_item.estimated_material_cost = flt(estimated_material_cost)
		boq_item.estimated_labour_cost = flt(estimated_labour_cost)
		boq_item.estimated_subcontract_cost = flt(estimated_subcontract_cost)
		boq_item.estimated_asset_cost = flt(estimated_asset_cost)
		boq_item.estimated_other_cost = flt(estimated_other_cost)
		# Calculate total from breakdown
		boq_item.total_estimated_cost = (
			flt(estimated_material_cost) + flt(estimated_labour_cost) + 
			flt(estimated_subcontract_cost) + flt(estimated_asset_cost) + 
			flt(estimated_other_cost)
		)
	
	boq_item.insert()
	
	result = {
		"boq_item": boq_item.name,
		"task": None
	}
	
	# Set task-related fields after insert using db.set_value for custom fields
	if int(is_task):
		# Update custom fields for Gantt chart display
		update_fields = {"is_task": 1}
		if start_date:
			update_fields["start_date"] = getdate(start_date)
		if end_date:
			update_fields["end_date"] = getdate(end_date)
		
		# Use db.set_value to update custom fields
		for field, value in update_fields.items():
			frappe.db.set_value("BOQ Item", boq_item.name, field, value, update_modified=False)
		
		frappe.db.commit()
		
		# Create linked task
		task = create_group_task_for_boq_item(
			boq_item_name=boq_item.name,
			project=project,
			description=description,
			start_date=start_date,
			end_date=end_date
		)
		if task:
			result["task"] = task
	
	return result


def create_group_task_for_boq_item(
	boq_item_name: str,
	project: str,
	description: str,
	start_date: str = None,
	end_date: str = None
) -> str:
	"""
	Create a Group Task linked to a BOQ Item.
	
	Args:
		boq_item_name: BOQ Item name
		project: Project name
		description: Task description (from BOQ Item)
		start_date: Optional start date
		end_date: Optional end date
		
	Returns:
		Task name
	"""
	try:
		# Truncate description for task subject
		subject = f"BOQ: {description[:80]}" if description else f"BOQ Item: {boq_item_name}"
		
		task = frappe.new_doc("Task")
		task.subject = subject
		task.project = project
		task.is_group = 1  # Make it a group task (parent task)
		task.status = "Open"
		task.priority = "Medium"
		
		# Set dates if provided
		if start_date:
			task.exp_start_date = getdate(start_date)
		if end_date:
			task.exp_end_date = getdate(end_date)
		
		# Add description with BOQ Item reference
		task.description = f"""
			<p><strong>BOQ Item:</strong> <a href="/app/boq-item/{boq_item_name}">{boq_item_name}</a></p>
			<p><strong>Description:</strong> {description}</p>
		"""
		
		task.flags.ignore_permissions = True
		task.insert()
		
		# Link task to BOQ Item
		frappe.db.set_value("BOQ Item", boq_item_name, "linked_task", task.name)
		
		return task.name
		
	except Exception as e:
		frappe.log_error(f"Error creating task for BOQ Item {boq_item_name}: {str(e)}")
		return None


@frappe.whitelist()
def get_boq_item_tasks(boq_item: str) -> list:
	"""
	Get all tasks linked to a BOQ Item (parent task and children).
	Returns a flat list of tasks for popup display.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		list of task dicts with name, subject, status, dates, progress
	
	Requirements: 5.2
	"""
	# Get the linked parent task
	linked_task = frappe.db.get_value("BOQ Item", boq_item, "linked_task")
	
	if not linked_task:
		return []
	
	# Get all tasks in the tree (parent and children)
	tasks = []
	
	def collect_tasks(task_name):
		"""Recursively collect tasks"""
		task = frappe.get_doc("Task", task_name)
		tasks.append({
			"name": task.name,
			"subject": task.subject,
			"status": task.status,
			"progress": flt(task.progress),
			"priority": task.priority,
			"exp_start_date": str(task.exp_start_date) if task.exp_start_date else None,
			"exp_end_date": str(task.exp_end_date) if task.exp_end_date else None,
			"is_group": task.is_group
		})
		
		# Get child tasks
		child_tasks = frappe.get_all(
			"Task",
			filters={"parent_task": task_name},
			fields=["name"],
			order_by="idx, creation"
		)
		
		for child in child_tasks:
			collect_tasks(child.name)
	
	collect_tasks(linked_task)
	return tasks


@frappe.whitelist()
def get_boq_item_tasks_tree(boq_item: str) -> dict:
	"""
	Get all tasks linked to a BOQ Item as a tree structure.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		dict with task tree data
	"""
	# Get the linked parent task
	linked_task = frappe.db.get_value("BOQ Item", boq_item, "linked_task")
	
	boq_item_doc = frappe.get_doc("BOQ Item", boq_item)
	
	result = {
		"boq_item": {
			"name": boq_item_doc.name,
			"description": boq_item_doc.description,
			"project": boq_item_doc.project,
			"total_qty": boq_item_doc.total_qty,
			"unit": boq_item_doc.unit,
			"rate": boq_item_doc.rate,
			"total_amount": boq_item_doc.total_amount
		},
		"linked_task": linked_task,
		"tasks": [],
		"has_tasks": False
	}
	
	if not linked_task:
		return result
	
	# Get parent task
	parent_task = frappe.get_doc("Task", linked_task)
	
	# Build task tree
	task_tree = build_task_tree(linked_task)
	result["tasks"] = task_tree
	result["has_tasks"] = True
	result["parent_task"] = {
		"name": parent_task.name,
		"subject": parent_task.subject,
		"status": parent_task.status,
		"progress": flt(parent_task.progress),
		"exp_start_date": str(parent_task.exp_start_date) if parent_task.exp_start_date else None,
		"exp_end_date": str(parent_task.exp_end_date) if parent_task.exp_end_date else None,
		"is_group": parent_task.is_group
	}
	
	return result


def build_task_tree(parent_task: str, level: int = 0) -> list:
	"""
	Recursively build task tree starting from parent task.
	
	Args:
		parent_task: Parent task name
		level: Current nesting level
		
	Returns:
		List of task dicts with children
	"""
	tasks = []
	
	# Get parent task details
	parent = frappe.get_doc("Task", parent_task)
	
	task_data = {
		"name": parent.name,
		"subject": parent.subject,
		"status": parent.status,
		"progress": flt(parent.progress),
		"priority": parent.priority,
		"exp_start_date": str(parent.exp_start_date) if parent.exp_start_date else None,
		"exp_end_date": str(parent.exp_end_date) if parent.exp_end_date else None,
		"is_group": parent.is_group,
		"level": level,
		"children": []
	}
	
	# Get child tasks
	child_tasks = frappe.get_all(
		"Task",
		filters={"parent_task": parent_task},
		fields=["name"],
		order_by="idx, creation"
	)
	
	for child in child_tasks:
		child_tree = build_task_tree(child.name, level + 1)
		task_data["children"].extend(child_tree)
	
	tasks.append(task_data)
	return tasks


@frappe.whitelist()
def create_child_task(
	parent_task: str,
	subject: str,
	project: str = None,
	start_date: str = None,
	end_date: str = None,
	assigned_to: str = None
) -> dict:
	"""
	Create a child task under a parent task.
	
	Args:
		parent_task: Parent task name
		subject: Task subject
		project: Project name (optional, will inherit from parent)
		start_date: Optional start date
		end_date: Optional end date
		assigned_to: Optional user to assign
		
	Returns:
		dict with task details
	"""
	# Get parent task to inherit project
	parent = frappe.get_doc("Task", parent_task)
	
	task = frappe.new_doc("Task")
	task.subject = subject
	task.parent_task = parent_task
	task.project = project or parent.project
	task.status = "Open"
	task.priority = "Medium"
	
	if start_date:
		task.exp_start_date = getdate(start_date)
	if end_date:
		task.exp_end_date = getdate(end_date)
	
	task.flags.ignore_permissions = True
	task.insert()
	
	# Assign to user if specified
	if assigned_to:
		frappe.share.add("Task", task.name, assigned_to, write=1)
	
	return {
		"name": task.name,
		"subject": task.subject,
		"status": task.status,
		"parent_task": task.parent_task
	}


@frappe.whitelist()
def update_task_status(task: str, status: str = None, progress: float = None) -> dict:
	"""
	Update task status and/or progress.
	
	Args:
		task: Task name
		status: New status (optional)
		progress: Optional progress percentage (0-100)
		
	Returns:
		dict with updated task details
	"""
	task_doc = frappe.get_doc("Task", task)
	
	# Update status if provided
	if status:
		task_doc.status = status
	
	# Update progress if provided
	if progress is not None:
		task_doc.progress = flt(progress)
		
		# Auto-update status based on progress if status not explicitly set
		if not status:
			if flt(progress) >= 100:
				task_doc.status = "Completed"
				task_doc.progress = 100
			elif flt(progress) > 0 and task_doc.status == "Open":
				task_doc.status = "Working"
	
	# Auto-set progress based on status
	if status == "Completed":
		task_doc.progress = 100
	elif status == "Open":
		task_doc.progress = 0
	elif status == "Cancelled":
		task_doc.progress = 0
	
	task_doc.flags.ignore_permissions = True
	task_doc.save()
	
	return {
		"name": task_doc.name,
		"status": task_doc.status,
		"progress": flt(task_doc.progress)
	}


@frappe.whitelist()
def update_task_details(
	task: str,
	subject: str = None,
	start_date: str = None,
	end_date: str = None,
	priority: str = None
) -> dict:
	"""
	Update task details.
	
	Args:
		task: Task name
		subject: New subject
		start_date: New start date
		end_date: New end date
		priority: New priority
		
	Returns:
		dict with updated task details
	"""
	task_doc = frappe.get_doc("Task", task)
	
	if subject:
		task_doc.subject = subject
	if start_date:
		task_doc.exp_start_date = getdate(start_date)
	if end_date:
		task_doc.exp_end_date = getdate(end_date)
	if priority:
		task_doc.priority = priority
	
	task_doc.flags.ignore_permissions = True
	task_doc.save()
	
	return {
		"name": task_doc.name,
		"subject": task_doc.subject,
		"status": task_doc.status,
		"exp_start_date": str(task_doc.exp_start_date) if task_doc.exp_start_date else None,
		"exp_end_date": str(task_doc.exp_end_date) if task_doc.exp_end_date else None,
		"priority": task_doc.priority
	}


@frappe.whitelist()
def delete_task(task: str) -> dict:
	"""
	Delete a task and its children.
	
	Args:
		task: Task name
		
	Returns:
		dict with success status
	"""
	# Check if this is a linked task from BOQ Item
	boq_item = frappe.db.get_value("BOQ Item", {"linked_task": task}, "name")
	
	# Delete the task
	frappe.delete_doc("Task", task, force=True)
	
	# Clear the link from BOQ Item if it was linked
	if boq_item:
		frappe.db.set_value("BOQ Item", boq_item, "linked_task", None)
	
	return {"success": True}


@frappe.whitelist()
def create_task_for_existing_boq_item(
	boq_item: str,
	start_date: str = None,
	end_date: str = None
) -> dict:
	"""
	Create a task for an existing BOQ Item that doesn't have one.
	
	Args:
		boq_item: BOQ Item name
		start_date: Optional start date
		end_date: Optional end date
		
	Returns:
		dict with task details
	"""
	boq_item_doc = frappe.get_doc("BOQ Item", boq_item)
	
	if boq_item_doc.linked_task:
		frappe.throw(_("This BOQ Item already has a linked task"))
	
	task_name = create_group_task_for_boq_item(
		boq_item_name=boq_item,
		project=boq_item_doc.project,
		description=boq_item_doc.description,
		start_date=start_date,
		end_date=end_date
	)
	
	if task_name:
		return {
			"task": task_name,
			"message": _("Task created successfully")
		}
	else:
		frappe.throw(_("Failed to create task"))
