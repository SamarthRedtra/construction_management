"""Split aggregated combined Tax Invoice lines so each source Sales Order is linked on items.

	bench --site <site> execute construction_management.api.repair_combined_si_sales_orders.run
	bench --site <site> execute construction_management.api.repair_combined_si_sales_orders.run --kwargs "{'dry_run': 0, 'invoices': 'TINV/1171/May26-June26-July26/1'}"
"""

from __future__ import annotations

import frappe
from frappe.utils import cint, flt

from construction_management.api.boq_invoice import SO_DEDUCTION_ITEM_CODES
from construction_management.api.relink_si_sales_orders import (
	_merge_boq_ledger_row,
	_named_orders,
	_queue_gl_repost,
)
from construction_management.overrides.sales_invoice import DEDUCTION_ITEM_CODES, link_deduction_rows

DEDUCTIONS = frozenset(SO_DEDUCTION_ITEM_CODES) | frozenset(DEDUCTION_ITEM_CODES)


def run(dry_run: int = 1, invoices: list | str | None = None) -> list[dict]:
	"""Repair combined invoices (dry run default)."""
	if isinstance(invoices, str):
		invoices = [name.strip() for name in invoices.split(",") if name.strip()]
	names = invoices or _broken_invoice_names()
	report: list[dict] = []
	changed: list[str] = []
	for name in names:
		try:
			rows, repaired = _repair_invoice(name, dry_run=cint(dry_run))
			report.extend(rows)
			if repaired and not cint(dry_run):
				frappe.db.commit()
				changed.append(name)
		except Exception as error:
			frappe.db.rollback()
			report.append({"invoice": name, "result": f"error: {error}"})
	if changed:
		report.extend(_queue_gl_repost(changed))
	_print_report(report)
	return report


def _broken_invoice_names() -> list[str]:
	from construction_management.api.audit_combined_si_sales_orders import run as audit

	rows = audit()
	return [row["invoice"] for row in rows if row.get("is_broken")]


def _repair_invoice(name: str, dry_run: bool) -> tuple[list[dict], bool]:
	report: list[dict] = []
	si = frappe.get_doc("Sales Invoice", name)
	if si.docstatus != 1:
		report.append({"invoice": name, "result": "skipped: not submitted"})
		return report, False

	sources = _named_orders(si)
	if len(sources) < 2:
		report.append({"invoice": name, "result": "skipped: not a multi-source combined invoice"})
		return report, False

	splits = _plan_splits(si, sources)
	if not splits:
		report.append({"invoice": name, "result": "skipped: nothing to split"})
		return report, False

	if dry_run:
		for plan in splits:
			report.append(
				{
					"invoice": name,
					"action": "split",
					"sales_order": plan["sales_order"],
					"boq_item": plan["boq_item"],
					"qty": plan["qty"],
					"amount": plan["amount"],
					"so_detail": plan["so_detail"],
					"replaces_row": plan.get("replaces_row"),
				}
			)
		report.append({"invoice": name, "result": f"would apply {len(splits)} work line(s)"})
		return report, True

	_clear_wrong_ledger_tax_invoices(si, sources)
	_remove_deduction_rows(si, report)
	_apply_work_splits(si, splits, report)
	si.reload()
	link_deduction_rows(si.items)
	for row in si.items:
		if row.item_code in DEDUCTIONS and row.get("sales_order"):
			frappe.db.set_value(
				"Sales Invoice Item",
				row.name,
				{
					"sales_order": row.sales_order,
					"so_detail": row.so_detail,
				},
				update_modified=False,
			)

	if not cint(si.update_billed_amount_in_sales_order):
		frappe.db.set_value(
			"Sales Invoice",
			name,
			"update_billed_amount_in_sales_order",
			1,
			update_modified=False,
		)

	si.reload()
	si.update_prevdoc_status()

	for row in si.items:
		if row.item_code in DEDUCTIONS or not row.get("sales_order"):
			continue
		_merge_boq_ledger_row(si, row)
		_stamp_so_ledger_for_work_line(si, row)

	for so_name in sources:
		frappe.get_doc("Sales Order", so_name).set_status(update=True)

	report.append({"invoice": name, "result": f"repaired {len(splits)} work line(s)"})
	return report, True


