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

function apply_commission_payout_fields(frm, invoice) {
	if (!invoice || !frm.fields_dict.custom_commission_sales_invoice) {
		return;
	}

	frm.set_value('custom_commission_sales_invoice', invoice);
	frm.set_value('custom_is_commission_payout', 1);
	frm.set_value('remarks', `${COMMISSION_PAYOUT_REMARK_PREFIX}${invoice}`);
	frm.set_value('custom_remarks', 1);
	frm.set_df_property('custom_commission_sales_invoice', 'hidden', 0);
	frm.set_df_property('custom_commission_sales_invoice', 'read_only', 1);
}

function sync_commission_payout_fields(frm) {
	if (!is_commission_payout_entry(frm)) {
		return;
	}

	let invoice = frm.doc.custom_commission_sales_invoice;
	if (!invoice) {
		invoice = extract_commission_invoice_from_remarks(frm.doc.remarks);
	}
	if (!invoice && frappe.commission_payout_invoice) {
		invoice = frappe.commission_payout_invoice;
	}

	if (invoice) {
		apply_commission_payout_fields(frm, invoice);
	}
}

frappe.ui.form.on('Payment Entry', {
	onload(frm) {
		sync_commission_payout_fields(frm);
	},

	refresh(frm) {
		sync_commission_payout_fields(frm);
	},

	before_save(frm) {
		sync_commission_payout_fields(frm);
	},
});
