// Copyright (c) 2026, Construction Management
// License: MIT

frappe.pages['project-commission'].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Project Commission'),
		single_column: true,
	});

	const page_body = $(wrapper).find('.layout-main-section');
	page_body.html(`
		<div id="project-commission-wrapper" class="project-commission-layout">
			<div class="project-commission-header-row">
				<h1 class="commission-title-main">${__('COMMISSION - PROJECT WISE')}</h1>
			</div>
			<div class="project-commission-filters-row">
				<div id="project-commission-company-wrapper"></div>
				<div id="project-commission-field-wrapper"></div>
			</div>
			<div id="project-commission-container"></div>
		</div>
	`);

	const container_el = wrapper.querySelector('#project-commission-container');
	let selected_company = frappe.defaults.get_user_default('Company') || '';

	function reset_page_state() {
		reset_project_commission_dashboard(container_el, { company: selected_company });
	}

	function render_for_project(project) {
		if (project) {
			render_project_commission_dashboard(container_el, project);
		} else {
			reset_page_state();
		}
	}

	function sync_project_field_state() {
		project_control.df.get_query = () => ({
			filters: selected_company ? { company: selected_company } : {},
		});
		project_control.df.read_only = selected_company ? 0 : 1;
		project_control.refresh();
	}

	const company_control = frappe.ui.form.make_control({
		parent: wrapper.querySelector('#project-commission-company-wrapper'),
		df: {
			label: __('Company'),
			fieldname: 'company',
			fieldtype: 'Link',
			options: 'Company',
			placeholder: __('Select Company'),
			change() {
				selected_company = this.get_value() || '';
				project_control.set_value('');
				sync_project_field_state();
				reset_page_state();
			},
		},
		render_input: true,
	});

	const project_control = frappe.ui.form.make_control({
		parent: wrapper.querySelector('#project-commission-field-wrapper'),
		df: {
			label: __('Project'),
			fieldname: 'project',
			fieldtype: 'Link',
			options: 'Project',
			placeholder: __('Select Project'),
			get_query() {
				return {
					filters: selected_company ? { company: selected_company } : {},
				};
			},
			change() {
				render_for_project(this.get_value());
			},
		},
		render_input: true,
	});

	let project_val = null;
	let company_val = frappe.defaults.get_user_default('Company') || '';
	if (frappe.get_route().length > 2) {
		project_val = frappe.get_route()[2];
	} else if (frappe.route_options) {
		project_val = frappe.route_options.project || null;
		company_val = frappe.route_options.company || company_val;
	}

	if (company_val) {
		selected_company = company_val;
		company_control.set_value(company_val);
	}

	sync_project_field_state();
	reset_page_state();

	if (project_val) {
		frappe.db.get_value('Project', project_val, 'company').then((r) => {
			const project_company = r.message && r.message.company;
			if (project_company) {
				selected_company = project_company;
				company_control.set_value(project_company);
				sync_project_field_state();
			}
			project_control.set_value(project_val);
		});
	}
};
