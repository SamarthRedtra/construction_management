// Copyright (c) 2025, Construction Management and contributors
// For license information, please see license.txt

frappe.ui.form.on("BOQ Item", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.trigger("render_rate_history");
		}
		// Add "Recalculate Costs" button to refresh all cost calculations
		if (!frm.is_new()) {
			frm.add_custom_button(__("Recalculate Costs"), function () {
				frappe.call({
					method: "construction_management.construction_management.doctype.boq_item.boq_item.recalculate_costs",
					args: {
						boq_item_name: frm.doc.name
					},
					freeze: true,
					freeze_message: __("Recalculating costs..."),
					callback: function (r) {
						if (r.message && r.message.success) {
							frappe.show_alert({
								message: __("Costs recalculated successfully"),
								indicator: "green"
							});
							frm.reload_doc();
						} else {
							frappe.msgprint({
								title: __("Error"),
								message: r.message?.error || __("Failed to recalculate costs"),
								indicator: "red"
							});
						}
					}
				});
			}, __("Actions"));

			frm.add_custom_button(__("Calculate Progressive Billing"), function () {
				frappe.call({
					method: "construction_management.construction_management.doctype.boq_item.boq_item.recalculate_progressive_billing",
					args: {
						boq_item_name: frm.doc.name
					},
					freeze: true,
					freeze_message: __("Recalculating billing..."),
					callback: function (r) {
						if (r.message && r.message.success) {
							frappe.show_alert({
								message: __("Progressive billing recalculated successfully"),
								indicator: "green"
							});
							frm.reload_doc();
						} else {
							frappe.msgprint({
								title: __("Error"),
								message: r.message?.error || __("Failed to recalculate billing"),
								indicator: "red"
							});
						}
					}
				});
			}, __("Actions"));
		}

		// Add "Update Estimated Cost" button for Project Managers
		if (!frm.is_new() && frappe.user_roles.includes("Project Manager") || frappe.user_roles.includes("System Manager")) {
			frm.add_custom_button(__("Update Estimated Cost"), function () {
				show_estimated_cost_dialog(frm);
			}, __("Actions"));
		}

		// Add "Create Invoice" button if not fully billed
		if (!frm.is_new() && frm.doc.billing_status !== "Fully Billed" && flt(frm.doc.current_qty) > 0) {
			frm.add_custom_button(__("Create Invoice"), function () {
				frm.call({
					method: "create_invoice",
					doc: frm.doc,
					callback: function (r) {
						if (r.message && r.message.invoice) {
							frappe.set_route("Form", "Sales Invoice", r.message.invoice);
						}
					}
				});
			}, __("Actions"));
		}

		// Add "Create Task" button if no linked task
		if (!frm.is_new() && !frm.doc.linked_task) {
			frm.add_custom_button(__("Create Task"), function () {
				frm.call({
					method: "create_linked_task",
					doc: frm.doc,
					callback: function (r) {
						if (r.message && r.message.task) {
							frm.reload_doc();
						}
					}
				});
			}, __("Actions"));
		}
	},

	total_qty(frm) {
		calculate_unit_based_totals(frm);
	},

	estimated_material_cost_per_unit(frm) {
		calculate_unit_based_totals(frm);
	},

	estimated_labour_cost_per_unit(frm) {
		calculate_unit_based_totals(frm);
	},

	estimated_subcontract_cost_per_unit(frm) {
		calculate_unit_based_totals(frm);
	},

	estimated_asset_cost_per_unit(frm) {
		calculate_unit_based_totals(frm);
	},

	estimated_other_cost_per_unit(frm) {
		calculate_unit_based_totals(frm);
	},

	render_rate_history(frm) {
		if (frm.is_new()) return;
		frappe.call({
			method: "construction_management.construction_management.doctype.boq_item.boq_item.get_rate_history",
			args: {
				boq_item: frm.doc.name
			},
			callback(r) {
				if (r.message && r.message.length) {
					let html = `
						<div class="rate-history-container" style="margin-top: 15px; margin-bottom: 15px; border: 1px solid var(--border-color); border-radius: var(--border-radius-md); padding: 12px; background-color: var(--light-bg);">
							<details>
								<summary style="font-weight: bold; color: var(--text-color); cursor: pointer; font-size: var(--text-md); outline: none;">
									<i class="fa fa-history" style="color: var(--text-muted); margin-right: 6px;"></i> ${__('View Pricing/Rate Change History')} (${r.message.length})
								</summary>
								<div style="margin-top: 10px; overflow-x: auto;">
									<table class="table table-bordered table-condensed" style="margin-bottom: 0; font-size: var(--text-sm); background-color: var(--card-bg);">
										<thead>
											<tr style="background-color: var(--border-color); font-weight: bold;">
												<th>${__('Changed Date')}</th>
												<th>${__('User')}</th>
												<th style="text-align: right;">${__('Rate')}</th>
												<th style="text-align: right;">${__('BOQ Item Total Amount')}</th>
											</tr>
										</thead>
										<tbody>
					`;
					r.message.forEach(row => {
						let rate = flt(row.rate);
						let amount = flt(row.amount);
						let user_name = row.user_name || row.changed_by || '';
						html += `
							<tr>
								<td>${frappe.datetime.str_to_user(row.posting_date)}</td>
								<td>${user_name}</td>
								<td style="text-align: right; font-weight: bold; color: var(--text-color);">${format_currency(rate, (frappe.boot.sysdefaults && frappe.boot.sysdefaults.currency) || 'AED')}</td>
								<td style="text-align: right; font-weight: bold; color: var(--text-color);">${format_currency(amount, (frappe.boot.sysdefaults && frappe.boot.sysdefaults.currency) || 'AED')}</td>
							</tr>
						`;
					});
					html += `
										</tbody>
									</table>
								</div>
							</details>
						</div>
					`;
					frm.get_field('rate_history_html').$wrapper.html(html);
				} else {
					frm.get_field('rate_history_html').$wrapper.html(
						`<div style="font-size: var(--text-sm); color: var(--text-muted); margin-top: 15px; margin-bottom: 15px; padding: 12px; border: 1px dashed var(--border-color); border-radius: var(--border-radius-md); text-align: center;">${__('No billing history found.')}</div>`
					);
				}
			}
		});
	}
});

