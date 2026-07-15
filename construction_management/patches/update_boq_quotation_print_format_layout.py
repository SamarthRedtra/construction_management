# Copyright (c) 2026, Construction Management
# License: MIT

import os

import frappe


def execute():
	"""Reload BOQ Quotation print HTML into Print Format record."""
	module_path = frappe.get_module_path("Construction Management", "Print Format", "BOQ Quotation")
	html_path = os.path.join(module_path, "boq_quotation.html")
	if not os.path.exists(html_path):
		return

	with open(html_path) as handle:
		html = handle.read()

	if frappe.db.exists("Print Format", "BOQ Quotation"):
		frappe.db.set_value("Print Format", "BOQ Quotation", "html", html, update_modified=False)

	frappe.clear_cache(doctype="Print Format")
