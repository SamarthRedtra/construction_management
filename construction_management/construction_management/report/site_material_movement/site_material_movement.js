// Copyright (c) 2026, Construction Management
// License: MIT

frappe.query_reports["Site Material Movement"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -3),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "site_warehouse",
			label: __("Site Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: function () {
				const company = frappe.query_report.get_filter_value("company");
				return {
					filters: {
						company: company || undefined,
						is_group: 0,
					},
				};
			},
		},
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "transaction_type",
			label: __("Transaction Type"),
			fieldtype: "Select",
			options: "\nPurchase Receipt\nMaterial Transfer\nMaterial Issue (Consumption)",
		},
		{
			fieldname: "consumption_status",
			label: __("Consumption Entry Posted?"),
			fieldtype: "Select",
			options: "\nYes\nNo\nN/A",
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) {
			return value;
		}

		if (column.fieldname === "transaction_type") {
			if (data.transaction_type === "Purchase Receipt") {
				value = `<span class="indicator-pill blue">${value}</span>`;
			} else if (data.transaction_type === "Material Transfer") {
				value = `<span class="indicator-pill orange">${value}</span>`;
			} else if (data.transaction_type === "Material Issue (Consumption)") {
				value = `<span class="indicator-pill green">${value}</span>`;
			}
		}

		if (column.fieldname === "consumption_posted") {
			if (data.consumption_posted === "Yes") {
				value = `<span style="color: var(--green-600); font-weight: 600;">✅ ${__("Yes")}</span>`;
			} else if (data.consumption_posted === "No") {
				value = `<span style="color: var(--red-600); font-weight: 600;">❌ ${__("No")}</span>`;
			} else if (data.consumption_posted === "N/A") {
				value = `<span class="text-muted">${__("N/A")}</span>`;
			}
		}

		if (
			(column.fieldname === "qty_consumed" || column.fieldname === "qty_pending") &&
			data &&
			flt(data[column.fieldname]) > 0
		) {
			value = `<span style="font-weight: 600;">${value}</span>`;
		}

		return value;
	},
};
