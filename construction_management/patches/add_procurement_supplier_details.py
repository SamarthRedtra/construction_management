"""Add supplier identifiers shown in the Procurement profile dialog."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields({"Supplier": [
		{"fieldname": "custom_trade_licence_no", "label": "Trade Licence No", "fieldtype": "Data",
			"insert_after": "tax_id"},
		{"fieldname": "custom_po_box_no", "label": "PO Box No", "fieldtype": "Data",
			"insert_after": "custom_trade_licence_no"},
	]}, update=True)
	frappe.clear_cache(doctype="Supplier")
