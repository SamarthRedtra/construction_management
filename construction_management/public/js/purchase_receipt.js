// Copyright (c) 2024, Construction Management
// License: MIT
// Purchase Receipt client script for Payment Certificate integration and deduction recalculation

frappe.ui.form.on('Purchase Receipt', {
	onload: function (frm) {
		frm._pr_deduction_busy = false;
		frm._pr_deduction_timer = null;

		if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
			construction_management.dimension_utils.setup_accounting_dimension_filters(frm);
			construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'items');
		}
		setup_extra_accounting_entry_queries(frm);
	},

	refresh: function (frm) {
		ensure_additional_discount_fields(frm);
		if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
			construction_management.dimension_utils.setup_accounting_dimension_filters(frm);
			construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'items');
		}
		setup_extra_accounting_entry_queries(frm);

		// Do NOT recalculate deductions on every refresh — that calls set_value and
		// marks a just-saved draft dirty again ("Not Saved"). Server validate already
		// applies deductions on save. Only seed once for new docs missing deduction rows.
		if (frm.doc.docstatus === 0 && frm.is_new()) {
			const has_billable = (frm.doc.items || []).some(
				(i) => i.item_code && !is_pr_deduction_item(i.item_code)
			);
			const has_deduction = (frm.doc.items || []).some((i) => is_pr_deduction_item(i.item_code));
			if (has_billable && !has_deduction) {
				schedule_pr_deduction_recalc(frm);
			}
		}

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
			}
			let project = row.project || doc.project;
			if (project) {
				return { filters: { project: project } };
			}
			return {};
		});

		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__('Create Material Issue'), function () {
				construction_management.bulk_material_issue.open_tool(
					[{ doctype: 'Purchase Receipt', name: frm.doc.name }],
					{
						company: frm.doc.company,
						project: frm.doc.project,
						source_type: 'Purchase Receipt',
					}
				);
			}, __('Actions'));
		}

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
		// Set directly — frappe.model.set_value here races save and leaves form dirty.
		(frm.doc.items || []).forEach((item) => {
			if (Object.prototype.hasOwnProperty.call(item, 'site') && !item.site) {
				item.site = 'Transit';
			}
			if (Object.prototype.hasOwnProperty.call(item, 'rejected_site') && !item.rejected_site) {
				item.rejected_site = 'Transit';
			}
		});
	},

	custom_skip_advance_deduction: function (frm) {
		if (frm.doc.docstatus !== 0) {
			return;
		}
		if (cint(frm.doc.custom_skip_advance_deduction)) {
			const advance_row = (frm.doc.items || []).find(i => i.item_code === 'ADVANCE-DEDUCTION');
			if (advance_row) {
				frappe.model.clear_doc(advance_row.doctype, advance_row.name);
				frm.refresh_field('items');
			}
			frappe.show_alert({
				message: __('Advance deduction skipped for this receipt'),
				indicator: 'blue',
			});
			return;
		}
		schedule_pr_deduction_recalc(frm);
	}
});


frappe.ui.form.on('Purchase Receipt Item', {
	warehouse(frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		const warehouse = row.warehouse;

		if (!warehouse) return;
		if (row.purchase_order_item) {
			return;
		}

		frappe.call({
			method: 'construction_management.api.purchase_receipt_utils.get_warehouse_project',
			args: {
				warehouse,
				company: frm.doc.company
			},
			callback: function (r) {
				if (!r.message) return;
				if (row.project === r.message) return;

				frappe.model.set_value(cdt, cdn, 'project', r.message);
				frappe.show_alert({
					message: __('Project {0} linked from Warehouse', [r.message]),
					indicator: 'green'
				}, 3);
			}
		});
	},

	items_add: function (frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		if (Object.prototype.hasOwnProperty.call(row, 'site') && !row.site) {
			row.site = 'Transit';
		}
		schedule_pr_deduction_recalc(frm);
	},

	items_remove: function (frm) {
		schedule_pr_deduction_recalc(frm);
	},

	qty: function (frm, cdt, cdn) {
		if (is_pr_deduction_row(cdt, cdn)) return;
		schedule_pr_deduction_recalc(frm);
	},

	rate: function (frm, cdt, cdn) {
		if (is_pr_deduction_row(cdt, cdn) || frm._pr_deduction_busy) return;
		schedule_pr_deduction_recalc(frm);
	},

	amount: function (frm, cdt, cdn) {
		if (is_pr_deduction_row(cdt, cdn) || frm._pr_deduction_busy) return;
		schedule_pr_deduction_recalc(frm);
	},

	boq_item: function (frm, cdt, cdn) {
		if (is_pr_deduction_row(cdt, cdn) || frm._pr_deduction_busy) return;
		schedule_pr_deduction_recalc(frm);
	},

	custom_skip_advance_deduction: function (frm, cdt, cdn) {
		if (is_pr_deduction_row(cdt, cdn) || frm._pr_deduction_busy) return;
		schedule_pr_deduction_recalc(frm);
	}
});


