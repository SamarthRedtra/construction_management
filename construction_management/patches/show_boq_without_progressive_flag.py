# Copyright (c) 2026, Construction Management
# License: MIT

"""Always show BOQ Management on Construction — do not gate on enable_progressive_boq."""

import frappe


BOQ_ALWAYS_VISIBLE_FIELDS = (
	"construction_dashboard_section",
	"construction_dashboard",
)


def execute():
	for fieldname in BOQ_ALWAYS_VISIBLE_FIELDS:
		name = frappe.db.get_value(
			"Custom Field",
			{"dt": "Project", "fieldname": fieldname},
			"name",
		)
		if not name:
			continue
		frappe.db.set_value(
			"Custom Field",
			name,
			{
				"depends_on": "",
				"hidden": 0,
			},
			update_modified=False,
		)

	frappe.clear_cache(doctype="Project")
