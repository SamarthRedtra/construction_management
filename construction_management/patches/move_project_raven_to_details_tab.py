# Copyright (c) 2026, Construction Management
# License: MIT

"""Move Raven communications panel to Project Details (first tab), before Team Allocation."""

from __future__ import annotations

import json

import frappe

from construction_management.patches.project_accounting_tab_layout import PROJECT_FIELD_ORDER


RAVEN_FIELDS_AFTER = "site_location"

INSERTIONS = [
	"custom_raven_channel",
	"custom_raven_communications_html",
]


def execute():
	_update_custom_field_insert_after()
	_update_field_order()
	frappe.clear_cache(doctype="Project")
	frappe.db.commit()


def _update_custom_field_insert_after():
	# Place Raven channel link + HTML panel on Details, after project warehouse.
	anchors = {
		"custom_raven_channel": RAVEN_FIELDS_AFTER,
		"custom_raven_communications_html": "custom_raven_channel",
	}
	for fieldname, insert_after in anchors.items():
		cf_name = frappe.db.get_value(
			"Custom Field", {"dt": "Project", "fieldname": fieldname}, "name"
		)
		if not cf_name:
			continue
		frappe.db.set_value(
			"Custom Field",
			cf_name,
			"insert_after",
			insert_after,
			update_modified=False,
		)


def _update_field_order():
	order = list(PROJECT_FIELD_ORDER)
	for fieldname in INSERTIONS:
		if fieldname in order:
			order.remove(fieldname)

	anchor = RAVEN_FIELDS_AFTER
	if anchor not in order:
		# Fallbacks if site_location was removed from order on some sites.
		for candidate in ("company", "custom_project_no", "project_name"):
			if candidate in order:
				anchor = candidate
				break
		else:
			return

	idx = order.index(anchor) + 1
	for fieldname in reversed(INSERTIONS):
		order.insert(idx, fieldname)

	prop_name = "Project-main-field_order"
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
