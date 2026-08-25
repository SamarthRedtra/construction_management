# Copyright (c) 2026, Construction Management
# License: MIT

"""Capitalize SKD-LPO-00371-1 power tools as fixed assets without cancelling PO/PR."""

from __future__ import annotations

import frappe
from frappe.utils import cint, flt, getdate

PO_NAME = "SKD-LPO-00371-1"
PATCH_JE_REMARK = "construction_management: SKD-LPO-00371-1 fixed asset capitalization"
ASSET_CATEGORY = "POWER TOOLS"
ASSET_NAMING_SERIES = "ACC-ASS-.YYYY.-"
DEFAULT_ASSET_LOCATION = "SKD-50"


def execute():
	if not frappe.db.exists("Purchase Order", PO_NAME):
		return

	pr_name = _get_purchase_receipt_name()
	if not pr_name:
		frappe.logger("construction_management").warning(
			f"Skip {PO_NAME}: no submitted purchase receipt found"
		)
		return

	if _is_fully_capitalized(pr_name):
		frappe.logger("construction_management").info(
			f"Skip {PO_NAME}: fixed asset capitalization already applied"
		)
		return

	pr = frappe.get_doc("Purchase Receipt", pr_name)
	po_items = _get_po_items()
	pr_items = _get_pr_items(pr_name)

	_update_item_masters({row.item_code for row in pr_items})
	_update_purchase_order_items(po_items)
	_update_purchase_receipt_items(pr_items)
	_create_assets(pr, pr_items)
	_create_capitalization_journal_entry(pr, pr_items)

	frappe.db.commit()
	frappe.logger("construction_management").info(
		f"Fixed asset capitalization completed for {PO_NAME} via {pr_name}"
	)


def _prepare_asset_for_submit(asset, posting_date) -> None:
	purchase_date = getdate(posting_date)
	asset.purchase_date = purchase_date
	asset.available_for_use_date = purchase_date
	asset.calculate_depreciation = 1
	asset.set_missing_values()
	for finance_book in asset.get("finance_books") or []:
		finance_book.depreciation_start_date = purchase_date


def _get_purchase_receipt_name() -> str | None:
	rows = frappe.db.sql(
		"""
		SELECT pri.parent
		FROM `tabPurchase Receipt Item` pri
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pri.purchase_order = %s AND pr.docstatus = 1
		LIMIT 1
		""",
		(PO_NAME,),
	)
	return rows[0][0] if rows else None


def _get_po_items() -> list[dict]:
	return frappe.get_all(
		"Purchase Order Item",
		filters={"parent": PO_NAME},
		fields=["name", "item_code"],
	)


def _get_pr_items(pr_name: str) -> list[dict]:
	return frappe.get_all(
		"Purchase Receipt Item",
		filters={"parent": pr_name, "purchase_order": PO_NAME},
		fields=[
			"name",
			"item_code",
			"item_name",
			"qty",
			"rate",
			"valuation_rate",
			"amount",
			"project",
			"cost_center",
			"expense_account",
		],
		order_by="idx asc",
	)


def _is_fully_capitalized(pr_name: str) -> bool:
	po_fixed = frappe.get_all(
		"Purchase Order Item",
		filters={"parent": PO_NAME, "is_fixed_asset": 0},
		pluck="name",
		limit=1,
	)
	if po_fixed:
		return False

	pr_items = _get_pr_items(pr_name)
	for row in pr_items:
		if frappe.db.get_value("Purchase Receipt Item", row.name, "is_fixed_asset") != 1:
			return False

		existing_assets = frappe.db.count(
			"Asset",
			{
				"purchase_receipt": pr_name,
				"item_code": row.item_code,
				"docstatus": 1,
			},
		)
		if existing_assets < cint(row.qty):
			return False

	return _capitalization_je_exists()


def _capitalization_je_exists() -> bool:
	return bool(
		frappe.db.exists(
			"Journal Entry",
			{"user_remark": PATCH_JE_REMARK, "docstatus": 1},
		)
	)


