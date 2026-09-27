frappe.ui.form.on(['Purchase Order', 'Purchase Receipt', 'Stock Entry'], {
	refresh(frm) {
		if (!frm.doc.controlled_procurement || frm.doc.docstatus !== 0) return;
		frm.add_custom_button(__('Submit Controlled Document'), () => {
			frappe.call({
				method: 'construction_management.api.controlled_procurement.submit_document',
				args: { doctype: frm.doctype, name: frm.doc.name },
				freeze: true,
			}).then(() => frm.reload_doc());
		}, __('Actions'));
	},
});
