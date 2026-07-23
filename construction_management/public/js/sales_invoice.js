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

		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__('Add BOQ Service'), () => {
				if (!frm.doc.project) {
					frappe.msgprint(__('Please select a Project before adding a BOQ service.'));
					return;
				}
				open_boq_service_picker(frm);
			});
		}

		if (frm.doc.docstatus === 0 && frm.doc.project) {
			frm.add_custom_button(__('Pull Retention'), () => {
				pull_retention(frm);
			}, __('Get Deductions'));

			frm.add_custom_button(__('Pull Advance Deduction'), () => {
				pull_advance_deduction(frm);
			}, __('Get Deductions'));
		}

		construction_management.deduction_summary.render(frm);

		// Render reversal JV summary widget for submitted invoices
		if (frm.doc.docstatus === 1) {
			cm_render_si_jv_summary(frm);
		}
	}
});

function open_boq_service_picker(frm) {
	const d = new frappe.ui.Dialog({
		title: __('Add Project BOQ Service'),
		fields: [
			{
				fieldname: 'boq_item', label: __('BOQ Service'), fieldtype: 'Link',
				options: 'BOQ Item', reqd: 1,
				description: __('Only BOQ services with a linked Item for this project are available.'),
			},
			{ fieldname: 'description', label: __('Description'), fieldtype: 'Small Text', read_only: 1 },
			{ fieldtype: 'Column Break' },
			{ fieldname: 'linked_item', label: __('Linked Item'), fieldtype: 'Link', options: 'Item', read_only: 1 },
			{ fieldname: 'boq_total_qty', label: __('BOQ Total Qty'), fieldtype: 'Float' },
			{ fieldname: 'billed_qty', label: __('Billed / Ordered Qty'), fieldtype: 'Float', read_only: 1 },
			{ fieldname: 'balance_qty', label: __('Available Qty'), fieldtype: 'Float', read_only: 1 },
			{ fieldname: 'qty', label: __('Invoice Qty'), fieldtype: 'Float', reqd: 1, default: 1 },
			{ fieldname: 'rate', label: __('Rate'), fieldtype: 'Currency' },
			{ fieldname: 'qty_hint', fieldtype: 'HTML' },
		],
		primary_action_label: __('Add Service'),
		primary_action(values) {
			_add_boq_service_from_dialog(frm, d, values);
		},
	});

	d.set_query('boq_item', () => ({
		filters: { project: frm.doc.project, linked_item: ['!=', ''] },
	}));

	const refresh_balance_and_hint = () => _refresh_boq_service_dialog_balance(d);

	d.fields_dict.boq_item.df.onchange = () => {
		const boqItem = d.get_value('boq_item');
		if (!boqItem) return;
		_load_boq_service_details(frm, d, boqItem).then(() => {
			const details = d._boq_service_details;
			if (!details) return;
			d.set_value('qty', details.balance_qty > 0 ? details.balance_qty : 1).then(refresh_balance_and_hint);
		});
	};
	d.fields_dict.boq_total_qty.df.onchange = refresh_balance_and_hint;
	d.fields_dict.qty.df.onchange = refresh_balance_and_hint;

	d.show();
	_render_boq_qty_hint(d, null);
}

function _load_boq_service_details(frm, d, boqItem) {
	return frappe.call({
		method: 'construction_management.api.boq_invoice.get_project_boq_service_details',
		args: { project: frm.doc.project, boq_item: boqItem },
	}).then((r) => {
		const details = r.message;
		if (!details) return null;
		d._boq_service_details = details;
		d._boq_service_baseline = {
			total_qty: flt(details.total_qty),
			rate: flt(details.rate),
		};
		const locked = !!details.boq_locked;
		d.set_df_property('boq_total_qty', 'read_only', locked ? 1 : 0);
		d.set_df_property('rate', 'read_only', locked ? 1 : 0);
		return Promise.all([
			d.set_value('description', details.description),
			d.set_value('linked_item', details.item_code),
			d.set_value('boq_total_qty', details.total_qty),
			d.set_value('billed_qty', details.billed_qty),
			d.set_value('balance_qty', details.balance_qty),
			d.set_value('rate', details.rate),
		]).then(() => {
			_refresh_boq_service_dialog_balance(d);
			return details;
		});
	});
}

