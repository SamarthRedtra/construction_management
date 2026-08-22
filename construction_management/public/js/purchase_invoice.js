/**
 * Purchase Invoice client script extensions for Construction Management
 * 
 * Note: The parent-level `bill_no` field in Purchase Invoice is ERPNext's 
 * standard "Supplier Invoice No" (Data type) and is NOT related to BOQ Bill.
 * BOQ dimension fields (bill_no, boq_item) are on the child table (items).
 */

function setup_purchase_receipt_fetch(frm) {
	if (frm.doc.docstatus !== 0) {
		return;
	}

	frm.remove_custom_button(__("Purchase Receipt"), __("Get Items From"));

	frm.add_custom_button(
		__("Purchase Receipt"),
		function () {
			erpnext.utils.map_current_doc({
				method: "erpnext.stock.doctype.purchase_receipt.mapper.make_purchase_invoice",
				source_doctype: "Purchase Receipt",
				target: frm,
				setters: {
					supplier: frm.doc.supplier || undefined,
					posting_date: undefined,
					supplier_delivery_note: undefined,
				},
				get_query_filters: {
					docstatus: 1,
					status: ["not in", ["Closed", "Completed", "Return Issued"]],
					company: frm.doc.company,
					is_return: 0,
				},
				get_query_method:
					"construction_management.api.purchase_receipt_utils.get_purchase_receipts_for_invoice",
				allow_child_item_selection: true,
				child_fieldname: "items",
				child_columns: ["item_code", "item_name", "qty", "amount", "billed_amt"],
			});
		},
		__("Get Items From")
	);
}

const PO_LINE_PROGRESS_FIELDS = [
	'custom_prev_qty',
	'custom_prev_amount',
	'custom_current_qty',
	'custom_current_amount',
	'custom_accumulated_qty',
	'custom_accumulated_amount'
];

function setup_po_line_progress_columns(frm) {
	for (const fieldname of PO_LINE_PROGRESS_FIELDS) {
		frm.set_df_property('items', fieldname, 'read_only', 1);
	}
}

function apply_item_liability_account_row(frm, cdt, cdn) {
	const row = locals[cdt] && locals[cdt][cdn];
	if (!row) return;

	if (row.item_code === 'RETENTION-DEDUCTION' || row.item_code === 'ADVANCE-DEDUCTION' || row.item_code === 'PURCHASE-ADVANCE') {
		return;
	}

	// Row-level value always wins over expense account.
	if (row.custom_liability_account) {
		frappe.model.set_value(cdt, cdn, 'expense_account', row.custom_liability_account);
		return;
	}

	if (!row.item_code) return;
	const liability_account = frm && frm.doc ? frm.doc.custom_liability_account : null;
	if (!liability_account) return;

	frappe.model.set_value(cdt, cdn, 'custom_liability_account', liability_account);
	frappe.model.set_value(cdt, cdn, 'expense_account', liability_account);
}

function apply_item_liability_account_all_rows(frm) {
	if (!frm || frm.doc.docstatus !== 0) return;
	(frm.doc.items || []).forEach(row => {
		apply_item_liability_account_row(frm, row.doctype, row.name);
	});
}

