"""Install audit links after the price-request DocType has synced; do not rewrite old rates."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields({"Item Price": [
		{"fieldname": "custom_controlled_price_request", "label": "Approved Price Request", "fieldtype": "Link", "options": "Controlled Buying Price Request", "insert_after": "price_list_rate", "read_only": 1, "no_copy": 1},
		{"fieldname": "custom_controlled_catalog_request", "label": "Approved Catalog Request", "fieldtype": "Link", "options": "Controlled Catalog Request", "insert_after": "custom_controlled_price_request", "read_only": 1, "no_copy": 1},
	]}, update=True)
	frappe.clear_cache(doctype="Item Price")
