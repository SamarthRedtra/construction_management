// Copyright (c) 2026, Construction Management
// License: MIT

frappe.ui.form.on("Bulk Material Issue Tool", {
	onload(frm) {
		if (!frm.doc.company) {
			frm.set_value(
				"company",
				frappe.defaults.get_default("company") || frappe.defaults.get_user_default("company")
			);
		}
	},
	refresh(frm) {
		frm.disable_save();
	},
	fetch_eligible_sources(frm) {
		if (!frm.doc.company) {
			frappe.msgprint(__("Company is required"));
			return;
		}

		frappe.dom.freeze(__("Fetching eligible sources..."));
		frappe.call({
			method: "construction_management.construction_management.doctype.bulk_material_issue_tool.bulk_material_issue_tool.fetch_eligible_sources",
			args: {
				company: frm.doc.company,
				source_type: frm.doc.source_type,
				project: frm.doc.project,
				from_date: frm.doc.from_date,
				to_date: frm.doc.to_date,
				posting_date_override: frm.doc.posting_date_override,
				selected_sources: frm.selected_sources || null,
				hide_zero_stock: frm.doc.show_zero_stock_rows ? 0 : 1,
			},
			callback(r) {
				frappe.dom.unfreeze();
				const rows = r.message || [];
				frm.clear_table("items");
				let stock_limited_count = 0;
				let zero_stock_count = 0;
				rows.forEach((row) => {
					const child = frm.add_child("items");
					Object.assign(child, {
						source_doctype: row.source_doctype,
						source_name: row.source_name,
						source_posting_date: row.source_posting_date,
						source_line_name: row.source_line_name,
						item_code: row.item_code,
						warehouse: row.warehouse,
						remaining_qty: row.remaining_qty,
						available_qty: row.available_qty,
						qty_to_issue: row.qty_to_issue,
						project: row.project,
						boq_item: row.boq_item,
						bill_no: row.bill_no,
						posting_date: row.posting_date,
						status: "Pending",
						stock_entry: "",
						error_message: "",
					});
					if (flt(row.available_qty) <= 0) {
						zero_stock_count += 1;
					} else if (flt(row.qty_to_issue) < flt(row.remaining_qty)) {
						stock_limited_count += 1;
					}
				});
				frm.refresh_field("items");
				let message = __("{0} eligible row(s) loaded", [rows.length]);
				if (stock_limited_count) {
					message = __(
						"{0} row(s) loaded. {1} capped to available stock. Posting date follows BOQ Settings.",
						[rows.length, stock_limited_count]
					);
				}
				frappe.show_alert({
					message,
					indicator: rows.length ? (stock_limited_count ? "orange" : "green") : "orange",
				});
			},
			error() {
				frappe.dom.unfreeze();
			},
		});
	},
	create_material_issues(frm) {
		if (!frm.doc.items || !frm.doc.items.length) {
			frappe.msgprint(__("Fetch eligible sources first"));
			return;
		}

		const rows = frm.doc.items.filter((row) => flt(row.qty_to_issue) > 0);
		if (!rows.length) {
			frappe.msgprint(__("No rows with quantity to issue"));
			return;
		}

		frappe.dom.freeze(__("Creating Material Issues..."));
		frappe.call({
			method: "construction_management.construction_management.doctype.bulk_material_issue_tool.bulk_material_issue_tool.process_bulk_material_issues",
			args: {
				company: frm.doc.company,
				action_type: frm.doc.action_type,
				posting_date_override: frm.doc.posting_date_override || null,
				rows: rows,
			},
			callback(r) {
				frappe.dom.unfreeze();
				const results = r.message || [];
				const result_map = {};
				results.forEach((result) => {
					result_map[`${result.source_doctype}::${result.source_name}`] = result;
				});

				(frm.doc.items || []).forEach((row) => {
					const key = `${row.source_doctype}::${row.source_name}`;
					const result = result_map[key];
					if (!result) {
						return;
					}
					frappe.model.set_value(row.doctype, row.name, "status", result.status);
					frappe.model.set_value(row.doctype, row.name, "stock_entry", result.stock_entry || "");
					frappe.model.set_value(
						row.doctype,
						row.name,
						"error_message",
						result.error_message || ""
					);
				});
				frm.refresh_field("items");

				const success_count = results.filter((row) => row.status === "Success").length;
				const failed_count = results.length - success_count;
				frappe.msgprint(
					__(
						"Created {0} Material Issue(s). Failed: {1}",
						[success_count, failed_count]
					)
				);
			},
			error() {
				frappe.dom.unfreeze();
			},
		});
	},
});
