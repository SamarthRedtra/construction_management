// Copyright (c) 2026, Construction Management
// License: MIT

(function () {
	const existing = frappe.listview_settings["Stock Entry"] || {};
	const existing_onload = existing.onload;

	frappe.listview_settings["Stock Entry"] = {
		...existing,
		add_fields: [...new Set([...(existing.add_fields || []), "stock_entry_type"])],
		onload(listview) {
			if (typeof existing_onload === "function") {
				existing_onload(listview);
			}

			listview.page.add_action_item(__("Bulk Material Issue"), () => {
				const selected = listview.get_checked_items(true);
				if (!selected.length) {
					frappe.msgprint(__("Select at least one Stock Entry"));
					return;
				}

				const names = selected
					.filter(
						(row) => row.docstatus === 1 && row.stock_entry_type === "Material Transfer"
					)
					.map((row) => ({ doctype: "Stock Entry", name: row.name }));

				if (!names.length) {
					frappe.msgprint(__("Select submitted Material Transfer Stock Entries only"));
					return;
				}

				construction_management.bulk_material_issue.open_tool(names, {
					source_type: "Material Transfer",
					company: selected[0].company,
				});
			});
		},
	};
})();
