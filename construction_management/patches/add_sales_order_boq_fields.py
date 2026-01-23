import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
	custom_fields = {
		"Sales Order": [
			{
				"fieldname": "custom_retention_amount",
				"label": "Retention Amount",
				"fieldtype": "Currency",
				"insert_after": "base_grand_total",
				"read_only": 1,
				"print_hide": 0,
			},
			{
				"fieldname": "custom_net_amount",
				"label": "Net Amount",
				"fieldtype": "Currency",
				"insert_after": "custom_retention_amount",
				"read_only": 1,
				"print_hide": 0,
			},
			{
				"fieldname": "custom_payment_certificate",
				"label": "Payment Certificate",
				"fieldtype": "Link",
				"options": "Payment Certificate",
				"insert_after": "custom_net_amount",
				"read_only": 1,
				"print_hide": 0,
			},
			{
				"fieldname": "custom_tax_invoice",
				"label": "Tax Invoice",
				"fieldtype": "Link",
				"options": "Sales Invoice",
				"insert_after": "custom_payment_certificate",
				"read_only": 1,
				"print_hide": 0,
			},
		]
	}
	create_custom_fields(custom_fields, ignore_validate=True)

	# Update BOQ Progress Ledger Source field options
	if frappe.db.exists("DocType", "BOQ Progress Ledger"):
		source_field = frappe.get_doc("DocType", "BOQ Progress Ledger").get("fields", {"fieldname": "source"})[0]
		new_options = "Invoice\nProforma\nProforma Reversal\nOrder\nOrder Reversal\nAdjustment\nReversal"
		if source_field.options != new_options:
			source_field.options = new_options
			source_field.parent_doc.save(ignore_permissions=True)