frappe.ui.form.on('Purchase Invoice', {
	onload: function (frm) {
		setup_po_line_progress_columns(frm);
		// Setup cascading dimension filters for child table
		if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
			construction_management.dimension_utils.setup_accounting_dimension_filters(frm);
			construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'items');
		}
	},

	custom_is_advance: function (frm) {
		if (frm.doc.custom_is_advance) {
			frm.set_df_property("project", "reqd", 1);

			// Auto-add advance item based on PO advance percentage
			let purchase_order = null;
			for (let item of (frm.doc.items || [])) {
				if (item.purchase_order) {
					purchase_order = item.purchase_order;
					break;
				}
			}

			if (purchase_order) {
				frappe.db.get_value('Purchase Order', purchase_order,
					['custom_advance_', 'grand_total']).then(r => {
						if (!r.message) return;
						const advance_pct = flt(r.message.custom_advance_);
						const po_total = flt(r.message.grand_total);
						if (advance_pct <= 0) return;

						const advance_amount = flt(po_total * advance_pct / 100, 2);
						if (advance_amount <= 0) return;

						// Check if already exists
						let existing = (frm.doc.items || []).find(i => i.item_code === 'PURCHASE-ADVANCE');
						if (!existing) {
							const new_row = frm.add_child('items');
							frappe.model.set_value(new_row.doctype, new_row.name, {
								'item_code': 'PURCHASE-ADVANCE',
								'item_name': 'Purchase Advance',
								'uom': 'Nos',
								'qty': 1,
								'rate': advance_amount,
								'amount': advance_amount,
								'description': `Advance payment (${advance_pct}% of PO ${purchase_order})`
							});
							frm.refresh_field('items');
							frappe.show_alert({
								message: __('Advance item added: {0}', [format_currency(advance_amount, frm.doc.currency)]),
								indicator: 'green'
							}, 5);
						}
					});
			}
		} else {
			frm.set_df_property("project", "reqd", 0);
			// Remove advance item if unticked
			let advance_row = (frm.doc.items || []).find(i => i.item_code === 'PURCHASE-ADVANCE');
			if (advance_row) {
				frappe.model.clear_doc(advance_row.doctype, advance_row.name);
				frm.refresh_field('items');
			}
		}
	},

	custom_skip_advance_deduction: function (frm) {
		if (frm.doc.docstatus !== 0) {
			return;
		}
		if (cint(frm.doc.custom_skip_advance_deduction)) {
			strip_purchase_advance_rows(frm);
			frappe.show_alert({
				message: __('Advance deduction skipped for this invoice'),
				indicator: 'blue',
			});
			return;
		}
		recalculate_purchase_deductions(frm);
	},

	custom_liability_account: function (frm) {
		// When header account changes, push it to rows where row value is empty.
		apply_item_liability_account_all_rows(frm);
	},

	refresh: function (frm) {
		ensure_additional_discount_fields(frm);
		setup_po_line_progress_columns(frm);
		apply_item_liability_account_all_rows(frm);
		// Re-setup on refresh to ensure filters are applied after form loads
		if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
			construction_management.dimension_utils.setup_accounting_dimension_filters(frm);
			construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'items');
		}

		// Set project required if is_advance is checked
		if (frm.doc.custom_is_advance) {
			frm.set_df_property("project", "reqd", 1);
		}

		// Run after ERPNext adds its default Purchase Receipt fetch button.
		setTimeout(() => setup_purchase_receipt_fetch(frm), 0);
	},

	before_save: function (frm) {
		(frm.doc.items || []).forEach(item => {
			if (item.item_code === 'RETENTION-DEDUCTION' || item.item_code === 'ADVANCE-DEDUCTION') {
				apply_pi_deduction_row_values(
					item,
					frm,
					Math.abs(flt(item.amount)),
					item.description || item.item_name
				);
				return;
			}
			if (!item.site) {
				frappe.model.set_value(item.doctype, item.name, 'site', 'Transit');
			}
			if (!item.rejected_site && item.hasOwnProperty('rejected_site')) {
				frappe.model.set_value(item.doctype, item.name, 'rejected_site', 'Transit');
			}
		});
	}
});

function ensure_additional_discount_fields(frm) {
	if (!frm || frm.doc.docstatus !== 0) return;

	const fields = ["section_break_44", "apply_discount_on", "additional_discount_percentage", "discount_amount"];
	for (const fieldname of fields) {
		if (!frm.fields_dict[fieldname]) continue;
		frm.set_df_property(fieldname, "hidden", 0);
		frm.set_df_property(fieldname, "read_only", 0);
	}
}

frappe.ui.form.on('Purchase Invoice Item', {
	items_add: function (frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, 'site', 'Transit');
		apply_item_liability_account_row(frm, cdt, cdn);
		recalculate_purchase_deductions(frm);
	},

	item_code: function (frm, cdt, cdn) {
		apply_item_liability_account_row(frm, cdt, cdn);
	},

	custom_liability_account: function (frm, cdt, cdn) {
		apply_item_liability_account_row(frm, cdt, cdn);
	},

	items_remove: function (frm, cdt, cdn) {
		recalculate_purchase_deductions(frm);
	},

	qty: function (frm, cdt, cdn) {
		recalculate_purchase_deductions(frm);
	},

	rate: function (frm, cdt, cdn) {
		recalculate_purchase_deductions(frm);
	},

	amount: function (frm, cdt, cdn) {
		recalculate_purchase_deductions(frm);
	},

	boq_item: function (frm, cdt, cdn) {
		recalculate_purchase_deductions(frm);
	},

	custom_skip_advance_deduction: function (frm, cdt, cdn) {
		recalculate_purchase_deductions(frm);
	}
});


function strip_purchase_advance_rows(frm) {
	const rows = (frm.doc.items || []).filter((row) => row.item_code === 'ADVANCE-DEDUCTION');
	rows.forEach((row) => {
		frappe.model.clear_doc(row.doctype, row.name);
	});
	frm.refresh_field('items');
}

