# Copyright (c) 2026, Construction Management
# License: MIT

"""Custom fields for sales commission accrual JV link and payout Payment Entry flag."""

import frappe

from construction_management.patches.v2_enhancements import create_custom_field_if_not_exists


def execute():
	fields = [
		{
			"dt": "Sales Invoice",
			"fieldname": "custom_commission_accrual_jv",
			"label": "Commission Accrual Journal Entry",
			"fieldtype": "Link",
			"options": "Journal Entry",
			"read_only": 1,
			"hidden": 1,
			"insert_after": "custom_commission_recorded",
			"no_copy": 1,
		},
		{
			"dt": "Payment Entry",
			"fieldname": "custom_is_commission_payout",
			"label": "Is Commission Payout",
			"fieldtype": "Check",
			"default": "0",
			"hidden": 1,
			"insert_after": "remarks",
			"no_copy": 1,
		},
	]

	for field_def in fields:
		create_custom_field_if_not_exists(field_def)

	frappe.clear_cache(doctype="Sales Invoice")
	frappe.clear_cache(doctype="Payment Entry")
	frappe.db.commit()
