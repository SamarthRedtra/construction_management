# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe.utils import flt


def on_update(doc, method=None):
	"""Log BOQ sub-task progress when a linked task is updated from the Task form."""
	if frappe.flags.in_import or frappe.flags.in_patch or getattr(frappe.flags, "skip_task_progress_log", False):
		return

	from construction_management.api.boq_tasks import (
		get_boq_item_for_task,
		log_task_progress,
		rollup_boq_progress,
	)

	boq_item = get_boq_item_for_task(doc.name)
	if not boq_item:
		return

	# Only log leaf sub-tasks (not the root group task)
	if frappe.db.get_value("BOQ Item", boq_item, "linked_task") == doc.name:
		return

	progress = flt(doc.progress)
	completed_qty = flt(doc.get("completed_qty")) if hasattr(doc, "completed_qty") else 0.0
	if progress <= 0 and completed_qty <= 0:
		return

	log_task_progress(
		task=doc.name,
		boq_item=boq_item,
		progress=progress,
		completed_qty=completed_qty,
		remarks="Updated from Task form",
	)
	rollup_boq_progress(boq_item)
