# Copyright (c) 2024, Construction Management
# License: MIT

import frappe


def clear_project_cache(doc, method=None):
	"""
	Clear cached project document so company changes are picked up immediately.
	"""
	frappe.clear_document_cache("Project", doc.name)
