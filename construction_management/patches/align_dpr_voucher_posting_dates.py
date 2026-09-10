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
		names.update(
			frappe.get_all(
				"Journal Entry",
				filters={"user_remark": f"{prefix} {dpr.name}", "docstatus": 1},
				pluck="name",
			)
		)
	for child_dt in ("DPR Overhead", "DPR Expense"):
		names.update(
			frappe.get_all(
				child_dt,
				filters={"parent": dpr.name, "journal_entry": ["is", "set"]},
				pluck="journal_entry",
			)
		)
	return {name for name in names if name}


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
	if getdate(row.posting_date) == target:
		return False

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
	if getdate(row.posting_date) == target:
		return False

	frappe.db.set_value("Journal Entry", je_name, "posting_date", target, update_modified=False)
	frappe.db.sql(
		"""
		UPDATE `tabGL Entry`
		SET posting_date = %s
		WHERE voucher_type = 'Journal Entry'
			AND voucher_no = %s
			AND is_cancelled = 0
		""",
		(target, je_name),
	)
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
