// Copyright (c) 2026, Construction Management
// License: MIT

(function () {
	const existing = frappe.listview_settings["Sales Order"] || {};
	const existing_onload = existing.onload;
	const existing_add_fields = existing.add_fields || [];

	frappe.listview_settings["Sales Order"] = {
		...existing,
		add_fields: [...new Set([...existing_add_fields, "project"])],
		onload(listview) {
			if (typeof existing_onload === "function") {
				existing_onload(listview);
			}

			if (!frappe.model.can_create("Sales Invoice")) {
				return;
			}

			listview.page.add_action_item(__("Combined Tax Invoice"), () => {
				construction_management.combined_sales_invoice_from_so.create_from_listview(
					listview
				);
			});
		},
	};
})();
