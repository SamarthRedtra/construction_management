"""Unlink April Sales Order lines from July tax invoice TINV/1148/2026-JUL/1-1.

Header `custom_sales_order` is already July (`SAL-ORD-2026-00334`), but item rows and
BOQ Progress Ledger Invoice rows still point at April (`SAL-ORD-2026-00277`). Those BOQ
items (BOQI-2026-00276 / 00277) are not on the July order, so lines are cleared rather
than remapped.

	bench --site skada.local execute \\
		construction_management.api.fix_tinv_1148_jul_april_so_link.run
	bench --site skada.local execute \\
		construction_management.api.fix_tinv_1148_jul_april_so_link.run --kwargs "{'dry_run': 0}"
"""

from __future__ import annotations

import frappe
from frappe.utils import cint

INVOICE = "TINV/1148/2026-JUL/1-1"
APRIL_SO = "SAL-ORD-2026-00277"
JULY_SO = "SAL-ORD-2026-00334"


def run(dry_run: int = 1) -> list[dict]:
	"""Report (default) or apply the unlink + SO billing / BOQ ledger refresh."""
	dry_run = cint(dry_run)
	report: list[dict] = []

	if not frappe.db.exists("Sales Invoice", INVOICE):
		report.append({"step": "missing", "result": f"{INVOICE} not found"})
		_print(report)
		return report

	si = frappe.get_doc("Sales Invoice", INVOICE)
	header = si.get("custom_sales_order")
	report.append({
		"step": "header",
		"result": f"custom_sales_order={header} (keep {JULY_SO})",
	})

	cleared_rows = []
	for row in si.items:
		if row.sales_order != APRIL_SO:
			continue
		report.append({
			"step": "line",
			"idx": row.idx,
			"item_code": row.item_code,
			"boq_item": row.get("boq_item"),
			"sales_order": row.sales_order,
			"so_detail": row.so_detail,
			"result": "clear April sales_order/so_detail",
		})
		cleared_rows.append(row)

	ledger_rows = frappe.get_all(
		"BOQ Progress Ledger",
		filters={"tax_invoice": INVOICE, "reference_name": APRIL_SO},
		fields=["name", "boq_item", "amount", "tax_invoice_amount", "source"],
	)
	for ledger in ledger_rows:
		report.append({
			"step": "boq_ledger",
			"name": ledger.name,
			"boq_item": ledger.boq_item,
			"result": "clear tax_invoice on April ledger row",
		})

	if dry_run:
		report.append({"step": "dry_run", "result": f"would clear {len(cleared_rows)} lines, {len(ledger_rows)} ledger rows"})
		_print(report)
		return report

	for row in cleared_rows:
		frappe.db.set_value(
			"Sales Invoice Item",
			row.name,
			{"sales_order": "", "so_detail": ""},
			update_modified=False,
		)

	boq_items = set()
	for ledger in ledger_rows:
		frappe.db.set_value(
			"BOQ Progress Ledger",
			ledger.name,
			{
				"tax_invoice": "",
				"tax_invoice_amount": 0,
				"source": "Order",
			},
			update_modified=False,
		)
		if ledger.boq_item:
			boq_items.add(ledger.boq_item)

	si.reload()
	si.update_prevdoc_status()

	from construction_management.api.boq_ledger import recalculate_ledger_for_item

	for boq_item in sorted(boq_items):
		recalculate_ledger_for_item(boq_item)
		report.append({"step": "recalc", "boq_item": boq_item, "result": "ok"})

	april = frappe.get_doc("Sales Order", APRIL_SO)
	april.set_status(update=True)
	report.append({
		"step": "april_so_status",
		"result": f"{APRIL_SO} status={april.status} per_billed={april.per_billed}",
	})

	frappe.db.commit()
	report.append({"step": "done", "result": f"unlinked {len(cleared_rows)} lines from {APRIL_SO}"})
	_print(report)
	return report


def _print(report: list[dict]) -> None:
	for entry in report:
		print(" | ".join(f"{key}={entry[key]}" for key in entry))
