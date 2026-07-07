// Copyright (c) 2026, Construction Management
// License: MIT

frappe.provide("construction_management.combined_sales_invoice_from_so");

construction_management.combined_sales_invoice_from_so = {
	create_invoice(sales_orders, options = {}) {
		const selected = (sales_orders || []).filter(Boolean);
		if (!selected.length) {
			frappe.show_alert({ message: __("Select at least one Sales Order"), indicator: "orange" });
			return;
		}

		frappe.call({
			method:
				"construction_management.api.boq_invoice.make_combined_sales_invoice_from_selected_sales_orders",
			args: { sales_orders: selected },
			freeze: true,
			freeze_message: __("Creating combined Sales Invoice..."),
			callback(r) {
				if (r.exc || !r.message?.sales_invoice) {
					return;
				}
				frappe.show_alert({
					message: __("Sales Invoice {0} created", [r.message.sales_invoice]),
					indicator: "green",
				});
				if (options.route !== false) {
					frappe.set_route("Form", "Sales Invoice", r.message.sales_invoice);
				}
				if (typeof options.callback === "function") {
					options.callback(r.message);
				}
			},
		});
	},

	open_project_dialog(project, preselected = [], options = {}) {
		if (!project) {
			frappe.msgprint(__("Project is required to create a combined tax invoice"));
			return;
		}

		frappe.call({
			method: "construction_management.api.boq_invoice.get_billable_sales_orders_for_invoice",
			args: { project },
			callback(r) {
				const billable_sos = r.message || [];
				if (!billable_sos.length) {
					frappe.show_alert({
						message: __("No billable Sales Orders found for this project"),
						indicator: "orange",
					});
					return;
				}

				const preselected_set = new Set(preselected || []);
				const fields = billable_sos.map((so) => ({
					fieldtype: "Check",
					fieldname: so.name,
					label: `${so.name} — ${format_currency(so.pending_amount || so.amount)} (${frappe.datetime.str_to_user(so.posting_date)})`,
					default: preselected_set.has(so.name) ? 1 : billable_sos.length <= 2 ? 1 : 0,
				}));

				frappe.prompt(
					fields,
					(values) => {
						const selected_sos = Object.keys(values || {}).filter((key) => values[key]);
						construction_management.combined_sales_invoice_from_so.create_invoice(
							selected_sos,
							options
						);
					},
					__("Combined Tax Invoice from SO"),
					__("Create")
				);
			},
		});
	},

	create_from_listview(listview) {
		const checked = listview.get_checked_items(true) || [];
		if (!checked.length) {
			frappe.show_alert({ message: __("Select Sales Orders from the list"), indicator: "orange" });
			return;
		}

		const rows = (listview.data || []).filter((row) => checked.includes(row.name));
		const projects = [...new Set(rows.map((row) => row.project).filter(Boolean))];

		if (!projects.length) {
			frappe.msgprint(__("Selected Sales Orders must have a Project"));
			return;
		}
		if (projects.length > 1) {
			frappe.msgprint(__("Select Sales Orders from the same project only"));
			return;
		}

		const submitted = rows.filter((row) => row.docstatus === 1);
		if (submitted.length !== rows.length) {
			frappe.msgprint(__("Only submitted Sales Orders can be combined into one tax invoice"));
			return;
		}

		construction_management.combined_sales_invoice_from_so.open_project_dialog(
			projects[0],
			checked
		);
	},
};
