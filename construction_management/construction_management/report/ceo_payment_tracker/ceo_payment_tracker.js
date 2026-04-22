// Copyright (c) 2026, Construction Management
// License: MIT

frappe.query_reports["CEO Payment Tracker"] = {
	"filters": [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company"),
			"on_change": function() {
				// Clear project when company changes so stale value doesn't slip through
				frappe.query_report.set_filter_value("project", "");
				frappe.query_report.refresh();
			}
		},
		{
			"fieldname": "project",
			"label": __("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"get_query": function() {
				let company = frappe.query_report.get_filter_value("company");
				if (company) {
					return { filters: { company: company } };
				}
				return {};
			}
		},
		{
			"fieldname": "type",
			"label": __("Type"),
			"fieldtype": "Select",
			"options": "\nSales\nPurchase"
		},
		{
			"fieldname": "cheque_no",
			"label": __("Cheque/Reference No"),
			"fieldtype": "Data",
			"description": __("Filter rows where a linked Payment Entry has this reference (partial match).")
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -6)
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today()
		}
	],

	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (!data) return value;

		// Highlight overdue invoices (due_date passed, no payment yet)
		if (column.fieldname === "due_date" && data.due_date && !data.payment_date) {
			if (data.due_date < frappe.datetime.get_today()) {
				value = `<span style="color: var(--red-500); font-weight: 600;">${value} ⚠</span>`;
			}
		}

		// Payment mode badge
		if (column.fieldname === "payment_mode" && data.payment_mode) {
			value = `<span class="indicator-pill green">${value}</span>`;
		}

		return value;
	}
};
