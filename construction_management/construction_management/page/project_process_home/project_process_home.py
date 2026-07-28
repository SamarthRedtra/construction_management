# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import cint, flt

from construction_management.api.boq_tasks import create_boq_item_with_task
from construction_management.construction_management.doctype.project_tab_access.project_tab_access import (
	get_user_project_scope,
)
from construction_management.overrides.project import get_project_contractor_name


STATUS_FILTERS = {
	"ongoing": ("Open",),
	"completed": ("Completed",),
	"all": None,
}


def _active_project_filters() -> dict:
	"""ERPNext Project.is_active is Yes/No, not 0/1."""
	return {"is_active": "Yes"}


def _apply_member_project_scope(filters: dict) -> list[str] | None:
	"""Apply Project Access selections to Member Home data queries."""
	scope = get_user_project_scope(frappe.session.user)
	if scope is not None:
		filters["name"] = ["in", scope]
	return scope


def _boq_item_optional_fields() -> list[str]:
	fields = []
	for fieldname in ("start_date", "end_date", "custom_skirting"):
		if frappe.db.exists("Custom Field", {"dt": "BOQ Item", "fieldname": fieldname}):
			fields.append(fieldname)
	return fields


@frappe.whitelist()
def get_project_process_home_data(
	status_filter: str = "ongoing",
	search: str = "",
	company: str = "",
	start: int = 0,
	page_length: int = 25,
	project_number_sort: str = "asc",
) -> dict:
	"""Return paginated project list for the member home page."""
	status_filter = (status_filter or "ongoing").lower()
	if status_filter not in STATUS_FILTERS:
		frappe.throw(_("Invalid status filter"))

	start = cint(start)
	page_length = max(1, min(cint(page_length) or 25, 100))
	project_number_sort = (project_number_sort or "asc").lower()
	if project_number_sort not in {"asc", "desc"}:
		frappe.throw(_("Project number sort must be ascending or descending"))

	filters = _active_project_filters()
	_apply_member_project_scope(filters)
	statuses = STATUS_FILTERS[status_filter]
	if statuses:
		filters["status"] = ["in", list(statuses)]

	if company:
		filters["company"] = company

	projects = frappe.get_all(
		"Project",
		filters=filters,
		fields=[
			"name",
			"company",
			"custom_project_no",
			"custom_sales_engineer",
			"custom_project_engineer",
			"customer",
			"contractor",
			"project_name",
			"custom_location",
			"custom_emirates",
			"status",
			"enable_progressive_boq",
		],
		order_by=f"custom_project_no {project_number_sort}, name {project_number_sort}",
	)

	employee_ids = {
		p.custom_sales_engineer for p in projects if p.custom_sales_engineer
	} | {p.custom_project_engineer for p in projects if p.custom_project_engineer}
	employee_names = _get_employee_names(list(employee_ids))
	contractor_names = {
		p.name: get_project_contractor_name(p)
		for p in projects
		if getattr(p, "customer", None) or getattr(p, "contractor", None)
	}

	if search:
		needle = search.strip().lower()
		projects = [
			p
			for p in projects
			if _project_matches_search(p, needle, employee_names, contractor_names)
		]

	total_count = len(projects)
	page = projects[start : start + page_length]

	rows = []
	for project in page:
		rows.append(
			{
				"name": project.name,
				"company": project.company or "",
				"project_no": project.custom_project_no or project.name,
				"sales_person": employee_names.get(project.custom_sales_engineer, ""),
				"assign_to": employee_names.get(project.custom_project_engineer, _("!Not Assign")),
				"contractor": contractor_names.get(project.name, ""),
				"project_name": project.project_name,
				"location": project.custom_location or "",
				"emirates": project.custom_emirates or "",
				"status": project.status,
				"enable_progressive_boq": cint(project.enable_progressive_boq),
			}
		)

	return {
		"projects": rows,
		"total_count": total_count,
		"start": start,
		"page_length": page_length,
	}


