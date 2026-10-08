frappe.query_reports["Outstanding PO Items Missing From Catalog"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "catalog_request",
			label: __("Catalog Request"),
			fieldtype: "Link",
			options: "Controlled Catalog Request",
			reqd: 1,
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company") || undefined },
			}),
		},
		{
			fieldname: "purchase_order",
			label: __("Purchase Order"),
			fieldtype: "Link",
			options: "Purchase Order",
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
	],
};
