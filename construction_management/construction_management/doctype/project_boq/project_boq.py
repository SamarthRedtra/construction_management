# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ProjectBOQ(Document):
	def validate(self):
		self.validate_status_change()
		self.calculate_totals()
	
	def validate_status_change(self):
		"""Prevent modifications when BOQ is approved"""
		if self.is_new():
			return
		
		old_doc = self.get_doc_before_save()
		if not old_doc:
			return
		
		# If status was Approved and trying to change back to Draft
		if old_doc.status == "Approved" and self.status == "Draft":
			frappe.throw(
				_("Cannot change status from Approved to Draft. Create a new revision instead."),
				title=_("Status Change Not Allowed")
			)
		
		# If status is Closed, no changes allowed
		if old_doc.status == "Closed":
			frappe.throw(
				_("Cannot modify a Closed BOQ"),
				title=_("BOQ Closed")
			)
	
	def calculate_totals(self):
		"""Calculate total BOQ value from all BOQ Items"""
		total = frappe.db.sql("""
			SELECT COALESCE(SUM(bi.total_amount), 0)
			FROM `tabBOQ Item` bi
			JOIN `tabBOQ Bill` bb ON bi.parent_bill = bb.name
			WHERE bb.project_boq = %s
		""", self.name)
		
		self.total_boq_value = flt(total[0][0]) if total else 0
		
		# Calculate Total Estimated BOQ Value (from BOQ Items)
		# Per user request: This field should have the BOQ items sum of total_amount field
		estimated_total = frappe.db.sql("""
			SELECT COALESCE(SUM(bi.total_amount), 0)
			FROM `tabBOQ Item` bi
			JOIN `tabBOQ Bill` bb ON bi.parent_bill = bb.name
			WHERE bb.project_boq = %s
		""", self.name)
		
		self.total_estimated_boq_value = flt(estimated_total[0][0]) if estimated_total else 0

		# Calculate billed and collected from ledger
		billed = frappe.db.sql("""
			SELECT COALESCE(SUM(amount), 0)
			FROM `tabBOQ Progress Ledger`
			WHERE project_boq = %s AND source = 'Invoice'
		""", self.name)
		self.total_billed = flt(billed[0][0]) if billed else 0
		
		# Get collected from paid invoices
		collected = frappe.db.sql("""
			SELECT COALESCE(SUM(si.grand_total), 0)
			FROM `tabSales Invoice` si
			WHERE si.project = %s
			AND si.docstatus = 1
			AND si.status = 'Paid'
			AND EXISTS (
				SELECT 1 FROM `tabSales Invoice Item` sii
				JOIN `tabBOQ Item` bi ON sii.boq_item = bi.name
				JOIN `tabBOQ Bill` bb ON bi.parent_bill = bb.name
				WHERE sii.parent = si.name AND bb.project_boq = %s
			)
		""", (self.project, self.name))
		self.total_collected = flt(collected[0][0]) if collected else 0
		
		self.total_estimated_boq_value = flt(estimated_total[0][0]) if estimated_total else 0
	
	@frappe.whitelist()
	def recalculate_estimated_value(self):
		"""Manually recalculate Total Estimated BOQ Value (button action)"""
		self.calculate_totals()
		self.save()
		return self.total_estimated_boq_value
	
	def on_update(self):
		"""Update project's enable_progressive_boq flag if not set"""
		if not frappe.db.get_value("Project", self.project, "enable_progressive_boq"):
			frappe.db.set_value("Project", self.project, "enable_progressive_boq", 1)
	
	@frappe.whitelist()
	def approve(self):
		"""Approve the BOQ and lock it for editing"""
		if self.status == "Approved":
			frappe.throw(_("BOQ is already approved"))
		
		self.status = "Approved"
		self.save()
		frappe.msgprint(_("BOQ has been approved and locked for editing"))
	
	@frappe.whitelist()
	def close(self):
		"""Close the BOQ"""
		if self.status != "Approved":
			frappe.throw(_("Only approved BOQ can be closed"))
		
		self.status = "Closed"
		self.save()
		frappe.msgprint(_("BOQ has been closed"))


def is_boq_locked(project_boq: str) -> bool:
	"""Check if a Project BOQ is locked (Approved or Closed)"""
	status = frappe.db.get_value("Project BOQ", project_boq, "status")
	return status in ("Approved", "Closed")
