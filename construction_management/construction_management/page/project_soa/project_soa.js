// Copyright (c) 2026, Construction Management
// License: MIT

frappe.pages['project-soa'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Project SOA'),
		single_column: true,
	});

	page.body.html(`
		<div id="project-soa-wrapper" class="project-soa-layout">
			<div class="project-soa-header-row">
				<div class="project-soa-title-container">
					<h1 class="soa-title-main">${__('SOA - PROJECT WISE')}</h1>
				</div>
				<div class="project-soa-filter-container">
					<div id="project-field-wrapper"></div>
				</div>
			</div>
			<div id="project-soa-container"></div>
		</div>
	`);

	reset_project_soa_dashboard(wrapper.querySelector('#project-soa-container'));

	const project_control = frappe.ui.form.make_control({
		parent: wrapper.querySelector('#project-field-wrapper'),
		df: {
			label: __('Project'),
			fieldname: 'project',
			fieldtype: 'Link',
			options: 'Project',
			placeholder: __('Select Project'),
			change() {
				const project = this.get_value();
				if (project) {
					render_project_soa_dashboard(
						wrapper.querySelector('#project-soa-container'),
						project
					);
				} else {
					reset_project_soa_dashboard(wrapper.querySelector('#project-soa-container'));
				}
			},
		},
		render_input: true,
	});

	let project_val = null;
	const route = frappe.get_route();
	if (route && route[2]) {
		project_val = route[2];
	} else if (frappe.route_options && frappe.route_options.project) {
		project_val = frappe.route_options.project;
	}
	if (project_val) {
		project_control.set_value(project_val);
	}
};
