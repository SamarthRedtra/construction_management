# Copyright (c) 2026, Construction Management
# License: MIT

"""Move SKD-LPO-00371-1 capitalized tools to POWER TOOLS asset category."""

from __future__ import annotations

import frappe

PO_NAME = "SKD-LPO-00371-1"
OLD_CATEGORY = "Plant & Machinery- Office"
NEW_CATEGORY = "POWER TOOLS"


def execute():
	if not frappe.db.exists("Purchase Order", PO_NAME):
		return
	if not frappe.db.exists("Asset Category", NEW_CATEGORY):
		frappe.throw(f"Asset Category {NEW_CATEGORY} not found")

	item_codes = _get_item_codes()
	if not item_codes:
		return

	company = frappe.db.get_value("Purchase Order", PO_NAME, "company")
	_ensure_category_accounts(company)
	updated = []
	updated.extend(_update_items(item_codes))
	updated.extend(_update_child_rows("Purchase Receipt Item", "purchase_order", PO_NAME))
	updated.extend(_update_child_rows("Purchase Invoice Item", "purchase_order", PO_NAME))
	updated.extend(_update_assets(item_codes))

	if not updated:
		frappe.logger("construction_management").info(
			f"Skip {PO_NAME}: items already on {NEW_CATEGORY}"
		)
		return

	frappe.logger("construction_management").info(
		f"Moved {PO_NAME} asset category to {NEW_CATEGORY}: {len(updated)} rows"
	)


def _get_item_codes() -> list[str]:
	return frappe.get_all(
		"Purchase Order Item",
		filters={"parent": PO_NAME, "docstatus": 1},
		pluck="item_code",
		distinct=True,
	)


def _ensure_category_accounts(company: str) -> None:
	if frappe.db.exists(
		"Asset Category Account",
		{"parent": NEW_CATEGORY, "parenttype": "Asset Category", "company_name": company},
	):
		return

	source = frappe.db.get_value(
		"Asset Category Account",
		{"parent": OLD_CATEGORY, "parenttype": "Asset Category", "company_name": company},
		["fixed_asset_account", "accumulated_depreciation_account", "depreciation_expense_account", "capital_work_in_progress_account"],
		as_dict=True,
	)
	if not source:
		frappe.throw(
			f"No Asset Category Account for {OLD_CATEGORY} / {company} to copy onto {NEW_CATEGORY}"
		)

	category = frappe.get_doc("Asset Category", NEW_CATEGORY)
	category.append(
		"accounts",
		{
			"company_name": company,
			"fixed_asset_account": source.fixed_asset_account,
			"accumulated_depreciation_account": source.accumulated_depreciation_account,
			"depreciation_expense_account": source.depreciation_expense_account,
			"capital_work_in_progress_account": source.capital_work_in_progress_account,
		},
	)
	category.flags.ignore_permissions = True
	category.save()


def _update_items(item_codes: list[str]) -> list[str]:
	updated = []
	for item_code in item_codes:
		if frappe.db.get_value("Item", item_code, "asset_category") == NEW_CATEGORY:
			continue
		frappe.db.set_value(
			"Item",
			item_code,
			"asset_category",
			NEW_CATEGORY,
			update_modified=False,
		)
		updated.append(item_code)
	return updated


def _update_child_rows(doctype: str, link_field: str, parent_name: str) -> list[str]:
	rows = frappe.get_all(
		doctype,
		filters={link_field: parent_name, "asset_category": ["!=", NEW_CATEGORY]},
		pluck="name",
	)
	for name in rows:
		frappe.db.set_value(doctype, name, "asset_category", NEW_CATEGORY, update_modified=False)
	return rows


def _update_assets(item_codes: list[str]) -> list[str]:
	pr_names = frappe.get_all(
		"Purchase Receipt Item",
		filters={"purchase_order": PO_NAME, "docstatus": 1},
		pluck="parent",
		distinct=True,
	)
	if not pr_names:
		return []
	assets = frappe.get_all(
		"Asset",
		filters={
			"purchase_receipt": ["in", pr_names],
			"item_code": ["in", item_codes],
			"asset_category": ["!=", NEW_CATEGORY],
			"docstatus": ["!=", 2],
		},
		pluck="name",
	)
	for name in assets:
		frappe.db.set_value("Asset", name, "asset_category", NEW_CATEGORY, update_modified=False)
	return assets
