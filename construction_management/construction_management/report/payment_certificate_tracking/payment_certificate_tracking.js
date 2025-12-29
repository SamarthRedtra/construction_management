// Copyright (c) 2024, Construction Management
// License: MIT

frappe.query_reports["Payment Certificate Tracking"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -3)
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today()
		},
		{
			"fieldname": "project",
			"label": __("Project"),
			"fieldtype": "Link",
			"options": "Project"
		},
		{
			"fieldname": "type",
			"label": __("Type"),
			"fieldtype": "Select",
			"options": "\nSales\nPurchase"
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
			"fieldname": "boq_item",
			"label": __("BOQ Item"),
			"fieldtype": "Link",
			"options": "BOQ Item",
			"get_query": function() {
				let bill_no = frappe.query_report.get_filter_value('bill_no');
				if (bill_no) {
					return {
						filters: { parent_bill: bill_no }
					};
				}
			}
		},
		{
			"fieldname": "status",
			"label": __("Status"),
			"fieldtype": "Select",
			"options": "\nDraft\nSubmitted\nInvoiced\nPaid\nCancelled"
		}
	],
	
	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		
		// Type color coding
		if (column.fieldname === "type") {
			if (data.type === "Sales") {
				value = `<span class="indicator-pill blue">${value}</span>`;
			} else if (data.type === "Purchase") {
				value = `<span class="indicator-pill orange">${value}</span>`;
			}
		}
		
		// Status color coding
		if (column.fieldname === "status") {
			const statusColors = {
				'Draft': 'gray',
				'Submitted': 'blue',
				'Invoiced': 'green',
				'Paid': 'green',
				'Cancelled': 'red'
			};
			const color = statusColors[data.status] || 'gray';
			value = `<span class="indicator-pill ${color}">${value}</span>`;
		}
		
		// Variance highlighting
		if (column.fieldname === "variance" && flt(data.variance) > 0) {
			value = `<span style="color: red; font-weight: bold;">${value}</span>`;
		}
		
		return value;
	},
	
	"onload": function(report) {
		// Add row click handler
		report.$report.on('click', '.dt-cell', function() {
			let row_index = $(this).closest('.dt-row').data('row-index');
			let data = report.data[row_index];
			if (data && data.name) {
				frappe.set_route('Form', 'Payment Certificate', data.name);
			}
		});
	}
};
