/**
 * Purchase Order client script extensions for Construction Management
 * 
 * BOQ dimension fields (bill_no, boq_item) are on the child table (items).
 */

frappe.ui.form.on('Purchase Order', {
	onload: function (frm) {
		// Setup cascading dimension filters for child table
		if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
			construction_management.dimension_utils.setup_accounting_dimension_filters(frm);
			construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'items');
		}
	},

	refresh: function (frm) {
		// Ensure additional discount controls are editable/visible in draft
		ensure_additional_discount_fields(frm);

		// Re-setup on refresh to ensure filters are applied after form loads
		if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
			construction_management.dimension_utils.setup_accounting_dimension_filters(frm);
			construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'items');
		}

		// Always clear the purchase history HTML first to avoid stale data from SPA navigation
		if (frm.fields_dict.custom_purchase_history) {
			frm.fields_dict.custom_purchase_history.$wrapper.html('');
		}

		// Render purchase history dashboard only for submitted Subcontractor POs
		if (frm.doc.docstatus === 1 && frm.doc.custom_suppliersubcontractor === 'Subcontractor') {
			render_purchase_history(frm);

			// Add "Record Advance" button if advance % is configured
			if (flt(frm.doc.custom_advance_) > 0) {
				frm.add_custom_button(__('Record Advance'), function () {
					frappe.model.with_doctype('Purchase Invoice', function () {
						var pi = frappe.model.get_new_doc('Purchase Invoice');
						pi.supplier = frm.doc.supplier;
						pi.company = frm.doc.company;
						pi.project = frm.doc.project;
						pi.currency = frm.doc.currency;
						pi.conversion_rate = frm.doc.conversion_rate;
						pi.buying_price_list = frm.doc.buying_price_list;
						pi.price_list_currency = frm.doc.price_list_currency;
						pi.plc_conversion_rate = frm.doc.plc_conversion_rate;
						pi.cost_center = frm.doc.cost_center;
						pi.custom_is_advance = 1;
						pi.update_billed_amount_in_purchase_order = 0;
						pi.custom_suppliersubcontractor = frm.doc.custom_suppliersubcontractor || '';

						if (frm.doc.bill_no) pi.bill_no = frm.doc.bill_no;
						if (frm.doc.boq_item) pi.boq_item = frm.doc.boq_item;

						// Calculate advance amount
						var advance_pct = flt(frm.doc.custom_advance_);
						var advance_amount = flt(frm.doc.grand_total * advance_pct / 100, 2);

						if (advance_amount > 0) {
							var row = frappe.model.add_child(pi, 'items');
							row.item_code = 'PURCHASE-ADVANCE';
							row.item_name = 'Purchase Advance';
							row.qty = 1;
							row.rate = advance_amount;
							row.amount = advance_amount;
							row.uom = 'Nos';
							row.conversion_factor = 1.0;
							row.description = `Advance payment (${advance_pct}% of PO ${frm.doc.name})`;
							row.project = frm.doc.project;
							row.cost_center = frm.doc.cost_center;
							row.purchase_order = frm.doc.name
						}

						frappe.set_route('Form', 'Purchase Invoice', pi.name);
					});
				}, __('Create'));
			}
		}
	},

	before_save: function (frm) {
		// Auto-fill blank custom site fields to resolve mandatory dimension errors
		(frm.doc.items || []).forEach(item => {
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
	// Some deployments hide/lock these fields via Property Setters or scripts.
	// For Purchase Order drafts, keep ERPNext standard behavior: user can set additional discount.
	if (!frm || frm.doc.docstatus !== 0) return;

	const fields = ["discount_section", "apply_discount_on", "additional_discount_percentage", "discount_amount"];
	for (const f of fields) {
		if (!frm.fields_dict[f]) continue;
		frm.set_df_property(f, "hidden", 0);
		frm.set_df_property(f, "read_only", 0);
	}
}


function render_purchase_history(frm) {
	frappe.call({
		method: 'construction_management.api.purchase_order_utils.get_purchase_history',
		args: { purchase_order: frm.doc.name },
		callback: function (r) {
			if (!r.message) return;

			// Double-check we're still on the same PO (user may have navigated away)
			if (cur_frm && cur_frm.doc.name !== frm.doc.name) return;

			const d = r.message;
			const fmt = (val) => format_currency(val, frm.doc.currency);

			let html = `
			<div style="padding: 15px 0;">
				<div style="display: flex; gap: 15px; flex-wrap: wrap; margin-bottom: 20px;">
					<!-- Advance Card -->
					<div style="flex: 1; min-width: 200px; border: 1px solid var(--border-color); border-radius: 8px; padding: 15px; background: var(--card-bg);">
						<h6 style="color: var(--text-muted); margin-bottom: 10px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">Advance Payments</h6>
						<div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
							<span style="color: var(--text-muted);">Total Advance</span>
							<strong>${fmt(d.total_advance)}</strong>
						</div>
						<div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
							<span style="color: var(--text-muted);">Utilized</span>
							<strong style="color: var(--orange-500);">${fmt(d.advance_deducted)}</strong>
						</div>
						<div style="display: flex; justify-content: space-between;">
							<span style="color: var(--text-muted);">Balance</span>
							<strong style="color: ${d.advance_balance > 0 ? 'var(--green-600)' : 'var(--text-color)'};">${fmt(d.advance_balance)}</strong>
						</div>
					</div>

					<!-- Invoice Card -->
					<div style="flex: 1; min-width: 200px; border: 1px solid var(--border-color); border-radius: 8px; padding: 15px; background: var(--card-bg);">
						<h6 style="color: var(--text-muted); margin-bottom: 10px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">Purchase Invoices</h6>
						<div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
							<span style="color: var(--text-muted);">Total Invoiced</span>
							<strong>${fmt(d.total_invoice_amount)}</strong>
						</div>
						<div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
							<span style="color: var(--text-muted);">Total Tax</span>
							<strong>${fmt(d.total_tax)}</strong>
						</div>
						<div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
							<span style="color: var(--text-muted);">Net Billed</span>
							<strong style="color: var(--green-600);">${fmt(d.net_billed)}</strong>
						</div>
						<div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
							<span style="color: var(--text-muted);">Advance Invoices</span>
							<strong>${fmt(d.total_advance_invoices)}</strong>
						</div>
						<div style="display: flex; justify-content: space-between;">
							<span style="color: var(--text-muted);">Regular Invoices</span>
							<strong>${fmt(d.total_regular_invoices)}</strong>
						</div>
					</div>

					<!-- Retention Card -->
					<div style="flex: 1; min-width: 200px; border: 1px solid var(--border-color); border-radius: 8px; padding: 15px; background: var(--card-bg);">
						<h6 style="color: var(--text-muted); margin-bottom: 10px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">Retention (${d.retention_pct}%)</h6>
						<div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
							<span style="color: var(--text-muted);">Expected Total</span>
							<strong>${fmt(d.expected_retention)}</strong>
						</div>
						<div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
							<span style="color: var(--text-muted);">Deducted</span>
							<strong style="color: var(--orange-500);">${fmt(d.total_retention_deducted)}</strong>
						</div>
						<div style="display: flex; justify-content: space-between;">
							<span style="color: var(--text-muted);">Balance</span>
							<strong style="color: ${d.retention_balance > 0 ? 'var(--red-500)' : 'var(--green-600)'};">${fmt(d.retention_balance)}</strong>
						</div>
					</div>
				</div>`;

			// Advance Payments Table
			if (d.advances && d.advances.length > 0) {
				html += `
				<h6 style="margin-bottom: 8px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted);">Advance Payment Records</h6>
				<table class="table table-bordered table-sm" style="font-size: 12px;">
					<thead>
						<tr style="background: var(--subtle-fg);">
							<th>ID</th>
							<th>Date</th>
							<th>Amount</th>
							<th>Allocated</th>
							<th>Unallocated</th>
							<th>Status</th>
						</tr>
					</thead>
					<tbody>`;

				for (let adv of d.advances) {
					const status_color = adv.status === 'Active' ? 'green' :
						adv.status === 'Fully Utilized' ? 'blue' : 'orange';
					html += `
						<tr>
							<td><a href="/app/purchase-advance-payment/${adv.name}">${adv.name}</a></td>
							<td>${frappe.datetime.str_to_user(adv.date)}</td>
							<td>${fmt(adv.amount)}</td>
							<td>${fmt(adv.allocated_amount)}</td>
							<td>${fmt(adv.unallocated_amount)}</td>
							<td><span class="indicator-pill ${status_color}">${adv.status}</span></td>
						</tr>`;
				}

				html += `</tbody></table>`;
			}

			// Invoices Table
			if (d.invoices && d.invoices.length > 0) {
				html += `
				<h6 style="margin-top: 15px; margin-bottom: 8px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted);">Purchase Invoices</h6>
				<table class="table table-bordered table-sm" style="font-size: 12px;">
					<thead>
						<tr style="background: var(--subtle-fg);">
							<th>Invoice</th>
							<th>Date</th>
							<th>Grand Total</th>
							<th>Status</th>
							<th>Advance?</th>
						</tr>
					</thead>
					<tbody>`;

				for (let pi of d.invoices) {
					html += `
						<tr>
							<td><a href="/app/purchase-invoice/${pi.name}">${pi.name}</a></td>
							<td>${frappe.datetime.str_to_user(pi.posting_date)}</td>
							<td>${fmt(pi.grand_total)}</td>
							<td>${pi.status}</td>
							<td>${pi.custom_is_advance ? '✓' : ''}</td>
						</tr>`;
				}

				html += `</tbody></table>`;
			}

			html += `</div>`;

			// Final safety check before rendering
			if (frm.fields_dict.custom_purchase_history) {
				frm.fields_dict.custom_purchase_history.$wrapper.html(html);
			}
		}
	});
}

frappe.ui.form.on('Purchase Order Item', {
	items_add: function (frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, 'site', 'Transit');
	}
});
