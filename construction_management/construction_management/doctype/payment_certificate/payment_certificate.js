
frappe.ui.form.on('Payment Certificate', {
    refresh: function (frm) {
        frm.set_query('proforma_invoice', function () {
            let filters = {
                project: frm.doc.project,
                docstatus: 1,
                status: ['not in', ['Converted', 'Cancelled']]
            };

            if (frm.doc.boq_item) {
                // If BOQ Item is selected, filter Proformas that contain this item
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
            // Auto fetch details from Proforma
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
    }
});
