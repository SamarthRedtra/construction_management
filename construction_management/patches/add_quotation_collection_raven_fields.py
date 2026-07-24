# Copyright (c) 2026, Construction Management
# License: MIT

"""Quotation SM editability, TC type, collection overdue, PC certificate date, Raven channel link."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Quotation": [
				{
					"fieldname": "custom_sales_manager_approver",
					"fieldtype": "Link",
					"label": "Sales Manager Approver",
					"options": "User",
					"insert_after": "custom_approval_col_break",
					"read_only": 0,
					"description": "Only this Sales Manager is assigned on submit.",
				},
			],
			"Terms and Conditions": [
				{
					"fieldname": "custom_tc_type",
					"fieldtype": "Select",
					"label": "Terms Type",
					"options": "\nGeneral\nPayment Terms\nExclusion\nValidity",
					"insert_after": "selling",
					"description": "Used to filter templates on Quotation (Payment Terms / Exclusion / Validity).",
				},
			],
			"Project": [
				{
					"fieldname": "custom_collection_overdue_basis",
					"fieldtype": "Select",
					"label": "Collection Overdue Basis",
					"options": "Tax Invoice\nProforma Invoice",
					"default": "Tax Invoice",
					"insert_after": "custom_payment_terms_data",
					"description": "Date source used with overdue days for Collection Manager.",
				},
				{
					"fieldname": "custom_collection_overdue_days",
					"fieldtype": "Int",
					"label": "Collection Overdue Days",
					"insert_after": "custom_collection_overdue_basis",
					"description": "Days after the basis date before a row is overdue. Blank = legacy Tax Invoice due_date.",
				},
				{
					"fieldname": "custom_raven_channel",
					"fieldtype": "Link",
					"label": "Raven Channel",
					"options": "Raven Channel",
					"insert_after": "custom_collection_overdue_days",
					"read_only": 1,
					"description": "Auto-created project communication channel.",
				},
				{
					"fieldname": "custom_raven_communications_html",
					"fieldtype": "HTML",
					"label": "Project Communications",
					"insert_after": "custom_raven_channel",
				},
			],
			"Payment Certificate": [
				{
					"fieldname": "custom_certificate_date",
					"fieldtype": "Date",
					"label": "Certificate Date",
					"insert_after": "posting_date",
					"allow_on_submit": 1,
					"description": "Used as PC Date in Collection Manager when set.",
				},
			],
		},
		update=True,
	)
