# Copyright (c) 2026, Construction Management
# License: MIT

import frappe


LEGACY_FIELD_MAP = (
	("custom_sales_engineer", "Salesman"),
	("custom_project_engineer", "Engineer"),
)


def execute():
	backfill_team_member_names()
	sync_legacy_assignments()
	frappe.clear_cache(doctype="Project")


def backfill_team_member_names():
	rows = frappe.db.sql(
		"""
		SELECT ptm.name, ptm.employee, ptm.employee_name, ptm.designation
		FROM `tabProject Team Member` ptm
		WHERE ptm.employee IS NOT NULL
			AND (IFNULL(ptm.employee_name, '') = '' OR IFNULL(ptm.designation, '') = '')
		""",
		as_dict=True,
	)
	for row in rows:
		emp = frappe.db.get_value(
			"Employee",
			row.employee,
			["employee_name", "designation"],
			as_dict=True,
		)
		if not emp:
			continue
		frappe.db.set_value(
			"Project Team Member",
			row.name,
			{
				"employee_name": emp.employee_name,
				"designation": emp.designation,
			},
			update_modified=False,
		)


def sync_legacy_assignments():
	projects = frappe.get_all(
		"Project",
		fields=["name", "custom_sales_engineer", "custom_project_engineer"],
	)
	for project in projects:
		doc = frappe.get_doc("Project", project.name)
		changed = False

		for fieldname, role in LEGACY_FIELD_MAP:
			employee = project.get(fieldname)
			if not employee:
				continue

			team_rows = doc.get("custom_project_team") or []

			for row in team_rows:
				if (
					fieldname == "custom_sales_engineer"
					and row.role == "Sales Manager"
					and row.employee == employee
				):
					row.role = "Salesman"
					changed = True

			if not any(row.role == role and row.employee == employee for row in team_rows):
				emp = frappe.db.get_value(
					"Employee",
					employee,
					["employee_name", "designation"],
					as_dict=True,
				) or {}
				doc.append(
					"custom_project_team",
					{
						"role": role,
						"employee": employee,
						"employee_name": emp.get("employee_name"),
						"designation": emp.get("designation"),
					},
				)
				changed = True
				continue

			role_row = next((row for row in team_rows if row.role == role), None)
			if role_row and not role_row.employee_name:
				emp = frappe.db.get_value(
					"Employee",
					role_row.employee,
					["employee_name", "designation"],
					as_dict=True,
				) or {}
				role_row.employee_name = emp.get("employee_name")
				role_row.designation = emp.get("designation")
				changed = True

		if changed:
			doc.flags.ignore_validate = True
			doc.save(ignore_permissions=True)
