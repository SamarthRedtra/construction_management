// Copyright (c) 2026, Construction Management
// License: MIT

function is_commission_payout_entry(frm) {
	return cint(frm.doc.custom_is_commission_payout)
		|| cint(frm.doc.__commission_payout_from_dashboard)
		|| Boolean(frm.doc.custom_commission_sales_invoice);
}

function configure_commission_payout_form(frm) {
	if (!is_commission_payout_entry(frm)) {
		return;
	}

	frm.set_df_property('custom_commission_sales_invoice', 'hidden', 0);
	frm.set_df_property('custom_commission_sales_invoice', 'read_only', 1);
	frm.set_df_property('custom_is_commission_payout', 'hidden', 0);
	frm.set_df_property('custom_is_commission_payout', 'read_only', 1);

	if (!frm.doc.custom_is_commission_payout) {
		frm.set_value('custom_is_commission_payout', 1);
	}
}

frappe.ui.form.on('Payment Entry', {
	onload(frm) {
		configure_commission_payout_form(frm);
	},

	refresh(frm) {
		configure_commission_payout_form(frm);
	},

	before_save(frm) {
		if (!is_commission_payout_entry(frm)) {
			return;
		}
		const invoice = frm.doc.custom_commission_sales_invoice;
		if (invoice) {
			frm.set_value(
				'remarks',
				`Commission payout for Sales Invoice ${invoice}`
			);
			frm.set_value('custom_remarks', 1);
			frm.set_value('custom_is_commission_payout', 1);
		}
	},
});
