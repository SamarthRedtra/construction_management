# Copyright (c) 2026, Construction Management
# License: MIT

import json

import frappe

from construction_management.patches.v2_enhancements import create_custom_field_if_not_exists


def execute():
	project_fields = [
		{
			"dt": "Project",
			"fieldname": "project_commission_tab",
			"label": "Project Commission",
			"fieldtype": "Tab Break",
			"insert_after": "project_soa_tab",
		},
		{
			"dt": "Project",
			"fieldname": "project_commission_section",
			"label": "Commission Statement",
			"fieldtype": "Section Break",
			"insert_after": "project_commission_tab",
		},
		{
			"dt": "Project",
			"fieldname": "project_commission_html",
			"label": "Project Commission Dashboard",
			"fieldtype": "HTML",
			"insert_after": "project_commission_section",
			"depends_on": "eval:doc.name",
		},
	]

	for field_def in project_fields:
		create_custom_field_if_not_exists(field_def)

	_update_project_field_order()
	frappe.db.commit()


def _update_project_field_order():
	meta = frappe.get_meta("Project")
	field_order = [f.fieldname for f in meta.fields]

	insertions = [
		"project_commission_tab",
		"project_commission_section",
		"project_commission_html",
	]
	anchor = "project_soa_tab"
	if anchor not in field_order:
		anchor = "construction_tab"
	if anchor not in field_order:
		return

	idx = field_order.index(anchor) + 1
	for fieldname in reversed(insertions):
		if fieldname in field_order:
			field_order.remove(fieldname)
		field_order.insert(idx, fieldname)

	frappe.make_property_setter(
		{
			"doctype": "Project",
			"fieldname": None,
			"property": "field_order",
			"value": json.dumps(field_order),
			"property_type": "Data",
		},
		validate_fields_for_doctype=False,
	)
