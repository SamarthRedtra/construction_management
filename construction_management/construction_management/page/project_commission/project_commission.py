# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _

from construction_management.api.project_commission_data import (
	build_commission_ledger,
	build_services,
	build_summary,
)


@frappe.whitelist()
def get_project_commission_data(project: str) -> dict:
	if not project:
		frappe.throw(_("Project is required"))

	services, total_project_value, boq_source_project = build_services(project)
	ledger_rows, meta = build_commission_ledger(project)
	summary = build_summary(project, ledger_rows)

	return {
		"services": services,
		"total_project_value": total_project_value,
		"boq_source_project": boq_source_project,
		"ledger": ledger_rows,
		"summary": summary,
		"meta": meta,
	}
