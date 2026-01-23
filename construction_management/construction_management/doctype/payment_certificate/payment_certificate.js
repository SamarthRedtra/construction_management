frappe.ui.form.on('Payment Certificate', {
    refresh: function (frm) {
        // Make total amounts read-only if items are present to force item-level management
        if (frm.doc.items && frm.doc.items.length > 0) {
            frm.set_df_property('proforma_amount', 'read_only', 1);
            frm.set_df_property('accepted_amount', 'read_only', 1);
        }

        frm.set_query('proforma_invoice', function () {
            let filters = {
                project: frm.doc.project,
                docstatus: 1,
                status: ['not in', ['Converted', 'Cancelled']]
            };

            if (frm.doc.boq_item) {
                return {
                    query: "construction_management.construction_management.doctype.payment_certificate.payment_certificate.get_proforma_invoices_for_item",
                    filters: {
                        ...filters,
                        boq_item: frm.doc.boq_item
                    }
                };
            }

            return {
                filters: filters
            };
        });

        frm.set_query('boq_item', function () {
            if (frm.doc.proforma_invoice) {
                return {
                    query: "construction_management.api.boq_tree.get_proforma_boq_items",
                    filters: {
                        proforma_invoice: frm.doc.proforma_invoice
                    }
                };
            }
            return {
                filters: {
                    project: frm.doc.project
                }
            };
        });
    },

    project: function (frm) {
        frm.set_value('proforma_invoice', '');
        frm.set_value('boq_item', '');
    },

    proforma_invoice: function (frm) {
        if (frm.doc.proforma_invoice) {
            frappe.call({
                method: 'construction_management.construction_management.doctype.proforma_invoice.proforma_invoice.get_proforma_details',
                args: {
                    proforma_name: frm.doc.proforma_invoice
                },
                callback: function (r) {
                    if (r.message && r.message.status === 'success') {
                        const details = r.message.proforma;
                        frm.set_value('customer', details.customer);
                        frm.set_value('proforma_amount', details.net_amount || details.amount);
                        if (!frm.doc.accepted_amount) {
                            frm.set_value('accepted_amount', details.net_amount || details.amount);
                        }
                    }
                }
            });
        }
    },

    calculate_totals: function (frm) {
        if (!frm.doc.items || frm.doc.items.length === 0) return;

        let total_proforma = 0;
        let total_accepted = 0;

        frm.doc.items.forEach(item => {
            total_proforma += flt(item.amount);
            total_accepted += flt(item.accepted_amount);
        });

        frm.set_value('proforma_amount', total_proforma);
        frm.set_value('accepted_amount', total_accepted);

        let original = frm.doc.type === "Sales" ? flt(frm.doc.proforma_amount) : flt(frm.doc.pr_amount);
        let variance = original - total_accepted;
        frm.set_value('variance', variance);
        frm.set_value('variance_percent', original > 0 ? (variance / original) * 100 : 0);
    }
});

frappe.ui.form.on('Payment Certificate Item', {
    accepted_amount: function (frm, cdt, cdn) {
        let item = locals[cdt][cdn];
        frappe.model.set_value(cdt, cdn, 'variance', flt(item.amount) - flt(item.accepted_amount));
        frm.events.calculate_totals(frm);
    },
    items_add: function (frm) {
        frm.events.calculate_totals(frm);
    },
    items_remove: function (frm) {
        frm.events.calculate_totals(frm);
    }
});