@frappe.whitelist()
def get_member_home_companies() -> list[dict]:
	"""Distinct companies from active projects for the member home filter."""
	filters = _active_project_filters()
	_apply_member_project_scope(filters)
	project_companies = frappe.get_all(
		"Project",
		filters=filters,
		fields=["company"],
		group_by="company",
		order_by="company asc",
	)
	company_names = [row.company for row in project_companies if row.company]
	if not company_names:
		return []

	companies = frappe.get_all(
		"Company",
		filters={"name": ["in", company_names]},
		fields=["name", "company_name"],
		order_by="company_name asc, name asc",
	)
	return [{"name": row.name, "company_name": row.company_name or row.name} for row in companies]


def _project_matches_search(project, needle: str, employee_names: dict, contractor_names: dict) -> bool:
	search_values = [
		project.custom_project_no,
		project.project_name,
		project.name,
		project.custom_location,
		project.custom_emirates,
		project.custom_sales_engineer,
		project.custom_project_engineer,
		project.customer,
		project.contractor,
		employee_names.get(project.custom_sales_engineer),
		employee_names.get(project.custom_project_engineer),
		contractor_names.get(project.name),
	]
	return any(needle in (value or "").lower() for value in search_values)


def _installment_exclusion_sql() -> str:
	"""Exclude payment-milestone BOQ rows (e.g. 1st Installment) from scope/process list."""
	return """
		AND LOWER(COALESCE(bi.description, '')) NOT LIKE '%%installment%%'
		AND LOWER(COALESCE(bi.item_code, '')) NOT LIKE '%%installment%%'
		AND LOWER(COALESCE(bi.label, '')) NOT LIKE '%%installment%%'
	"""


def _get_related_construction_project(project: str) -> str | None:
	"""Map billing-side projects (e.g. SKD-46 (SIDE)) to main construction project BOQ."""
	candidates = []
	if "(SIDE)" in project:
		candidates.append(project.replace("(SIDE)", "").strip())

	project_no = frappe.db.get_value("Project", project, "custom_project_no") or ""
	if project_no and "SIDE" in project_no.upper():
		base_no = project_no.split("(")[0].strip()
		match = frappe.db.get_value("Project", {"custom_project_no": base_no}, "name")
		if match:
			candidates.append(match)

	for candidate in candidates:
		if candidate and candidate != project and frappe.db.exists("Project", candidate):
			if _has_scope_boq_items(candidate):
				return candidate
	return None


def _has_scope_boq_items(project: str) -> bool:
	return bool(
		frappe.db.sql(
			f"""
			SELECT 1
			FROM `tabBOQ Item` bi
			WHERE bi.project = %s
			{_installment_exclusion_sql()}
			LIMIT 1
			""",
			project,
		)
	)


def _resolve_boq_source_project(project: str) -> str:
	if _has_scope_boq_items(project):
		return project
	related = _get_related_construction_project(project)
	return related or project


def _fetch_scope_boq_items(project: str) -> list[dict]:
	optional_fields = _boq_item_optional_fields()
	extra_select = "".join(f", bi.`{field}`" for field in optional_fields)

	return frappe.db.sql(
		f"""
		SELECT
			bi.name,
			bi.description,
			bi.label,
			bi.item_code,
			bi.total_qty,
			bi.unit,
			bi.parent_bill,
			bb.bill_no,
			bb.label AS bill_label,
			bb.sequence
			{extra_select}
		FROM `tabBOQ Item` bi
		INNER JOIN `tabBOQ Bill` bb ON bb.name = bi.parent_bill
		WHERE bi.project = %s
		{_installment_exclusion_sql()}
		ORDER BY bb.sequence ASC, bi.idx ASC, bi.creation ASC
		""",
		project,
		as_dict=True,
	)


