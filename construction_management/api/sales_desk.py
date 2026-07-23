# Copyright (c) 2026, Construction Management
# License: MIT

"""Sales Desk — employee-scoped Lead / Quotation / Project / Commission overview."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, get_first_day, getdate, today


@frappe.whitelist()
def get_sales_desk_data(company: str | None = None) -> dict:
	user = frappe.session.user
	employee = _get_employee_for_user(user)
	sales_person = _get_sales_person(employee) if employee else None

	is_manager = "Sales Manager" in frappe.get_roles(user) or user == "Administrator"
	# Pipeline KPIs: managers see company-wide; sales users see own Lead owner / Quotation owner.
	scope_all_pipeline = bool(is_manager)
	company = company or frappe.defaults.get_user_default("Company")
	from_date = get_first_day(today())
	to_date = getdate(today())

	lead_kpis = _lead_kpis(user, company, scope_all=scope_all_pipeline)
	quotation_kpis = _quotation_kpis(user, sales_person, company, scope_all=scope_all_pipeline)
	# Projects / commission always employee-scoped when Employee is linked.
	if employee:
		projects = _my_projects(employee, company)
	elif is_manager:
		projects = _all_open_sales_projects(company)
	else:
		projects = []
	commission = _commission_summary(sales_person, company, from_date, to_date, projects)

	# Funnel snapshot for tracking
	funnel = {
		"leads_open": lead_kpis.get("open", 0),
		"leads_quotation": lead_kpis.get("with_quotation", 0),
		"leads_agreed": lead_kpis.get("agreed", 0),
		"leads_converted": lead_kpis.get("converted", 0),
		"quotations_open": quotation_kpis.get("open", 0),
		"quotations_agreed": quotation_kpis.get("agreed", 0),
		"quotations_lost": quotation_kpis.get("lost", 0),
	}

	return {
		"user": user,
		"employee": employee,
		"employee_name": frappe.db.get_value("Employee", employee, "employee_name") if employee else None,
		"sales_person": sales_person,
		"is_sales_manager": is_manager,
		"company": company,
		"period": {"from_date": str(from_date), "to_date": str(to_date)},
		"leads": lead_kpis,
		"quotations": quotation_kpis,
		"funnel": funnel,
		"sales_person_pipeline": _sales_person_pipeline(
			company, sales_person=None if scope_all_pipeline else sales_person
		),
		"projects": projects,
		"commission": commission,
	}


def _get_employee_for_user(user: str) -> str | None:
	if not user or user == "Guest":
		return None
	return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")


def _get_sales_person(employee: str) -> str | None:
	if not employee:
		return None
	return frappe.db.get_value("Sales Person", {"employee": employee, "enabled": 1}, "name")


def _lead_kpis(user: str, company: str | None, scope_all: bool) -> dict:
	filters = {"docstatus": ["<", 2]}
	if company and frappe.db.has_column("Lead", "company"):
		filters["company"] = company
	if not scope_all:
		filters["lead_owner"] = user

	total = frappe.db.count("Lead", filters)
	open_count = frappe.db.count(
		"Lead", {**filters, "status": ["in", ["Lead", "Open", "Replied", "Interested"]]}
	)
	quotation_status = frappe.db.count("Lead", {**filters, "status": "Quotation"})
	agreed = frappe.db.count("Lead", {**filters, "status": "Agreed"})
	converted = frappe.db.count("Lead", {**filters, "status": "Converted"})
	lost = frappe.db.count(
		"Lead", {**filters, "status": ["in", ["Lost Quotation", "Do Not Contact"]]}
	)
	opportunity = frappe.db.count("Lead", {**filters, "status": "Opportunity"})

	by_status = _count_grouped("Lead", filters, "status")

	return {
		"total": total,
		"open": open_count,
		"with_quotation": quotation_status,
		"agreed": agreed,
		"converted": converted,
		"lost": lost,
		"opportunity": opportunity,
		"by_status": by_status,
	}


def _quotation_kpis(user: str, sales_person: str | None, company: str | None, scope_all: bool) -> dict:
	filters: dict = {}
	if company:
		filters["company"] = company
	if not scope_all:
		if sales_person and frappe.db.has_column("Quotation", "custom_sales_person"):
			filters["custom_sales_person"] = sales_person
		else:
			filters["owner"] = user

	draft = frappe.db.count("Quotation", {**filters, "docstatus": 0, "status": "Draft"})
	open_q = frappe.db.count(
		"Quotation",
		{
			**filters,
			"docstatus": 1,
			"status": [
				"in",
				[
					"Open",
					"Replied",
					"Pending Agreement",
					"Pending Sales Manager Approval",
					"Pending Director Approval",
					"Approved",
				],
			],
		},
	)
	# Customer accepted quote (custom Agreed) or already ordered
	agreed = frappe.db.count(
		"Quotation",
		{**filters, "docstatus": 1, "status": ["in", ["Agreed", "Ordered", "Partially Ordered"]]},
	)
	lost = frappe.db.count(
		"Quotation",
		{
			**filters,
			"docstatus": 1,
			"status": ["in", ["Lost", "Not Agreed", "Rejected by Sales Manager", "Rejected by Director"]],
		},
	)
	expired = frappe.db.count("Quotation", {**filters, "docstatus": 1, "status": "Expired"})
	submitted = frappe.db.count("Quotation", {**filters, "docstatus": 1})

	agreed_amount = 0.0
	open_amount = 0.0
	conditions = ["docstatus = 1"]
	values: dict = {}
	if company:
		conditions.append("company = %(company)s")
		values["company"] = company
	if not scope_all:
		if sales_person and frappe.db.has_column("Quotation", "custom_sales_person"):
			conditions.append("custom_sales_person = %(sales_person)s")
			values["sales_person"] = sales_person
		else:
			conditions.append("owner = %(owner)s")
			values["owner"] = user
	where = " AND ".join(conditions)
	agreed_amount = flt(
		frappe.db.sql(
			f"""
			SELECT COALESCE(SUM(base_grand_total), 0)
			FROM `tabQuotation`
			WHERE {where}
			  AND status IN ('Agreed', 'Ordered', 'Partially Ordered')
			""",
			values,
		)[0][0]
	)
	open_amount = flt(
		frappe.db.sql(
			f"""
			SELECT COALESCE(SUM(base_grand_total), 0)
			FROM `tabQuotation`
			WHERE {where}
			  AND status IN (
				'Open', 'Replied', 'Pending Agreement',
				'Pending Sales Manager Approval', 'Pending Director Approval', 'Approved'
			  )
			""",
			values,
		)[0][0]
	)

	by_status_filters = dict(filters)
	by_status_filters["docstatus"] = ["<", 2]
	by_status = _count_grouped("Quotation", by_status_filters, "status")

	return {
		"draft": draft,
		"open": open_q,
		"agreed": agreed,
		"lost": lost,
		"expired": expired,
		"submitted": submitted,
		"agreed_amount": agreed_amount,
		"open_amount": open_amount,
		"by_status": by_status,
	}


def _count_grouped(doctype: str, filters: dict, field: str) -> list[dict]:
	"""Return [{label, value}] for pie charts, skipping empty labels."""
	try:
		rows = frappe.get_all(
			doctype,
			filters=filters,
			fields=[field, "count(name) as cnt"],
			group_by=field,
			order_by="cnt desc",
		)
	except Exception:
		# Fallback if group_by unsupported in older path
		rows = []
		raw = frappe.get_all(doctype, filters=filters, fields=[field])
		counts: dict[str, int] = {}
		for r in raw:
			key = r.get(field) or _("Blank")
			counts[key] = counts.get(key, 0) + 1
		rows = [{field: k, "cnt": v} for k, v in counts.items()]

	out = []
	for r in rows:
		label = r.get(field) or _("Blank")
		value = cint(r.get("cnt"))
		if value:
			out.append({"label": label, "value": value})
	return out


def _sales_person_pipeline(company: str | None, sales_person: str | None = None) -> list[dict]:
	"""Lead, qualified-lead and quotation counts grouped by the tagged Sales Person."""
	if not frappe.db.has_column("Quotation", "custom_sales_person"):
		return []

	quotation_filters = {"docstatus": ["<", 2]}
	if company:
		quotation_filters["company"] = company
	if sales_person:
		quotation_filters["custom_sales_person"] = sales_person

	result: dict[str, dict] = {}
	for row in frappe.get_all(
		"Quotation",
		filters=quotation_filters,
		fields=["custom_sales_person", "base_grand_total"],
	):
		person = row.custom_sales_person or _("Unassigned")
		entry = result.setdefault(
			person,
			{"sales_person": person, "leads": 0, "qualified": 0, "quotations": 0, "quotation_amount": 0.0},
		)
		entry["quotations"] += 1
		entry["quotation_amount"] += flt(row.base_grand_total)

	lead_filters = {"docstatus": ["<", 2]}
	if company and frappe.db.has_column("Lead", "company"):
		lead_filters["company"] = company
	lead_fields = ["lead_owner", "status"]
	if frappe.db.has_column("Lead", "qualification_status"):
		lead_fields.append("qualification_status")
	lead_rows = frappe.get_all("Lead", filters=lead_filters, fields=lead_fields)
	user_sales_people = _sales_people_for_users({row.lead_owner for row in lead_rows if row.lead_owner})
	for row in lead_rows:
		person = user_sales_people.get(row.lead_owner) or _("Unassigned")
		if sales_person and person != sales_person:
			continue
		entry = result.setdefault(
			person,
			{"sales_person": person, "leads": 0, "qualified": 0, "quotations": 0, "quotation_amount": 0.0},
		)
		entry["leads"] += 1
		if getattr(row, "qualification_status", None) == "Qualified" or row.status in (
			"Agreed",
			"Converted",
			"Quotation",
		):
			# Treat progressed leads as "qualified" for the team graph
			if row.status in ("Agreed", "Converted") or getattr(row, "qualification_status", None) == "Qualified":
				entry["qualified"] += 1

	return sorted(result.values(), key=lambda row: (row["leads"] + row["quotations"], row["sales_person"]), reverse=True)


def _sales_people_for_users(users: set[str]) -> dict[str, str]:
	if not users:
		return {}
	employees = frappe.get_all(
		"Employee",
		filters={"user_id": ["in", list(users)], "status": "Active"},
		fields=["name", "user_id"],
	)
	if not employees:
		return {}
	person_by_employee = {
		row.employee: row.name
		for row in frappe.get_all(
			"Sales Person",
			filters={"employee": ["in", [employee.name for employee in employees]], "enabled": 1},
			fields=["name", "employee"],
		)
	}
	return {employee.user_id: person_by_employee[employee.name] for employee in employees if employee.name in person_by_employee}


def _my_projects(employee: str, company: str | None) -> list[dict]:
	if not employee:
		return []

	project_names = set()

	# Team roles
	team_projects = frappe.db.sql(
		"""
		SELECT DISTINCT parent
		FROM `tabProject Team Member`
		WHERE employee = %s
		  AND role IN ('Sales Manager', 'Salesman')
		  AND parenttype = 'Project'
		""",
		employee,
		pluck=True,
	)
	project_names.update(team_projects or [])

	# Legacy sales engineer
	legacy = frappe.get_all(
		"Project",
		filters={"custom_sales_engineer": employee, **({"company": company} if company else {})},
		pluck="name",
	)
	project_names.update(legacy or [])

	if not project_names:
		return []

	filters = {"name": ["in", list(project_names)]}
	if company:
		filters["company"] = company

	rows = frappe.get_all(
		"Project",
		filters=filters,
		fields=[
			"name",
			"project_name",
			"status",
			"customer",
			"company",
			"custom_sales_engineer",
		],
		order_by="modified desc",
		limit_page_length=50,
	)
	return rows


def _all_open_sales_projects(company: str | None) -> list[dict]:
	filters = {"status": ["not in", ["Cancelled", "Completed"]]}
	if company:
		filters["company"] = company
	return frappe.get_all(
		"Project",
		filters=filters,
		fields=["name", "project_name", "status", "customer", "company", "custom_sales_engineer"],
		order_by="modified desc",
		limit_page_length=30,
	)


def _commission_summary(
	sales_person: str | None,
	company: str | None,
	from_date,
	to_date,
	projects: list[dict],
) -> dict:
	result = {
		"sales_person": sales_person,
		"accrued_total": 0.0,
		"invoice_count": 0,
		"by_project": [],
		"from_date": str(from_date),
		"to_date": str(to_date),
	}
	if not sales_person:
		return result

	conditions = [
		"si.docstatus = 1",
		"IFNULL(si.is_return, 0) = 0",
		"st.sales_person = %(sales_person)s",
		"si.posting_date BETWEEN %(from_date)s AND %(to_date)s",
	]
	values = {
		"sales_person": sales_person,
		"from_date": from_date,
		"to_date": to_date,
	}
	if company:
		conditions.append("si.company = %(company)s")
		values["company"] = company

	rows = frappe.db.sql(
		f"""
		SELECT
			si.project,
			COUNT(DISTINCT si.name) AS invoice_count,
			COALESCE(SUM(st.incentives), 0) AS commission_amount
		FROM `tabSales Invoice` si
		INNER JOIN `tabSales Team` st
			ON st.parent = si.name AND st.parenttype = 'Sales Invoice'
		WHERE {" AND ".join(conditions)}
		GROUP BY si.project
		ORDER BY commission_amount DESC
		""",
		values,
		as_dict=True,
	)

	project_names = {p.name: p.project_name for p in (projects or [])}
	by_project = []
	total = 0.0
	invoices = 0
	for row in rows:
		amt = flt(row.commission_amount)
		total += amt
		invoices += cint(row.invoice_count)
		by_project.append(
			{
				"project": row.project,
				"project_name": project_names.get(row.project)
				or frappe.db.get_value("Project", row.project, "project_name")
				or row.project
				or _("No Project"),
				"invoice_count": cint(row.invoice_count),
				"commission_amount": amt,
			}
		)

	result["accrued_total"] = total
	result["invoice_count"] = invoices
	result["by_project"] = by_project
	return result


def cint(value) -> int:
	try:
		return int(flt(value))
	except Exception:
		return 0
