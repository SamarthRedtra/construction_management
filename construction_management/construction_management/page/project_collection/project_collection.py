# Copyright (c) 2026, Construction Management
# License: MIT

import json

import frappe
from frappe import _

from construction_management.api.project_collection_data import (
	get_collection_portfolio as _get_collection_portfolio,
	get_collection_project_rows,
)
from construction_management.construction_management.page.project_soa.project_soa import (
	create_project_soa_follow_up,
)


@frappe.whitelist()
def get_collection_portfolio(company: str, filters: str | dict | None = None) -> list[dict]:
	if not company:
		frappe.throw(_("Company is required"))

	if isinstance(filters, str):
		filters = json.loads(filters) if filters else {}
	filters = filters or {}

	return _get_collection_portfolio(company, filters)


@frappe.whitelist()
def get_collection_project_detail(project: str) -> dict:
	if not project:
		frappe.throw(_("Project is required"))

	return get_collection_project_rows(project)
