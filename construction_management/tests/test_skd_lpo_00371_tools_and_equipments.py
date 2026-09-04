# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.overrides.purchase_invoice import (
	LEGACY_FIXED_ASSET_PO,
	_set_legacy_fixed_asset_stock_clearing_account,
)
from construction_management.patches.fix_skd_lpo_00371_1_tools_and_equipments import (
	ACCUMULATED_DEPRECIATION_ACCOUNT,
	COMPANY,
	DEPRECIATION_EXPENSE_ACCOUNT,
	FIXED_ASSET_ACCOUNT,
	REPOST_BATCH_SIZE,
	TARGET_CATEGORY,
	_batched,
	_ensure_category_account_mapping,
	_get_asset_names,
	_get_depreciation_replacement,
	_replace_against_accounts,
	_repost_journal_entries,
	_rewrite_capitalization_journal,
	_validate_existing_account,
)


class TestSKDLPO00371ToolsAndEquipments(UnitTestCase):
	def test_existing_account_is_validated_before_reuse(self):
		spec = {
			"name": FIXED_ASSET_ACCOUNT,
			"parent_account": "Fixed Assets (Cost Price) - SC",
			"account_type": "Fixed Asset",
		}
		account = frappe._dict(
			company=COMPANY,
			parent_account=spec["parent_account"],
			account_type=spec["account_type"],
			account_currency="AED",
			is_group=0,
			disabled=0,
		)

		_validate_existing_account(account, spec, "AED")
		account.disabled = 1
		with self.assertRaises(frappe.ValidationError):
			_validate_existing_account(account, spec, "AED")

	@patch(
		"construction_management.patches.fix_skd_lpo_00371_1_tools_and_equipments.frappe.get_doc"
	)
	@patch(
		"construction_management.patches.fix_skd_lpo_00371_1_tools_and_equipments.frappe.db.get_value"
	)
	def test_category_account_mapping_is_created(self, get_value, get_doc):
		get_value.return_value = None
		category = get_doc.return_value

		_ensure_category_account_mapping()

		get_doc.assert_called_once_with("Asset Category", TARGET_CATEGORY)
		category.append.assert_called_once_with(
			"accounts",
			{
				"company_name": COMPANY,
				"fixed_asset_account": FIXED_ASSET_ACCOUNT,
				"accumulated_depreciation_account": ACCUMULATED_DEPRECIATION_ACCOUNT,
				"depreciation_expense_account": DEPRECIATION_EXPENSE_ACCOUNT,
				"capital_work_in_progress_account": None,
			},
		)
		category.save.assert_called_once_with(ignore_permissions=True)

	@patch(
		"construction_management.patches.fix_skd_lpo_00371_1_tools_and_equipments.frappe.get_all"
	)
	def test_assets_are_selected_from_items_and_receipts(self, get_all):
		get_all.return_value = ["ACC-ASS-1"]

		assets = _get_asset_names(["ITEM-1"], ["SKD-GRN-1"])

		self.assertEqual(assets, ["ACC-ASS-1"])
		get_all.assert_called_once_with(
			"Asset",
			filters={
				"purchase_receipt": ["in", ["SKD-GRN-1"]],
				"item_code": ["in", ["ITEM-1"]],
				"docstatus": ["!=", 2],
			},
			pluck="name",
		)

	def test_batched_keeps_reposts_synchronous(self):
		batches = list(_batched([f"JE-{index}" for index in range(11)], REPOST_BATCH_SIZE))
		self.assertEqual([len(batch) for batch in batches], [5, 5, 1])

	@patch(
		"construction_management.patches.fix_skd_lpo_00371_1_tools_and_equipments.frappe.new_doc"
	)
	def test_repost_journals_uses_delete_mode(self, new_doc):
		repost_docs = [MagicMock() for _index in range(3)]
		new_doc.side_effect = repost_docs

		_repost_journal_entries(f"JE-{index}" for index in range(11))

		self.assertEqual(new_doc.call_count, 3)
		for repost in repost_docs:
			self.assertEqual(repost.company, COMPANY)
			self.assertEqual(repost.delete_cancelled_entries, 1)
			repost.insert.assert_called_once_with()
			repost.submit.assert_called_once_with()
			self.assertLessEqual(repost.append.call_count, REPOST_BATCH_SIZE)

	def test_depreciation_replacement_is_idempotent(self):
		account_types = {
			"Old Expense": "Depreciation",
			"Old Accumulated": "Accumulated Depreciation",
			DEPRECIATION_EXPENSE_ACCOUNT: "Depreciation",
			ACCUMULATED_DEPRECIATION_ACCOUNT: "Accumulated Depreciation",
		}
		self.assertEqual(
			_get_depreciation_replacement(
				frappe._dict(account="Old Expense", debit=10, credit=0), account_types
			),
			DEPRECIATION_EXPENSE_ACCOUNT,
		)
		self.assertEqual(
			_get_depreciation_replacement(
				frappe._dict(account="Old Accumulated", debit=0, credit=10), account_types
			),
			ACCUMULATED_DEPRECIATION_ACCOUNT,
		)
		self.assertIsNone(
			_get_depreciation_replacement(
				frappe._dict(account=DEPRECIATION_EXPENSE_ACCOUNT, debit=10, credit=0),
				account_types,
			)
		)

	@patch(
		"construction_management.patches.fix_skd_lpo_00371_1_tools_and_equipments.frappe.db.set_value"
	)
	@patch(
		"construction_management.patches.fix_skd_lpo_00371_1_tools_and_equipments.frappe.get_all"
	)
	def test_against_account_replacement_is_idempotent(self, get_all, set_value):
		get_all.return_value = [
			frappe._dict(name="ROW-1", against_account="Old Expense"),
			frappe._dict(name="ROW-2", against_account="New Expense"),
		]

		changed = _replace_against_accounts("JE-1", {"Old Expense": "New Expense"})

		self.assertTrue(changed)
		set_value.assert_called_once_with(
			"Journal Entry Account",
			"ROW-1",
			"against_account",
			"New Expense",
			update_modified=False,
		)

	@patch(
		"construction_management.patches.fix_skd_lpo_00371_1_tools_and_equipments.frappe.db.set_value"
	)
	@patch(
		"construction_management.patches.fix_skd_lpo_00371_1_tools_and_equipments.frappe.get_all"
	)
	def test_capitalization_journal_account_is_replaced(self, get_all, set_value):
		rows = [
			frappe._dict(
				name=f"ROW-{index}",
				account="Plant & Machinery- Office - SC",
				debit=1000 if index < 10 else 2355,
				user_remark=f"ITEM-{index}",
				against_account="Cost of Goods Sold in Trading - SC",
			)
			for index in range(11)
		]
		get_all.side_effect = [["ACC-JV-2026-03455"], rows, rows, []]

		journals = _rewrite_capitalization_journal([f"ITEM-{index}" for index in range(11)])

		self.assertEqual(journals, {"ACC-JV-2026-03455"})
		account_updates = [
			call
			for call in set_value.call_args_list
			if len(call.args) >= 3 and call.args[2] == "account"
		]
		self.assertEqual(len(account_updates), 11)

	@patch("construction_management.overrides.purchase_invoice.frappe.get_all")
	def test_legacy_invoice_clears_stock_receipt_accrual(self, get_all):
		get_all.return_value = ["SKD-GRN-00957"]
		doc = frappe._dict(
			items=[
				frappe._dict(
					purchase_order=LEGACY_FIXED_ASSET_PO,
					purchase_receipt="SKD-GRN-00957",
					expense_account="Tools & Equipments - SC",
				)
			]
		)
		doc.get_company_default = MagicMock(return_value="Stock Received But Not Billed - SC")

		_set_legacy_fixed_asset_stock_clearing_account(doc)

		self.assertEqual(doc["items"][0].expense_account, "Stock Received But Not Billed - SC")

	@patch("construction_management.overrides.purchase_invoice.frappe.get_all")
	def test_legacy_invoice_requires_stock_accrual_receipt(self, get_all):
		get_all.return_value = []
		doc = frappe._dict(
			items=[
				frappe._dict(
					purchase_order=LEGACY_FIXED_ASSET_PO,
					purchase_receipt="SKD-GRN-OTHER",
					expense_account="Asset Received But Not Billed - SC",
				)
			]
		)
		doc.get_company_default = MagicMock(return_value="Stock Received But Not Billed - SC")

		_set_legacy_fixed_asset_stock_clearing_account(doc)

		self.assertEqual(doc["items"][0].expense_account, "Asset Received But Not Billed - SC")

	@patch("construction_management.overrides.purchase_invoice.frappe.get_all")
	def test_unrelated_invoice_keeps_standard_account(self, get_all):
		doc = frappe._dict(
			items=[
				frappe._dict(
					purchase_order="SKD-LPO-OTHER",
					purchase_receipt="SKD-GRN-OTHER",
					expense_account="Asset Received But Not Billed - SC",
				)
			]
		)
		doc.get_company_default = MagicMock(return_value="Stock Received But Not Billed - SC")

		_set_legacy_fixed_asset_stock_clearing_account(doc)

		get_all.assert_not_called()
		self.assertEqual(doc["items"][0].expense_account, "Asset Received But Not Billed - SC")
