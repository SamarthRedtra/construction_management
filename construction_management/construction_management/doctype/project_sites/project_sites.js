// Copyright (c) 2026, Construction Management
// License: MIT

frappe.ui.form.on("Project Sites", {
	refresh(frm) {
		// Setup cascading filters
		setup_filters(frm);
	},
	
	onload(frm) {
		// Setup cascading filters
		setup_filters(frm);
	},
	
	project(frm) {
		// Clear bill_no and boq_item when project changes
		if (frm.doc.bill_no) {
			frm.set_value("bill_no", "");
		}
		if (frm.doc.boq_item) {
			frm.set_value("boq_item", "");
		}
	},
	
	bill_no(frm) {
		// Clear boq_item when bill_no changes
		if (frm.doc.boq_item) {
			frm.set_value("boq_item", "");
		}
	}
});

function setup_filters(frm) {
	// Filter bill_no by project
	frm.set_query("bill_no", function() {
		if (frm.doc.project) {
			return {
				filters: {
					project: frm.doc.project
				}
			};
		}
		return {};
	});
	
	// Filter boq_item by bill_no
	frm.set_query("boq_item", function() {
		if (frm.doc.bill_no) {
			return {
				filters: {
					parent_bill: frm.doc.bill_no
				}
			};
		} else if (frm.doc.project) {
			return {
				filters: {
					project: frm.doc.project
				}
			};
		}
		return {};
	});
}

// List view: Add bulk creation button
frappe.listview_settings['Project Sites'] = {
	onload: function(listview) {
		listview.page.add_inner_button(__('Bulk Create Sites'), function() {
			show_bulk_create_dialog();
		});
	}
};

function show_bulk_create_dialog() {
	const d = new frappe.ui.Dialog({
		title: __('Bulk Create Project Sites'),
		fields: [
			{
				fieldname: 'project',
				fieldtype: 'Link',
				label: __('Project'),
				options: 'Project',
				reqd: 1
			},
			{
				fieldtype: 'Column Break'
			},
			{
				fieldname: 'site_names',
				fieldtype: 'Small Text',
				label: __('Site Names (one per line)'),
				reqd: 1,
				description: __('Enter each site name on a new line')
			}
		],
		primary_action_label: __('Create Sites'),
		primary_action: function(values) {
			frappe.call({
				method: 'construction_management.construction_management.doctype.project_sites.project_sites.create_bulk_sites',
				args: {
					project: values.project,
					site_names: values.site_names
				},
				freeze: true,
				freeze_message: __('Creating sites...'),
				callback: function(r) {
					if (r.message) {
						const result = r.message;
						let message = __('Created {0} out of {1} sites', [result.success, result.total]);
						
						if (result.errors.length > 0) {
							message += '<br><br><strong>' + __('Errors:') + '</strong><ul>';
							result.errors.forEach(function(error) {
								message += `<li>${error.site_name}: ${error.error}</li>`;
							});
							message += '</ul>';
						}
						
						frappe.msgprint({
							title: __('Bulk Creation Complete'),
							message: message,
							indicator: result.errors.length > 0 ? 'orange' : 'green'
						});
						
						d.hide();
						frappe.set_route('List', 'Project Sites', {project: values.project});
					}
				}
			});
		}
	});
	
	d.show();
}

