# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, date_diff, getdate


class ResourcePlanner(Document):
	def validate(self):
		self.validate_dates()
		self.calculate_total_hours()
		self.set_calendar_title()
		self.check_employee_availability()
	
	def validate_dates(self):
		"""Validate start and end dates"""
		if self.start_date and self.end_date:
			if getdate(self.end_date) < getdate(self.start_date):
				frappe.throw(_("End Date cannot be before Start Date"))
	
	def calculate_total_hours(self):
		"""Calculate total hours based on date range and hours per day"""
		if self.start_date and self.end_date:
			days = date_diff(self.end_date, self.start_date) + 1
			self.total_hours = flt(days) * flt(self.hours_per_day or 8)
	
	def set_calendar_title(self):
		"""Set calendar title combining employee, project, bill and item info"""
		parts = []
		
		# Employee name
		if self.employee_name:
			parts.append(self.employee_name)
		elif self.employee:
			parts.append(self.employee)
		
		# Project
		if self.project:
			parts.append(f"[{self.project}]")
		
		# Bill No - get the bill_no field value from BOQ Bill
		if self.bill_no:
			bill_no_value = frappe.db.get_value("BOQ Bill", self.bill_no, "bill_no")
			if bill_no_value:
				parts.append(f"Bill: {bill_no_value}")
		
		# BOQ Item - get short description
		if self.boq_item:
			item_desc = frappe.db.get_value("BOQ Item", self.boq_item, "description")
			if item_desc:
				# Truncate to 30 chars
				short_desc = item_desc[:30] + "..." if len(item_desc) > 30 else item_desc
				parts.append(f"Item: {short_desc}")
		
		self.calendar_title = " | ".join(parts) if parts else self.name
	
	def check_employee_availability(self):
		"""Check if employee is already assigned during this period"""
		if not self.employee or not self.start_date or not self.end_date:
			return
		
		# Check for overlapping assignments
		overlapping = frappe.db.sql("""
			SELECT name, project, start_date, end_date
			FROM `tabResource Planner`
			WHERE employee = %s
			AND name != %s
			AND (
				(start_date <= %s AND end_date >= %s)
				OR (start_date <= %s AND end_date >= %s)
				OR (start_date >= %s AND end_date <= %s)
			)
		""", (
			self.employee,
			self.name or "",
			self.start_date, self.start_date,
			self.end_date, self.end_date,
			self.start_date, self.end_date
		), as_dict=True)
		
		if overlapping:
			overlap = overlapping[0]
			frappe.msgprint(
				_("Warning: {0} is already assigned to {1} from {2} to {3}").format(
					self.employee_name or self.employee,
					overlap.project,
					overlap.start_date,
					overlap.end_date
				),
				indicator="orange",
				alert=True
			)



def update_all_calendar_titles():
	"""Update calendar_title for all existing Resource Planner records"""
	records = frappe.get_all("Resource Planner", pluck="name")
	for name in records:
		doc = frappe.get_doc("Resource Planner", name)
		doc.set_calendar_title()
		doc.db_update()
	frappe.db.commit()
