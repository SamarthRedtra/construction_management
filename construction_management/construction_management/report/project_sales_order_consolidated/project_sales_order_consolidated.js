// Copyright (c) 2026, Construction Management
// License: MIT

frappe.query_reports["Project Sales Order Consolidated"] = {
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
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			width: "80",
			reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			on_change: (report) => {
				report.set_filter_value("sales_order", []);
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
				report.set_filter_value("sales_order", []);
				report.refresh();
			},
		},
		{
			fieldname: "sales_order",
			label: __("Sales Order"),
			fieldtype: "MultiSelectList",
			width: "80",
			options: "Sales Order",
			get_data: function (txt) {
				let filters = { docstatus: 1 };

				const from_date = frappe.query_report.get_filter_value("from_date");
				const to_date = frappe.query_report.get_filter_value("to_date");
				const project = frappe.query_report.get_filter_value("project");

				if (from_date && to_date) filters["transaction_date"] = ["between", [from_date, to_date]];
				if (project) filters["project"] = project;

				return frappe.db.get_link_options("Sales Order", txt, filters);
			},
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "MultiSelectList",
			options: ["To Pay", "To Bill", "To Deliver", "To Deliver and Bill", "Completed", "Closed"],
			width: "80",
			get_data: function () {
				return [
					"To Pay",
					"To Bill",
					"To Deliver",
					"To Deliver and Bill",
					"Completed",
					"Closed",
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

		if (
			["tax_invoiced_amount", "received_amount"].includes(column.fieldname) &&
			data &&
			data[column.fieldname] > 0
		) {
			value = "<span style='color:green;'>" + value + "</span>";
		}

		if (
			column.fieldname === "pending_tax_amount" &&
			data &&
			data[column.fieldname] > 0
		) {
			value = "<span style='color:#c0392b;'>" + value + "</span>";
		}

		return value;
	},
};