function get_pi_deduction_row_values(frm, item_code, amount, description) {
	const conversion_rate = flt(frm.doc.conversion_rate || 1);
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
		base_rate: line_amount * conversion_rate,
		base_amount: line_amount * conversion_rate,
		description,
		project: frm.doc.project,
		site: 'Transit',
	};
}

function apply_pi_deduction_row_values(row, frm, amount, description) {
	Object.assign(row, get_pi_deduction_row_values(frm, row.item_code, amount, description));
}

function recalculate_purchase_deductions(frm) {
	// Only recalculate if the document is in draft and not an advance invoice
	if (frm.doc.docstatus !== 0 || frm.doc.custom_is_advance) {
		return;
	}

	if (cint(frm.doc.custom_skip_advance_deduction)) {
		strip_purchase_advance_rows(frm);
		return;
	}

	// Find linked Purchase Order from items
	let purchase_order = null;
	for (let item of (frm.doc.items || [])) {
		if (item.purchase_order) {
			purchase_order = item.purchase_order;
			break;
		}
	}

	if (!purchase_order) return;

	const form_items = (frm.doc.items || []).map((item) => ({
		item_code: item.item_code,
		amount: item.amount,
		boq_item: item.boq_item,
		custom_skip_advance_deduction: item.custom_skip_advance_deduction,
		purchase_receipt: item.purchase_receipt,
	}));

	// Fetch PO retention/advance percentages and supplier/subcontractor type
	Promise.all([
		frappe.db.get_value('Purchase Order', purchase_order,
			['custom_retention_', 'custom_advance_', 'custom_suppliersubcontractor']),
		frappe.call({
			method: 'construction_management.api.purchase_receipt_utils.get_purchase_advance_billable_for_form',
			args: {
				items: form_items,
				skip_doc_advance: cint(frm.doc.custom_skip_advance_deduction),
			},
		}),
	]).then(([poResult, billableResult]) => {
		if (!poResult.message) return;

		// Only apply for Subcontractor type
		if (poResult.message.custom_suppliersubcontractor !== 'Subcontractor') return;

		const retention_pct = flt(poResult.message.custom_retention_);
		const advance_pct = flt(poResult.message.custom_advance_);

		if (retention_pct <= 0 && advance_pct <= 0) return;

		const total_billable = flt(billableResult.message && billableResult.message.total_billable);
		const advance_billable = flt(billableResult.message && billableResult.message.advance_billable);

		let pr_has_retention = false;
		let pr_has_advance = false;
		for (let item of (frm.doc.items || [])) {
			if (item.purchase_receipt && item.item_code === 'RETENTION-DEDUCTION') {
				pr_has_retention = true;
			}
			if (item.purchase_receipt && item.item_code === 'ADVANCE-DEDUCTION') {
				pr_has_advance = true;
			}
		}

		// Update or create retention deduction (skip if PR already has it)
		if (retention_pct > 0 && !pr_has_retention) {
			const retention_amount = flt(total_billable * retention_pct / 100, 2);

			if (retention_amount > 0) {
				let retention_row = (frm.doc.items || []).find(i => i.item_code === 'RETENTION-DEDUCTION');
				const retention_desc = `Retention deduction (${retention_pct}%)`;

				if (retention_row) {
					apply_pi_deduction_row_values(retention_row, frm, retention_amount, retention_desc);
				} else {
					const new_row = frm.add_child('items');
					Object.assign(
						new_row,
						get_pi_deduction_row_values(frm, 'RETENTION-DEDUCTION', retention_amount, retention_desc)
					);
				}
			} else {
				const retention_row = (frm.doc.items || []).find(i => i.item_code === 'RETENTION-DEDUCTION');
				if (retention_row) {
					frappe.model.clear_doc(retention_row.doctype, retention_row.name);
				}
			}
		}

		// Update or create advance deduction (skip if PR already has it)
		if (advance_pct > 0 && !pr_has_advance) {
			const advance_amount = flt(advance_billable * advance_pct / 100, 2);

			if (advance_amount > 0) {
				let advance_row = (frm.doc.items || []).find(i => i.item_code === 'ADVANCE-DEDUCTION');
				const advance_desc = `Advance deduction (${advance_pct}%)`;

				if (advance_row) {
					apply_pi_deduction_row_values(advance_row, frm, advance_amount, advance_desc);
				} else {
					const new_row = frm.add_child('items');
					Object.assign(
						new_row,
						get_pi_deduction_row_values(frm, 'ADVANCE-DEDUCTION', advance_amount, advance_desc)
					);
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
