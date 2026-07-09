// Copyright (c) 2026, Construction Management
// License: MIT

(function () {
	const existing = frappe.listview_settings["Purchase Receipt"] || {};
	const existing_onload = existing.onload;

	frappe.listview_settings["Purchase Receipt"] = {
		...existing,
		onload(listview) {
			if (typeof existing_onload === "function") {
				existing_onload(listview);
			}

			listview.page.add_action_item(__("Bulk Material Issue"), () => {
				const selected = listview.get_checked_items(true);
				if (!selected.length) {
					frappe.msgprint(__("Select at least one Purchase Receipt"));
					return;
				}

				const names = selected
					.filter((row) => row.docstatus === 1)
					.map((row) => ({ doctype: "Purchase Receipt", name: row.name }));

				if (!names.length) {
					frappe.msgprint(__("Select submitted Purchase Receipts only"));
					return;
				}

				construction_management.bulk_material_issue.open_tool(names, {
					source_type: "Purchase Receipt",
					company: selected[0].company,
				});
			});
		},
	};
})();
