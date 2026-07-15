import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	if frappe.db.exists("DocField", {"parent": "BOQ Item", "fieldname": "pricing_entry_mode"}):
		return

	create_custom_fields(
		{
			"BOQ Item": [
				{
					"fieldname": "pricing_entry_mode",
					"label": "Pricing Entry Mode",
					"fieldtype": "Select",
					"options": "Unit Rate\nLump Sum Total",
					"default": "Unit Rate",
					"insert_after": "section_quantity",
				},
				{
					"fieldname": "lump_sum_total",
					"label": "Lump Sum Total",
					"fieldtype": "Currency",
					"insert_after": "rate",
					"depends_on": "eval:doc.pricing_entry_mode=='Lump Sum Total'",
				},
			]
		},
		update=True,
	)
