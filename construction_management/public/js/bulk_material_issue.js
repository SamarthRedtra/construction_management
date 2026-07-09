// Copyright (c) 2026, Construction Management
// License: MIT

frappe.provide("construction_management.bulk_material_issue");

construction_management.bulk_material_issue.open_tool = function (selected_sources, defaults = {}) {
	frappe.set_route("Form", "Bulk Material Issue Tool").then(() => {
		const frm = cur_frm;
		if (!frm) {
			return;
		}

		frm.selected_sources = selected_sources || null;
		if (defaults.company) {
			frm.set_value("company", defaults.company);
		}
		if (defaults.project) {
			frm.set_value("project", defaults.project);
		}
		if (defaults.source_type) {
			frm.set_value("source_type", defaults.source_type);
		}
		setTimeout(() => frm.trigger("fetch_eligible_sources"), 300);
	});
};