function _refresh_boq_service_dialog_balance(d) {
	const details = d._boq_service_details;
	if (!details) {
		_render_boq_qty_hint(d, null);
		return;
	}
	const billed = flt(details.billed_qty);
	const total = flt(d.get_value('boq_total_qty'));
	const invoice_qty = flt(d.get_value('qty'));
	const balance = Math.max(0, total - billed);
	d.set_value('balance_qty', balance);

	const overage = invoice_qty - balance;
	if (invoice_qty > 0 && overage > 0 && !cint(details.allow_overbilling)) {
		_render_boq_qty_hint(d, {
			overage,
			balance,
			invoice_qty,
			suggested_total: billed + invoice_qty,
			boq_locked: !!details.boq_locked,
		});
	} else if (details.boq_locked) {
		_render_boq_qty_hint(d, { boq_locked: true, info_only: true });
	} else {
		_render_boq_qty_hint(d, null);
	}
}

function _render_boq_qty_hint(d, hint) {
	const $wrap = d.fields_dict.qty_hint.$wrapper;
	$wrap.empty();
	if (!hint) {
		return;
	}
	if (hint.info_only && hint.boq_locked) {
		$wrap.html(`
			<div class="alert alert-warning" style="margin:8px 0 0;">
				${__('Parent Project BOQ is locked. BOQ Total Qty and Rate cannot be changed here.')}
			</div>
		`);
		return;
	}
	if (hint.boq_locked) {
		$wrap.html(`
			<div class="alert alert-danger" style="margin:8px 0 0;">
				${__('Invoice Qty exceeds available qty ({0}) by {1}. Parent Project BOQ is locked, so BOQ Total Qty cannot be increased here.',
					[hint.balance, hint.overage])}
			</div>
		`);
		return;
	}
	const suggested = flt(hint.suggested_total);
	$wrap.html(`
		<div class="alert alert-warning" style="margin:8px 0 0;">
			<p style="margin:0 0 8px;">
				${__('Invoice Qty ({0}) exceeds available qty ({1}) by {2}.',
					[hint.invoice_qty, hint.balance, hint.overage])}
			</p>
			<p style="margin:0 0 8px;">
				${__('Suggested BOQ Total Qty to cover this invoice: {0}', [suggested])}
			</p>
			<button type="button" class="btn btn-xs btn-primary cm-apply-suggested-boq-qty">
				${__('Use suggested BOQ qty')}
			</button>
		</div>
	`);
	$wrap.find('.cm-apply-suggested-boq-qty').on('click', () => {
		d.set_value('boq_total_qty', suggested).then(() => _refresh_boq_service_dialog_balance(d));
	});
}

function _add_boq_service_from_dialog(frm, d, values) {
	const details = d._boq_service_details;
	if (!details) {
		frappe.msgprint(__('Select a BOQ service first.'));
		return;
	}
	const invoice_qty = flt(values.qty);
	const rate = flt(values.rate);
	const boq_total_qty = flt(values.boq_total_qty);
	if (invoice_qty <= 0) {
		frappe.msgprint(__('Invoice quantity must be greater than zero.'));
		return;
	}

	const baseline = d._boq_service_baseline || {};
	const qty_changed = Math.abs(boq_total_qty - flt(baseline.total_qty)) > 0.000001;
	const rate_changed = Math.abs(rate - flt(baseline.rate)) > 0.000001;
	const needs_boq_update = (qty_changed || rate_changed) && !details.boq_locked;

	const append_row = (final_details) => {
		const billed = flt(final_details.billed_qty);
		const total = needs_boq_update ? boq_total_qty : flt(final_details.total_qty);
		const balance = Math.max(0, total - billed);
		if (invoice_qty > balance && !cint(final_details.allow_overbilling)) {
			frappe.msgprint(
				__('Invoice quantity cannot exceed the available BOQ quantity ({0}). Increase BOQ Total Qty or use the suggested value.',
					[balance])
			);
			_refresh_boq_service_dialog_balance(d);
			return;
		}

		const row = frm.add_child('items');
		frappe.model.set_value(row.doctype, row.name, 'item_code', final_details.item_code).then(() => {
			frappe.model.set_value(row.doctype, row.name, {
				item_name: final_details.description,
				description: final_details.description,
				qty: invoice_qty,
				rate: rate,
				amount: invoice_qty * rate,
				uom: final_details.uom,
				project: frm.doc.project,
				boq_item: final_details.boq_item,
				bill_no: final_details.bill_no,
			});
			frm.refresh_field('items');
			_si_deduction_debounce(frm);
		});
		d.hide();
	};

	if (!needs_boq_update) {
		append_row(details);
		return;
	}

	const update_args = { boq_item: details.boq_item };
	if (qty_changed) {
		update_args.total_qty = boq_total_qty;
	}
	if (rate_changed) {
		update_args.rate = rate;
	}

	frappe.call({
		method: 'construction_management.api.boq_tree.update_boq_item_base',
		args: update_args,
		freeze: true,
		freeze_message: __('Updating BOQ Item'),
	}).then(() => _load_boq_service_details(frm, d, details.boq_item)).then((updated) => {
		if (!updated) {
			frappe.msgprint(__('Could not refresh BOQ service details after update.'));
			return;
		}
		append_row(updated);
	});
}

