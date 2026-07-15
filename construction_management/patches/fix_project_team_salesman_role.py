# Copyright (c) 2026, Construction Management
# License: MIT

import frappe


def execute():
	_fix_sales_manager_to_salesman()
	frappe.clear_cache(doctype="Project")


def _fix_sales_manager_to_salesman():
	rows = frappe.db.sql(
		"""
		SELECT ptm.name, ptm.parent, ptm.employee, p.custom_sales_engineer
		FROM `tabProject Team Member` ptm
		INNER JOIN `tabProject` p ON p.name = ptm.parent
		WHERE ptm.role = 'Sales Manager'
			AND p.custom_sales_engineer = ptm.employee
		""",
		as_dict=True,
	)
	for row in rows:
		frappe.db.set_value("Project Team Member", row.name, "role", "Salesman", update_modified=False)
