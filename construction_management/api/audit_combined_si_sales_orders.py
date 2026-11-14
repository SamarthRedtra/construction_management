"""Audit combined Tax Invoices whose item rows do not link every source Sales Order.

	bench --site <site> execute construction_management.api.audit_combined_si_sales_orders.run
	bench --site <site> execute construction_management.api.audit_combined_si_sales_orders.run --kwargs "{'project': '1171'}"
"""

from __future__ import annotations

import frappe
from frappe.utils import cint, flt

from construction_management.api.boq_invoice import SO_DEDUCTION_ITEM_CODES
from construction_management.api.relink_si_sales_orders import _named_orders

DEDUCTIONS = tuple(SO_DEDUCTION_ITEM_CODES)


def run(project: str | None = None, include_ok: int = 0) -> list[dict]:
	"""Return combined invoices where linked revenue SOs are fewer than source SOs."""
	if not frappe.db.has_column("Sales Invoice", "custom_source_sales_orders"):
		return []
	rows = _fetch_invoices(project)
	report = []
	for row in rows:
		entry = _analyse_invoice(row.name)
		if entry.get("is_broken") or cint(include_ok):
			report.append(entry)
	_print_report(report)
	return report


def _fetch_invoices(project: str | None) -> list[dict]:
	params: dict = {}
	project_clause = ""
	if project:
		params["project"] = project
		project_clause = "AND si.project = %(project)s"
	return frappe.db.sql(
		f"""
		SELECT si.name, si.project, si.custom_source_sales_orders
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
			AND IFNULL(si.is_return, 0) = 0
			AND IFNULL(TRIM(si.custom_source_sales_orders), '') != ''
			AND LOCATE(',', si.custom_source_sales_orders) > 0
			{project_clause}
		ORDER BY si.posting_date, si.name
		""",
		params,
		as_dict=True,
	)


def _analyse_invoice(name: str) -> dict:
	si = frappe.get_doc("Sales Invoice", name)
	sources = _named_orders(si)
	source_set = set(sources)
	revenue_rows = [
		row
		for row in si.items
		if row.item_code not in DEDUCTIONS and row.get("boq_item")
	]
	linked = {
		row.sales_order
		for row in revenue_rows
		if row.get("sales_order") and row.sales_order in source_set
	}
	missing = sorted(source_set - linked)
	extra_linked = sorted(
		{
			row.sales_order
			for row in revenue_rows
			if row.get("sales_order") and row.sales_order not in source_set
		}
	)
	aggregated = []
	for row in revenue_rows:
		if not row.get("sales_order"):
			continue
		so_line = frappe.db.get_value(
			"Sales Order Item",
			row.so_detail,
			["qty", "amount"],
			as_dict=True,
		)
		if so_line and (
			flt(row.qty) > flt(so_line.qty) * 1.001
			or flt(row.amount) > flt(so_line.amount) * 1.001
		):
			aggregated.append(
				{
					"idx": row.idx,
					"boq_item": row.boq_item,
					"sales_order": row.sales_order,
					"qty": row.qty,
					"amount": row.amount,
					"so_qty": so_line.qty,
					"so_amount": so_line.amount,
				}
			)

	is_broken = bool(missing or aggregated or extra_linked)
	suggestion = "ok"
	if missing or aggregated:
		suggestion = "repair_combined_si_sales_orders"
	elif extra_linked:
		suggestion = "review manually"

	return {
		"invoice": name,
		"project": si.project,
		"source_count": len(sources),
		"linked_count": len(linked),
		"sources": ", ".join(sources),
		"linked_sales_orders": ", ".join(sorted(linked)),
		"missing_sales_orders": ", ".join(missing),
		"extra_sales_orders": ", ".join(extra_linked),
		"revenue_rows": len(revenue_rows),
		"aggregated_rows": len(aggregated),
		"is_broken": is_broken,
		"suggestion": suggestion,
	}


def _print_report(report: list[dict]) -> None:
	headers = (
		"invoice",
		"source_count",
		"linked_count",
		"missing_sales_orders",
		"aggregated_rows",
		"suggestion",
	)
	print(" | ".join(headers))
	for row in report:
		print(" | ".join(str(row.get(h) or "") for h in headers))
	print(f"\nTotal: {len(report)} (broken: {sum(1 for r in report if r.get('is_broken'))})")