/**
 * Renders a summary card of all Unearned Revenue reversal JVs linked to this Sales Invoice
 * in the form's Connections dashboard section.
 */
function cm_render_si_jv_summary(frm) {
	frappe.db.get_list('Journal Entry', {
		filters: { custom_sales_invoice: frm.doc.name, docstatus: 1 },
		fields: ['name', 'posting_date', 'total_debit', 'custom_sales_order', 'user_remark'],
		order_by: 'posting_date asc',
		limit: 50
	}).then(jvs => {
		if (!jvs || jvs.length === 0) return;

		const total_reversed = jvs.reduce((s, j) => s + flt(j.total_debit), 0);
		const currency = frm.doc.currency || frappe.boot.sysdefaults.currency;
		const fmt = (v) => format_currency(v, currency, 2);

		let rows_html = jvs.map(jv => {
			const so_link = jv.custom_sales_order
				? `<a href="${frappe.utils.get_form_link('Sales Order', jv.custom_sales_order)}">${jv.custom_sales_order}</a>`
				: '—';
			const link = frappe.utils.get_form_link('Journal Entry', jv.name);
			return `
				<tr>
					<td style="padding:5px 8px;"><a href="${link}">${jv.name}</a></td>
					<td style="padding:5px 8px;">${frappe.datetime.str_to_user(jv.posting_date)}</td>
					<td style="padding:5px 8px;text-align:right;">${fmt(jv.total_debit)}</td>
					<td style="padding:5px 8px;">${so_link}</td>
				</tr>`;
		}).join('');

		const html = `
			<div class="cm-jv-summary" style="margin-bottom:12px;border:1px solid #e0e0e0;border-radius:6px;overflow:hidden;font-size:12px;">
				<div style="background:#f0fff4;padding:8px 12px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #e0e0e0;">
					<strong>📗 Unearned Revenue Recognized</strong>
					<span style="color:#555;">
						${jvs.length} Reversal JV(s) &nbsp;|&nbsp;
						Total Recognized: <b>${fmt(total_reversed)}</b>
					</span>
				</div>
				<table style="width:100%;border-collapse:collapse;">
					<thead style="background:#fafafa;border-bottom:1px solid #eee;">
						<tr>
							<th style="padding:5px 8px;text-align:left;font-weight:500;">Journal Entry</th>
							<th style="padding:5px 8px;text-align:left;font-weight:500;">Date</th>
							<th style="padding:5px 8px;text-align:right;font-weight:500;">Amount Recognized</th>
							<th style="padding:5px 8px;text-align:left;font-weight:500;">Sales Order</th>
						</tr>
					</thead>
					<tbody>${rows_html}</tbody>
				</table>
			</div>`;

		// Remove old widget and inject at top of Connections section body
		const $conn = frm.dashboard.links_area.body;
		$conn.find('.cm-jv-summary').remove();
		$conn.prepend(html);
		frm.dashboard.links_area.show();
		frm.dashboard.show();
	});
}


