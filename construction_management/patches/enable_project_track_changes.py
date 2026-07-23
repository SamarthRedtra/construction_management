# Copyright (c) 2026, Construction Management
# License: MIT

"""Enable DocType-level Track Changes on Project."""

import frappe


def execute():
	existing = frappe.db.exists(
		"Property Setter",
		{"doc_type": "Project", "property": "track_changes", "doctype_or_field": "DocType"},
	)
	if existing:
		frappe.db.set_value("Property Setter", existing, "value", "1")
	else:
		frappe.make_property_setter(
			{
				"doctype": "Project",
				"doctype_or_field": "DocType",
				"property": "track_changes",
				"value": "1",
				"property_type": "Check",
			},
			validate_fields_for_doctype=False,
		)
	frappe.clear_cache(doctype="Project")
