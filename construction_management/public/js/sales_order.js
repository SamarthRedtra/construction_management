/**
 * Sales Order client script extensions for Construction Management
 * 
 * BOQ dimension fields (bill_no, boq_item) are on the child table (items).
 */

frappe.ui.form.on('Sales Order', {
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

frappe.ui.form.on('Sales Order Item', {
	items_add: function (frm, cdt, cdn) {
		recalculate_retention_so(frm);
	},

	items_remove: function (frm, cdt, cdn) {
		recalculate_retention_so(frm);
	},

	qty: function (frm, cdt, cdn) {
		recalculate_retention_so(frm);
	},

	rate: function (frm, cdt, cdn) {
		recalculate_retention_so(frm);
	},

	amount: function (frm, cdt, cdn) {
		recalculate_retention_so(frm);
	}
});

function recalculate_retention_so(frm) {
	// Only recalculate if we have a project and the document is in draft
	if (!frm.doc.project || frm.doc.docstatus !== 0) {
		return;
	}

	// Get retention percentage from project
	frappe.db.get_value('Project', frm.doc.project, 'retention_percentage')
		.then(r => {
			const retention_percentage = flt(r.message ? r.message.retention_percentage : 0);

			if (retention_percentage <= 0) {
				return; // No retention to calculate
			}

			// Calculate total gross amount (excluding deduction items)
			let total_gross_amount = 0;
			(frm.doc.items || []).forEach(item => {
				if (item.item_code !== 'RETENTION-DEDUCTION' && item.item_code !== 'ADVANCE-DEDUCTION') {
					total_gross_amount += flt(item.amount);
				}
			});

			// Calculate retention amount
			const retention_amount = flt(total_gross_amount * retention_percentage / 100, 2);

			if (retention_amount <= 0) {
				// Remove retention item if amount is 0 or negative
				const retention_row = (frm.doc.items || []).find(i => i.item_code === 'RETENTION-DEDUCTION');
				if (retention_row) {
					frappe.model.clear_doc(retention_row.doctype, retention_row.name);
					frm.refresh_field('items');
				}
				return;
			}

			// Find existing retention item or create new
			let retention_row = (frm.doc.items || []).find(i => i.item_code === 'RETENTION-DEDUCTION');

			if (retention_row) {
				// Update existing row
				frappe.model.set_value(retention_row.doctype, retention_row.name, 'rate', -retention_amount);
				frappe.model.set_value(retention_row.doctype, retention_row.name, 'amount', -retention_amount);
				frappe.model.set_value(retention_row.doctype, retention_row.name, 'description', `Retention deduction (${retention_percentage}%)`);
			} else {
				// Create new row
				const new_row = frm.add_child('items');
				frappe.model.set_value(new_row.doctype, new_row.name, {
					'item_code': 'RETENTION-DEDUCTION',
					'qty': 1,
					'rate': -retention_amount,
					'amount': -retention_amount,
					'description': `Retention deduction (${retention_percentage}%)`,
					'project': frm.doc.project
				});
			}

			frm.refresh_field('items');
		});
}

