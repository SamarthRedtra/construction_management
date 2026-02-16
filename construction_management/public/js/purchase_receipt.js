// Copyright (c) 2024, Construction Management
// License: MIT
// Purchase Receipt client script for Payment Certificate integration

frappe.ui.form.on('Purchase Receipt', {
	refresh: function (frm) {
		// Add "Create Payment Certificate" button for submitted PRs with project
		if (frm.doc.docstatus === 1 && frm.doc.custom_suppliersubcontractor == "Subcontractor") {
			// Check if PC already exists for this PR
			frappe.call({
				method: 'frappe.client.get_count',
				args: {
					doctype: 'Payment Certificate',
					filters: {
						purchase_receipt: frm.doc.name,
						docstatus: ['!=', 2]
					}
				},
				callback: function (r) {
					if (r.message === 0) {
						frm.add_custom_button(__('Create Payment Certificate'), function () {
							create_payment_certificate_from_pr(frm);
						}, __('Actions'));
					}
				}
			});
		}
	}
});



frappe.ui.form.on('Purchase Receipt', {
	onload: function (frm) {
		// Setup cascading dimension filters for child table
		if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
			construction_management.dimension_utils.setup_accounting_dimension_filters(frm);
			construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'items');
		}
	},

	refresh: function (frm) {
		// Re-setup on refresh to ensure filters are applied after form loads
		if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
			construction_management.dimension_utils.setup_accounting_dimension_filters(frm);
			construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'items');
		}
	}
});


// Auto-set Project on item rows when Accepted Warehouse is chosen
frappe.ui.form.on('Purchase Receipt Item', {
	warehouse(frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		const warehouse = row.warehouse;

		// Always clear the row's project first; we only set it when a match is found
		frappe.model.set_value(cdt, cdn, 'project', '');

		if (!warehouse) return;

		frappe.call({
			method: 'construction_management.api.purchase_receipt_utils.get_warehouse_project',
			args: {
				warehouse,
				company: frm.doc.company
			},
			callback: function (r) {
				if (!r.message) return;

				frappe.model.set_value(cdt, cdn, 'project', r.message);
				frappe.show_alert({
					message: __('Project {0} linked from Warehouse', [r.message]),
					indicator: 'green'
				}, 3);
			}
		});
	}
});

function create_payment_certificate_from_pr(frm) {
	frappe.prompt([
		{
			fieldname: 'accepted_amount',
			fieldtype: 'Currency',
			label: __('Accepted Amount'),
			default: frm.doc.grand_total,
			reqd: 1
		},
		{
			fieldname: 'bill_no',
			fieldtype: 'Link',
			label: __('Bill No'),
			options: 'BOQ Bill',
			get_query: function () {
				return {
					filters: {
						project: frm.doc.project
					}
				};
			}
		},
		{
			fieldname: 'remarks',
			fieldtype: 'Small Text',
			label: __('Remarks')
		}
	], function (values) {
		frappe.call({
			method: 'construction_management.api.boq_invoice.create_pc_from_purchase_receipt',
			args: {
				purchase_receipt: frm.doc.name,
				accepted_amount: values.accepted_amount,
				bill_no: values.bill_no,
				remarks: values.remarks
			},
			freeze: true,
			freeze_message: __('Creating Payment Certificate...'),
			callback: function (r) {
				if (r.message) {
					frappe.show_alert({
						message: __('Payment Certificate {0} created', [r.message.name]),
						indicator: 'green'
					});
					frappe.set_route('Form', 'Payment Certificate', r.message.name);
				}
			}
		});
	}, __('Create Payment Certificate'), __('Create'));
}
