# Copyright (c) 2026, Construction Management
# License: MIT

"""Reload Sales Order BOQ Progress print HTML into the Print Format record."""

from __future__ import annotations

import os

import frappe


PRINT_FORMAT = "Sales Order BOQ Progress"


def execute():
	html_path = os.path.join(
		frappe.get_module_path("Construction Management", "Print Format", PRINT_FORMAT),
		"sales_order_boq_progress.html",
	)
	if not os.path.exists(html_path):
		return

	with open(html_path) as handle:
		html = handle.read()

	if frappe.db.exists("Print Format", PRINT_FORMAT):
		frappe.db.set_value(
			"Print Format",
			PRINT_FORMAT,
			{
				"html": html,
				"custom_format": 1,
				"print_format_type": "Jinja",
				"print_format_for": "DocType",
				"doc_type": "Sales Order",
				"module": "Construction Management",
			},
			update_modified=False,
		)
	else:
		from frappe.modules.import_file import import_file_by_path

		json_path = os.path.join(os.path.dirname(html_path), "sales_order_boq_progress.json")
		if os.path.exists(json_path):
			import_file_by_path(json_path, force=True)
			frappe.db.set_value("Print Format", PRINT_FORMAT, "html", html, update_modified=False)

	frappe.clear_cache(doctype="Print Format")
