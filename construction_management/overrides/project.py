# Copyright (c) 2024, Construction Management
# License: MIT

import frappe


def clear_project_cache(doc, method=None):
	"""Clear cached project document so company changes are picked up immediately."""
	frappe.clear_document_cache("Project", doc.name)


def get_project_contractor_name(project) -> str:
	"""Return contractor/client display name from Customer (contractor = customer)."""
	if isinstance(project, str):
		project = frappe.get_doc("Project", project)

	customer = getattr(project, "customer", None)
	if customer:
		return frappe.db.get_value("Customer", customer, "customer_name") or customer

	contractor = getattr(project, "contractor", None)
	if contractor:
		return frappe.db.get_value("Supplier", contractor, "supplier_name") or contractor

	return ""