frappe.ui.form.on('Sales Invoice Item', {
	items_add: function (frm, cdt, cdn) {
		_si_deduction_debounce(frm);
		construction_management.deduction_summary.render(frm);
	},

	items_remove: function (frm, cdt, cdn) {
		_si_deduction_debounce(frm);
		construction_management.deduction_summary.render(frm);
	},

	qty: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (_is_deduction_item(row)) return;
		_si_deduction_debounce(frm);
	},

	rate: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (_is_deduction_item(row)) return;
		_si_deduction_debounce(frm);
	},

	amount: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (_is_deduction_item(row)) {
			construction_management.deduction_summary.render(frm);
			return;
		}
		_si_deduction_debounce(frm);
	},

	item_code: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row && row.custom_include_in_deductions) _si_deduction_debounce(frm);
	},

	custom_include_in_deductions: function (frm, cdt, cdn) {
		_si_deduction_debounce(frm);
	}
});

const _DEDUCTION_ITEMS = ['RETENTION-DEDUCTION', 'ADVANCE-DEDUCTION', 'PURCHASE-ADVANCE'];

function _is_deduction_item(row) {
	return row && _DEDUCTION_ITEMS.includes(row.item_code);
}

// Debounce to avoid rapid-fire API calls when editing multiple fields
let _si_deduction_timer = null;
function _si_deduction_debounce(frm) {
	if (_si_deduction_timer) clearTimeout(_si_deduction_timer);
	_si_deduction_timer = setTimeout(() => {
		recalculate_deductions(frm);
	}, 800);
}

