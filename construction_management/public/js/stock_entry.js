/**
 * Stock Entry client script extensions for Construction Management
 * 
 * BOQ dimension fields (bill_no, boq_item) are on the child table (items).
 */

frappe.ui.form.on('Stock Entry', {
	onload: function (frm) {
		// Setup cascading dimension filters for child table
		if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
			construction_management.dimension_utils.setup_accounting_dimension_filters(frm);
			construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'items');
		}
	},

	refresh: function (frm) {
		show_stock_entry_key_fields(frm);

		// Re-setup on refresh to ensure filters are applied after form loads
		if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
			construction_management.dimension_utils.setup_accounting_dimension_filters(frm);
			construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'items');
		}
		schedule_posting_date_balance_refresh(frm);
	},

	posting_date: function (frm) {
		schedule_posting_date_balance_refresh(frm);
	},

	posting_time: function (frm) {
		schedule_posting_date_balance_refresh(frm);
	},

	set_posting_time: function (frm) {
		schedule_posting_date_balance_refresh(frm);
	}
});

function show_stock_entry_key_fields(frm) {
	// These fields are required for historical stock and project accounting.
	frm.set_df_property('posting_date', 'hidden', 0);
	frm.set_df_property('posting_time', 'hidden', 0);
	frm.set_df_property('set_posting_time', 'hidden', 0);
	frm.set_df_property('accounting_dimensions_section', 'hidden', 0);
	frm.set_df_property('project', 'hidden', 0);
}

function schedule_posting_date_balance_refresh(frm) {
	if (frm.doc.docstatus !== 0 || !frm.doc.posting_date || !frm.doc.posting_time) {
		return;
	}
	clearTimeout(frm.__posting_date_balance_timer);
	frm.__posting_date_balance_timer = setTimeout(
		() => refresh_posting_date_balances(frm),
		250
	);
}

function refresh_posting_date_balances(frm) {
	const items = (frm.doc.items || [])
		.filter((row) => row.item_code && (row.s_warehouse || row.t_warehouse))
		.map((row) => ({
			name: row.name,
			item_code: row.item_code,
			s_warehouse: row.s_warehouse,
			t_warehouse: row.t_warehouse,
		}));
	if (!items.length) {
		return;
	}

	const timestamp = `${frm.doc.posting_date} ${frm.doc.posting_time}`;
	frappe.call({
		method: 'construction_management.api.stock_entry_balance.get_item_balances',
		args: {
			items,
			posting_date: frm.doc.posting_date,
			posting_time: frm.doc.posting_time,
		},
		callback(r) {
			if (`${frm.doc.posting_date} ${frm.doc.posting_time}` !== timestamp) {
				return;
			}
			(r.message || []).forEach((balance) => {
				const row = (frm.doc.items || []).find((item) => item.name === balance.name);
				if (row) {
					row.actual_qty = flt(balance.actual_qty);
				}
			});
			frm.refresh_field('items');
		},
	});
}
