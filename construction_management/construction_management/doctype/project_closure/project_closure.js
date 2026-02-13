// Copyright (c) 2026, Construction Management
// License: MIT

frappe.ui.form.on('Project Closure', {
    refresh(frm) {
        if (frm.doc.project && !frm.doc.items?.length && !frm.is_dirty()) {
            // Auto-fetch data if project is set but no items loaded yet
            frm.trigger('project');
        }

        if (frm.doc.project && frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Record Advance'), () => {
                record_advance_from_closure(frm.doc.project);
            }, __('Actions'));

            const retention_pending = flt(frm.doc.retention_pending);
            if (retention_pending > 0) {
                const fmt = frappe.format(retention_pending, { fieldtype: 'Currency' }, { only_value: true });
                frm.add_custom_button(__('Release Retention ({0})', [fmt]), () => {
                    release_retention_from_closure(frm.doc.project);
                }, __('Actions'));
            }
        }
    },

    project(frm) {
        if (!frm.doc.project) return;

        frappe.call({
            method: 'construction_management.construction_management.doctype.project_closure.project_closure.fetch_project_data',
            args: { project: frm.doc.project },
            freeze: true,
            freeze_message: __('Fetching project data...'),
            callback: function (r) {
                if (!r.message) return;

                const data = r.message;

                // Set header fields
                frm.set_value('project_boq', data.project_boq);
                frm.set_value('total_boq_value', data.total_boq_value);

                // Set cost fields
                frm.set_value('labour_cost', data.labour_cost);
                frm.set_value('material_cost', data.material_cost);
                frm.set_value('other_cost', data.other_cost);
                frm.set_value('total_project_cost', data.total_project_cost);

                // Set revenue fields
                frm.set_value('total_revenue', data.total_revenue);

                // Set advance & retention
                frm.set_value('retention_pending', data.retention_pending || 0);
                frm.set_value('advance_balance', data.advance_balance || 0);

                // Clear and populate items table
                frm.clear_table('items');
                (data.items || []).forEach(item => {
                    const row = frm.add_child('items');
                    row.sr_no = item.sr_no;
                    row.service_description = item.service_description;
                    row.boq_item = item.boq_item;
                    row.bill_no = item.bill_no || '';
                    row.billing_status = item.billing_status || 'Not Billed';
                    row.area_qty = item.area_qty;
                    row.uom = item.uom;
                    row.unit_price = item.unit_price;
                    row.total_amount = item.total_amount;
                    row.cost_to_date = item.cost_to_date;
                    row.labour_cost = item.labour_cost;
                    row.material_cost = item.material_cost;
                    row.subcontract_cost = item.subcontract_cost;
                    row.asset_cost = item.asset_cost;
                    row.expense_cost = item.expense_cost;
                    row.overhead_cost = item.overhead_cost;
                    row.to_date_amount = item.to_date_amount;
                    row.retention_amount = item.retention_amount;
                    row.advance_amount = item.advance_amount;
                    row.margin = item.margin;
                });

                frm.refresh_fields();
                frappe.show_alert({
                    message: __('Project data fetched successfully'),
                    indicator: 'green'
                });
            }
        });
    }
});

frappe.ui.form.on('Project Closure Item', {
    area_qty(frm, cdt, cdn) {
        calculate_item_total(frm, cdt, cdn);
    },

    unit_price(frm, cdt, cdn) {
        calculate_item_total(frm, cdt, cdn);
    }
});

function calculate_item_total(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    row.total_amount = flt(row.area_qty) * flt(row.unit_price);
    frm.refresh_field('items');

    // Recalculate subtotal
    let subtotal = 0;
    (frm.doc.items || []).forEach(item => {
        subtotal += flt(item.total_amount);
    });
    frm.set_value('services_subtotal', subtotal);
}

function record_advance_from_closure(project) {
    frappe.call({
        method: 'construction_management.api.project_closure_api.prepare_advance_sales_invoice',
        args: { project: project },
        callback: function (r) {
            if (r.message && r.message.invoice_name) {
                frappe.set_route('Form', 'Sales Invoice', r.message.invoice_name);
            } else if (r.message && r.message.error) {
                frappe.msgprint(r.message.error);
            }
        }
    });
}

function release_retention_from_closure(project) {
    frappe.call({
        method: 'construction_management.api.boq_invoice.release_retention',
        args: { project: project },
        callback: function (r) {
            if (r.message && r.message.invoice) {
                frappe.set_route('Form', 'Sales Invoice', r.message.invoice);
                cur_frm.reload_doc();
            } else if (r.exc) {
                frappe.msgprint(r.exc);
            }
        }
    });
}