@frappe.whitelist()
def get_project_process_rows(project: str) -> dict:
	"""Return construction BOQ Bill + BOQ Item rows (excludes payment installments)."""
	scope = get_user_project_scope(frappe.session.user)
	if scope is not None and project not in scope:
		frappe.throw(_("You do not have access to this project."), frappe.PermissionError)
	if not project:
		frappe.throw(_("Project is required"))

	if not frappe.db.exists("Project", project):
		frappe.throw(_("Project {0} does not exist").format(project))

	source_project = _resolve_boq_source_project(project)
	rows = _fetch_scope_boq_items(source_project)
	process_rows = [_boq_item_as_process_row(row) for row in rows]
	bills = _get_scope_boq_bills(source_project)

	return {
		"project": project,
		"boq_source_project": source_project,
		"processes": process_rows,
		"bills": bills,
	}


@frappe.whitelist()
def create_project_process_boq_item(
	project: str,
	parent_bill: str,
	description: str,
	total_qty: float = 0,
	unit: str = "m²",
	rate: float = 0,
	start_date: str = None,
	end_date: str = None,
	custom_skirting: float = 0,
) -> dict:
	"""Create a BOQ Item (process row) under a BOQ Bill — no ERPNext Task."""
	if not project or not parent_bill or not description:
		frappe.throw(_("Project, BOQ Bill, and Process Name are required"))

	bill_project = frappe.db.get_value("BOQ Bill", parent_bill, "project")
	source_project = _resolve_boq_source_project(project)
	if bill_project != source_project:
		frappe.throw(_("Selected BOQ Bill does not belong to this project's BOQ"))

	result = create_boq_item_with_task(
		parent_bill=parent_bill,
		description=description,
		unit=unit or "m²",
		total_qty=flt(total_qty),
		rate=flt(rate),
		is_task=0,
		start_date=start_date,
		end_date=end_date,
	)

	boq_item_name = result.get("boq_item")
	if boq_item_name and frappe.db.exists("Custom Field", {"dt": "BOQ Item", "fieldname": "custom_skirting"}):
		frappe.db.set_value("BOQ Item", boq_item_name, "custom_skirting", flt(custom_skirting))

	return result


def _get_scope_boq_bills(project: str) -> list[dict]:
	"""Return BOQ Bills that contain at least one non-installment scope item."""
	return frappe.db.sql(
		f"""
		SELECT DISTINCT
			bb.name,
			bb.bill_no,
			bb.label,
			bb.sequence
		FROM `tabBOQ Bill` bb
		INNER JOIN `tabBOQ Item` bi ON bi.parent_bill = bb.name
		WHERE bb.project = %s
		{_installment_exclusion_sql()}
		ORDER BY bb.sequence ASC, bb.creation ASC
		""",
		project,
		as_dict=True,
	)


def _get_project_boq_bills(project: str) -> list[dict]:
	return _get_scope_boq_bills(project)


def _boq_item_as_process_row(boq_item: dict) -> dict:
	start_date = boq_item.get("start_date")
	end_date = boq_item.get("end_date")

	return {
		"process_name": boq_item.get("description") or boq_item.get("label") or boq_item.get("name"),
		"area": flt(boq_item.get("total_qty")),
		"skirting": flt(boq_item.get("custom_skirting")),
		"unit": boq_item.get("unit") or "m²",
		"start_date": str(start_date) if start_date else None,
		"end_date": str(end_date) if end_date else None,
		"boq_item": boq_item.get("name"),
		"boq_bill": boq_item.get("parent_bill"),
		"bill_no": boq_item.get("bill_no") or "",
		"bill_label": boq_item.get("bill_label") or "",
		"doctype": "BOQ Item",
	}


def _get_employee_names(employee_ids: list) -> dict:
	employee_ids = list({e for e in employee_ids if e})
	if not employee_ids:
		return {}
	rows = frappe.get_all(
		"Employee",
		filters={"name": ["in", employee_ids]},
		fields=["name", "employee_name"],
	)
	return {row.name: row.employee_name for row in rows}


def _get_supplier_names(supplier_ids: list) -> dict:
	supplier_ids = list({s for s in supplier_ids if s})
	if not supplier_ids:
		return {}
	rows = frappe.get_all(
		"Supplier",
		filters={"name": ["in", supplier_ids]},
		fields=["name", "supplier_name"],
	)
	return {row.name: row.supplier_name for row in rows}