def _update_item_masters(item_codes: set[str]) -> None:
	for item_code in item_codes:
		frappe.db.set_value(
			"Item",
			item_code,
			{
				"is_fixed_asset": 1,
				"is_stock_item": 0,
				"asset_category": ASSET_CATEGORY,
				"auto_create_assets": 1,
				"asset_naming_series": ASSET_NAMING_SERIES,
			},
			update_modified=False,
		)


def _update_purchase_order_items(po_items: list[dict]) -> None:
	for row in po_items:
		frappe.db.set_value(
			"Purchase Order Item",
			row.name,
			{"is_fixed_asset": 1},
			update_modified=False,
		)


def _update_purchase_receipt_items(pr_items: list[dict]) -> None:
	for row in pr_items:
		location = _get_asset_location(row.project)
		frappe.db.set_value(
			"Purchase Receipt Item",
			row.name,
			{
				"is_fixed_asset": 1,
				"asset_category": ASSET_CATEGORY,
				"asset_location": location,
			},
			update_modified=False,
		)
		row["asset_location"] = location


def _get_asset_location(project: str | None) -> str:
	if project and frappe.db.exists("Location", project):
		return project
	if frappe.db.exists("Location", DEFAULT_ASSET_LOCATION):
		return DEFAULT_ASSET_LOCATION
	return DEFAULT_ASSET_LOCATION


def _create_assets(pr, pr_items: list[dict]) -> None:
	from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_dimensions

	pr.reload()
	accounting_dimensions = get_dimensions(with_cost_center_and_project=True)
	created = []

	for row in pr.items:
		if row.purchase_order != PO_NAME:
			continue

		existing = frappe.db.count(
			"Asset",
			{
				"purchase_receipt": pr.name,
				"purchase_receipt_item": row.name,
				"docstatus": ("!=", 2),
			},
		)
		remaining = cint(row.qty) - existing
		if remaining <= 0:
			continue

		if not row.asset_location:
			row.asset_location = _get_asset_location(row.project)

		for _index in range(remaining):
			asset_name = pr.make_asset(row, accounting_dimensions)
			asset = frappe.get_doc("Asset", asset_name)
			_prepare_asset_for_submit(asset, pr.posting_date)
			asset.flags.ignore_permissions = True
			asset.save()
			asset.submit()
			created.append(asset_name)

	if created:
		frappe.logger("construction_management").info(
			f"Created {len(created)} assets for {PO_NAME}: {', '.join(created[:10])}"
			+ (" ..." if len(created) > 10 else "")
		)


def _create_capitalization_journal_entry(pr, pr_items: list[dict]) -> None:
	if _capitalization_je_exists():
		return

	fixed_asset_account = _get_fixed_asset_account(pr.company)
	if not fixed_asset_account:
		frappe.throw(
			f"Fixed Asset Account not configured for {ASSET_CATEGORY} / {pr.company}"
		)

	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Journal Entry"
	je.company = pr.company
	je.posting_date = pr.posting_date
	je.user_remark = PATCH_JE_REMARK
	je.cheque_no = PO_NAME
	je.cheque_date = pr.posting_date

	total_amount = 0
	for row in pr_items:
		amount = flt(row.amount)
		if amount <= 0:
			continue

		total_amount += amount
		je.append(
			"accounts",
			{
				"account": fixed_asset_account,
				"debit_in_account_currency": amount,
				"credit_in_account_currency": 0,
				"cost_center": row.cost_center,
				"project": row.project,
				"user_remark": row.item_code,
			},
		)
		je.append(
			"accounts",
			{
				"account": row.expense_account,
				"debit_in_account_currency": 0,
				"credit_in_account_currency": amount,
				"cost_center": row.cost_center,
				"project": row.project,
				"user_remark": row.item_code,
			},
		)

	if total_amount <= 0:
		return

	je.flags.ignore_permissions = True
	je.insert()
	je.submit()
	frappe.logger("construction_management").info(
		f"Capitalization JE {je.name} posted for {total_amount} ({PO_NAME})"
	)


def _get_fixed_asset_account(company: str) -> str | None:
	account = frappe.db.get_value(
		"Asset Category Account",
		{"parent": ASSET_CATEGORY, "company_name": company},
		"fixed_asset_account",
	)
	if account:
		return account

	return frappe.db.get_value("Company", company, "default_fixed_asset_account")
