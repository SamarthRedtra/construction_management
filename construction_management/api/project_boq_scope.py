# Copyright (c) 2026, Construction Management
# License: MIT

"""Shared BOQ scope helpers — exclude payment installments, resolve SIDE projects."""

import frappe


def installment_exclusion_sql() -> str:
	return """
		AND LOWER(COALESCE(bi.description, '')) NOT LIKE '%%installment%%'
		AND LOWER(COALESCE(bi.item_code, '')) NOT LIKE '%%installment%%'
		AND LOWER(COALESCE(bi.label, '')) NOT LIKE '%%installment%%'
	"""


def get_related_construction_project(project: str) -> str | None:
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
			if has_scope_boq_items(candidate):
				return candidate
	return None


def has_scope_boq_items(project: str) -> bool:
	return bool(
		frappe.db.sql(
			f"""
			SELECT 1
			FROM `tabBOQ Item` bi
			WHERE bi.project = %s
			{installment_exclusion_sql()}
			LIMIT 1
			""",
			project,
		)
	)


def resolve_boq_source_project(project: str) -> str:
	if has_scope_boq_items(project):
		return project
	related = get_related_construction_project(project)
	return related or project


def fetch_scope_boq_items(project: str, extra_fields: list[str] | None = None) -> list[dict]:
	extra_fields = extra_fields or []
	extra_select = "".join(f", bi.`{field}`" for field in extra_fields if field)

	return frappe.db.sql(
		f"""
		SELECT
			bi.name,
			bi.description,
			bi.label,
			bi.item_code,
			bi.total_qty,
			bi.rate,
			bi.total_amount,
			bi.unit,
			bi.parent_bill
			{extra_select}
		FROM `tabBOQ Item` bi
		WHERE bi.project = %s
		{installment_exclusion_sql()}
		ORDER BY bi.idx ASC, bi.creation ASC
		""",
		project,
		as_dict=True,
	)
