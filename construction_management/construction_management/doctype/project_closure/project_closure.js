// Copyright (c) 2026, Construction Management
// License: MIT

frappe.ui.form.on('Project Closure', {
    refresh(frm) {
        if (frm.doc.project && !frm.doc.items?.length && !frm.is_dirty()) {
            // Auto-fetch data if project is set but no items loaded yet
            frm.trigger('project');
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

                // Set estimated cost (consolidated)
                frm.set_value('estimated_material_cost', data.estimated_material_cost || 0);
                frm.set_value('estimated_labour_cost', data.estimated_labour_cost || 0);
                frm.set_value('estimated_asset_cost', data.estimated_asset_cost || 0);
                frm.set_value('estimated_subcontract_cost', data.estimated_subcontract_cost || 0);
                frm.set_value('estimated_other_cost', data.estimated_other_cost || 0);
                frm.set_value('total_estimated_cost', data.total_estimated_cost || 0);

                // Set actual cost (consolidated)
                frm.set_value('actual_material_cost', data.actual_material_cost || 0);
                frm.set_value('actual_labour_cost', data.actual_labour_cost || 0);
                frm.set_value('actual_asset_cost', data.actual_asset_cost || 0);
                frm.set_value('actual_subcontract_cost', data.actual_subcontract_cost || 0);
                frm.set_value('actual_overhead_cost', data.actual_overhead_cost || 0);
                frm.set_value('actual_expense_cost', data.actual_expense_cost || 0);
                frm.set_value('total_actual_cost', data.total_actual_cost || 0);

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
                    row.estimated_material_cost = item.estimated_material_cost;
                    row.estimated_labour_cost = item.estimated_labour_cost;
                    row.estimated_asset_cost = item.estimated_asset_cost;
                    row.estimated_subcontract_cost = item.estimated_subcontract_cost;
                    row.estimated_other_cost = item.estimated_other_cost;
                    row.total_estimated_cost = item.total_estimated_cost;
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
