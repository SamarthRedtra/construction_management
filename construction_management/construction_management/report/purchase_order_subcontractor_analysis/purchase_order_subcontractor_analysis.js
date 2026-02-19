// Copyright (c) 2026, Construction Management
// License: MIT

frappe.query_reports["Purchase Order Subcontractor Analysis"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            width: "80",
            options: "Company",
            reqd: 1,
            default: frappe.defaults.get_user_default("Company"),
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            width: "80",
            reqd: 1,
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -6),
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            width: "80",
            reqd: 1,
            default: frappe.datetime.get_today(),
        },
        {
            fieldname: "project",
            label: __("Project"),
            fieldtype: "Link",
            width: "80",
            options: "Project",
        },
        {
            fieldname: "supplier",
            label: __("Supplier"),
            fieldtype: "Link",
            width: "80",
            options: "Supplier",
        },
        {
            fieldname: "name",
            label: __("Purchase Order"),
            fieldtype: "MultiSelectList",
            width: "80",
            options: "Purchase Order",
            get_data: function (txt) {
                let filters = { docstatus: 1, custom_suppliersubcontractor: "Subcontractor" };
                return frappe.db.get_link_options("Purchase Order", txt, filters);
            },
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "MultiSelectList",
            width: "80",
            get_data: function (txt) {
                let status = ["To Pay", "To Bill", "To Receive", "To Receive and Bill", "Completed", "Closed"];
                return status.map(s => ({ value: s, label: __(s), description: "" }));
            },
        },
        {
            fieldname: "group_by_po",
            label: __("Group by Purchase Order"),
            fieldtype: "Check",
            default: 1,
        },
    ],

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        let green_fields = ["received_qty", "billed_amount", "advance_paid", "retention_deducted"];
        let red_fields = ["retention_balance", "advance_balance"];

        if (green_fields.includes(column.fieldname) && data && data[column.fieldname] > 0) {
            value = "<span style='color:green'>" + value + "</span>";
        }
        if (red_fields.includes(column.fieldname) && data && data[column.fieldname] > 0) {
            value = "<span style='color:orange'>" + value + "</span>";
        }
        return value;
    },
};
