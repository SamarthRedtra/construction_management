// Material Request client script extensions for Construction Management

frappe.ui.form.on('Material Request', {
    onload: function (frm) {
        if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
            construction_management.dimension_utils.setup_accounting_dimension_filters(frm);
            construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'items');
        }
    },
    refresh: function (frm) {
        if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
            construction_management.dimension_utils.setup_accounting_dimension_filters(frm);
            construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'items');
        }

        // Explicit queries for BOQ dimensions in child table
        frm.set_query("bill_no", "items", function (doc, cdt, cdn) {
            let row = locals[cdt][cdn];
            let project = row.project || doc.project;
            if (project) {
                return { filters: { project: project } };
            }
            return {};
        });

        frm.set_query("boq_item", "items", function (doc, cdt, cdn) {
            let row = locals[cdt][cdn];
            if (row.bill_no) {
                return { filters: { parent_bill: row.bill_no } };
            } else {
                let project = row.project || doc.project;
                if (project) {
                    return { filters: { project: project } };
                }
            }
            return {};
        });
    }
});
