# Copyright (c) 2024, Construction Management
# License: MIT
"""
Patch: allow editing of 'is_subcontracted' on submitted Purchase Orders by setting allow_on_submit.
"""

import frappe


def execute():
	property_name = "allow_on_submit"
	doctype = "Purchase Order"
	fieldname = "is_subcontracted"

	if frappe.db.exists(
		"Property Setter",
		{"doc_type": doctype, "property": property_name, "field_name": fieldname},
	):
		return

	frappe.get_doc(
		{
			"doctype": "Property Setter",
			"doc_type": doctype,
			"doctype_or_field": "DocField",
			"field_name": fieldname,
			"property": property_name,
			"value": "1",
			"property_type": "Check",
		}
	).insert(ignore_permissions=True)