function is_pr_deduction_item(item_code) {
	return item_code === 'RETENTION-DEDUCTION' || item_code === 'ADVANCE-DEDUCTION';
}

function is_pr_deduction_row(cdt, cdn) {
	const row = frappe.get_doc(cdt, cdn);
	return row && is_pr_deduction_item(row.item_code);
}

function schedule_pr_deduction_recalc(frm) {
	if (!frm || frm.doc.docstatus !== 0 || frm._pr_deduction_busy) {
		return;
	}
	if (frm._pr_deduction_timer) {
		clearTimeout(frm._pr_deduction_timer);
	}
	frm._pr_deduction_timer = setTimeout(() => {
		frm._pr_deduction_timer = null;
		recalculate_pr_deductions(frm);
	}, 250);
}

function recalculate_pr_deductions(frm) {
	if (frm.doc.docstatus !== 0 || frm._pr_deduction_busy) {
		return;
	}

	if (cint(frm.doc.custom_skip_advance_deduction)) {
		const advance_row = (frm.doc.items || []).find(i => i.item_code === 'ADVANCE-DEDUCTION');
		if (advance_row) {
			frappe.model.clear_doc(advance_row.doctype, advance_row.name);
			frm.refresh_field('items');
		}
	}

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

	const is_subcontractor = frm.doc.custom_suppliersubcontractor === 'Subcontractor';
	const form_items = (frm.doc.items || []).map((item) => ({
		item_code: item.item_code,
		amount: item.amount,
		boq_item: item.boq_item,
		custom_skip_advance_deduction: item.custom_skip_advance_deduction,
	}));

	Promise.all([
		frappe.db.get_value('Purchase Order', purchase_order,
			['custom_retention_', 'custom_advance_', 'custom_suppliersubcontractor', 'project']),
		frappe.call({
			method: 'construction_management.api.purchase_receipt_utils.get_purchase_advance_billable_for_form',
			args: {
				items: form_items,
				skip_doc_advance: cint(frm.doc.custom_skip_advance_deduction),
			},
		}),
	]).then(([poResult, billableResult]) => {
		if (!poResult.message) return;
		if (!is_subcontractor && poResult.message.custom_suppliersubcontractor !== 'Subcontractor') return;

		let retention_pct = flt(poResult.message.custom_retention_);
		let advance_pct = flt(poResult.message.custom_advance_);

		if (retention_pct <= 0 && advance_pct <= 0) {
			remove_pr_deduction_rows(frm);
			return;
		}

		const total_billable = flt(billableResult.message && billableResult.message.total_billable);
		const advance_billable = flt(billableResult.message && billableResult.message.advance_billable);
		apply_pr_deduction_amounts(frm, retention_pct, advance_pct, total_billable, advance_billable);
	});
}

function remove_pr_deduction_rows(frm) {
	let removed = false;
	for (const item_code of ['RETENTION-DEDUCTION', 'ADVANCE-DEDUCTION']) {
		const row = (frm.doc.items || []).find(i => i.item_code === item_code);
		if (row) {
			frappe.model.clear_doc(row.doctype, row.name);
			removed = true;
		}
	}
	if (removed) {
		frm.refresh_field('items');
	}
}

