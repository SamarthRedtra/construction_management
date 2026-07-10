# Copyright (c) 2026, Construction Management
# License: MIT

import json

import frappe

from construction_management.patches.v2_enhancements import create_custom_field_if_not_exists

EMIRATES_OPTIONS = (
	"\nDubai\nAbu Dhabi\nSharjah\nAjman\nFujairah\nRas Al Khaimah\nUmm Al Quwain"
)


def execute():
	project_fields = [
		{
			"dt": "Project",
			"fieldname": "custom_emirates",
			"label": "Emirates",
			"fieldtype": "Select",
			"options": EMIRATES_OPTIONS,
			"insert_after": "custom_location",
		},
		{
			"dt": "Project",
			"fieldname": "project_soa_tab",
			"label": "Project SOA",
			"fieldtype": "Tab Break",
			"insert_after": "construction_tab",
		},
		{
			"dt": "Project",
			"fieldname": "project_soa_section",
			"label": "Statement of Account",
			"fieldtype": "Section Break",
			"insert_after": "project_soa_tab",
		},
		{
			"dt": "Project",
			"fieldname": "project_soa_html",
			"label": "Project SOA Dashboard",
			"fieldtype": "HTML",
			"insert_after": "project_soa_section",
			"depends_on": "eval:doc.name",
		},
	]

	boq_fields = [
		{
			"dt": "BOQ Item",
			"fieldname": "custom_skirting",
			"label": "Skirting",
			"fieldtype": "Float",
			"default": "0",
			"insert_after": "total_qty",
		},
	]

	for field_def in project_fields + boq_fields:
		create_custom_field_if_not_exists(field_def)

	_update_project_field_order()
	frappe.db.commit()


def _update_project_field_order():
	"""Insert SOA tab fields after construction_tab in Project field order."""
	meta = frappe.get_meta("Project")
	field_order = [f.fieldname for f in meta.fields]

	insertions = [
		"project_soa_tab",
		"project_soa_section",
		"project_soa_html",
	]
	anchor = "construction_tab"
	if anchor not in field_order:
		return

	idx = field_order.index(anchor) + 1
	for fieldname in reversed(insertions):
		if fieldname in field_order:
			field_order.remove(fieldname)
		field_order.insert(idx, fieldname)

	if "custom_emirates" not in field_order and frappe.db.exists(
		"Custom Field", {"dt": "Project", "fieldname": "custom_emirates"}
	):
		if "custom_location" in field_order:
			loc_idx = field_order.index("custom_location") + 1
			field_order.insert(loc_idx, "custom_emirates")

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
