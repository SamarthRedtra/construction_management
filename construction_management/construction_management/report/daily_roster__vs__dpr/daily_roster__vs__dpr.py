# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"fieldname": "roster_id",
			"label": _("Roster ID"),
			"fieldtype": "Link",
			"options": "Daily Roster",
			"width": 150,
		},
		{
			"fieldname": "date",
			"label": _("Date"),
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 180,
		},
		{
			"fieldname": "engineer",
			"label": _("Engineer"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 140,
		},
		{
			"fieldname": "custom_engineer_name",
			"label": _("Engineer Name"),
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"fieldname": "custom_foreman",
			"label": _("Foreman"),
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"fieldname": "custom_total_workers",
			"label": _("Total Workers"),
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"fieldname": "site",
			"label": _("Site"),
			"fieldtype": "Link",
			"options": "Project Sites",
			"width": 150,
		},
		{
			"fieldname": "dpr_id",
			"label": _("DPR ID"),
			"fieldtype": "Link",
			"options": "Daily Progress Record",
			"width": 150,
		},
		{
			"fieldname": "dpr_status",
			"label": _("Status"),
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"fieldname": "roster_created",
			"label": _("Roster Created"),
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"fieldname": "dpr_created",
			"label": _("DPR Created"),
			"fieldtype": "Data",
			"width": 110,
		},
	]


def get_data(filters):
	conditions = get_conditions(filters)
	roster_engineer_name_expr = get_roster_engineer_name_expression()
	roster_foreman_expr = get_roster_foreman_expression()
	roster_total_workers_expr = get_roster_total_workers_expression()

	return frappe.db.sql(
		f"""
		SELECT
			dr.name AS roster_id,
			dr.date,
			dr.project,
			dr.engineer,
			{roster_engineer_name_expr},
			{roster_foreman_expr},
			{roster_total_workers_expr},
			dpr.project_sites AS site,
			dpr.name AS dpr_id,
			dpr.status AS dpr_status,
			'Yes' AS roster_created,
			CASE
				WHEN dpr.name IS NULL THEN 'No'
				ELSE 'Yes'
			END AS dpr_created
		FROM `tabDaily Roster` dr
		LEFT JOIN `tabDaily Progress Record` dpr
			ON dpr.date = dr.date
			AND dpr.project = dr.project
		LEFT JOIN `tabEmployee` eng
			ON eng.name = dr.engineer
		WHERE dr.docstatus = 1
			{conditions['roster']}

		UNION ALL

		SELECT
			NULL AS roster_id,
			dpr.date,
			dpr.project,
			NULL AS engineer,
			'' AS custom_engineer_name,
			'' AS custom_foreman,
			0 AS custom_total_workers,
			dpr.project_sites AS site,
			dpr.name AS dpr_id,
			dpr.status AS dpr_status,
			'No' AS roster_created,
			'Yes' AS dpr_created
		FROM `tabDaily Progress Record` dpr
		LEFT JOIN `tabDaily Roster` dr
			ON dr.date = dpr.date
			AND dr.project = dpr.project
			AND dr.docstatus = 1
		WHERE dr.name IS NULL
			{conditions['dpr']}

		ORDER BY date ASC
		""",
		filters,
		as_dict=True,
	)


def get_conditions(filters):
	roster_conditions = []
	dpr_conditions = []

	if filters.get("from_date"):
		roster_conditions.append("AND dr.date >= %(from_date)s")
		dpr_conditions.append("AND dpr.date >= %(from_date)s")

	if filters.get("to_date"):
		roster_conditions.append("AND dr.date <= %(to_date)s")
		dpr_conditions.append("AND dpr.date <= %(to_date)s")

	if filters.get("project"):
		roster_conditions.append("AND dr.project = %(project)s")
		dpr_conditions.append("AND dpr.project = %(project)s")

	if filters.get("site"):
		roster_conditions.append("AND dpr.project_sites = %(site)s")
		dpr_conditions.append("AND dpr.project_sites = %(site)s")

	return {
		"roster": " ".join(roster_conditions),
		"dpr": " ".join(dpr_conditions),
	}


def get_roster_engineer_name_expression():
	if frappe.db.has_column("Daily Roster", "custom_engineer_name"):
		return "COALESCE(dr.custom_engineer_name, eng.employee_name, '') AS custom_engineer_name"

	return "COALESCE(eng.employee_name, '') AS custom_engineer_name"


def get_roster_foreman_expression():
	if frappe.db.has_column("Daily Roster", "custom_foreman"):
		return "COALESCE(dr.custom_foreman, '') AS custom_foreman"

	return "'' AS custom_foreman"


def get_roster_total_workers_expression():
	worker_count_sql = """
		(
			SELECT COUNT(*)
			FROM `tabRoster Employee Child` rec
			WHERE rec.parent = dr.name
				AND rec.parenttype = 'Daily Roster'
				AND rec.parentfield = 'workers'
		)
	"""

	if frappe.db.has_column("Daily Roster", "custom_total_workers"):
		return (
			f"COALESCE(dr.custom_total_workers, {worker_count_sql}, 0) "
			"AS custom_total_workers"
		)

	return f"COALESCE({worker_count_sql}, 0) AS custom_total_workers"
