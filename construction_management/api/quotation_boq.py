# Copyright (c) 2026, Construction Management
# License: MIT

"""API helpers for BOQ-style Quotation HTML content."""

from __future__ import annotations

import html

import frappe
from frappe.utils import flt


BOQ_TABLE_STYLE = (
	"width:100%;border-collapse:collapse;font-family:Arial,Helvetica,sans-serif;font-size:11px;"
)
BOQ_CELL_STYLE = "border:1px solid #333;padding:5px 7px;vertical-align:top;"
BOQ_HEAD_STYLE = BOQ_CELL_STYLE + "background:#e8e8e8;font-weight:bold;text-align:center;"
BOQ_SECTION_STYLE = BOQ_CELL_STYLE + "font-weight:bold;text-transform:uppercase;background:#f0f0f0;"
BOQ_NUM_STYLE = BOQ_CELL_STYLE + "text-align:right;"


@frappe.whitelist()
def get_boq_html_template() -> str:
	"""Return a starter BOQ HTML table users can edit in the Text Editor."""
	return _render_boq_html([], include_totals=True, template_only=True)


@frappe.whitelist()
def import_boq_lines_from_estimation(estimation_name: str) -> list[dict]:
	"""Build Quotation BOQ Line rows from Project Estimation (grouped by task)."""
	if not estimation_name:
		frappe.throw("Project Estimation is required")

	if not frappe.db.exists("Project Estimation", estimation_name):
		frappe.throw(f"Project Estimation {estimation_name} not found")

	estimation = frappe.get_doc("Project Estimation", estimation_name)
	source_items = _get_estimation_source_items(estimation)

	lines: list[dict] = []
	parent_counter = 0
	current_task = object()

	for item in source_items:
		task_name = (item.get("task") or item.get("activity_type") or "General").strip()
		if task_name != current_task:
			current_task = task_name
			lines.append(
				{
					"line_type": "Section",
					"section_title": task_name,
					"description": task_name,
				}
			)
			parent_counter = 0

		parent_counter += 1
		lines.append(
			{
				"line_type": "Parent",
				"section_title": task_name,
				"parent_no": str(parent_counter),
				"description": _estimation_item_description(item),
			}
		)

	return lines


@frappe.whitelist()
def import_boq_html_from_estimation(estimation_name: str) -> str:
	"""Build BOQ HTML from Project Estimation (for print / legacy)."""
	lines = import_boq_lines_from_estimation(estimation_name)
	return lines_to_boq_html(lines, include_totals=True)


def lines_to_boq_html(lines: list, include_totals: bool = True) -> str:
	"""Convert Quotation BOQ Line child rows to print HTML."""
	ordered = sorted(lines, key=lambda row: getattr(row, "idx", None) or row.get("idx") or 0)
	rows: list[dict] = []
	total_excl = 0.0

	for row in ordered:
		line_type = row.get("line_type") if isinstance(row, dict) else getattr(row, "line_type", None)
		if line_type == "Section":
			title = (row.get("section_title") or row.get("description") or "").strip()
			rows.append({"kind": "section", "title": title})
		elif line_type == "Parent":
			rows.append(
				{
					"kind": "parent",
					"parent_no": row.get("parent_no") or getattr(row, "parent_no", ""),
					"description": row.get("description") or getattr(row, "description", ""),
				}
			)
		elif line_type == "Sub":
			display_mode = (
				row.get("display_mode")
				if isinstance(row, dict)
				else getattr(row, "display_mode", "Normal")
			) or "Normal"
			amount = flt(row.get("amount") if isinstance(row, dict) else getattr(row, "amount", 0))
			qty = flt(row.get("qty") if isinstance(row, dict) else getattr(row, "qty", 0))
			rate = flt(row.get("rate") if isinstance(row, dict) else getattr(row, "rate", 0))
			if display_mode == "Normal" and not amount:
				amount = qty * rate
			if display_mode == "Normal":
				total_excl += amount
			rows.append(
				{
					"kind": "sub",
					"sub_no": row.get("sub_no") or getattr(row, "sub_no", ""),
					"description": row.get("description") or getattr(row, "description", ""),
					"uom": row.get("uom") or getattr(row, "uom", ""),
					"qty": qty,
					"rate": rate if display_mode != "N/A" else "-",
					"amount": amount,
					"display_mode": display_mode,
				}
			)

	return _render_boq_html(rows, include_totals=include_totals, total_excl=total_excl)


