// Copyright (c) 2026, Construction Management and contributors
// For license information, please see license.txt

frappe.ui.form.on("Daily Progress Record", {
    refresh(frm) {
        if (frm.is_new()) {
            (frm.doc.materials || []).forEach(function (item) {
                frappe.model.set_value(item.doctype, item.name, "stock_entry", "");
            });
        }
    },
});