function pull_retention(frm) {
	if (!frm.doc.project) {
		frappe.msgprint(__('Please select a Project first'));
		return;
	}

	frappe.call({
		method: 'construction_management.api.boq_invoice.get_deduction_details',
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
				construction_management.deduction_summary.render(frm);
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
		method: 'construction_management.api.boq_invoice.get_deduction_details',
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
							label: __('Available BOQ Balance'),
							fieldname: 'available_boq_balance',
							fieldtype: 'Currency',
							default: flt(r.message.available_boq_balance),
							read_only: 1,
							description: __('Project BOQ total less billed BOQ lines (ex-VAT)')
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
						construction_management.deduction_summary.render(frm);
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

function recalculate_deductions(frm) {
	// Only recalculate if we have a project and the document is in draft
	// Skip if this is an advance invoice or from payment certificate/proforma
	if (!frm.doc.project || frm.doc.docstatus !== 0 ||
		frm.doc.custom_is_advanced || frm.doc.custom_payment_certificate ||
		frm.doc.custom_proforma_invoice || frm.doc.custom_is_proforma) {
		return;
	}

	// Check if any deduction items exist (per-item deductions)
	const has_deductions = (frm.doc.items || []).some(
		i => _DEDUCTION_ITEMS.includes(i.item_code)
	);
	const has_additional_service = (frm.doc.items || []).some(
		i => i.custom_include_in_deductions && !i.boq_item && !_DEDUCTION_ITEMS.includes(i.item_code)
	);
	if (!has_deductions && !has_additional_service) return;

	// Prevent re-entrant calls
	if (frm._recalculating_deductions) return;
	frm._recalculating_deductions = true;

	// Get retention/advance percentages from server
	frappe.call({
		method: 'construction_management.api.boq_invoice.get_deduction_details',
		args: {
			project: frm.doc.project,
			items: frm.doc.items,
			invoice_name: frm.doc.name
		},
		callback: function (r) {
			if (!r.message || !r.message.enable_progressive_boq) {
				return;
			}

			const retention_pct = flt(r.message.retention_percentage);
			const advance_pct = flt(r.message.advance_percentage);
			const skipAdvanceSet = new Set(r.message.skip_advance_boq_items || []);
			const hasPerItemDeductions = (frm.doc.items || []).some(
				i => _DEDUCTION_ITEMS.includes(i.item_code) && i.boq_item
			);

			// Build a map of boq_item -> BOQ item amount (non-deduction items)
			const boq_amounts = {};
			(frm.doc.items || []).forEach(item => {
				if (item.boq_item && !_DEDUCTION_ITEMS.includes(item.item_code)) {
					boq_amounts[item.boq_item] = flt(item.amount);
				}
			});

			// Recalculate each per-item deduction row
			let changed = false;
			(frm.doc.items || []).forEach(item => {
				if (!item.boq_item) return;

				const parent_amount = boq_amounts[item.boq_item] || 0;

				if (item.item_code === 'RETENTION-DEDUCTION' && retention_pct > 0) {
					const new_retention = flt(parent_amount * retention_pct / 100, precision('rate', item));
					if (flt(item.rate) !== -new_retention) {
						frappe.model.set_value(item.doctype, item.name, {
							'rate': -new_retention,
							'amount': -new_retention,
							'description': `Retention deduction (${retention_pct}%)`
						});
						changed = true;
					}
				}

				if (item.item_code === 'ADVANCE-DEDUCTION' && advance_pct > 0) {
					if (skipAdvanceSet.has(item.boq_item)) {
						if (flt(item.amount) !== 0) {
							frappe.model.set_value(item.doctype, item.name, {
								'rate': 0,
								'amount': 0,
								'qty': 0,
								'description': __('Advance deduction skipped for this BOQ item')
							});
							changed = true;
						}
						return;
					}
					const new_advance = flt(parent_amount * advance_pct / 100, precision('rate', item));
					if (flt(item.rate) !== -new_advance) {
						frappe.model.set_value(item.doctype, item.name, {
							'rate': -new_advance,
							'amount': -new_advance,
							'description': `Advance deduction (${advance_pct}%)`
						});
						changed = true;
					}
				}
			});

			if (changed) {
				frm.refresh_field('items');
			}
			if (hasPerItemDeductions) {
				sync_additional_service_deductions(frm, r.message);
			} else if (has_additional_service) {
				sync_global_deductions(frm, r.message);
			}
			frm.refresh_field('items');
			construction_management.deduction_summary.render(frm);
		},
		always: function () {
			frm._recalculating_deductions = false;
		}
	});
}

function sync_additional_service_deductions(frm, details) {
	const serviceTotal = (frm.doc.items || []).reduce((total, item) => {
		if (item.custom_include_in_deductions && !item.boq_item &&
			!item.custom_service_deduction && !_DEDUCTION_ITEMS.includes(item.item_code)) {
			return total + flt(item.amount);
		}
		return total;
	}, 0);
	const retention = Math.max(0, flt(serviceTotal) * flt(details.retention_percentage) / 100);
	const boqAdvance = (frm.doc.items || []).reduce((total, item) =>
		total + (item.item_code === 'ADVANCE-DEDUCTION' && item.boq_item && !item.custom_service_deduction
			? Math.abs(flt(item.amount)) : 0), 0);
	const advance = Math.max(0, flt(details.suggested_advance) - boqAdvance);
	sync_deduction_row(frm, 'RETENTION-DEDUCTION', retention,
		__('Retention deduction ({0}%) for additional services', [details.retention_percentage]), true);
	sync_deduction_row(frm, 'ADVANCE-DEDUCTION', advance,
		__('Advance deduction for additional services'), true);
}

function sync_global_deductions(frm, details) {
	sync_deduction_row(frm, 'RETENTION-DEDUCTION', flt(details.suggested_retention),
		__('Retention deduction ({0}%)', [details.retention_percentage]), false);
	sync_deduction_row(frm, 'ADVANCE-DEDUCTION', flt(details.suggested_advance),
		__('Deduction from advance payment'), false);
}

function sync_deduction_row(frm, itemCode, amount, description, isServiceDeduction) {
	let rows = (frm.doc.items || []).filter(item => item.item_code === itemCode &&
		Boolean(item.custom_service_deduction) === Boolean(isServiceDeduction));
	if (amount <= 0) {
		rows.forEach(row => frappe.model.clear_doc(row.doctype, row.name));
		frm.doc.items = (frm.doc.items || []).filter(row => !rows.includes(row));
		return;
	}
	let row = rows[0];
	if (!row) row = frm.add_child('items');
	frappe.model.set_value(row.doctype, row.name, {
		item_code: itemCode,
		qty: 1,
		rate: -amount,
		amount: -amount,
		description,
		project: frm.doc.project,
		custom_service_deduction: isServiceDeduction ? 1 : 0,
	});
	rows.slice(1).forEach(extra => frappe.model.clear_doc(extra.doctype, extra.name));
	if (rows.length > 1) frm.doc.items = (frm.doc.items || []).filter(row => !rows.slice(1).includes(row));
}
