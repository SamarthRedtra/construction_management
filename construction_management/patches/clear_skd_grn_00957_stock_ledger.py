# Copyright (c) 2026, Construction Management
# License: MIT

"""Retire obsolete stock history for cancelled GRN SKD-GRN-00957."""

from __future__ import annotations

import frappe
from frappe.utils import flt

SOURCE_GRN = "SKD-GRN-00957"
REPLACEMENT_GRN = "SKD-GRN-01398-1"
WAREHOUSE = "SKD-50 - SC"
EXPECTED_ITEM_COUNT = 11
EXPECTED_QTY = 25.0
EXPECTED_AMOUNT = 12355.0

MATERIAL_ISSUES = {
	"MAT-STE-2026-02525",
	"MAT-STE-2026-02526",
	"MAT-STE-2026-02527",
	"MAT-STE-2026-02528",
	"MAT-STE-2026-02529",
	"MAT-STE-2026-02530",
	"MAT-STE-2026-02531",
	"MAT-STE-2026-02532",
	"MAT-STE-2026-02533",
	"MAT-STE-2026-02534",
	"MAT-STE-2026-02535",
	"MAT-STE-2026-02657",
	"MAT-STE-2026-02669",
}


def execute() -> None:
	item_codes = _validate_receipts()
	_validate_items(item_codes)
	_validate_material_issues(item_codes)
	_validate_active_stock_history(item_codes)

	_cancel_stock_ledger_rows()
	_rebuild_bins(item_codes)
	_verify_repair(item_codes)

	frappe.logger("construction_management").info(
		f"Retired obsolete stock history for cancelled {SOURCE_GRN}: "
		f"{len(item_codes)} items in {WAREHOUSE}"
	)


def _validate_receipts() -> set[str]:
	source = frappe.db.get_value(
		"Purchase Receipt", SOURCE_GRN, ["docstatus", "company"], as_dict=True
	)
	replacement = frappe.db.get_value(
		"Purchase Receipt", REPLACEMENT_GRN, ["docstatus", "company"], as_dict=True
	)
	if not source or source.docstatus != 2:
		frappe.throw(f"{SOURCE_GRN} must exist and be cancelled before this repair")
	if not replacement or replacement.docstatus != 1:
		frappe.throw(f"{REPLACEMENT_GRN} must exist and be submitted before this repair")
	if source.company != replacement.company:
		frappe.throw("Source and replacement GRNs belong to different companies")

	source_rows = _get_receipt_rows(SOURCE_GRN)
	replacement_rows = _get_receipt_rows(REPLACEMENT_GRN)
	_validate_receipt_totals(SOURCE_GRN, source_rows)
	_validate_receipt_totals(REPLACEMENT_GRN, replacement_rows)

	source_items = {row.item_code for row in source_rows}
	replacement_items = {row.item_code for row in replacement_rows}
	if source_items != replacement_items:
		frappe.throw("Source and replacement GRNs have different item sets")
	return source_items


def _get_receipt_rows(receipt: str) -> list[frappe._dict]:
	return frappe.get_all(
		"Purchase Receipt Item",
		filters={"parent": receipt},
		fields=["item_code", "warehouse", "qty", "amount", "is_fixed_asset"],
		order_by="idx asc",
	)


def _validate_receipt_totals(receipt: str, rows: list[frappe._dict]) -> None:
	if len(rows) != EXPECTED_ITEM_COUNT:
		frappe.throw(f"{receipt} must contain exactly {EXPECTED_ITEM_COUNT} items")
	if any(row.warehouse != WAREHOUSE for row in rows):
		frappe.throw(f"{receipt} contains a warehouse other than {WAREHOUSE}")
	if flt(sum(row.qty for row in rows), 6) != EXPECTED_QTY:
		frappe.throw(f"{receipt} quantity does not match the expected {EXPECTED_QTY}")
	if flt(sum(row.amount for row in rows), 6) != EXPECTED_AMOUNT:
		frappe.throw(f"{receipt} amount does not match the expected {EXPECTED_AMOUNT}")


def _validate_items(item_codes: set[str]) -> None:
	items = frappe.get_all(
		"Item",
		filters={"name": ["in", list(item_codes)]},
		fields=["name", "is_stock_item", "is_fixed_asset"],
	)
	invalid = [row.name for row in items if row.is_stock_item or not row.is_fixed_asset]
	if len(items) != EXPECTED_ITEM_COUNT or invalid:
		frappe.throw(
			"All repaired materials must exist as non-stock fixed assets. "
			f"Invalid items: {', '.join(invalid) or 'missing item records'}"
		)


