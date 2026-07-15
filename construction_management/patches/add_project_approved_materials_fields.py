# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute():
	fields = [
		{
			"fieldname": "custom_approved_materials",
			"label": "Approved Materials",
			"fieldtype": "Section Break",
			"insert_after": "custom_payment_terms_html",
			"collapsible": 1,
		},
		{
			"fieldname": "custom_approved_materials_data",
			"label": "Approved Materials Data",
			"fieldtype": "JSON",
			"insert_after": "custom_approved_materials",
			"hidden": 1,
		},
		{
			"fieldname": "custom_approved_materials_html",
			"label": "Approved Materials",
			"fieldtype": "HTML",
			"insert_after": "custom_approved_materials_data",
		},
	]

	for field in fields:
		if not frappe.db.exists("Custom Field", {"dt": "Project", "fieldname": field["fieldname"]}):
			create_custom_field("Project", field)

	_update_field_order()
	frappe.clear_cache(doctype="Project")


def _update_field_order():
	"""Insert approved materials fields after payment terms in form layout."""
	prop_name = "Project-main-field_order"
	current = frappe.db.get_value("Property Setter", prop_name, "value")
	if not current:
		return

	import json

	try:
		order = json.loads(current)
	except Exception:
		return

	insert_block = [
		"custom_approved_materials",
		"custom_approved_materials_data",
		"custom_approved_materials_html",
	]
	for fieldname in insert_block:
		if fieldname in order:
			order.remove(fieldname)

	anchor = "custom_payment_terms_html"
	if anchor in order:
		idx = order.index(anchor) + 1
		for offset, fieldname in enumerate(insert_block):
			order.insert(idx + offset, fieldname)

		frappe.db.set_value("Property Setter", prop_name, "value", json.dumps(order))
