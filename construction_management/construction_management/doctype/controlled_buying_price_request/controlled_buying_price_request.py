from frappe.model.document import Document
import frappe
from frappe import _


class ControlledBuyingPriceRequest(Document):
	def validate(self):
		if not self.flags.get("controlled_price_request_api"):
			frappe.throw(_("Price requests are managed through Procurement actions only."), frappe.PermissionError)

	def on_trash(self):
		frappe.throw(_("Controlled buying price requests are audit records and cannot be deleted."), frappe.PermissionError)