function calculate_unit_based_totals(frm) {
	let qty = flt(frm.doc.total_qty);
	if (qty <= 0) return;

	let mat = flt(frm.doc.estimated_material_cost_per_unit) * qty;
	let lab = flt(frm.doc.estimated_labour_cost_per_unit) * qty;
	let sub = flt(frm.doc.estimated_subcontract_cost_per_unit) * qty;
	let ast = flt(frm.doc.estimated_asset_cost_per_unit) * qty;
	let oth = flt(frm.doc.estimated_other_cost_per_unit) * qty;

	frm.set_value("estimated_material_cost", mat);
	frm.set_value("estimated_labour_cost", lab);
	frm.set_value("estimated_subcontract_cost", sub);
	frm.set_value("estimated_asset_cost", ast);
	frm.set_value("estimated_other_cost", oth);

	frm.set_value("total_estimated_cost", mat + lab + sub + ast + oth);
}

/**
 * Show dialog to update estimated costs
 * Requires Project Manager role or explicit permission
 * Logs changes for audit trail
 */
function show_estimated_cost_dialog(frm) {
	// Check permission
	if (!frappe.user_roles.includes("Project Manager") && !frappe.user_roles.includes("System Manager")) {
		frappe.msgprint({
			title: __("Permission Denied"),
			message: __("Only Project Managers can update estimated costs."),
			indicator: "red"
		});
		return;
	}

	let d = new frappe.ui.Dialog({
		title: __("Update Estimated Costs"),
		fields: [
			{
				fieldname: "info_section",
				fieldtype: "HTML",
				options: `<div class="alert alert-info">
					<strong>${__("Note:")}</strong> ${__("Changes to estimated costs will be logged for audit purposes.")}
				</div>`
			},
			{
				fieldname: "section_estimated_costs",
				fieldtype: "Section Break",
				label: __("Estimated Costs (Per Unit vs Total)")
			},
			{
				fieldname: "estimated_material_cost_per_unit",
				fieldtype: "Currency",
				label: __("Material / Unit"),
				default: frm.doc.estimated_material_cost_per_unit || 0
			},
			{
				fieldname: "estimated_labour_cost_per_unit",
				fieldtype: "Currency",
				label: __("Labour / Unit"),
				default: frm.doc.estimated_labour_cost_per_unit || 0
			},
			{
				fieldname: "estimated_subcontract_cost_per_unit",
				fieldtype: "Currency",
				label: __("Subcontract / Unit"),
				default: frm.doc.estimated_subcontract_cost_per_unit || 0
			},
			{
				fieldname: "column_break_totals_1",
				fieldtype: "Column Break"
			},
			{
				fieldname: "estimated_material_cost",
				fieldtype: "Currency",
				label: __("Material Total"),
				default: frm.doc.estimated_material_cost || 0,
				read_only: 1
			},
			{
				fieldname: "estimated_labour_cost",
				fieldtype: "Currency",
				label: __("Labour Total"),
				default: frm.doc.estimated_labour_cost || 0,
				read_only: 1
			},
			{
				fieldname: "estimated_subcontract_cost",
				fieldtype: "Currency",
				label: __("Subcontract Total"),
				default: frm.doc.estimated_subcontract_cost || 0,
				read_only: 1
			},
			{
				fieldname: "section_other_costs",
				fieldtype: "Section Break"
			},
			{
				fieldname: "estimated_asset_cost_per_unit",
				fieldtype: "Currency",
				label: __("Asset / Unit"),
				default: frm.doc.estimated_asset_cost_per_unit || 0
			},
			{
				fieldname: "estimated_other_cost_per_unit",
				fieldtype: "Currency",
				label: __("Other / Unit"),
				default: frm.doc.estimated_other_cost_per_unit || 0
			},
			{
				fieldname: "column_break_totals_2",
				fieldtype: "Column Break"
			},
			{
				fieldname: "estimated_asset_cost",
				fieldtype: "Currency",
				label: __("Asset Total"),
				default: frm.doc.estimated_asset_cost || 0,
				read_only: 1
			},
			{
				fieldname: "estimated_other_cost",
				fieldtype: "Currency",
				label: __("Other Total"),
				default: frm.doc.estimated_other_cost || 0,
				read_only: 1
			},
			{
				fieldname: "section_grand_total",
				fieldtype: "Section Break"
			},
			{
				fieldname: "total_estimated_cost",
				fieldtype: "Currency",
				label: __("Total Estimated Cost"),
				read_only: 1,
				default: frm.doc.total_estimated_cost || 0
			}
		],
		primary_action_label: __("Update"),
		primary_action: function (values) {
			// Calculate total
			let total = flt(values.estimated_material_cost) +
				flt(values.estimated_labour_cost) +
				flt(values.estimated_subcontract_cost) +
				flt(values.estimated_asset_cost) +
				flt(values.estimated_other_cost);

			// Prepare old values for audit
			let old_values = {
				estimated_material_cost: frm.doc.estimated_material_cost,
				estimated_labour_cost: frm.doc.estimated_labour_cost,
				estimated_subcontract_cost: frm.doc.estimated_subcontract_cost,
				estimated_asset_cost: frm.doc.estimated_asset_cost,
				estimated_other_cost: frm.doc.estimated_other_cost,
				total_estimated_cost: frm.doc.total_estimated_cost
			};

			// Update via API to log changes
			frappe.call({
				method: "construction_management.api.cost_validation.update_estimated_costs",
				args: {
					boq_item: frm.doc.name,
					new_values: {
						estimated_material_cost_per_unit: values.estimated_material_cost_per_unit,
						estimated_labour_cost_per_unit: values.estimated_labour_cost_per_unit,
						estimated_subcontract_cost_per_unit: values.estimated_subcontract_cost_per_unit,
						estimated_asset_cost_per_unit: values.estimated_asset_cost_per_unit,
						estimated_other_cost_per_unit: values.estimated_other_cost_per_unit,
						estimated_material_cost: values.estimated_material_cost,
						estimated_labour_cost: values.estimated_labour_cost,
						estimated_subcontracting_cost: values.estimated_subcontracting_cost,
						estimated_asset_cost: values.estimated_asset_cost,
						estimated_other_cost: values.estimated_other_cost,
						total_estimated_cost: total
					},
					old_values: old_values
				},
				callback: function (r) {
					if (r.message && r.message.success) {
						frappe.show_alert({
							message: __("Estimated costs updated successfully"),
							indicator: "green"
						});
						frm.reload_doc();
						d.hide();
					}
				}
			});
		}
	});

	// Update totals based on unit costs in dialog
	let qty = flt(frm.doc.total_qty);
	["estimated_material_cost_per_unit", "estimated_labour_cost_per_unit",
		"estimated_subcontract_cost_per_unit", "estimated_asset_cost_per_unit",
		"estimated_other_cost_per_unit"].forEach(function (field) {
			d.fields_dict[field].$input.on("change", function () {
				let unit_val = flt(d.get_value(field));
				let total_field = field.replace("_per_unit", "");
				d.set_value(total_field, unit_val * qty);

				let grand_total = flt(d.get_value("estimated_material_cost")) +
					flt(d.get_value("estimated_labour_cost")) +
					flt(d.get_value("estimated_subcontract_cost")) +
					flt(d.get_value("estimated_asset_cost")) +
					flt(d.get_value("estimated_other_cost"));
				d.set_value("total_estimated_cost", grand_total);
			});
		});

	d.show();
}
