frappe.ui.form.on('Security Instrument', {
	refresh(frm) {
		if (frm.doc.payment_entry) {
			frm.add_custom_button(__('Issue Payment Entry'), () => {
				frappe.set_route('Form', 'Payment Entry', frm.doc.payment_entry);
			});
		}

		if (frm.doc.reclaim_payment_entry) {
			frm.add_custom_button(__('Reclaim Payment Entry'), () => {
				frappe.set_route('Form', 'Payment Entry', frm.doc.reclaim_payment_entry);
			});
		}

		if (
			frm.doc.name &&
			frm.doc.payment_entry &&
			!frm.doc.reclaim_payment_entry &&
			!['Reclaimed', 'Cancelled'].includes(frm.doc.status || '')
		) {
			frm.add_custom_button(__('Reclaim'), () => {
				frappe.confirm(
					__('Create a reclaim Payment Entry for this security instrument?'),
					() => {
						frappe.call({
							method: 'construction_management.api.security_instrument.reclaim_security_instrument',
							args: { name: frm.doc.name },
							callback: function(r) {
								if (!r.exc && r.message && r.message.payment_entry) {
									frappe.set_route('Form', 'Payment Entry', r.message.payment_entry);
								} else if (!r.exc) {
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
