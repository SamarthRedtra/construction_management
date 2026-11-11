"""Link TINV/1148/2026-JUL/1-1 to July Sales Order SAL-ORD-2026-00334 for Connections.

BOQ items BOQI-2026-00276 / 00277 exist on the April order only; the July proforma did not
include those lines. This routine copies the missing lines onto the July order (incremental
BOQ ledger), then links invoice rows to the July order — not via the generic open-ledger fallback
(which would pick April).

	bench --site skada.local execute \\
		construction_management.api.fix_tinv_1148_jul_april_so_link.run
	bench --site skada.local execute \\
		construction_management.api.fix_tinv_1148_jul_april_so_link.run --kwargs "{'dry_run': 0}"
"""

from __future__ import annotations

import frappe
from frappe.utils import cint, flt

from construction_management.api.relink_si_sales_orders import (
	_merge_boq_ledger_row,
	_named_orders,
	_header_order_lines,
	_queue_gl_repost,
)
from construction_management.overrides.sales_invoice import DEDUCTION_ITEM_CODES, link_deduction_rows

INVOICE = "TINV/1148/2026-JUL/1-1"
APRIL_SO = "SAL-ORD-2026-00277"
JULY_SO = "SAL-ORD-2026-00334"
BOQ_ITEMS = ("BOQI-2026-00276", "BOQI-2026-00277")


def run(dry_run: int = 1) -> list[dict]:
	dry_run = cint(dry_run)
	report: list[dict] = []

	if not frappe.db.exists("Sales Invoice", INVOICE):
		report.append({"step": "missing", "result": f"{INVOICE} not found"})
		_print(report)
		return report

	si = frappe.get_doc("Sales Invoice", INVOICE)
	if si.docstatus != 1:
		report.append({"step": "docstatus", "result": "invoice must be submitted"})
		_print(report)
		return report

	report.append({
		"step": "header",
		"result": f"custom_sales_order={si.get('custom_sales_order')} (target {JULY_SO})",
	})

	copy_report, copy_error = _copy_july_lines_if_missing(dry_run=dry_run)
	report.extend(copy_report)
	if copy_error:
		_print(report)
		return report

	link_rows, link_report = _relink_to_header_order(si, dry_run=dry_run)
	report.extend(link_report)

	if dry_run:
		report.append({"step": "dry_run", "result": f"would link {len(link_rows)} invoice rows"})
		_print(report)
		return report

	if link_rows:
		if not cint(si.update_billed_amount_in_sales_order):
			frappe.db.set_value(
				"Sales Invoice",
				INVOICE,
				"update_billed_amount_in_sales_order",
				1,
				update_modified=False,
			)
			report.append({"step": "flag", "result": "set update_billed_amount_in_sales_order"})

		si.reload()
		si.update_prevdoc_status()

		july = frappe.get_doc("Sales Order", JULY_SO)
		july.set_status(update=True)
		report.append({
			"step": "july_so_status",
			"result": f"{JULY_SO} status={july.status} per_billed={july.per_billed}",
		})

		frappe.db.commit()
		report.extend(_queue_gl_repost([INVOICE]))

	report.append({"step": "done", "result": f"linked {len(link_rows)} rows to {JULY_SO}"})
	_print(report)
	return report


def _copy_july_lines_if_missing(dry_run: bool) -> tuple[list[dict], bool]:
	report: list[dict] = []
	july = frappe.get_doc("Sales Order", JULY_SO)
	existing = {
		(row.boq_item, row.item_code, row.uom)
		for row in july.items
		if row.get("boq_item") in BOQ_ITEMS
	}
	april = frappe.get_doc("Sales Order", APRIL_SO)
	to_copy = [
		row
		for row in april.items
		if row.get("boq_item") in BOQ_ITEMS
		and (row.boq_item, row.item_code, row.uom) not in existing
	]
	for row in to_copy:
		report.append({
			"step": "copy_so_line",
			"boq_item": row.boq_item,
			"item_code": row.item_code,
			"uom": row.uom,
			"result": f"append to {JULY_SO}",
		})
	if not to_copy:
		report.append({"step": "copy_so_line", "result": f"{JULY_SO} already has BOQ lines"})
		return report, False
	if dry_run:
		return report, False

	try:
		for row in to_copy:
			child = frappe.copy_doc(row)
			child.parent = JULY_SO
			child.parenttype = "Sales Order"
			child.parentfield = "items"
			child.delivery_date = july.delivery_date or july.transaction_date
			july.append("items", child)
		july.flags.ignore_validate_update_after_submit = True
		july.flags.ignore_validate = True
		july.save(ignore_permissions=True)
		report.append({"step": "copy_so_line", "result": f"appended {len(to_copy)} lines"})
	except Exception as error:
		frappe.db.rollback()
		report.append({"step": "copy_so_line", "result": f"error: {error}"})
		return report, True
	return report, False


def _effective_header_lines(orders: list[str]) -> dict:
	"""July order lines, plus April lines that will be copied before linking."""
	lines = _header_order_lines(orders)
	april = frappe.get_doc("Sales Order", APRIL_SO)
	for row in april.items:
		if row.get("boq_item") not in BOQ_ITEMS:
			continue
		key = (row.boq_item, row.item_code, row.uom)
		if key in lines or row.item_code in DEDUCTION_ITEM_CODES:
			continue
		lines[key] = (JULY_SO, row.name)
	return lines


def _relink_to_header_order(si, dry_run: bool) -> tuple[list, list[dict]]:
	"""Link work rows using header / source orders only (never open-ledger fallback)."""
	orders = _named_orders(si)
	header_lines = _effective_header_lines(orders) if dry_run else _header_order_lines(orders)
	report: list[dict] = []
	linked_work = []

	work_rows = [
		row
		for row in si.items
		if orders
		and not row.get("sales_order")
		and row.item_code not in DEDUCTION_ITEM_CODES
		and row.get("boq_item")
	]
	for row in work_rows:
		match = header_lines.get((row.boq_item, row.item_code, row.uom))
		rule = "header order" if match else "skipped: no line on header Sales Order"
		if match:
			if dry_run:
				row.sales_order, row.so_detail = match
			else:
				frappe.db.set_value(
					"Sales Invoice Item",
					row.name,
					{"sales_order": match[0], "so_detail": match[1]},
					update_modified=False,
				)
				row.sales_order, row.so_detail = match
			linked_work.append(row)
		report.append(_report_row(si, row, rule))

	if not dry_run and linked_work:
		si.reload()

	for row in link_deduction_rows(si.items):
		if not row.get("sales_order"):
			continue
		report.append(_report_row(si, row, "deduction follows its work line"))
		if not dry_run:
			values = {"sales_order": row.sales_order, "so_detail": row.so_detail}
			frappe.db.set_value("Sales Invoice Item", row.name, values, update_modified=False)

	linked_deductions = [row for row in si.items if row.get("sales_order") and row.item_code in DEDUCTION_ITEM_CODES]
	linked = linked_work + [row for row in linked_deductions if row not in linked_work]

	if linked and not dry_run:
		for row in linked_work:
			_merge_boq_ledger_row(si, row)

	return linked, report


def _report_row(si, row, result: str) -> dict:
	return {
		"step": "invoice_line",
		"invoice": si.name,
		"idx": row.idx,
		"item_code": row.item_code,
		"boq_item": row.get("boq_item"),
		"sales_order": row.get("sales_order"),
		"so_detail": row.get("so_detail"),
		"result": result,
	}


def _print(report: list[dict]) -> None:
	for entry in report:
		print(" | ".join(f"{key}={entry[key]}" for key in entry if entry.get(key) is not None))