def _plan_splits(si, sources: list[str]) -> list[dict]:
	"""One SI work row per source SO revenue line (same item_code, boq_item, uom)."""
	revenue_by_boq: dict[str, list] = {}
	for row in si.get("items") or []:
		if row.item_code in DEDUCTIONS or not row.get("boq_item"):
			continue
		revenue_by_boq.setdefault(row.boq_item, []).append(row)

	splits: list[dict] = []
	linked_sources = {
		row.sales_order
		for row in si.get("items") or []
		if row.get("sales_order") and row.item_code not in DEDUCTIONS
	}
	missing_sources = [so for so in sources if so not in linked_sources]

	for boq_item, rows in revenue_by_boq.items():
		needs_split = bool(missing_sources)
		for row in rows:
			if _row_over_billed(row):
				needs_split = True
				break
		if not needs_split:
			continue
		template = rows[0]
		so_lines = _source_so_lines(sources, boq_item, template.item_code, template.uom)
		if len(so_lines) < 2:
			continue

		first_row_name = template.name
		for index, line in enumerate(so_lines):
			splits.append(
				{
					"sales_order": line.parent,
					"boq_item": boq_item,
					"item_code": template.item_code,
					"qty": flt(line.qty),
					"rate": flt(line.rate),
					"amount": flt(line.amount),
					"so_detail": line.name,
					"uom": line.uom,
					"stock_uom": line.stock_uom or line.uom,
					"conversion_factor": flt(line.conversion_factor) or 1,
					"description": line.description or template.description,
					"bill_no": line.bill_no or template.bill_no,
					"income_account": template.income_account,
					"cost_center": template.cost_center,
					"project": template.project or si.project,
					"replaces_row": first_row_name if index == 0 else None,
					"template_name": template.name,
				}
			)
	return splits


def _source_so_lines(
	sources: list[str], boq_item: str, item_code: str, uom: str
) -> list[frappe._dict]:
	lines = []
	for so_name in sources:
		if not frappe.db.exists("Sales Order", so_name):
			continue
		so_line = frappe.db.get_value(
			"Sales Order Item",
			{
				"parent": so_name,
				"boq_item": boq_item,
				"item_code": item_code,
				"uom": uom,
			},
			["name", "parent", "qty", "rate", "amount", "uom", "stock_uom", "conversion_factor", "description", "bill_no"],
			as_dict=True,
		)
		if so_line and so_line.item_code not in DEDUCTIONS:
			lines.append(frappe._dict(so_line))
	return lines


def _remove_deduction_rows(si, report: list[dict]) -> None:
	for row in list(si.items):
		if row.item_code in DEDUCTIONS:
			report.append({"invoice": si.name, "action": "delete_deduction", "idx": row.idx})
			frappe.delete_doc("Sales Invoice Item", row.name, force=1, ignore_permissions=True)


def _apply_work_splits(si, splits: list[dict], report: list[dict]) -> None:
	by_template: dict[str, list[dict]] = {}
	for plan in splits:
		by_template.setdefault(plan["template_name"], []).append(plan)

	for template_name, plans in by_template.items():
		template = frappe.get_doc("Sales Invoice Item", template_name)
		for index, plan in enumerate(plans):
			values = {
				"item_code": plan["item_code"],
				"description": plan["description"],
				"qty": plan["qty"],
				"rate": plan["rate"],
				"amount": plan["amount"],
				"sales_order": plan["sales_order"],
				"so_detail": plan["so_detail"],
				"uom": plan["uom"],
				"stock_uom": plan["stock_uom"],
				"conversion_factor": plan["conversion_factor"],
				"stock_qty": plan["qty"] * plan["conversion_factor"],
				"boq_item": plan["boq_item"],
				"bill_no": plan["bill_no"],
				"project": plan["project"],
			}
			if index == 0:
				frappe.db.set_value(
					"Sales Invoice Item",
					template_name,
					{
						**values,
						"base_rate": plan["rate"],
						"base_amount": plan["amount"],
						"net_rate": plan["rate"],
						"net_amount": plan["amount"],
					},
					update_modified=False,
				)
				report.append(
					{"invoice": si.name, "action": "update_row", "sales_order": plan["sales_order"]}
				)
			else:
				child = frappe.copy_doc(template)
				child.update(
					{
						**values,
						"parent": si.name,
						"parenttype": "Sales Invoice",
						"parentfield": "items",
						"item_name": template.item_name or plan["item_code"],
						"idx": _next_item_idx(si.name),
						"base_rate": plan["rate"],
						"base_amount": plan["amount"],
						"net_rate": plan["rate"],
						"net_amount": plan["amount"],
					}
				)
				child.insert(ignore_permissions=True)
				report.append(
					{"invoice": si.name, "action": "insert_row", "sales_order": plan["sales_order"]}
				)

		_append_deductions_for_plans(si, plans, template, report)


