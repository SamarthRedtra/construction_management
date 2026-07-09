# Copyright (c) 2026, Construction Management
# License: MIT

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from construction_management.api.bulk_material_issue import (
	create_material_issues,
	get_eligible_sources,
)


class BulkMaterialIssueTool(Document):
	pass


@frappe.whitelist()
def fetch_eligible_sources(
	company,
	source_type="Both",
	project=None,
	from_date=None,
	to_date=None,
	posting_date_override=None,
	selected_sources=None,
	hide_zero_stock=1,
):
	return get_eligible_sources(
		company=company,
		source_type=source_type,
		project=project,
		from_date=from_date,
		to_date=to_date,
		posting_date_override=posting_date_override,
		selected_sources=selected_sources,
		hide_zero_stock=hide_zero_stock,
	)


@frappe.whitelist()
def process_bulk_material_issues(company, action_type, rows, posting_date_override=None):
	if not company:
		frappe.throw(_("Company is mandatory"))
	if not rows:
		frappe.throw(_("No rows to process"))

	rows_list = json.loads(rows) if isinstance(rows, str) else rows
	submit = 0 if action_type == "Save as Draft" else 1

	payload = []
	for row in rows_list:
		qty = flt(row.get("qty_to_issue"))
		if qty <= 0:
			continue
		payload.append(
			{
				"source_doctype": row.get("source_doctype"),
				"source_name": row.get("source_name"),
				"source_posting_date": row.get("source_posting_date"),
				"source_line_name": row.get("source_line_name"),
				"company": company,
				"item_code": row.get("item_code"),
				"warehouse": row.get("warehouse"),
				"qty_to_issue": qty,
				"project": row.get("project"),
				"boq_item": row.get("boq_item"),
				"bill_no": row.get("bill_no"),
			}
		)

	if not payload:
		frappe.throw(_("All selected rows have zero quantity"))

	return create_material_issues(payload, submit=submit, posting_date_override=posting_date_override)
