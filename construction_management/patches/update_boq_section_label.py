# Copyright (c) 2024, Construction Management
# License: MIT

import frappe


def execute():
	"""Update the BOQ section label from 'Construction Management' to 'BOQ Management'"""
	
	# Update the custom field label
	if frappe.db.exists("Custom Field", {"dt": "Project", "fieldname": "construction_dashboard_section"}):
		frappe.db.set_value(
			"Custom Field",
			{"dt": "Project", "fieldname": "construction_dashboard_section"},
			{
				"label": "BOQ Management",
				"insert_after": "notes"
			}
		)
		frappe.db.commit()
		print("Updated BOQ section label to 'BOQ Management'")
