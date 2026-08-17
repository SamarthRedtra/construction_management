// Copyright (c) 2026, Construction Management
// License: MIT

const COMMISSION_PAYOUT_REMARK_PREFIX = 'Commission payout for Sales Invoice ';

function is_commission_payout_entry(frm) {
	return cint(frm.doc.custom_is_commission_payout)
		|| Boolean(frm.doc.custom_commission_sales_invoice)
		|| (frm.doc.remarks || '').includes(COMMISSION_PAYOUT_REMARK_PREFIX);
}

function extract_commission_invoice_from_remarks(remarks) {
	if (!remarks || !remarks.includes(COMMISSION_PAYOUT_REMARK_PREFIX)) {
		return '';
	}
	const rest = remarks.split(COMMISSION_PAYOUT_REMARK_PREFIX)[1] || '';
	return (rest.trim().split(/\s+/)[0] || '').trim();
}

function sync_commission_payout_fields(frm) {
	if (!is_commission_payout_entry(frm)) {
		return;
	}

	let invoice = frm.doc.custom_commission_sales_invoice;
	if (!invoice) {
		invoice = extract_commission_invoice_from_remarks(frm.doc.remarks);
	}

	if (invoice) {
		frm.doc.custom_commission_sales_invoice = invoice;
		frm.doc.custom_is_commission_payout = 1;
		frm.doc.remarks = `${COMMISSION_PAYOUT_REMARK_PREFIX}${invoice}`;
		frm.doc.custom_remarks = 1;
	}
}

function configure_commission_payout_form(frm) {
	if (!is_commission_payout_entry(frm)) {
		return;
	}

	sync_commission_payout_fields(frm);

	frm.set_df_property('custom_commission_sales_invoice', 'hidden', 0);
	frm.set_df_property('custom_commission_sales_invoice', 'read_only', 1);
}

frappe.ui.form.on('Payment Entry', {
	onload(frm) {
		configure_commission_payout_form(frm);
	},

	refresh(frm) {
		configure_commission_payout_form(frm);
	},

	before_save(frm) {
		sync_commission_payout_fields(frm);
	},
});
