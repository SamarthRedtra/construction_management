// Copyright (c) 2024, Construction Management
// License: MIT
// Purchase Receipt client script for Payment Certificate integration and deduction recalculation

frappe.ui.form.on('Purchase Receipt', {
	onload: function (frm) {
		// Setup cascading dimension filters for child table
		if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
			construction_management.dimension_utils.setup_accounting_dimension_filters(frm);
			construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'items');
		}
		setup_extra_accounting_entry_queries(frm);
	},

	refresh: function (frm) {
		// Re-setup dimension filters on refresh
		if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
			construction_management.dimension_utils.setup_accounting_dimension_filters(frm);
			construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'items');
		}
		setup_extra_accounting_entry_queries(frm);

		// Explicit queries for BOQ dimensions in child table
		frm.set_query("bill_no", "items", function (doc, cdt, cdn) {
			let row = locals[cdt][cdn];
			let project = row.project || doc.project;
			if (project) {
				return { filters: { project: project } };
			}
			return {};
		});

		frm.set_query("boq_item", "items", function (doc, cdt, cdn) {
			let row = locals[cdt][cdn];
			if (row.bill_no) {
				return { filters: { parent_bill: row.bill_no } };
			} else {
				let project = row.project || doc.project;
				if (project) {
					return { filters: { project: project } };
				}
			}
			return {};
		});

		// Add "Create Payment Certificate" button for submitted PRs with Subcontractor type
		if (frm.doc.docstatus === 1 && frm.doc.custom_suppliersubcontractor == "Subcontractor") {
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

	},

	before_save: function (frm) {
		// Auto-fill blank custom site fields to resolve mandatory dimension errors
		(frm.doc.items || []).forEach(item => {
			if (item.hasOwnProperty('site') && !item.site) {
				frappe.model.set_value(item.doctype, item.name, 'site', 'Transit');
			}
			if (item.hasOwnProperty('rejected_site') && !item.rejected_site) {
				frappe.model.set_value(item.doctype, item.name, 'rejected_site', 'Transit');
			}
		});
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
	},

	items_add: function (frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, 'site', 'Transit');
		recalculate_pr_deductions(frm);
	},

	items_remove: function (frm, cdt, cdn) {
		recalculate_pr_deductions(frm);
	},

	qty: function (frm, cdt, cdn) {
		recalculate_pr_deductions(frm);
	},

	rate: function (frm, cdt, cdn) {
		recalculate_pr_deductions(frm);
	},

	amount: function (frm, cdt, cdn) {
		recalculate_pr_deductions(frm);
	}
});


function recalculate_pr_deductions(frm) {
	// Only recalculate if the document is in draft
	if (frm.doc.docstatus !== 0) {
		return;
	}

	// Find linked Purchase Order
	let purchase_order = frm.doc.custom_purchase_order;
	if (!purchase_order) {
		for (let item of (frm.doc.items || [])) {
			if (item.purchase_order) {
				purchase_order = item.purchase_order;
				break;
			}
		}
	}

	if (!purchase_order) return;

	// Fetch PO retention/advance percentages and supplier/subcontractor type
	frappe.db.get_value('Purchase Order', purchase_order,
		['custom_retention_', 'custom_advance_', 'custom_suppliersubcontractor'])
		.then(r => {
			if (!r.message) return;

			// Only apply for Subcontractor type
			if (r.message.custom_suppliersubcontractor !== 'Subcontractor') return;

			const retention_pct = flt(r.message.custom_retention_);
			const advance_pct = flt(r.message.custom_advance_);

			if (retention_pct <= 0 && advance_pct <= 0) return;

			// Calculate total billable (exclude deduction items)
			let total_billable = 0;
			for (let item of (frm.doc.items || [])) {
				if (item.item_code !== 'RETENTION-DEDUCTION' && item.item_code !== 'ADVANCE-DEDUCTION') {
					total_billable += flt(item.amount);
				}
			}

			// Update or create retention deduction
			if (retention_pct > 0) {
				const retention_amount = flt(total_billable * retention_pct / 100, 2);

				if (retention_amount > 0) {
					let retention_row = (frm.doc.items || []).find(i => i.item_code === 'RETENTION-DEDUCTION');

					if (retention_row) {
						frappe.model.set_value(retention_row.doctype, retention_row.name, 'rate', -retention_amount);
						frappe.model.set_value(retention_row.doctype, retention_row.name, 'amount', -retention_amount);
						frappe.model.set_value(retention_row.doctype, retention_row.name, 'description',
							`Retention deduction (${retention_pct}%)`);
					} else {
						const new_row = frm.add_child('items');
						frappe.model.set_value(new_row.doctype, new_row.name, {
							'item_code': 'RETENTION-DEDUCTION',
							'item_name': 'Retention Deduction',
							'uom': 'Nos',
							'qty': 1,
							'rate': -retention_amount,
							'amount': -retention_amount,
							'description': `Retention deduction (${retention_pct}%)`,
							'project': frm.doc.project
						});
					}
				} else {
					const retention_row = (frm.doc.items || []).find(i => i.item_code === 'RETENTION-DEDUCTION');
					if (retention_row) {
						frappe.model.clear_doc(retention_row.doctype, retention_row.name);
					}
				}
			}

			// Update or create advance deduction
			if (advance_pct > 0) {
				const advance_amount = flt(total_billable * advance_pct / 100, 2);

				if (advance_amount > 0) {
					let advance_row = (frm.doc.items || []).find(i => i.item_code === 'ADVANCE-DEDUCTION');

					if (advance_row) {
						frappe.model.set_value(advance_row.doctype, advance_row.name, 'rate', -advance_amount);
						frappe.model.set_value(advance_row.doctype, advance_row.name, 'amount', -advance_amount);
						frappe.model.set_value(advance_row.doctype, advance_row.name, 'description',
							`Advance deduction (${advance_pct}%)`);
					} else {
						const new_row = frm.add_child('items');
						frappe.model.set_value(new_row.doctype, new_row.name, {
							'item_code': 'ADVANCE-DEDUCTION',
							'item_name': 'Advance Deduction',
							'uom': 'Nos',
							'qty': 1,
							'rate': -advance_amount,
							'amount': -advance_amount,
							'description': `Advance deduction (${advance_pct}%)`,
							'project': frm.doc.project
						});
					}
				} else {
					const advance_row = (frm.doc.items || []).find(i => i.item_code === 'ADVANCE-DEDUCTION');
					if (advance_row) {
						frappe.model.clear_doc(advance_row.doctype, advance_row.name);
					}
				}
			}

			frm.refresh_field('items');
		});
}


function create_payment_certificate_from_pr(frm) {
	frappe.call({
		method: 'construction_management.api.boq_invoice.create_pc_from_purchase_receipt',
		args: {
			purchase_receipt: frm.doc.name
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
}

function setup_extra_accounting_entry_queries(frm) {
	frm.set_query("account", "custom_extra_accounting_entries", function (doc) {
		return {
			filters: {
				company: doc.company,
				is_group: 0
			}
		};
	});

	frm.set_query("party", "custom_extra_accounting_entries", function (doc, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.party_type) {
			return { filters: { name: "__invalid__" } };
		}

		const filters = {};
		if (row.party_type === "Supplier" || row.party_type === "Customer" || row.party_type === "Employee") {
			filters.disabled = 0;
		}
		return { filters: filters };
	});
}

frappe.ui.form.on('Purchase Receipt Extra Entry', {
	party_type: function (frm, cdt, cdn) {
		// Reset party when party type changes to prevent stale invalid links.
		frappe.model.set_value(cdt, cdn, 'party', '');
	}
});
