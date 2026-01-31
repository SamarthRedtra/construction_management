frappe.ui.form.on('Project BOQ', {
    refresh: function (frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__('Recalculate Estimated Value'), function () {
                frappe.call({
                    doc: frm.doc,
                    method: 'recalculate_estimated_value',
                    freeze: true,
                    callback: function (r) {
                        if (!r.exc) {
                            frappe.show_alert({
                                message: __('Estimated value updated: {0}', [format_currency(r.message, frm.doc.currency)]),
                                indicator: 'green'
                            });
                            frm.reload_doc();
                        }
                    }
                });
            }, __('Actions'));
        }
    }
});