def _append_deductions_for_plans(si, plans: list[dict], template, report: list[dict]) -> None:
	for plan in plans:
		so_deductions = frappe.get_all(
			"Sales Order Item",
			filters={
				"parent": plan["sales_order"],
				"boq_item": plan["boq_item"],
				"item_code": ["in", list(DEDUCTIONS)],
			},
			fields=["item_code", "rate", "amount", "name"],
		)
		for ded in so_deductions:
			row = frappe.copy_doc(template)
			row.update(
				{
					"parent": si.name,
					"parenttype": "Sales Invoice",
					"parentfield": "items",
					"idx": _next_item_idx(si.name),
					"item_code": ded.item_code,
					"item_name": ded.item_code,
					"qty": 1,
					"rate": flt(ded.rate),
					"amount": flt(ded.amount),
					"base_rate": flt(ded.rate),
					"base_amount": flt(ded.amount),
					"net_rate": flt(ded.rate),
					"net_amount": flt(ded.amount),
					"uom": "Nos",
					"stock_uom": "Nos",
					"conversion_factor": 1,
					"stock_qty": 1,
					"boq_item": plan["boq_item"],
					"bill_no": plan["bill_no"],
					"project": plan["project"],
					"sales_order": plan["sales_order"],
					"so_detail": ded.name,
					"description": ded.item_code,
				}
			)
			row.insert(ignore_permissions=True)
			report.append(
				{
					"invoice": si.name,
					"action": "insert_deduction",
					"sales_order": plan["sales_order"],
					"item_code": ded.item_code,
				}
			)


def _next_item_idx(parent: str) -> int:
	current = frappe.db.sql(
		"SELECT COALESCE(MAX(idx), 0) FROM `tabSales Invoice Item` WHERE parent = %s",
		parent,
	)[0][0]
	return int(current) + 1


def _clear_wrong_ledger_tax_invoices(si, sources: list[str]) -> None:
	"""Clear tax_invoice on source SO ledger rows so merge can re-allocate per SO line."""
	for so_name in sources:
		for name in frappe.get_all(
			"BOQ Progress Ledger",
			filters={
				"reference_doctype": "Sales Order",
				"reference_name": so_name,
				"tax_invoice": si.name,
			},
			pluck="name",
		):
			frappe.db.set_value(
				"BOQ Progress Ledger",
				name,
				{
					"tax_invoice": None,
					"tax_invoice_amount": 0,
					"source": "Order",
				},
				update_modified=False,
			)


def _stamp_so_ledger_for_work_line(si, row) -> None:
	"""Ensure each source SO ledger row references this invoice (when merge finds no SI ledger row)."""
	from construction_management.api.boq_ledger import recalculate_ledger_for_item

	ledger_name = frappe.db.get_value(
		"BOQ Progress Ledger",
		{
			"boq_item": row.boq_item,
			"reference_doctype": "Sales Order",
			"reference_name": row.sales_order,
		},
		"name",
	)
	if not ledger_name:
		return

	tax_rate = 0.0
	if hasattr(si, "get_effective_tax_rate"):
		tax_rate = flt(si.get_effective_tax_rate())
	elif si.get("taxes"):
		tax_rate = sum(flt(t.rate) for t in si.taxes) / 100

	retention = abs(
		frappe.db.get_value(
			"Sales Invoice Item",
			{
				"parent": si.name,
				"item_code": "RETENTION-DEDUCTION",
				"boq_item": row.boq_item,
				"sales_order": row.sales_order,
			},
			"amount",
		)
		or 0
	)
	base = flt(row.amount) + retention
	net_amount = base * (1 + tax_rate)
	if flt(si.get("discount_amount")) and flt(si.apply_discount_on) == "Grand Total":
		share = flt(row.amount) / sum(
			flt(r.amount)
			for r in si.items
			if r.item_code not in DEDUCTIONS and r.get("boq_item") == row.boq_item
		)
		net_amount = max(0, net_amount - flt(si.discount_amount) * share)

	frappe.db.set_value(
		"BOQ Progress Ledger",
		ledger_name,
		{
			"tax_invoice": si.name,
			"tax_invoice_amount": net_amount,
			"source": "Invoice",
			"amount": net_amount,
			"retention_amount": retention,
		},
		update_modified=False,
	)
	recalculate_ledger_for_item(row.boq_item)


def _row_over_billed(row) -> bool:
	if not row.get("so_detail"):
		return False
	so_line = frappe.db.get_value(
		"Sales Order Item",
		row.so_detail,
		["qty", "amount"],
		as_dict=True,
	)
	if not so_line:
		return False
	so_qty = so_line.get("qty") if isinstance(so_line, dict) else so_line.qty
	so_amount = so_line.get("amount") if isinstance(so_line, dict) else so_line.amount
	return flt(row.qty) > flt(so_qty) * 1.001 or flt(row.amount) > flt(so_amount) * 1.001


def _print_report(report: list[dict]) -> None:
	for entry in report:
		print(" | ".join(f"{k}={v}" for k, v in entry.items() if v is not None))