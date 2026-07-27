# Copyright (c) 2026, Construction Management
# License: MIT

"""Advance-from-customer liability accounts must not be typed as Receivable.

If account_type=Receivable, Sales Invoice credit GL lines to this account fail with:
'Customer is required against Receivable account Advance from customer - …'
"""

import frappe


def execute():
	accounts = frappe.get_all(
		"Account",
		filters={
			"account_name": "Advance from customer",
			"root_type": "Liability",
			"account_type": "Receivable",
		},
		pluck="name",
	)
	for name in accounts:
		frappe.db.set_value("Account", name, "account_type", "", update_modified=False)
	if accounts:
		frappe.clear_cache(doctype="Account")
