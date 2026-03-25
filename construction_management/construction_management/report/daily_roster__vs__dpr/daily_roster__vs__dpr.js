// Copyright (c) 2026, Construction Management
// License: MIT

frappe.query_reports["Daily Roster  vs  DPR"] = {
	"filters": [
		{
			"fieldname": "project",
			"label": __("Project"),
			"fieldtype": "Link",
			"options": "Project"
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date"
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date"
		},
		{
			"fieldname": "site",
			"label": __("Site"),
			"fieldtype": "Link",
			"options": "Project Sites"
		}
	],

	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (!data) {
			return value;
		}

		if (column.fieldname === "roster_created") {
			const color = data.roster_created === "Yes" ? "green" : "red";
			return `<span class="indicator-pill ${color}">${value}</span>`;
		}

		if (column.fieldname === "dpr_created") {
			const color = data.dpr_created === "Yes" ? "green" : "red";
			return `<span class="indicator-pill ${color}">${value}</span>`;
		}

		if (column.fieldname === "dpr_status" && data.dpr_status) {
			const s = data.dpr_status;
			const color =
				s === "Submitted" ? "green" : s === "Cancelled" ? "red" : "orange";
			return `<span class="indicator-pill ${color}">${frappe.utils.escape_html(s)}</span>`;
		}

		return value;
	}
};
