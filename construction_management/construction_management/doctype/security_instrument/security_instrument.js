frappe.ui.form.on('Security Instrument', {
	refresh(frm) {
		if (frm.doc.payment_entry) {
			frm.add_custom_button(__('Payment Entry'), () => {
				frappe.set_route('Form', 'Payment Entry', frm.doc.payment_entry);
			});
		}

		if (frm.doc.name && !['Redeemed', 'Cancelled'].includes(frm.doc.status || '')) {
			frm.add_custom_button(__('Mark Redeemed'), () => {
				frappe.confirm(
					__('Mark this security instrument as redeemed?'),
					() => {
						frappe.call({
							method: 'construction_management.api.security_instrument.mark_security_instrument_redeemed',
							args: { name: frm.doc.name },
							callback: function(r) {
								if (!r.exc) {
									frm.reload_doc();
								}
							}
						});
					}
				);
			});
		}
	}
});
