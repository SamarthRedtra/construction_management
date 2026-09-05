# Copyright (c) 2026, Construction Management
# License: MIT

"""Reclassify SKD-LPO-00371-1 assets and journals to Tools & Equipments."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

import frappe
from frappe.utils import flt

PO_NAME = "SKD-LPO-00371-1"
COMPANY = "SKADA CONSTRUCTION L.L.C"
TARGET_CATEGORY = "Tools & Equipments"
CAPITALIZATION_REMARK = "construction_management: SKD-LPO-00371-1 fixed asset capitalization"
EXPECTED_ITEM_COUNT = 11
EXPECTED_ASSET_COUNT = 25
EXPECTED_CAPITALIZATION_AMOUNT = 12355.0
REPOST_BATCH_SIZE = 5

FIXED_ASSET_ACCOUNT = "Tools & Equipments - SC"
ACCUMULATED_DEPRECIATION_ACCOUNT = "Accumulated Depreciation Tools & Equipments - SC"
DEPRECIATION_EXPENSE_ACCOUNT = "Depreciation Of Tools & Equipments - SC"

OLD_FIXED_ASSET_ACCOUNT = "Plant & Machinery- Office - SC"
OLD_ACCUMULATED_DEPRECIATION_ACCOUNT = "Acc. Depreciation of Plant & Machinery- Office - SC"
OLD_DEPRECIATION_EXPENSE_ACCOUNT = "Depreciation Of Motor Vehicles - SC"

ACCOUNT_SPECS = (
	{
		"account_name": "Tools & Equipments",
		"name": FIXED_ASSET_ACCOUNT,
		"parent_account": "Fixed Assets (Cost Price) - SC",
		"account_type": "Fixed Asset",
	},
	{
		"account_name": "Accumulated Depreciation Tools & Equipments",
		"name": ACCUMULATED_DEPRECIATION_ACCOUNT,
		"parent_account": "Accumulated Depreciation - SC",
		"account_type": "Accumulated Depreciation",
	},
	{
		"account_name": "Depreciation Of Tools & Equipments",
		"name": DEPRECIATION_EXPENSE_ACCOUNT,
		"parent_account": "Depreciation & Amortization - SC",
		"account_type": "Depreciation",
	},
)


def execute() -> None:
	po = frappe.db.get_value("Purchase Order", PO_NAME, ["company", "docstatus"], as_dict=True)
	if not po:
		return
	if po.company != COMPANY or po.docstatus not in (1, 2):
		frappe.logger("construction_management").info(
			f"Skip {PO_NAME}: not a submitted or cancelled Purchase Order for {COMPANY} "
			f"(company={po.company}, docstatus={po.docstatus})"
		)
		return
	if not frappe.db.exists("Asset Category", TARGET_CATEGORY):
		frappe.logger("construction_management").info(
			f"Skip {PO_NAME}: Asset Category {TARGET_CATEGORY} not found"
		)
		return

	item_codes = _get_item_codes()
	receipt_names = _get_receipt_names()
	asset_names = _get_asset_names(item_codes, receipt_names)
	_validate_target_counts(item_codes, asset_names)

	_ensure_accounts()
	_ensure_category_account_mapping()
	updated_rows = _update_asset_categories(item_codes, receipt_names, asset_names)
	_update_draft_invoice_clearing_account()

	capitalization_journals = _rewrite_capitalization_journal(item_codes)
	depreciation_journals = _rewrite_depreciation_journals(asset_names)
	journal_names = capitalization_journals | depreciation_journals
	_repost_journal_entries(journal_names)

	frappe.clear_cache(doctype="Asset Category")
	frappe.logger("construction_management").info(
		f"Reclassified {PO_NAME} to {TARGET_CATEGORY}: "
		f"{updated_rows} records, {len(journal_names)} journals reposted"
	)


def _get_item_codes() -> list[str]:
	return frappe.get_all(
		"Purchase Order Item",
		filters={"parent": PO_NAME, "docstatus": ["in", [1, 2]]},
		pluck="item_code",
		distinct=True,
	)


def _get_receipt_names() -> list[str]:
	return frappe.get_all(
		"Purchase Receipt Item",
		filters={"purchase_order": PO_NAME, "docstatus": 1},
		pluck="parent",
		distinct=True,
	)


def _get_asset_names(item_codes: list[str], receipt_names: list[str]) -> list[str]:
	if not receipt_names:
		return []
	return frappe.get_all(
		"Asset",
		filters={
			"purchase_receipt": ["in", receipt_names],
			"item_code": ["in", item_codes],
			"docstatus": ["!=", 2],
		},
		pluck="name",
	)


def _validate_target_counts(item_codes: list[str], asset_names: list[str]) -> None:
	if len(item_codes) != EXPECTED_ITEM_COUNT:
		frappe.throw(f"Expected {EXPECTED_ITEM_COUNT} items for {PO_NAME}, found {len(item_codes)}")
	if len(asset_names) != EXPECTED_ASSET_COUNT:
		frappe.throw(f"Expected {EXPECTED_ASSET_COUNT} active assets for {PO_NAME}, found {len(asset_names)}")


def _ensure_accounts() -> None:
	currency = frappe.db.get_value("Company", COMPANY, "default_currency")
	for spec in ACCOUNT_SPECS:
		existing = frappe.db.get_value(
			"Account",
			spec["name"],
			[
				"name",
				"company",
				"parent_account",
				"account_type",
				"account_currency",
				"is_group",
				"disabled",
			],
			as_dict=True,
		)
		if existing:
			_validate_existing_account(existing, spec, currency)
			continue

		account = frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": spec["account_name"],
				"parent_account": spec["parent_account"],
				"account_type": spec["account_type"],
				"account_currency": currency,
				"company": COMPANY,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
		if account.name != spec["name"]:
			frappe.throw(f"Expected Account {spec['name']}, created {account.name}")


def _validate_existing_account(account, spec: dict, currency: str) -> None:
	expected = {
		"company": COMPANY,
		"parent_account": spec["parent_account"],
		"account_type": spec["account_type"],
		"account_currency": currency,
		"is_group": 0,
		"disabled": 0,
	}
	mismatches = [field for field, value in expected.items() if account.get(field) != value]
	if mismatches:
		frappe.throw(f"Account {spec['name']} has incompatible fields: {', '.join(mismatches)}")


def _ensure_category_account_mapping() -> None:
	filters = {
		"parent": TARGET_CATEGORY,
		"parenttype": "Asset Category",
		"company_name": COMPANY,
	}
	values = {
		"fixed_asset_account": FIXED_ASSET_ACCOUNT,
		"accumulated_depreciation_account": ACCUMULATED_DEPRECIATION_ACCOUNT,
		"depreciation_expense_account": DEPRECIATION_EXPENSE_ACCOUNT,
		"capital_work_in_progress_account": None,
	}
	if row_name := frappe.db.get_value("Asset Category Account", filters, "name"):
		frappe.db.set_value("Asset Category Account", row_name, values, update_modified=False)
		return

	category = frappe.get_doc("Asset Category", TARGET_CATEGORY)
	category.append("accounts", {"company_name": COMPANY, **values})
	category.save(ignore_permissions=True)


def _update_asset_categories(
	item_codes: list[str], receipt_names: list[str], asset_names: list[str]
) -> int:
	updated = 0
	updated += _update_rows(
		"Item", {"name": ["in", item_codes]}, {"asset_category": TARGET_CATEGORY}
	)
	updated += _update_rows(
		"Purchase Receipt Item",
		{"parent": ["in", receipt_names], "purchase_order": PO_NAME, "docstatus": 1},
		{"asset_category": TARGET_CATEGORY},
	)
	updated += _update_rows(
		"Purchase Invoice Item",
		{"purchase_order": PO_NAME, "docstatus": ["!=", 2]},
		{"asset_category": TARGET_CATEGORY},
	)
	updated += _update_rows(
		"Asset", {"name": ["in", asset_names]}, {"asset_category": TARGET_CATEGORY}
	)
	return updated


def _update_rows(doctype: str, filters: dict, values: dict) -> int:
	names = frappe.get_all(doctype, filters=filters, pluck="name")
	updated = 0
	for name in names:
		current = frappe.db.get_value(doctype, name, list(values), as_dict=True)
		if current and all(current.get(field) == value for field, value in values.items()):
			continue
		frappe.db.set_value(doctype, name, values, update_modified=False)
		updated += 1
	return updated


def _update_draft_invoice_clearing_account() -> None:
	stock_received_but_not_billed = frappe.get_cached_value(
		"Company", COMPANY, "stock_received_but_not_billed"
	)
	if not stock_received_but_not_billed:
		frappe.throw(f"Stock Received But Not Billed account is not configured for {COMPANY}")
	_update_rows(
		"Purchase Invoice Item",
		{"purchase_order": PO_NAME, "docstatus": 0},
		{"expense_account": stock_received_but_not_billed},
	)


def _rewrite_capitalization_journal(item_codes: list[str]) -> set[str]:
	journal_names = frappe.get_all(
		"Journal Entry",
		filters={"user_remark": CAPITALIZATION_REMARK, "docstatus": 1},
		pluck="name",
	)
	if len(journal_names) != 1:
		frappe.throw(f"Expected one submitted capitalization Journal Entry for {PO_NAME}")

	journal_name = journal_names[0]
	rows = frappe.get_all(
		"Journal Entry Account",
		filters={"parent": journal_name, "account": ["in", [OLD_FIXED_ASSET_ACCOUNT, FIXED_ASSET_ACCOUNT]]},
		fields=["name", "account", "debit", "user_remark"],
	)
	asset_rows = [row for row in rows if flt(row.debit) > 0 and row.user_remark in item_codes]
	if len(asset_rows) != EXPECTED_ITEM_COUNT or flt(sum(row.debit for row in asset_rows)) != flt(
		EXPECTED_CAPITALIZATION_AMOUNT
	):
		frappe.throw(f"Unexpected capitalization rows or amount in {journal_name}")

	changed = False
	for row in asset_rows:
		if row.account == FIXED_ASSET_ACCOUNT:
			continue
		frappe.db.set_value(
			"Journal Entry Account", row.name, "account", FIXED_ASSET_ACCOUNT, update_modified=False
		)
		changed = True
	changed |= _replace_against_accounts(
		journal_name,
		{OLD_FIXED_ASSET_ACCOUNT: FIXED_ASSET_ACCOUNT},
	)
	frappe.db.set_value("Journal Entry", journal_name, "title", FIXED_ASSET_ACCOUNT, update_modified=False)

	return {journal_name} if changed or _journal_has_stale_gl(journal_name) else set()


def _rewrite_depreciation_journals(asset_names: list[str]) -> set[str]:
	schedule_names = frappe.get_all(
		"Asset Depreciation Schedule",
		filters={"asset": ["in", asset_names], "docstatus": 1},
		pluck="name",
	)
	journal_names = set(
		frappe.get_all(
			"Depreciation Schedule",
			filters={"parent": ["in", schedule_names], "journal_entry": ["is", "set"]},
			pluck="journal_entry",
		)
	)
	if not journal_names:
		return set()

	rows = frappe.get_all(
		"Journal Entry Account",
		filters={"parent": ["in", list(journal_names)]},
		fields=["name", "parent", "account", "debit", "credit"],
	)
	account_types = _get_account_types({row.account for row in rows})
	changed_journals = set()
	for row in rows:
		target_account = _get_depreciation_replacement(row, account_types)
		if not target_account:
			continue
		frappe.db.set_value(
			"Journal Entry Account", row.name, "account", target_account, update_modified=False
		)
		changed_journals.add(row.parent)

	for journal_name in journal_names:
		if _replace_against_accounts(
			journal_name,
			{
				OLD_ACCUMULATED_DEPRECIATION_ACCOUNT: ACCUMULATED_DEPRECIATION_ACCOUNT,
				OLD_DEPRECIATION_EXPENSE_ACCOUNT: DEPRECIATION_EXPENSE_ACCOUNT,
			},
		):
			changed_journals.add(journal_name)
		frappe.db.set_value(
			"Journal Entry",
			journal_name,
			"title",
			ACCUMULATED_DEPRECIATION_ACCOUNT,
			update_modified=False,
		)
		if _journal_has_stale_gl(journal_name):
			changed_journals.add(journal_name)
	return changed_journals


def _replace_against_accounts(journal_name: str, replacements: dict[str, str]) -> bool:
	changed = False
	rows = frappe.get_all(
		"Journal Entry Account",
		filters={"parent": journal_name},
		fields=["name", "against_account"],
	)
	for row in rows:
		against_account = row.against_account or ""
		updated_against_account = against_account
		for old_account, new_account in replacements.items():
			updated_against_account = updated_against_account.replace(old_account, new_account)
		if updated_against_account == against_account:
			continue
		frappe.db.set_value(
			"Journal Entry Account",
			row.name,
			"against_account",
			updated_against_account,
			update_modified=False,
		)
		changed = True
	return changed


def _get_account_types(accounts: set[str]) -> dict[str, str]:
	return {
		row.name: row.account_type
		for row in frappe.get_all(
			"Account", filters={"name": ["in", list(accounts)]}, fields=["name", "account_type"]
		)
	}


def _get_depreciation_replacement(row, account_types: dict[str, str]) -> str | None:
	account_type = account_types.get(row.account)
	if flt(row.debit) > 0 and account_type == "Depreciation" and row.account != DEPRECIATION_EXPENSE_ACCOUNT:
		return DEPRECIATION_EXPENSE_ACCOUNT
	if (
		flt(row.credit) > 0
		and account_type == "Accumulated Depreciation"
		and row.account != ACCUMULATED_DEPRECIATION_ACCOUNT
	):
		return ACCUMULATED_DEPRECIATION_ACCOUNT
	return None


def _journal_has_stale_gl(journal_name: str) -> bool:
	old_accounts = {
		OLD_FIXED_ASSET_ACCOUNT,
		OLD_ACCUMULATED_DEPRECIATION_ACCOUNT,
		OLD_DEPRECIATION_EXPENSE_ACCOUNT,
	}
	entries = frappe.get_all(
		"GL Entry",
		filters={"voucher_type": "Journal Entry", "voucher_no": journal_name, "is_cancelled": 0},
		fields=["account", "against"],
	)
	return any(
		row.account in old_accounts or any(account in (row.against or "") for account in old_accounts)
		for row in entries
	)


def _repost_journal_entries(journal_names: Iterable[str]) -> None:
	for journal_batch in _batched(sorted(set(journal_names)), REPOST_BATCH_SIZE):
		repost = frappe.new_doc("Repost Accounting Ledger")
		repost.company = COMPANY
		repost.delete_cancelled_entries = 1
		for journal_name in journal_batch:
			repost.append("vouchers", {"voucher_type": "Journal Entry", "voucher_no": journal_name})
		repost.flags.ignore_permissions = True
		repost.insert()
		repost.submit()


def _batched(values: list[str], size: int) -> Iterator[list[str]]:
	for index in range(0, len(values), size):
		yield values[index : index + size]
