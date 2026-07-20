// Copyright (c) 2026, Construction Management
// License: MIT

frappe.query_reports["Project Sales Invoice Consolidated"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			width: "80",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_default("company"),
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			width: "80",
			options: "Project",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			width: "80",
			options: "Customer",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			width: "80",
			reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			on_change: (report) => {
				report.set_filter_value("sales_invoice", []);
				report.refresh();
			},
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			width: "80",
			reqd: 1,
			default: frappe.datetime.get_today(),
			on_change: (report) => {
				report.set_filter_value("sales_invoice", []);
				report.refresh();
			},
		},
		{
			fieldname: "sales_invoice",
			label: __("Sales Invoice"),
			fieldtype: "MultiSelectList",
			width: "80",
			options: "Sales Invoice",
			get_data: function (txt) {
				let filters = { docstatus: 1, is_return: 0 };

				const from_date = frappe.query_report.get_filter_value("from_date");
				const to_date = frappe.query_report.get_filter_value("to_date");
				const project = frappe.query_report.get_filter_value("project");
				const customer = frappe.query_report.get_filter_value("customer");
				const company = frappe.query_report.get_filter_value("company");

				if (from_date && to_date) filters["posting_date"] = ["between", [from_date, to_date]];
				if (project) filters["project"] = project;
				if (customer) filters["customer"] = customer;
				if (company) filters["company"] = company;

				return frappe.db.get_link_options("Sales Invoice", txt, filters);
			},
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "MultiSelectList",
			options: [
				"Draft",
				"Return",
				"Credit Note Issued",
				"Submitted",
				"Paid",
				"Partly Paid",
				"Unpaid",
				"Overdue",
				"Cancelled",
			],
			width: "80",
			get_data: function () {
				return [
					"Paid",
					"Partly Paid",
					"Unpaid",
					"Overdue",
					"Submitted",
					"Return",
					"Credit Note Issued",
				].map((option) => ({
					value: option,
					label: __(option),
					description: "",
				}));
			},
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname === "received_amount" && data && data[column.fieldname] > 0) {
			value = "<span style='color:green;'>" + value + "</span>";
		}

		if (column.fieldname === "outstanding_amount" && data && data[column.fieldname] > 0) {
			value = "<span style='color:#c0392b;'>" + value + "</span>";
		}

		return value;
	},
};
