# Copyright (c) 2026, Construction Management
# License: MIT

"""Rename combined Tax Invoices that omit Project No in the document name.

Old: TINV/February26-May26-June26/1
New: TINV/1016/February26-May26-June26/1
"""

from __future__ import annotations

import frappe
from frappe.model.rename_doc import rename_doc
from frappe.utils import cstr


def execute():
	if not frappe.db.has_column("Sales Invoice", "custom_source_sales_orders"):
		return

	rows = frappe.db.sql(
		"""
		SELECT si.name, si.project, p.custom_project_no
		FROM `tabSales Invoice` si
		INNER JOIN `tabProject` p ON p.name = si.project
		WHERE si.docstatus != 2
			AND IFNULL(TRIM(si.custom_source_sales_orders), '') != ''
			AND si.name LIKE 'TINV/%%'
			AND IFNULL(p.custom_project_no, '') != ''
		""",
		as_dict=True,
	)

	for row in rows:
		old_name = row.name
		project_no = cstr(row.custom_project_no).strip()
		expected_prefix = f"TINV/{project_no}/"
		if old_name.startswith(expected_prefix):
			continue
		if not old_name.startswith("TINV/"):
			continue

		# TINV/{period…}/{n} → TINV/{project_no}/{period…}/{n}
		remainder = old_name[len("TINV/") :]
		new_name = f"TINV/{project_no}/{remainder}"
		if frappe.db.exists("Sales Invoice", new_name):
			frappe.logger("combined_tinv_rename").warning(
				f"skip {old_name}: target {new_name} already exists"
			)
			continue

		rename_doc(
			"Sales Invoice",
			old_name,
			new_name,
			force=True,
			merge=False,
			ignore_permissions=True,
			show_alert=False,
			rebuild_search=False,
		)
		frappe.db.commit()
