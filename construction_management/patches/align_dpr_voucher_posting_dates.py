# Copyright (c) 2026, Construction Management
# License: MIT

"""Set submitted DPR Stock Entry / Journal Entry posting dates to the DPR date."""

from __future__ import annotations

import frappe
from frappe.utils import getdate

JE_REMARK_PREFIXES = (
	"Asset costs for DPR",
	"Labour costs for DPR",
	"Overhead costs for DPR",
	"Expense costs for DPR",
)

LOGGER = frappe.logger("construction_management")


def execute():
	dprs = frappe.get_all(
		"Daily Progress Record",
		filters={"docstatus": 1},
		fields=["name", "date", "stock_entries", "journal_entries"],
	)
	fixed_se = 0
	fixed_je = 0
	skipped = 0
	for dpr in dprs:
		if not dpr.date:
			continue
		target = getdate(dpr.date)
		for se_name in _stock_entry_names(dpr):
			if _align_stock_entry(se_name, target):
				fixed_se += 1
			else:
				skipped += 1
		for je_name in _journal_entry_names(dpr):
			if _align_journal_entry(je_name, target):
				fixed_je += 1
			else:
				skipped += 1

	LOGGER.info(
		f"align_dpr_voucher_posting_dates: stock entries {fixed_se}, "
		f"journal entries {fixed_je}, skipped {skipped}"
	)


def _split_names(value: str | None) -> list[str]:
	if not value:
		return []
	return [part.strip() for part in str(value).split(",") if part.strip()]


def _stock_entry_names(dpr) -> set[str]:
	names = set(_split_names(dpr.stock_entries))
	names.update(
		frappe.get_all(
			"DPR Material",
			filters={"parent": dpr.name, "stock_entry": ["is", "set"]},
			pluck="stock_entry",
		)
	)
	return {name for name in names if name}


def _journal_entry_names(dpr) -> set[str]:
	names = set(_split_names(dpr.journal_entries))
	for prefix in JE_REMARK_PREFIXES:
		needle = f"%{prefix} {dpr.name}%"
		found = frappe.db.sql(
			"""
			SELECT name FROM `tabJournal Entry`
			WHERE docstatus = 1
				AND (IFNULL(user_remark, '') LIKE %(needle)s OR IFNULL(remark, '') LIKE %(needle)s)
			""",
			{"needle": needle},
		)
		names.update(row[0] for row in found)
	for child_dt in ("DPR Overhead", "DPR Expense"):
		names.update(
			frappe.get_all(
				child_dt,
				filters={"parent": dpr.name, "journal_entry": ["is", "set"]},
				pluck="journal_entry",
			)
		)
	return {name for name in names if name}


def _gl_needs_update(voucher_type: str, voucher_no: str, target) -> bool:
	return bool(
		frappe.db.sql(
			"""
			SELECT 1 FROM `tabGL Entry`
			WHERE voucher_type = %s AND voucher_no = %s
				AND is_cancelled = 0 AND posting_date != %s
			LIMIT 1
			""",
			(voucher_type, voucher_no, target),
		)
	)


def _sle_needs_update(voucher_no: str, target) -> bool:
	if not frappe.db.table_exists("Stock Ledger Entry"):
		return False
	return bool(
		frappe.db.sql(
			"""
			SELECT 1 FROM `tabStock Ledger Entry`
			WHERE voucher_type = 'Stock Entry' AND voucher_no = %s
				AND is_cancelled = 0 AND posting_date != %s
			LIMIT 1
			""",
			(voucher_no, target),
		)
	)


def _sync_gl_posting_date(voucher_type: str, voucher_no: str, target) -> None:
	frappe.db.sql(
		"""
		UPDATE `tabGL Entry`
		SET posting_date = %s
		WHERE voucher_type = %s
			AND voucher_no = %s
			AND is_cancelled = 0
			AND posting_date != %s
		""",
		(target, voucher_type, voucher_no, target),
	)
	if frappe.db.table_exists("Payment Ledger Entry"):
		frappe.db.sql(
			"""
			UPDATE `tabPayment Ledger Entry`
			SET posting_date = %s
			WHERE voucher_type = %s
				AND voucher_no = %s
				AND IFNULL(delinked, 0) = 0
				AND posting_date != %s
			""",
			(target, voucher_type, voucher_no, target),
		)


def _align_stock_entry(se_name: str, target) -> bool:
	if not frappe.db.exists("Stock Entry", se_name):
		return False
	row = frappe.db.get_value(
		"Stock Entry",
		se_name,
		["docstatus", "posting_date", "posting_time", "company"],
		as_dict=True,
	)
	if not row or row.docstatus != 1:
		return False

	header_mismatch = getdate(row.posting_date) != target
	ledger_mismatch = _gl_needs_update("Stock Entry", se_name, target) or _sle_needs_update(
		se_name, target
	)
	if not header_mismatch and not ledger_mismatch:
		return False

	if header_mismatch:
		frappe.db.set_value(
			"Stock Entry",
			se_name,
			{"posting_date": target, "set_posting_time": 1},
			update_modified=False,
		)
		try:
			_repost_stock_entry(se_name, row.company, target, row.posting_time)
		except Exception:
			LOGGER.warning(
				f"Could not repost Stock Entry {se_name} to {target}: {frappe.get_traceback()}"
			)

	_sync_gl_posting_date("Stock Entry", se_name, target)
	return True


def _align_journal_entry(je_name: str, target) -> bool:
	if not frappe.db.exists("Journal Entry", je_name):
		return False
	row = frappe.db.get_value(
		"Journal Entry",
		je_name,
		["docstatus", "posting_date"],
		as_dict=True,
	)
	if not row or row.docstatus != 1:
		return False

	header_mismatch = getdate(row.posting_date) != target
	ledger_mismatch = _gl_needs_update("Journal Entry", je_name, target)
	if not header_mismatch and not ledger_mismatch:
		return False

	if header_mismatch:
		frappe.db.set_value("Journal Entry", je_name, "posting_date", target, update_modified=False)
	_sync_gl_posting_date("Journal Entry", je_name, target)
	return True


def _repost_stock_entry(se_name: str, company: str, posting_date, posting_time) -> None:
	if not company:
		return
	repost = frappe.new_doc("Repost Item Valuation")
	repost.based_on = "Transaction"
	repost.voucher_type = "Stock Entry"
	repost.voucher_no = se_name
	repost.company = company
	repost.posting_date = posting_date
	repost.posting_time = posting_time
	repost.recreate_stock_ledgers = 1
	repost.flags.ignore_permissions = True
	repost.insert()
	repost.submit()
	if hasattr(repost, "repost_now"):
		repost.repost_now()
