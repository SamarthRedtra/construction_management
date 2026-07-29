# Copyright (c) 2026, Construction Management
# License: MIT

"""Allow Purchase Invoice credit_to / expense accounts without leaf Account User Permission blocks."""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
	# Match Sales Invoice.debit_to behaviour
	make_property_setter(
		"Purchase Invoice",
		"credit_to",
		"ignore_user_permissions",
		1,
		"Check",
		validate_fields_for_doctype=False,
	)
	make_property_setter(
		"Purchase Invoice Item",
		"expense_account",
		"ignore_user_permissions",
		1,
		"Check",
		validate_fields_for_doctype=False,
	)
	make_property_setter(
		"Purchase Taxes and Charges",
		"account_head",
		"ignore_user_permissions",
		1,
		"Check",
		validate_fields_for_doctype=False,
	)

	# Purchase Manager often used without Purchase User — grant Account select/read
	_ensure_account_perm("Purchase Manager")
	_ensure_account_perm("Purchase Master Manager")

	frappe.clear_cache(doctype="Purchase Invoice")
	frappe.clear_cache(doctype="Account")


def _ensure_account_perm(role: str):
	if not frappe.db.exists("Role", role):
		return
	exists = frappe.db.exists(
		"Custom DocPerm",
		{"parent": "Account", "role": role, "permlevel": 0},
	)
	if exists:
		frappe.db.set_value(
			"Custom DocPerm",
			exists,
			{"select": 1, "read": 1},
			update_modified=False,
		)
		return

	doc = frappe.get_doc(
		{
			"doctype": "Custom DocPerm",
			"parent": "Account",
			"role": role,
			"permlevel": 0,
			"select": 1,
			"read": 1,
			"write": 0,
			"create": 0,
			"delete": 0,
			"submit": 0,
			"cancel": 0,
			"amend": 0,
			"report": 0,
			"export": 0,
			"import": 0,
			"share": 0,
			"print": 0,
			"email": 0,
		}
	)
	doc.insert(ignore_permissions=True)
