# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class SecurityInstrument(Document):
	def validate(self):
		self.validate_amount()
		self.validate_project_context()
		self.validate_reference_no()

	def validate_amount(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be greater than zero"))

	def validate_project_context(self):
		if self.bill_no:
			bill_project = frappe.db.get_value("BOQ Bill", self.bill_no, "project")
			if bill_project != self.project:
				frappe.throw(_("BOQ Bill {0} does not belong to Project {1}").format(self.bill_no, self.project))

		if self.boq_item:
			boq_item_values = frappe.db.get_value(
				"BOQ Item",
				self.boq_item,
				["project", "parent_bill"],
			)
			if not boq_item_values:
				frappe.throw(_("BOQ Item {0} does not exist").format(self.boq_item))
			boq_item_project, parent_bill = boq_item_values
			if boq_item_project != self.project:
				frappe.throw(_("BOQ Item {0} does not belong to Project {1}").format(self.boq_item, self.project))
			if self.bill_no and parent_bill != self.bill_no:
				frappe.throw(_("BOQ Item {0} does not belong to BOQ Bill {1}").format(self.boq_item, self.bill_no))

	def validate_reference_no(self):
		if self.instrument_type == "Security Cheque" and not self.reference_no:
			frappe.throw(_("Cheque / Reference No is mandatory for Security Cheque"))

	def mark_issued(self):
		self.db_set("status", "Issued", update_modified=False)
		if self.payment_entry:
			frappe.db.set_value(
				"Payment Entry",
				self.payment_entry,
				{
					"custom_security_redeemed": 0,
					"custom_security_redeemed_on": None,
				},
				update_modified=False,
			)

	def mark_redeemed(self, redeemed_on=None):
		redeemed_on = redeemed_on or today()
		frappe.db.set_value(
			"Security Instrument",
			self.name,
			{
				"status": "Redeemed",
				"redeemed_on": redeemed_on,
			},
			update_modified=False,
		)
		self.status = "Redeemed"
		self.redeemed_on = redeemed_on
		if self.payment_entry:
			frappe.db.set_value(
				"Payment Entry",
				self.payment_entry,
				{
					"custom_security_redeemed": 1,
					"custom_security_redeemed_on": redeemed_on,
				},
				update_modified=False,
			)

	def mark_cancelled(self):
		self.db_set("status", "Cancelled", update_modified=False)
