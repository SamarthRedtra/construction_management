/**
 * Sales Invoice client script extensions for Construction Management
 * 
 * BOQ dimension fields (bill_no, boq_item) are on the child table (items).
 */

frappe.ui.form.on('Sales Invoice', {
	onload: function (frm) {
		// Setup cascading dimension filters for child table
		if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
			construction_management.dimension_utils.setup_accounting_dimension_filters(frm);
			construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'items');
		}
	},
	custom_is_advanced: function (frm) {
		if (frm.doc.custom_is_advanced) {
			frm.set_df_property("custom_advanced_percentage", "reqd", 1);
			frm.set_df_property("project", "reqd", 1);
			calculate_advance_amount(frm);
		} else {
			frm.set_df_property("project", "reqd", 0);
			frm.set_df_property("custom_advanced_percentage", "reqd", 0);
		}
	},

	project: function (frm) {
		if (frm.doc.custom_is_advanced) {
			calculate_advance_amount(frm);
		}
	},

	custom_advanced_percentage: function (frm) {
		if (frm.doc.custom_is_advanced) {
			calculate_advance_amount(frm);
		}
	},

	refresh: function (frm) {
		// Re-setup on refresh to ensure filters are applied after form loads
		if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
			construction_management.dimension_utils.setup_accounting_dimension_filters(frm);
			construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'items');
		}

		if (frm.doc.docstatus === 0 && frm.doc.project) {
			frm.add_custom_button(__('Pull Retention'), () => {
				pull_retention(frm);
			}, __('Get Deductions'));

			frm.add_custom_button(__('Pull Advance Deduction'), () => {
				pull_advance_deduction(frm);
			}, __('Get Deductions'));
		}
	}
});

function pull_retention(frm) {
	if (!frm.doc.project) {
		frappe.msgprint(__('Please select a Project first'));
		return;
	}

	frappe.call({
		method: 'construction_management.construction_management.api.boq_invoice.get_deduction_details',
		args: {
			project: frm.doc.project,
			items: frm.doc.items,
			invoice_name: frm.doc.name
		},
		callback: function (r) {
			if (r.message && r.message.suggested_retention > 0) {
				const amount = r.message.suggested_retention;
				// Check if already exists
				let row = (frm.doc.items || []).find(i => i.item_code === 'RETENTION-DEDUCTION');
				if (!row) {
					row = frm.add_child('items');
				}
				frappe.model.set_value(row.doctype, row.name, {
					'item_code': 'RETENTION-DEDUCTION',
					'qty': 1,
					'rate': -amount,
					'amount': -amount,
					'description': `Retention deduction (${r.message.retention_percentage}%)`,
					'project': frm.doc.project
				});
				frm.refresh_field('items');
			} else {
				frappe.msgprint(__('No retention to pull or retention percentage is 0.'));
			}
		}
	});
}

function pull_advance_deduction(frm) {
	if (!frm.doc.project) {
		frappe.msgprint(__('Please select a Project first'));
		return;
	}

	frappe.call({
		method: 'construction_management.construction_management.api.boq_invoice.get_deduction_details',
		args: {
			project: frm.doc.project,
			items: frm.doc.items,
			invoice_name: frm.doc.name
		},
		callback: function (r) {
			if (r.message && r.message.available_advance > 0) {
				const available = r.message.available_advance;
				const total_billable = r.message.total_billable_amount;

				let d = new frappe.ui.Dialog({
					title: __('Pull Advance Deduction'),
					fields: [
						{
							label: __('Available Advance'),
							fieldname: 'available_advance',
							fieldtype: 'Currency',
							default: available,
							read_only: 1
						},
						{
							label: __('Total Billable Amount'),
							fieldname: 'total_billable',
							fieldtype: 'Currency',
							default: total_billable,
							read_only: 1
						},
						{
							label: __('Deduction Amount'),
							fieldname: 'amount',
							fieldtype: 'Currency',
							default: r.message.suggested_advance || 0,
							description: r.message.advance_percentage ? __('Capped at {0}% of billable amount', [r.message.advance_percentage]) : '',
							reqd: 1
						}
					],
					primary_action_label: __('Apply'),
					primary_action(values) {
						if (values.amount > available) {
							frappe.msgprint(__('Deduction cannot exceed available advance'));
							return;
						}

						let row = (frm.doc.items || []).find(i => i.item_code === 'ADVANCE-DEDUCTION');
						if (!row) {
							row = frm.add_child('items');
						}
						frappe.model.set_value(row.doctype, row.name, {
							'item_code': 'ADVANCE-DEDUCTION',
							'qty': 1,
							'rate': -values.amount,
							'amount': -values.amount,
							'description': __('Deduction from advance payment'),
							'project': frm.doc.project
						});
						frm.refresh_field('items');
						d.hide();
					}
				});
				d.show();
			} else {
				frappe.msgprint(__('No available advance for this project.'));
			}
		}
	});
}

function calculate_advance_amount(frm) {
	if (!frm.doc.project || !frm.doc.custom_advanced_percentage || !frm.doc.custom_is_advanced) return;

	frappe.db.get_value('Project BOQ', { project: frm.doc.project }, 'total_estimated_boq_value')
		.then(r => {
			const total_boq_value = r.message ? r.message.total_estimated_boq_value : 0;
			if (!total_boq_value) {
				frappe.show_alert({ message: __('Total BOQ Value not found for project {0}', [frm.doc.project]), indicator: 'orange' });
				return;
			}

			const percentage = frm.doc.custom_advanced_percentage || 0;
			const amount = flt(total_boq_value * percentage / 100, precision('rate', 'items'));

			if (amount > 0) {
				frappe.db.get_value('BOQ Settings', { company: frm.doc.company }, 'default_advance_item')
					.then(res => {
						const advance_item = res.message ? res.message.default_advance_item : null;
						if (advance_item) {
							// Check if item already exists
							let row = (frm.doc.items || []).find(i => i.item_code === advance_item);
							if (!row) {
								frm.clear_table('items');
								row = frm.add_child('items');
							}

							frappe.model.set_value(row.doctype, row.name, 'item_code', advance_item)
								.then(() => {
									frappe.model.set_value(row.doctype, row.name, {
										'qty': 1,
										'rate': amount,
										'amount': amount
									});
									frm.refresh_field('items');
								});
						} else {
							frappe.msgprint(__('Please set "Default Advance Item" in BOQ Settings for company {0}', [frm.doc.company]));
						}
					});
			}
		});
}
