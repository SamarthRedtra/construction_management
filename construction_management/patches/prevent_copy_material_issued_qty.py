# Copyright (c) 2026, Construction Management
# License: MIT

"""Stop issue-tracking fields from copying onto duplicated GRN / transfer lines."""

from __future__ import annotations

import frappe
from frappe.utils import cint, flt


ISSUE_TRACKING_FIELDS = (
	("Purchase Receipt Item", "custom_material_issued_qty"),
	("Purchase Receipt Item", "custom_material_issue_stock_entries"),
	("Stock Entry Detail", "custom_material_issued_qty"),
	("Stock Entry Detail", "custom_bulk_issue_source_line"),
	("Stock Entry", "custom_bulk_issue_source_doctype"),
	("Stock Entry", "custom_bulk_issue_source_name"),
	("Stock Entry", "custom_source_purchase_receipt"),
	("Stock Entry", "custom_source_material_transfer"),
)


def execute():
	_set_no_copy()
	_clear_stale_draft_purchase_receipt_tracking()
	frappe.clear_cache(doctype="Purchase Receipt Item")
	frappe.clear_cache(doctype="Stock Entry Detail")
	frappe.clear_cache(doctype="Stock Entry")


def _set_no_copy():
	for dt, fieldname in ISSUE_TRACKING_FIELDS:
		name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": fieldname}, "name")
		if not name:
			continue
		frappe.db.set_value("Custom Field", name, "no_copy", 1, update_modified=False)


def _clear_stale_draft_purchase_receipt_tracking():
	"""Clear copied issued-qty markers on draft PR lines that do not belong to those issues."""
	if not frappe.db.has_column("Purchase Receipt Item", "custom_material_issued_qty"):
		return
	has_entries = frappe.db.has_column(
		"Purchase Receipt Item", "custom_material_issue_stock_entries"
	)
	rows = frappe.db.sql(
		"""
		SELECT pri.name, pri.parent, pri.custom_material_issued_qty,
			{entries} AS custom_material_issue_stock_entries
		FROM `tabPurchase Receipt Item` pri
		JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pr.docstatus = 0
			AND (
				IFNULL(pri.custom_material_issued_qty, 0) > 0
				{entries_filter}
			)
		""".format(
			entries="pri.custom_material_issue_stock_entries" if has_entries else "NULL",
			entries_filter=(
				"OR IFNULL(pri.custom_material_issue_stock_entries, '') != ''" if has_entries else ""
			),
		),
		as_dict=True,
	)
	for row in rows:
		if _tracking_belongs_to_line(row):
			continue
		values = {"custom_material_issued_qty": 0}
		if has_entries:
			values["custom_material_issue_stock_entries"] = None
		frappe.db.set_value(
			"Purchase Receipt Item",
			row.name,
			values,
			update_modified=False,
		)


def _tracking_belongs_to_line(row) -> bool:
	entries = [
		name.strip()
		for name in (row.custom_material_issue_stock_entries or "").split(",")
		if name.strip()
	]
	if not entries:
		return flt(row.custom_material_issued_qty) <= 0
	for entry in entries:
		se = frappe.db.get_value(
			"Stock Entry",
			entry,
			["docstatus", "custom_source_purchase_receipt", "custom_bulk_issue_source_name"],
			as_dict=True,
		)
		if not se or cint(se.docstatus) == 2:
			continue
		source = se.custom_source_purchase_receipt or se.custom_bulk_issue_source_name
		if source != row.parent:
			continue
		if frappe.db.exists(
			"Stock Entry Detail",
			{"parent": entry, "custom_bulk_issue_source_line": row.name, "docstatus": ["!=", 2]},
		):
			return True
	return False