function set_deduction_row_value(row, fieldname, value) {
	if (flt(row[fieldname]) === flt(value)) {
		return false;
	}
	row[fieldname] = value;
	return true;
}

function get_pr_deduction_row_values(frm, item_code, amount, description) {
	const line_amount = -flt(amount);
	return {
		item_code,
		item_name: item_code === 'RETENTION-DEDUCTION' ? 'Retention Deduction' : 'Advance Deduction',
		uom: 'Nos',
		stock_uom: 'Nos',
		qty: 1,
		received_qty: 1,
		conversion_factor: 1,
		stock_qty: 1,
		rate: line_amount,
		amount: line_amount,
		description,
		project: frm.doc.project,
		site: 'Transit',
	};
}

function apply_pr_deduction_row_values(row, frm, amount, description) {
	Object.assign(row, get_pr_deduction_row_values(frm, row.item_code, amount, description));
}

function apply_pr_deduction_amounts(frm, retention_pct, advance_pct, total_billable, advance_billable) {
	frm._pr_deduction_busy = true;
	try {
		let changed = false;

		if (retention_pct > 0) {
			const retention_amount = flt(total_billable * retention_pct / 100, 2);
			if (retention_amount > 0) {
				let retention_row = (frm.doc.items || []).find(i => i.item_code === 'RETENTION-DEDUCTION');
				const retention_desc = `Retention deduction (${retention_pct}%)`;
				if (retention_row) {
					apply_pr_deduction_row_values(retention_row, frm, retention_amount, retention_desc);
					changed = true;
				} else {
					const new_row = frm.add_child('items');
					Object.assign(
						new_row,
						get_pr_deduction_row_values(frm, 'RETENTION-DEDUCTION', retention_amount, retention_desc)
					);
					changed = true;
				}
			} else {
				const retention_row = (frm.doc.items || []).find(i => i.item_code === 'RETENTION-DEDUCTION');
				if (retention_row) {
					frappe.model.clear_doc(retention_row.doctype, retention_row.name);
					changed = true;
				}
			}
		} else {
			const retention_row = (frm.doc.items || []).find(i => i.item_code === 'RETENTION-DEDUCTION');
			if (retention_row) {
				frappe.model.clear_doc(retention_row.doctype, retention_row.name);
				changed = true;
			}
		}

		if (advance_pct > 0) {
			const advance_amount = flt(advance_billable * advance_pct / 100, 2);
			if (advance_amount > 0) {
				let advance_row = (frm.doc.items || []).find(i => i.item_code === 'ADVANCE-DEDUCTION');
				const advance_desc = `Advance deduction (${advance_pct}%)`;
				if (advance_row) {
					apply_pr_deduction_row_values(advance_row, frm, advance_amount, advance_desc);
					changed = true;
				} else {
					const new_row = frm.add_child('items');
					Object.assign(
						new_row,
						get_pr_deduction_row_values(frm, 'ADVANCE-DEDUCTION', advance_amount, advance_desc)
					);
					changed = true;
				}
			} else {
				const advance_row = (frm.doc.items || []).find(i => i.item_code === 'ADVANCE-DEDUCTION');
				if (advance_row) {
					frappe.model.clear_doc(advance_row.doctype, advance_row.name);
					changed = true;
				}
			}
		} else {
			const advance_row = (frm.doc.items || []).find(i => i.item_code === 'ADVANCE-DEDUCTION');
			if (advance_row) {
				frappe.model.clear_doc(advance_row.doctype, advance_row.name);
				changed = true;
			}
		}

		if (changed) {
			frm.refresh_field('items');
		}
	} finally {
		frm._pr_deduction_busy = false;
	}
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
		frappe.model.set_value(cdt, cdn, 'party', '');
	}
});

function ensure_additional_discount_fields(frm) {
	if (!frm || frm.doc.docstatus !== 0) return;

	const fields = ["section_break_42", "apply_discount_on", "additional_discount_percentage", "discount_amount"];
	for (const fieldname of fields) {
		if (!frm.fields_dict[fieldname]) continue;
		frm.set_df_property(fieldname, "hidden", 0);
		frm.set_df_property(fieldname, "read_only", 0);
	}
}
