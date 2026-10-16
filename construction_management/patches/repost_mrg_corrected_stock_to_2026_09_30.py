# Copyright (c) 2026, Construction Management
# License: MIT

"""Cancel Oct 12 MRG corrected-stock reconciliations and re-post on 30 Sep 2026."""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe.utils import getdate

from construction_management.patches import apply_mrg_corrected_stock_2026_10_12 as correction


COMPANY = correction.COMPANY
OLD_POSTING_DATE = "2026-10-12"
POSTING_DATE = "2026-09-30"
POSTING_TIME = "00:00:00"


def execute():
	"""Run only on sites that contain the MRG company."""
	if not frappe.db.exists("Company", COMPANY):
		return

	result = run()
	frappe.logger("controlled_procurement").info(
		{"event": "repost_mrg_corrected_stock_to_2026_09_30", **result}
	)


def run() -> dict:
	"""Cancel remaining Oct 12 correction SRs, then reconcile workbook targets on 30 Sep."""
	frappe.set_user("Administrator")
	cancelled = _cancel_oct_12_reconciliations()

	result = correction.preflight()
	if result["errors"]:
		frappe.throw(correction._preflight_error_message(result["errors"]))

	mismatches = correction._mismatches(result["targets"])
	documents = []
	with correction._allow_negative_stock_for_reconciliations():
		documents = _create_reconciliations(mismatches)
		for document in documents:
			document.submit()

	return {
		"old_posting_date": OLD_POSTING_DATE,
		"posting_date": POSTING_DATE,
		"cancelled": cancelled,
		"source_rows": result["source_rows"],
		"target_lines": result["target_lines"],
		"matched_balances": result["target_lines"] - len(mismatches),
		"reconciliation_balances": len(mismatches),
		"stock_reconciliations": [document.name for document in documents],
		"no_op": not cancelled and not documents,
	}


def _cancel_oct_12_reconciliations() -> list[str]:
	"""Cancel submitted MRG Stock Reconciliations still posted on 12 Oct 2026."""
	names = frappe.get_all(
		"Stock Reconciliation",
		filters={
			"company": COMPANY,
			"posting_date": OLD_POSTING_DATE,
			"docstatus": 1,
		},
		pluck="name",
		order_by="name asc",
		limit_page_length=0,
	)
	cancelled = []
	with correction._allow_negative_stock_for_reconciliations():
		for name in names:
			document = frappe.get_doc("Stock Reconciliation", name)
			document.flags.ignore_permissions = True
			document.cancel()
			cancelled.append(name)
	return cancelled


def _create_reconciliations(targets: list[dict]) -> list:
	"""Create draft Stock Reconciliations dated 30 Sep for mismatched warehouse balances."""
	by_warehouse = defaultdict(list)
	for target in targets:
		by_warehouse[target["warehouse"]].append(target)

	documents = []
	for warehouse, warehouse_targets in sorted(by_warehouse.items()):
		document = frappe.new_doc("Stock Reconciliation")
		document.company = COMPANY
		document.purpose = "Stock Reconciliation"
		document.set_posting_time = 1
		document.posting_date = getdate(POSTING_DATE)
		document.posting_time = POSTING_TIME
		for target in warehouse_targets:
			document.append(
				"items",
				{
					"item_code": target["item_code"],
					"warehouse": warehouse,
					"qty": target["qty"],
					"valuation_rate": target["valuation_rate"],
				},
			)
		document.flags.ignore_permissions = True
		document.insert()
		documents.append(document)
	return documents