def _render_boq_html(
	rows: list[dict],
	include_totals: bool = True,
	template_only: bool = False,
	total_excl: float = 0.0,
) -> str:
	if template_only:
		rows = [
			{"kind": "section", "title": "THERMAL AND MOISTURE PROTECTION TO SUBSTRUCTURE"},
			{
				"kind": "parent",
				"parent_no": "1",
				"description": "One layer of 1000 gauge polythene sheets; all in accordance with the drawings and specification",
			},
			{
				"kind": "sub",
				"sub_no": "A",
				"description": "To Raft Slab",
				"uom": "m2",
				"qty": "2,259.00",
				"rate": "-",
				"amount": "N/A",
			},
			{
				"kind": "sub",
				"sub_no": "B",
				"description": "Below Grade Slab",
				"uom": "m2",
				"qty": "1,800.00",
				"rate": "-",
				"amount": "N/A",
			},
			{
				"kind": "parent",
				"parent_no": "2",
				"description": "2 layers of 4mm thick SBS waterproofing membrane 180gm/m2 from Awazel or Equivalent",
			},
			{
				"kind": "sub",
				"sub_no": "A",
				"description": "Horizontally to Raft Slab",
				"uom": "m2",
				"qty": "2,184.00",
				"rate": "62.00",
				"amount": "135,408.00",
			},
		]

	body_rows = []
	for row in rows:
		kind = row.get("kind")
		if kind == "section":
			body_rows.append(
				f'<tr><td style="{BOQ_CELL_STYLE}"></td>'
				f'<td colspan="5" style="{BOQ_SECTION_STYLE}">{html.escape(row.get("title") or "")}</td></tr>'
			)
		elif kind == "parent":
			parent_no = html.escape(str(row.get("parent_no") or ""))
			desc = html.escape(row.get("description") or "")
			body_rows.append(
				f'<tr><td style="{BOQ_CELL_STYLE};text-align:center;">{parent_no}-</td>'
				f'<td colspan="5" style="{BOQ_CELL_STYLE};font-weight:bold;">{desc}</td></tr>'
			)
		elif kind == "sub":
			sub_no = html.escape(str(row.get("sub_no") or ""))
			desc = html.escape(row.get("description") or "")
			uom = html.escape(str(row.get("uom") or ""))
			qty = _format_cell(row.get("qty"))
			rate = _format_cell(row.get("rate"))
			amount = _format_amount_cell(row)
			body_rows.append(
				f'<tr><td style="{BOQ_CELL_STYLE};text-align:center;">{sub_no}.</td>'
				f'<td style="{BOQ_CELL_STYLE};padding-left:18px;">{desc}</td>'
				f'<td style="{BOQ_CELL_STYLE};text-align:center;">{uom}</td>'
				f'<td style="{BOQ_NUM_STYLE}">{qty}</td>'
				f'<td style="{BOQ_NUM_STYLE}">{rate}</td>'
				f'<td style="{BOQ_NUM_STYLE}">{amount}</td></tr>'
			)

	table_html = f"""
<table style="{BOQ_TABLE_STYLE}">
	<thead>
		<tr>
			<th style="{BOQ_HEAD_STYLE}">SL No.</th>
			<th style="{BOQ_HEAD_STYLE}">Description of Works</th>
			<th style="{BOQ_HEAD_STYLE}">Unit</th>
			<th style="{BOQ_HEAD_STYLE}">Approx. QTY.</th>
			<th style="{BOQ_HEAD_STYLE}">Rate AED</th>
			<th style="{BOQ_HEAD_STYLE}">Amount AED</th>
		</tr>
	</thead>
	<tbody>
		{''.join(body_rows)}
	</tbody>
</table>
""".strip()

	if not include_totals:
		return table_html

	vat = flt(total_excl) * 0.05
	incl = flt(total_excl) + vat
	totals_html = f"""
<table style="width:55%;margin-left:auto;border-collapse:collapse;{BOQ_TABLE_STYLE}">
	<tr>
		<td style="{BOQ_CELL_STYLE};font-weight:bold;text-align:right;">Total Amount Excl. VAT</td>
		<td style="{BOQ_NUM_STYLE}">{html.escape(f"{flt(total_excl):,.2f}")}</td>
	</tr>
	<tr>
		<td style="{BOQ_CELL_STYLE};font-weight:bold;text-align:right;">5% VAT</td>
		<td style="{BOQ_NUM_STYLE}">{html.escape(f"{vat:,.2f}")}</td>
	</tr>
	<tr>
		<td style="{BOQ_CELL_STYLE};font-weight:bold;text-align:right;">Total Amount Incl. VAT</td>
		<td style="{BOQ_NUM_STYLE}">{html.escape(f"{incl:,.2f}")}</td>
	</tr>
</table>
<p><br></p>
""".strip()

	return f"{table_html}\n{totals_html}"


def _format_cell(value) -> str:
	if value in (None, ""):
		return ""
	if isinstance(value, (int, float)):
		return html.escape(f"{flt(value):,.2f}")
	return html.escape(str(value))


def _format_amount_cell(row: dict) -> str:
	display_mode = row.get("display_mode") or "Normal"
	if display_mode == "N/A":
		return "N/A"
	if display_mode == "Rate Only":
		return "Rate only"
	return _format_cell(row.get("amount"))


def _get_estimation_source_items(estimation) -> list[dict]:
	boq_name = frappe.db.get_value(
		"Bill of Quantity",
		{"project_estimation": estimation.name},
		"name",
	)
	if boq_name:
		boq = frappe.get_doc("Bill of Quantity", boq_name)
		return [row.as_dict() for row in boq.get("items") or []]

	return [row.as_dict() for row in estimation.get("items") or []]


def _estimation_item_description(item: dict) -> str:
	parts = []
	for key in ("item", "activity_type", "task", "description"):
		value = item.get(key)
		if value:
			parts.append(str(value))
	return " - ".join(dict.fromkeys(parts)) if parts else "Item"
