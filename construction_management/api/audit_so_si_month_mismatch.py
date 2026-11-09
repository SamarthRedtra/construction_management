"""Readonly audit of Sales Order ↔ Sales Invoice Connections with a large month gap.

ERPNext Connections use `Sales Invoice Item.sales_order` and the reverse Link
`Sales Invoice.custom_sales_order`. A gap of two or more months can be legitimate
late conversion or a wrong link — this script only reports.

	bench --site <site> execute construction_management.api.audit_so_si_month_mismatch.run
	bench --site <site> execute construction_management.api.audit_so_si_month_mismatch.run --kwargs "{'min_month_gap': 3, 'project': '1169'}"
"""

from __future__ import annotations

import frappe
from frappe.utils import cint


def run(min_month_gap: int = 2, project: str | None = None) -> list[dict]:
	"""List submitted SO↔SI pairs whose dates differ by at least `min_month_gap` months."""
	gap = max(cint(min_month_gap), 1)
	rows = _fetch_pairs(gap, project)
	_print_report(rows)
	return rows


def _fetch_pairs(min_month_gap: int, project: str | None) -> list[dict]:
	has_sources = frappe.db.has_column("Sales Invoice", "custom_source_sales_orders")
	params: dict = {"min_gap": min_month_gap}
	project_clause = ""
	if project:
		params["project"] = project
		project_clause = "AND IFNULL(si.project, so.project) = %(project)s"

	sources_expr = (
		"IFNULL(si.custom_source_sales_orders, '')"
		if has_sources
		else "''"
	)

	return frappe.db.sql(
		f"""
		SELECT
			IFNULL(si.project, so.project) AS project,
			so.name AS sales_order,
			so.transaction_date AS so_date,
			si.name AS sales_invoice,
			si.posting_date AS si_date,
			TIMESTAMPDIFF(MONTH, so.transaction_date, si.posting_date) AS month_gap,
			CASE WHEN IFNULL(si.custom_sales_order, '') = so.name THEN 1 ELSE 0 END AS header_link,
			CASE WHEN EXISTS (
				SELECT 1 FROM `tabSales Invoice Item` sii
				WHERE sii.parent = si.name AND sii.sales_order = so.name
			) THEN 1 ELSE 0 END AS line_link,
			{sources_expr} AS custom_source_sales_orders,
			CASE WHEN {sources_expr} != '' THEN 1 ELSE 0 END AS is_combined
		FROM `tabSales Order` so
		INNER JOIN (
			SELECT DISTINCT parent AS sales_invoice, sales_order
			FROM `tabSales Invoice Item`
			WHERE IFNULL(sales_order, '') != ''
			UNION
			SELECT name AS sales_invoice, custom_sales_order AS sales_order
			FROM `tabSales Invoice`
			WHERE IFNULL(custom_sales_order, '') != ''
		) link ON link.sales_order = so.name
		INNER JOIN `tabSales Invoice` si ON si.name = link.sales_invoice
		WHERE so.docstatus = 1
			AND si.docstatus = 1
			AND IFNULL(si.is_return, 0) = 0
			AND so.transaction_date IS NOT NULL
			AND si.posting_date IS NOT NULL
			AND ABS(TIMESTAMPDIFF(MONTH, so.transaction_date, si.posting_date)) >= %(min_gap)s
			{project_clause}
		ORDER BY ABS(TIMESTAMPDIFF(MONTH, so.transaction_date, si.posting_date)) DESC,
			si.posting_date,
			so.name
		""",
		params,
		as_dict=True,
	)


def _print_report(rows: list[dict]) -> None:
	headers = (
		"project",
		"sales_order",
		"so_date",
		"sales_invoice",
		"si_date",
		"month_gap",
		"header_link",
		"line_link",
		"is_combined",
		"custom_source_sales_orders",
	)
	print(" | ".join(headers))
	print(" | ".join("-" * len(h) for h in headers))
	for row in rows:
		print(" | ".join(str(row.get(key) if row.get(key) is not None else "") for key in headers))
	print(f"\nTotal pairs: {len(rows)}")
