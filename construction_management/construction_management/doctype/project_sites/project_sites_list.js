// Copyright (c) 2026, Construction Management
// License: MIT

frappe.listview_settings['Project Sites'] = {
    refresh: function (listview) {
        listview.page.add_inner_button(__('Bulk Create Sites'), function () {
            show_bulk_create_dialog(listview);
        });
    }
};

function show_bulk_create_dialog(listview) {
    const d = new frappe.ui.Dialog({
        title: __('Bulk Create Project Sites'),
        fields: [
            {
                fieldname: 'project',
                fieldtype: 'Link',
                label: __('Project'),
                options: 'Project',
                reqd: 1,
                default: listview.filter_area.get_filter_value('project')
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
        primary_action: function (values) {
            frappe.call({
                method: 'construction_management.construction_management.doctype.project_sites.project_sites.create_bulk_sites',
                args: {
                    project: values.project,
                    site_names: values.site_names
                },
                freeze: true,
                freeze_message: __('Creating sites...'),
                callback: function (r) {
                    if (r.message) {
                        const result = r.message;
                        let message = __('Created {0} out of {1} sites', [result.success, result.total]);

                        if (result.errors.length > 0) {
                            message += '<br><br><strong>' + __('Errors:') + '</strong><ul>';
                            result.errors.forEach(function (error) {
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
                        listview.refresh();
                    }
                }
            });
        }
    });

    d.show();
}
