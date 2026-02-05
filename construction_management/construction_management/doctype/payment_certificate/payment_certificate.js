frappe.ui.form.on('Payment Certificate', {
    setup: function (frm) {
        frm.set_query('taxes_and_charges', function () {
            return {
                filters: {
                    company: frm.doc.company
                }
            };
        });
    },

    refresh: function (frm) {
        // Trigger type based fields setup
        frm.trigger('type');

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

    type: function (frm) {
        // Update taxes_and_charges options based on type
        if (frm.doc.type === 'Sales') {
            frm.set_df_property('taxes_and_charges', 'options', 'Sales Taxes and Charges Template');
            frm.set_df_property('taxes', 'options', 'Sales Taxes and Charges');
        } else {
            frm.set_df_property('taxes_and_charges', 'options', 'Purchase Taxes and Charges Template');
            frm.set_df_property('taxes', 'options', 'Purchase Taxes and Charges');
        }
    },

    taxes_and_charges: function (frm) {
        if (frm.doc.taxes_and_charges) {
            frappe.call({
                method: "erpnext.controllers.accounts_controller.get_taxes_and_charges",
                args: {
                    "master_doctype": frm.doc.type === 'Sales' ? "Sales Taxes and Charges Template" : "Purchase Taxes and Charges Template",
                    "master_name": frm.doc.taxes_and_charges
                },
                callback: function (r) {
                    if (r.message) {
                        frm.set_value("taxes", r.message);
                        frm.events.calculate_taxes(frm);
                    }
                }
            });
        }
    },

    apply_discount_on: function (frm) {
        frm.events.calculate_totals(frm);
    },

    discount_amount: function (frm) {
        frm.events.calculate_totals(frm);
    },

    calculate_taxes: function (frm) {
        let total_taxes = 0;
        let accepted_amount = flt(frm.doc.accepted_amount);

        // If discount is on Net Total, the taxable amount is reduced
        // But wait, the calculate_totals already reduces accepted_amount if On Net Total.
        // So we just use accepted_amount.

        (frm.doc.taxes || []).forEach(tax => {
            if (tax.charge_type === "On Net Total") {
                tax.tax_amount = flt(accepted_amount * tax.rate / 100);
            }
            total_taxes += flt(tax.tax_amount);
        });

        frm.set_value('total_taxes_and_charges', total_taxes);

        // Grand Total calculation depends on where discount is applied
        let grand_total = accepted_amount + total_taxes;
        if (frm.doc.apply_discount_on === "Grand Total" && frm.doc.discount_amount) {
            grand_total -= flt(frm.doc.discount_amount);
        }
        frm.set_value('grand_total', grand_total);
    },

    project: function (frm) {
        frm.set_value('proforma_invoice', '');
        frm.set_value('boq_item', '');

        // Fetch company from project
        if (frm.doc.project) {
            frappe.db.get_value('Project', frm.doc.project, 'company', (r) => {
                if (r && r.company) {
                    frm.set_value('company', r.company);
                }
            });
        }
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
                        // Recalculate taxes if amount changes
                        frm.events.calculate_totals(frm);
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

        // Trigger retention calculation so we have retention_amount for net_certified_amount
        frm.events.calculate_retention(frm);

        let accepted_amount = total_accepted;
        if (frm.doc.apply_discount_on === "Net Total" && frm.doc.discount_amount) {
            accepted_amount -= flt(frm.doc.discount_amount);
        }
        frm.set_value('accepted_amount', accepted_amount);

        // Calculate net_certified_amount for items
        let total_retention = flt(frm.doc.retention_amount);
        frm.doc.items.forEach(item => {
            let item_retention = 0;
            if (total_accepted > 0) {
                let item_share = flt(item.accepted_amount) / total_accepted;
                item_retention = total_retention * item_share;
            }
            item.net_certified_amount = flt(item.accepted_amount) - item_retention;
        });
        frm.refresh_field('items');

        let original = frm.doc.type === "Sales" ? flt(frm.doc.proforma_amount) : flt(frm.doc.pr_amount);
        let variance = original - total_accepted;
        frm.set_value('variance', variance);
        frm.set_value('variance_percent', original > 0 ? (variance / original) * 100 : 0);

        // Recalculate taxes on amount change
        frm.events.calculate_taxes(frm);
    },

    retention_percentage: function (frm) {
        frm.events.calculate_totals(frm);
    },

    calculate_retention: function (frm) {
        if (frm.doc.type !== "Sales" || !frm.doc.project) return;

        if (frm.doc.retention_percentage) {
            let total_accepted_before_discount = 0;
            (frm.doc.items || []).forEach(item => {
                total_accepted_before_discount += flt(item.accepted_amount);
            });

            // Retention is usually on Gross Accepted (before extra discounts)
            let retention_amount = total_accepted_before_discount * (flt(frm.doc.retention_percentage) / 100.0);
            frm.set_value('retention_amount', retention_amount);
        }
    }
});

frappe.ui.form.on('Sales Taxes and Charges', {
    rate: function (frm, cdt, cdn) {
        frm.events.calculate_taxes(frm);
    },
    tax_amount: function (frm, cdt, cdn) {
        frm.events.calculate_taxes(frm);
    },
    taxes_remove: function (frm) {
        frm.events.calculate_taxes(frm);
    }
});

frappe.ui.form.on('Purchase Taxes and Charges', {
    rate: function (frm, cdt, cdn) {
        frm.events.calculate_taxes(frm);
    },
    tax_amount: function (frm, cdt, cdn) {
        frm.events.calculate_taxes(frm);
    },
    taxes_remove: function (frm) {
        frm.events.calculate_taxes(frm);
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
