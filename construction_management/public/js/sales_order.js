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

		// Recalculate BOQ retention & advance (draft, saved orders with project + BOQ lines)
		if (
			!frm.is_new() &&
			frm.doc.docstatus === 0 &&
			frm.doc.project &&
			(frm.doc.items || []).some((r) => r.boq_item)
		) {
			frm.add_custom_button(
				__('Recalculate Retention & Advance'),
				function () {
					frappe.call({
						method:
							'construction_management.api.boq_invoice.recalculate_sales_order_boq_deductions',
						args: { sales_order: frm.doc.name },
						freeze: true,
						freeze_message: __('Updating deduction lines...'),
						callback: function (r) {
							if (!r.exc) {
								frappe.show_alert({
									message: __('Retention and advance lines updated'),
									indicator: 'green',
								});
								frm.reload_doc();
							}
						},
					});
				},
				__('Actions')
			);
		}

		// Render Unearned Revenue JV summary widget
		if (frm.doc.docstatus === 1) {
			cm_render_so_jv_summary(frm);
		}
	}
});

/**
 * Renders a summary card of all Unearned Revenue Journal Entries linked to this Sales Order
 * in the form's Connections dashboard section.
 */
function cm_render_so_jv_summary(frm) {
	frappe.db.get_list('Journal Entry', {
		filters: { custom_sales_order: frm.doc.name, docstatus: 1 },
		fields: ['name', 'posting_date', 'total_debit', 'custom_sales_invoice', 'user_remark'],
		order_by: 'posting_date asc',
		limit: 50
	}).then(jvs => {
		if (!jvs || jvs.length === 0) return;

		const originals = jvs.filter(j => !j.custom_sales_invoice);
		const reversals = jvs.filter(j => j.custom_sales_invoice);
		const total_unearned = originals.reduce((s, j) => s + flt(j.total_debit), 0);
		const total_reversed = reversals.reduce((s, j) => s + flt(j.total_debit), 0);
		const currency = frm.doc.currency || frappe.boot.sysdefaults.currency;
		const fmt = (v) => format_currency(v, currency, 2);

		let rows_html = jvs.map(jv => {
			const is_reversal = !!jv.custom_sales_invoice;
			const badge = is_reversal
				? `<span style="background:#fff3cd;color:#856404;border:1px solid #ffc107;border-radius:4px;padding:1px 7px;font-size:11px;">Reversal</span>`
				: `<span style="background:#d4edda;color:#155724;border:1px solid #28a745;border-radius:4px;padding:1px 7px;font-size:11px;">Original</span>`;
			const link = frappe.utils.get_form_link('Journal Entry', jv.name);
			const si_link = is_reversal
				? ` &rarr; <a href="${frappe.utils.get_form_link('Sales Invoice', jv.custom_sales_invoice)}">${jv.custom_sales_invoice}</a>`
				: '';
			return `
				<tr>
					<td style="padding:5px 8px;"><a href="${link}">${jv.name}</a></td>
					<td style="padding:5px 8px;">${frappe.datetime.str_to_user(jv.posting_date)}</td>
					<td style="padding:5px 8px;text-align:right;">${fmt(jv.total_debit)}</td>
					<td style="padding:5px 8px;">${badge}${si_link}</td>
				</tr>`;
		}).join('');

		const html = `
			<div class="cm-jv-summary" style="margin-bottom:12px;border:1px solid #e0e0e0;border-radius:6px;overflow:hidden;font-size:12px;">
				<div style="background:#f0f4ff;padding:8px 12px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #e0e0e0;">
					<strong>📒 Unearned Revenue JVs</strong>
					<span style="color:#555;">
						${originals.length} JV &nbsp;|&nbsp;
						Unearned: <b>${fmt(total_unearned)}</b> &nbsp;|&nbsp;
						Recognized: <b>${fmt(total_reversed)}</b> &nbsp;|&nbsp;
						Remaining: <b style="color:${(total_unearned - total_reversed) > 0 ? '#856404' : '#155724'}">${fmt(total_unearned - total_reversed)}</b>
					</span>
				</div>
				<table style="width:100%;border-collapse:collapse;">
					<thead style="background:#fafafa;border-bottom:1px solid #eee;">
						<tr>
							<th style="padding:5px 8px;text-align:left;font-weight:500;">Journal Entry</th>
							<th style="padding:5px 8px;text-align:left;font-weight:500;">Date</th>
							<th style="padding:5px 8px;text-align:right;font-weight:500;">Amount</th>
							<th style="padding:5px 8px;text-align:left;font-weight:500;">Type</th>
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


/* Per-BOQ retention/advance: use Actions → Recalculate Retention & Advance after editing lines. */
