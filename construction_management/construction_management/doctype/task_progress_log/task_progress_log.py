# Copyright (c) 2026, Construction Management and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, today


def progress_log_name(task: str, log_date) -> str:
	"""Deterministic name from task + log date (must match boq_tasks._progress_log_name)."""
	d = getdate(log_date or today())
	return f"TPL-{task}-{d.strftime('%Y')}-{d.strftime('%m')}-{d.strftime('%d')}"


class TaskProgressLog(Document):
	def autoname(self):
		if not self.task:
			frappe.throw(frappe._("Task is required"))
		self.name = progress_log_name(self.task, self.date)
