import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	if frappe.db.exists("DocField", {"parent": "BOQ Item", "fieldname": "skip_advance_deduction"}):
		return

	create_custom_fields(
		{
			"BOQ Item": [
				{
					"fieldname": "skip_advance_deduction",
					"label": "Skip Advance Deduction",
					"fieldtype": "Check",
					"default": "0",
					"insert_after": "total_amount",
				}
			]
		},
		update=True,
	)
