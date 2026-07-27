# Copyright (c) 2026, Construction Management
# License: MIT

"""Put Raven Channel + Project Communications HTML in a dedicated Details section."""

from __future__ import annotations

import json

import frappe

from construction_management.patches.project_accounting_tab_layout import PROJECT_FIELD_ORDER
from construction_management.patches.v2_enhancements import create_custom_field_if_not_exists


SECTION_FIELD = "custom_raven_communications_section"
RAVEN_FIELDS = [
	SECTION_FIELD,
	"custom_raven_channel",
	"custom_raven_communications_html",
]


def execute():
	create_custom_field_if_not_exists(
		{
			"dt": "Project",
			"fieldname": SECTION_FIELD,
			"label": "Project Communications",
			"fieldtype": "Section Break",
			"collapsible": 1,
			"insert_after": "site_location",
		}
	)

	_set_insert_after("custom_raven_channel", SECTION_FIELD)
	_set_insert_after("custom_raven_communications_html", "custom_raven_channel")
	_update_field_order()
	frappe.clear_cache(doctype="Project")
	frappe.db.commit()


def _set_insert_after(fieldname: str, insert_after: str) -> None:
	cf_name = frappe.db.get_value(
		"Custom Field", {"dt": "Project", "fieldname": fieldname}, "name"
	)
	if not cf_name:
		return
	frappe.db.set_value(
		"Custom Field",
		cf_name,
		"insert_after",
		insert_after,
		update_modified=False,
	)


def _update_field_order() -> None:
	order = list(PROJECT_FIELD_ORDER)
	for fieldname in RAVEN_FIELDS:
		if fieldname in order:
			order.remove(fieldname)

	# Prefer current live order if property setter already customized.
	prop_name = "Project-main-field_order"
	existing = frappe.db.get_value("Property Setter", prop_name, "value")
	if existing:
		try:
			order = json.loads(existing)
			for fieldname in RAVEN_FIELDS:
				if fieldname in order:
					order.remove(fieldname)
		except Exception:
			pass

	anchor = "site_location"
	if anchor not in order:
		for candidate in ("company", "custom_project_no", "project_name"):
			if candidate in order:
				anchor = candidate
				break
		else:
			return

	idx = order.index(anchor) + 1
	for fieldname in reversed(RAVEN_FIELDS):
		order.insert(idx, fieldname)

	value = json.dumps(order)
	if frappe.db.exists("Property Setter", prop_name):
		frappe.db.set_value("Property Setter", prop_name, "value", value, update_modified=False)
	else:
		frappe.get_doc(
			{
				"doctype": "Property Setter",
				"doc_type": "Project",
				"doctype_or_field": "DocType",
				"property": "field_order",
				"property_type": "Data",
				"value": value,
			}
		).insert(ignore_permissions=True)
