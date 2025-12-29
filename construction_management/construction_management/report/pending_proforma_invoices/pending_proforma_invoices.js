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
		
		// PC Status color coding
		if (column.fieldname === "pc_status") {
			const statusColors = {
				'Pending': 'orange',
				'Draft': 'gray',
				'Submitted': 'blue',
				'Invoiced': 'green',
				'Paid': 'green'
			};
			const color = statusColors[data.pc_status] || 'gray';
			value = `<span class="indicator-pill ${color}">${data.pc_status || 'Pending'}</span>`;
		}
		
		// Action buttons
		if (column.fieldname === "action") {
			const action = data.action || 'Create PC';
			if (action === 'Create PC') {
				value = `<button class="btn btn-xs btn-primary" onclick="create_pc_from_report('${data.name}', ${data.amount}, '${data.project}')">Create PC</button>`;
			} else if (action === 'Submit PC') {
				value = `<button class="btn btn-xs btn-success" onclick="submit_pc_from_report('${data.payment_certificate}')">Submit</button>`;
			} else {
				value = `<button class="btn btn-xs btn-default" onclick="frappe.set_route('Form', 'Payment Certificate', '${data.payment_certificate}')">View</button>`;
			}
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

// Action button handlers
window.create_pc_from_report = function(proforma_name, amount, project) {
	frappe.prompt([
		{
			fieldname: 'accepted_amount',
			fieldtype: 'Currency',
			label: __('Accepted Amount'),
			default: amount,
			reqd: 1
		},
		{
			fieldname: 'remarks',
			fieldtype: 'Small Text',
			label: __('Remarks')
		}
	], function(values) {
		frappe.call({
			method: 'construction_management.construction_management.doctype.payment_certificate.payment_certificate.create_payment_certificate_from_proforma',
			args: {
				proforma_invoice: proforma_name,
				accepted_amount: values.accepted_amount,
				remarks: values.remarks
			},
			freeze: true,
			freeze_message: __('Creating Payment Certificate...'),
			callback: function(r) {
				if (r.message) {
					frappe.show_alert({
						message: __('Payment Certificate {0} created', [r.message.name]),
						indicator: 'green'
					});
					frappe.query_report.refresh();
				}
			}
		});
	}, __('Create Payment Certificate'), __('Create'));
};

window.submit_pc_from_report = function(pc_name) {
	frappe.confirm(
		__('Are you sure you want to submit Payment Certificate {0}?', [pc_name]),
		function() {
			frappe.call({
				method: 'frappe.client.submit',
				args: {
					doc: {
						doctype: 'Payment Certificate',
						name: pc_name
					}
				},
				freeze: true,
				freeze_message: __('Submitting Payment Certificate...'),
				callback: function(r) {
					if (!r.exc) {
						frappe.show_alert({
							message: __('Payment Certificate {0} submitted', [pc_name]),
							indicator: 'green'
						});
						frappe.query_report.refresh();
					}
				}
			});
		}
	);
};
