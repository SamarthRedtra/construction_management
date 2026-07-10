# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document


TAB_FIELDNAMES = {
	"Details": "__details",
	"Connections": "connections_tab",
	"Construction": "construction_tab",
	"Costing": "costing_tab",
	"Progress": "monitor_progress_tab",
	"Project SOA": "project_soa_tab",
	"Project Commission": "project_commission_tab",
	"Dashboard": "custom_dashboard",
	"More Info": "more_info_tab",
}


class ProjectTabAccess(Document):
	def validate(self):
		for row in self.rules or []:
			if not row.role and not row.user:
				frappe.throw(
					_("Row {0}: Set either Role or User for tab {1}").format(row.idx, row.tab)
				)


@frappe.whitelist()
def get_project_tab_access_config() -> dict:
	"""Return tab access rules for the Project form."""
	settings = frappe.get_single("Project Tab Access")
	if not settings.enabled:
		return {"enabled": False, "restricted_tabs": {}}

	restricted_tabs: dict[str, list[dict]] = {}
	for row in settings.rules or []:
		fieldname = TAB_FIELDNAMES.get(row.tab)
		if not fieldname:
			continue
		restricted_tabs.setdefault(fieldname, []).append(
			{
				"tab": row.tab,
				"role": row.role or "",
				"user": row.user or "",
			}
		)

	return {
		"enabled": True,
		"restricted_tabs": restricted_tabs,
	}
