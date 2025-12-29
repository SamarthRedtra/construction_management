// Copyright (c) 2025, Construction Management and contributors
// For license information, please see license.txt

frappe.ui.form.on("BOQ Item", {
	refresh(frm) {
		// Add "Update Estimated Cost" button for Project Managers
		if (!frm.is_new() && frappe.user_roles.includes("Project Manager") || frappe.user_roles.includes("System Manager")) {
			frm.add_custom_button(__("Update Estimated Cost"), function() {
				show_estimated_cost_dialog(frm);
			}, __("Actions"));
		}
		
		// Add "Create Invoice" button if not fully billed
		if (!frm.is_new() && frm.doc.billing_status !== "Fully Billed" && flt(frm.doc.current_qty) > 0) {
			frm.add_custom_button(__("Create Invoice"), function() {
				frm.call({
					method: "create_invoice",
					doc: frm.doc,
					callback: function(r) {
						if (r.message && r.message.invoice) {
							frappe.set_route("Form", "Sales Invoice", r.message.invoice);
						}
					}
				});
			}, __("Actions"));
		}
		
		// Add "Create Task" button if no linked task
		if (!frm.is_new() && !frm.doc.linked_task) {
			frm.add_custom_button(__("Create Task"), function() {
				frm.call({
					method: "create_linked_task",
					doc: frm.doc,
					callback: function(r) {
						if (r.message && r.message.task) {
							frm.reload_doc();
						}
					}
				});
			}, __("Actions"));
		}
	}
});

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
				fieldname: "estimated_material_cost",
				fieldtype: "Currency",
				label: __("Estimated Material Cost"),
				default: frm.doc.estimated_material_cost || 0
			},
			{
				fieldname: "estimated_labour_cost",
				fieldtype: "Currency",
				label: __("Estimated Labour Cost"),
				default: frm.doc.estimated_labour_cost || 0
			},
			{
				fieldname: "estimated_subcontract_cost",
				fieldtype: "Currency",
				label: __("Estimated Subcontracting Cost"),
				default: frm.doc.estimated_subcontract_cost || 0
			},
			{
				fieldname: "column_break_1",
				fieldtype: "Column Break"
			},
			{
				fieldname: "estimated_asset_cost",
				fieldtype: "Currency",
				label: __("Estimated Asset Cost"),
				default: frm.doc.estimated_asset_cost || 0
			},
			{
				fieldname: "estimated_other_cost",
				fieldtype: "Currency",
				label: __("Estimated Other Costs"),
				default: frm.doc.estimated_other_cost || 0
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
		primary_action: function(values) {
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
						estimated_material_cost: values.estimated_material_cost,
						estimated_labour_cost: values.estimated_labour_cost,
						estimated_subcontract_cost: values.estimated_subcontract_cost,
						estimated_asset_cost: values.estimated_asset_cost,
						estimated_other_cost: values.estimated_other_cost,
						total_estimated_cost: total
					},
					old_values: old_values
				},
				callback: function(r) {
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
	
	// Update total when any field changes
	["estimated_material_cost", "estimated_labour_cost", "estimated_subcontract_cost", 
	 "estimated_asset_cost", "estimated_other_cost"].forEach(function(field) {
		d.fields_dict[field].$input.on("change", function() {
			let total = flt(d.get_value("estimated_material_cost")) +
				flt(d.get_value("estimated_labour_cost")) +
				flt(d.get_value("estimated_subcontract_cost")) +
				flt(d.get_value("estimated_asset_cost")) +
				flt(d.get_value("estimated_other_cost"));
			d.set_value("total_estimated_cost", total);
		});
	});
	
	d.show();
}
