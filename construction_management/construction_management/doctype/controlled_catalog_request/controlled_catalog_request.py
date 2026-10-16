# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document


class ControlledCatalogRequest(Document):
	def validate(self):
		if not getattr(self.flags, "controlled_catalog_request_api", False):
			frappe.throw(_("Create and update catalogue requests through Procurement approval actions."), frappe.PermissionError)