def _validate_material_issues(item_codes: set[str]) -> None:
	entries = frappe.get_all(
		"Stock Entry",
		filters={"name": ["in", list(MATERIAL_ISSUES)]},
		fields=["name", "docstatus", "purpose"],
	)
	if {row.name for row in entries} != MATERIAL_ISSUES:
		frappe.throw("One or more expected Material Issue documents are missing")
	invalid = [row.name for row in entries if row.docstatus != 1 or row.purpose != "Material Issue"]
	if invalid:
		frappe.throw(f"Expected submitted Material Issues: {', '.join(sorted(invalid))}")

	rows = frappe.get_all(
		"Stock Entry Detail",
		filters={"parent": ["in", list(MATERIAL_ISSUES)]},
		fields=["parent", "item_code", "s_warehouse", "t_warehouse"],
	)
	if len(rows) != len(MATERIAL_ISSUES):
		frappe.throw("Each repaired Material Issue must contain exactly one row")
	invalid_rows = [
		row.parent
		for row in rows
		if row.item_code not in item_codes or row.s_warehouse != WAREHOUSE or row.t_warehouse
	]
	if invalid_rows:
		frappe.throw(f"Unexpected Material Issue rows: {', '.join(sorted(invalid_rows))}")


def _validate_active_stock_history(item_codes: set[str]) -> None:
	active = frappe.get_all(
		"Stock Ledger Entry",
		filters={
			"item_code": ["in", list(item_codes)],
			"warehouse": WAREHOUSE,
			"is_cancelled": 0,
		},
		fields=["voucher_type", "voucher_no"],
	)
	allowed = {("Purchase Receipt", SOURCE_GRN)} | {
		("Stock Entry", name) for name in MATERIAL_ISSUES
	}
	unexpected = {
		(row.voucher_type, row.voucher_no)
		for row in active
		if (row.voucher_type, row.voucher_no) not in allowed
	}
	if unexpected:
		formatted = ", ".join(f"{doctype} {name}" for doctype, name in sorted(unexpected))
		frappe.throw(f"Unexpected active stock history found: {formatted}")


def _cancel_stock_ledger_rows() -> None:
	from erpnext.stock.stock_ledger import set_as_cancel

	set_as_cancel("Purchase Receipt", SOURCE_GRN)
	for stock_entry in sorted(MATERIAL_ISSUES):
		set_as_cancel("Stock Entry", stock_entry)


def _rebuild_bins(item_codes: set[str]) -> None:
	from erpnext.stock.stock_ledger import update_entries_after

	for item_code in sorted(item_codes):
		update_entries_after(
			{
				"item_code": item_code,
				"warehouse": WAREHOUSE,
				"posting_date": "2026-07-27",
				"posting_time": "00:00:00",
			},
			allow_negative_stock=True,
			verbose=0,
		)
		_reset_empty_bin(item_code)


def _reset_empty_bin(item_code: str) -> None:
	# Older ERPNext leaves Bin.actual_qty when no SLE remain to replay.
	bin_name = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": WAREHOUSE})
	if not bin_name:
		return

	frappe.db.set_value(
		"Bin",
		bin_name,
		{
			"actual_qty": 0.0,
			"stock_value": 0.0,
			"valuation_rate": 0.0,
		},
		update_modified=False,
	)
	bin_doc = frappe.get_doc("Bin", bin_name)
	bin_doc.set_projected_qty()
	bin_doc.db_set("projected_qty", bin_doc.projected_qty, update_modified=False)


def _verify_repair(item_codes: set[str]) -> None:
	active_count = frappe.db.count(
		"Stock Ledger Entry",
		{
			"item_code": ["in", list(item_codes)],
			"warehouse": WAREHOUSE,
			"is_cancelled": 0,
		},
	)
	if active_count:
		frappe.throw(f"Stock repair incomplete: {active_count} active ledger rows remain")

	bins = frappe.get_all(
		"Bin",
		filters={"item_code": ["in", list(item_codes)], "warehouse": WAREHOUSE},
		fields=["item_code", "actual_qty", "stock_value"],
	)
	invalid_bins = [
		row.item_code for row in bins if flt(row.actual_qty, 6) or flt(row.stock_value, 6)
	]
	if invalid_bins:
		frappe.throw(f"Stock repair left non-zero bins: {', '.join(sorted(invalid_bins))}")
