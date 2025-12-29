// Copyright (c) 2024, Construction Management
// License: MIT

frappe.query_reports["Pending Proforma Invoices"] = {
	"filters": [
		{
			"fieldname": "project",
			"label": __("Project"),
			"fieldtype": "Link",
			"options": "Project"
		},
		{
			"fieldname": "customer",
			"label": __("Customer"),
			"fieldtype": "Link",
			"options": "Customer"
		},
		{
			"fieldname": "bill_no",
			"label": __("Bill No"),
			"fieldtype": "Link",
			"options": "BOQ Bill",
			"get_query": function() {
				let project = frappe.query_report.get_filter_value('project');
				if (project) {
					return {
						filters: { project: project }
					};
				}
			}
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
			"fieldname": "min_amount",
			"label": __("Min Amount"),
			"fieldtype": "Currency"
		},
		{
			"fieldname": "max_amount",
			"label": __("Max Amount"),
			"fieldtype": "Currency"
		}
	],
	
	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		
		// Highlight old proformas (> 30 days)
		if (column.fieldname === "age_days" && data.age_days > 30) {
			value = `<span style="color: red; font-weight: bold;">${value}</span>`;
		}
		
		return value;
	},
	
	"onload": function(report) {
		report.page.add_inner_button(__("Create Payment Certificate"), function() {
			let selected = report.get_checked_items();
			if (selected.length === 0) {
				frappe.msgprint(__("Please select at least one proforma invoice"));
				return;
			}
			
			if (selected.length > 1) {
				frappe.msgprint(__("Please select only one proforma invoice at a time"));
				return;
			}
			
			let proforma = selected[0];
			frappe.new_doc("Payment Certificate", {
				project: proforma.project,
				proforma_invoice: proforma.name,
				proforma_amount: proforma.amount
			});
		});
	}
};
