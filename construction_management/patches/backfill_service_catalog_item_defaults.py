# Copyright (c) 2026, Construction Management
# License: MIT

"""Add missing Item Default expense rows so Service catalog items work in every company."""

from __future__ import annotations

import frappe

from construction_management.api.controlled_procurement import (
	SERVICE,
	_ensure_service_item_default_for_company,
)


def execute():
	if not frappe.get_meta("Item").has_field("item_defaults"):
		return
	if not frappe.get_meta("Company").has_field("controlled_service_expense_account"):
		return

	companies = frappe.get_all(
		"Company",
		filters={"controlled_service_expense_account": ["is", "set"]},
		pluck="name",
		limit_page_length=0,
	)
	if not companies:
		print("No companies with controlled_service_expense_account; skip Service Item Default backfill")
		return

	service_items = frappe.get_all(
		"Item",
		filters={
			"disabled": 0,
			"controlled_procurement_catalog": 1,
			"controlled_item_type": SERVICE,
		},
		pluck="name",
		limit_page_length=0,
	)
	if not service_items:
		print("No Service catalog items; skip Item Default backfill")
		return

	added = 0
	for company in companies:
		for item_code in service_items:
			before = frappe.db.exists("Item Default", {"parent": item_code, "company": company})
			_ensure_service_item_default_for_company(item_code, company)
			if not before and frappe.db.exists("Item Default", {"parent": item_code, "company": company}):
				added += 1

	print(f"Service catalog Item Defaults backfilled: {added} row(s) across {len(companies)} company(ies)")
