// Copyright (c) 2026, Construction Management
// License: MIT

frappe.pages['project-process-home'].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Member Home'),
		single_column: true,
	});

	new ProjectProcessHome(wrapper);
};

class ProjectProcessHome {
	project_id(value) {
		return String(value == null ? '' : value);
	}

	constructor(wrapper) {
		this.wrapper = $(wrapper);
		this.page_body = this.wrapper.find('.layout-main-section');
		this.status_filter = 'ongoing';
		this.search = '';
		this.company = frappe.defaults.get_user_default('Company') || '';
		this.start = 0;
		this.page_length = 25;
		this.total_count = 0;
		this.expanded_projects = new Set();
		this.process_cache = {};
		this.bills_cache = {};
		this.boq_source_cache = {};
		this.loading_projects = new Set();
		this.projects = [];
		this.companies = [];

		this.render_shell();
		this.bind_events();
		this.load_companies();
		this.load_projects();
	}

	render_shell() {
		this.page_body.html(`
			<div class="project-process-home-layout">
				<div class="pph-toolbar">
					<div class="pph-status-filters">
						<label><input type="radio" name="pph_status" value="ongoing" checked> ${__('On Going')}</label>
						<label><input type="radio" name="pph_status" value="completed"> ${__('Completed')}</label>
						<label><input type="radio" name="pph_status" value="all"> ${__('All')}</label>
					</div>
					<div class="pph-company-filter">
						<label>${__('Company')}</label>
						<select class="form-control input-sm" data-field="company" style="width: 220px; display: inline-block;">
							<option value="">${__('All Companies')}</option>
						</select>
					</div>
					<div class="pph-search-filter">
						<label>${__('Search')}</label>
						<div class="pph-search-input-wrap">
							<input
								type="text"
								class="form-control input-sm"
								data-field="search"
								placeholder="${__('Project no, name, engineer, location...')}"
								value="${frappe.utils.escape_html(this.search || '')}"
							>
							<button type="button" class="btn btn-default btn-xs pph-search-clear" data-action="clear-search" title="${__('Clear')}">&times;</button>
						</div>
					</div>
					<div class="pph-toolbar-actions">
						<button class="btn btn-default btn-sm" data-action="collapse-all">${__('Collapse All')}</button>
						<button class="btn btn-default btn-sm" data-action="expand-all">${__('Expand All')}</button>
					</div>
				</div>
				<div class="pph-table-controls">
					<div class="entries-control">
						<span>${__('Show')}</span>
						<select class="form-control input-sm" data-field="page-length" style="width: 70px; display: inline-block;">
							<option value="25">25</option>
							<option value="50">50</option>
							<option value="100">100</option>
						</select>
						<span>${__('entries')}</span>
					</div>
				</div>
				<div class="pph-table-wrapper">
					<table class="pph-table">
						<thead>
							<tr class="pph-parent-header">
								<th>${__('Project_No.')}</th>
								<th>${__('Sales Person')}</th>
								<th>${__('Assign_To')}</th>
								<th>${__('Contractor')}</th>
								<th>${__('Proname')}</th>
								<th>${__('Location')}</th>
								<th>${__('emirates')}</th>
							</tr>
						</thead>
						<tbody id="pph-project-tbody"></tbody>
					</table>
				</div>
				<div class="pph-pagination">
					<div class="pph-pagination-info"></div>
					<div class="btn-group">
						<button class="btn btn-default btn-sm" data-action="prev">${__('Previous')}</button>
						<button class="btn btn-default btn-sm" data-action="next">${__('Next')}</button>
					</div>
				</div>
			</div>
		`);
	}

	bind_events() {
		const me = this;
		this.page_body.on('change', 'input[name="pph_status"]', function () {
			me.status_filter = $(this).val();
			me.start = 0;
			me.expanded_projects.clear();
			me.load_projects();
		});

		this.page_body.on('change', '[data-field="page-length"]', function () {
			me.page_length = parseInt($(this).val(), 10) || 25;
			me.start = 0;
			me.load_projects();
		});

		this.page_body.on('change', '[data-field="company"]', function () {
			me.company = $(this).val();
			me.start = 0;
			me.expanded_projects.clear();
			me.process_cache = {};
			me.bills_cache = {};
			me.boq_source_cache = {};
			me.load_projects();
		});

		let search_timer = null;
		this.page_body.on('input', '[data-field="search"]', function () {
			clearTimeout(search_timer);
			search_timer = setTimeout(() => {
				me.search = $(this).val();
				me.start = 0;
				me.expanded_projects.clear();
				me.load_projects();
			}, 300);
		});

		this.page_body.on('keydown', '[data-field="search"]', function (e) {
			if (e.key === 'Enter') {
				e.preventDefault();
				clearTimeout(search_timer);
				me.search = $(this).val();
				me.start = 0;
				me.expanded_projects.clear();
				me.load_projects();
			}
		});

		this.page_body.on('click', '[data-action="clear-search"]', () => {
			me.search = '';
			me.start = 0;
			me.expanded_projects.clear();
			me.page_body.find('[data-field="search"]').val('');
			me.load_projects();
		});

		this.page_body.on('click', '[data-action="prev"]', () => {
			if (me.start > 0) {
				me.start = Math.max(0, me.start - me.page_length);
				me.load_projects();
			}
		});

		this.page_body.on('click', '[data-action="next"]', () => {
			if (me.start + me.page_length < me.total_count) {
				me.start += me.page_length;
				me.load_projects();
			}
		});

		this.page_body.on('click', '[data-action="collapse-all"]', () => {
			me.expanded_projects.clear();
			me.render_project_rows();
		});

		this.page_body.on('click', '[data-action="expand-all"]', () => {
			me.projects.forEach((p) => me.expanded_projects.add(me.project_id(p.name)));
			me.render_project_rows();
			me.projects.forEach((p) => {
				const project_name = me.project_id(p.name);
				if (me.process_cache[project_name] === undefined && !me.loading_projects.has(project_name)) {
					me.load_process_rows(project_name);
				}
			});
		});

		this.page_body.on('click', '.pph-expand-btn', function (e) {
			e.stopPropagation();
			const project = me.project_id($(this).attr('data-project'));
			me.toggle_expand(project);
		});

		this.page_body.on('click', '.pph-project-no', function (e) {
			e.stopPropagation();
			const project = me.project_id($(this).attr('data-project'));
			frappe.set_route('Form', 'Project', project);
		});

		this.page_body.on('click', '.pph-edit-process', function (e) {
			e.stopPropagation();
			const doctype = $(this).data('doctype');
			const docname = $(this).data('docname');
			if (doctype && docname) {
				frappe.set_route('Form', doctype, docname);
			}
		});

		this.page_body.on('click', '.pph-add-process', function (e) {
			e.stopPropagation();
			const project = me.project_id($(this).attr('data-project'));
			me.show_add_process_dialog(project);
		});
		this.page_body.on('click', '.pph-open-project', function (e) {
			e.stopPropagation();
			frappe.set_route('Form', 'Project', me.project_id($(this).attr('data-project')));
		});

		this.page_body.on('click', '.pph-open-boq', function (e) {
			e.stopPropagation();
			const project = me.project_id($(this).attr('data-project'));
			frappe.set_route('Form', 'Project', project, { tab: 'construction_tab' });
		});
	}

	load_companies() {
		const me = this;
		frappe.call({
			method: 'construction_management.construction_management.page.project_process_home.project_process_home.get_member_home_companies',
			callback(r) {
				if (!r.message) {
					return;
				}
				me.companies = r.message;
				const $select = me.page_body.find('[data-field="company"]');
				let options = `<option value="">${__('All Companies')}</option>`;
				me.companies.forEach((company) => {
					const selected = company.name === me.company ? 'selected' : '';
					options += `<option value="${frappe.utils.escape_html(company.name)}" ${selected}>${frappe.utils.escape_html(company.company_name || company.name)}</option>`;
				});
				$select.html(options);
			},
		});
	}

	load_projects() {
		const me = this;
		frappe.call({
			method: 'construction_management.construction_management.page.project_process_home.project_process_home.get_project_process_home_data',
			args: {
				status_filter: this.status_filter,
				search: this.search,
				company: this.company,
				start: this.start,
				page_length: this.page_length,
			},
			callback(r) {
				if (r.message) {
					me.projects = r.message.projects || [];
					me.total_count = r.message.total_count || 0;
					me.render_project_rows();
					me.render_pagination();
				}
			},
		});
	}

	render_pagination() {
		const from = this.total_count ? this.start + 1 : 0;
		const to = Math.min(this.start + this.page_length, this.total_count);
		this.page_body.find('.pph-pagination-info').text(
			__('Showing {0} to {1} of {2} entries', [from, to, this.total_count])
		);
		this.page_body.find('[data-action="prev"]').prop('disabled', this.start <= 0);
		this.page_body.find('[data-action="next"]').prop(
			'disabled',
			this.start + this.page_length >= this.total_count
		);
	}

	render_project_rows() {
		const tbody = this.page_body.find('#pph-project-tbody');
		if (!this.projects.length) {
			tbody.html(`
				<tr class="pph-empty-row">
					<td colspan="7">${__('No projects found')}</td>
				</tr>
			`);
			return;
		}

		let html = '';
		this.projects.forEach((project) => {
			const project_name = this.project_id(project.name);
			const expanded = this.expanded_projects.has(project_name);
			const assign_class = project.assign_to === __('!Not Assign') ? 'pph-not-assigned' : '';
			html += `
				<tr class="pph-project-row" data-project="${frappe.utils.escape_html(project_name)}">
					<td>
						<button type="button" class="pph-expand-btn ${expanded ? 'expanded' : ''}" data-project="${frappe.utils.escape_html(project_name)}">
							${expanded ? '−' : '+'}
						</button>
						<span class="pph-project-no" data-project="${frappe.utils.escape_html(project_name)}">${frappe.utils.escape_html(project.project_no)}</span>
					</td>
					<td>${frappe.utils.escape_html(project.sales_person || '')}</td>
					<td class="${assign_class}">${frappe.utils.escape_html(project.assign_to || '')}</td>
					<td>${frappe.utils.escape_html(project.contractor || '')}</td>
					<td>${frappe.utils.escape_html(project.project_name || '')}</td>
					<td>${frappe.utils.escape_html(project.location || '')}</td>
					<td>${frappe.utils.escape_html(project.emirates || '')}</td>
				</tr>
			`;
			if (expanded) {
				html += this.render_process_section(project_name);
			}
		});
		tbody.html(html);
	}

	render_process_section(project) {
		const cached = this.process_cache[project];
		const bills = this.bills_cache[project] || [];
		const boq_source_project = this.boq_source_cache[project];
		const project_row = this.projects.find((p) => p.name === project) || {};
		const enable_progressive_boq = project_row.enable_progressive_boq ? 1 : 0;

		if (cached === undefined) {
			return `
				<tr class="pph-process-section" data-project="${project}">
					<td colspan="7" class="pph-loading-row">${__('Loading processes...')}</td>
				</tr>
			`;
		}

		let note_html = '';
		if (boq_source_project && boq_source_project !== project) {
			note_html = `
				<tr class="pph-boq-source-note">
					<td colspan="7" class="text-muted">
						${__('Showing BOQ from {0}', [boq_source_project])}
					</td>
				</tr>
			`;
		}

		let rows_html = '';
		if (cached.length) {
			cached.forEach((row) => {
				const area_disp = frappe.format(row.area, { fieldtype: 'Float', precision: 2 });
				const skirting_disp = `${frappe.format(row.skirting || 0, { fieldtype: 'Float', precision: 2 })} ${row.unit || 'm²'}`;
				const start_disp = row.start_date ? frappe.datetime.str_to_user(row.start_date) : '';
				const end_disp = row.end_date ? frappe.datetime.str_to_user(row.end_date) : '';

				rows_html += `
					<tr class="pph-process-row">
						<td>${frappe.utils.escape_html(row.process_name || '')}</td>
						<td>${area_disp}</td>
						<td>${skirting_disp}</td>
						<td>${start_disp}</td>
						<td>${end_disp}</td>
						<td><span class="pph-action-link pph-edit-process" data-doctype="BOQ Item" data-docname="${row.boq_item}">${__('Edit')}</span></td>
						<td></td>
					</tr>
				`;
			});
		} else {
			const boq_btn = enable_progressive_boq
				? `<button class="btn btn-default btn-xs pph-open-boq" data-project="${project}">${__('Open Construction BOQ')}</button>`
				: '';
			rows_html = `
				<tr>
					<td colspan="7" class="pph-empty-boq text-center text-muted">
						<p>${__('No BOQ items configured for this project')}</p>
						<div class="pph-empty-actions">
							<button class="btn btn-default btn-xs pph-open-project" data-project="${project}">${__('Open Project')}</button>
							${boq_btn}
						</div>
					</td>
				</tr>
			`;
		}

		if (bills.length) {
			rows_html += `
				<tr class="pph-process-row">
					<td colspan="6"></td>
					<td>
						<span class="pph-action-link pph-add-process" data-project="${project}">
							${__('Add New')}
						</span>
					</td>
				</tr>
			`;
		}

		return `
			<tr class="pph-process-section" data-project="${project}">
				<td colspan="7" style="padding: 0;">
					<table class="pph-table" style="margin: 0;">
						<thead>
							<tr class="pph-child-header">
								<th>${__('Process Name')}</th>
								<th>${__('Area')}</th>
								<th>${__('Skirting')}</th>
								<th>${__('Start Date')}</th>
								<th>${__('End Date')}</th>
								<th>${__('Edit')}</th>
								<th>${__('Add New')}</th>
							</tr>
						</thead>
						<tbody>${note_html}${rows_html}</tbody>
					</table>
				</td>
			</tr>
		`;
	}

	toggle_expand(project) {
		project = this.project_id(project);
		if (this.expanded_projects.has(project)) {
			this.expanded_projects.delete(project);
		} else {
			this.expanded_projects.add(project);
			if (this.process_cache[project] === undefined && !this.loading_projects.has(project)) {
				this.load_process_rows(project);
			}
		}
		this.render_project_rows();
	}

	load_process_rows(project) {
		const me = this;
		project = me.project_id(project);
		me.loading_projects.add(project);
		if (me.expanded_projects.has(project)) {
			me.render_project_rows();
		}
		frappe.call({
			method: 'construction_management.construction_management.page.project_process_home.project_process_home.get_project_process_rows',
			args: { project },
			callback(r) {
				me.loading_projects.delete(project);
				if (r.message) {
					me.process_cache[project] = r.message.processes || [];
					me.bills_cache[project] = r.message.bills || [];
					me.boq_source_cache[project] = r.message.boq_source_project || project;
					if (me.expanded_projects.has(project)) {
						me.render_project_rows();
					}
				}
			},
			error() {
				me.loading_projects.delete(project);
				me.process_cache[project] = [];
				me.bills_cache[project] = [];
				if (me.expanded_projects.has(project)) {
					me.render_project_rows();
				}
			},
		});
	}

	show_add_process_dialog(project) {
		const bills = this.bills_cache[project] || [];
		if (!bills.length) {
			frappe.msgprint({
				title: __('No BOQ Bill'),
				message: __('This project has no BOQ Bill. Please create a BOQ Bill first from the Project Construction tab.'),
				indicator: 'orange',
			});
			return;
		}

		const bill_options = bills.map((bill) => {
			const label = bill.bill_no || bill.label || bill.name;
			return { label, value: bill.name };
		});

		const me = this;
		const dialog = new frappe.ui.Dialog({
			title: __('Add New BOQ Item'),
			fields: [
				{
					fieldname: 'parent_bill',
					label: __('BOQ Bill'),
					fieldtype: 'Select',
					options: bill_options,
					reqd: 1,
					default: bill_options[0]?.value,
				},
				{ fieldname: 'description', label: __('Process Name'), fieldtype: 'Data', reqd: 1 },
				{ fieldname: 'total_qty', label: __('Area'), fieldtype: 'Float' },
				{ fieldname: 'custom_skirting', label: __('Skirting'), fieldtype: 'Float' },
				{ fieldname: 'start_date', label: __('Start Date'), fieldtype: 'Date' },
				{ fieldname: 'end_date', label: __('End Date'), fieldtype: 'Date' },
				{ fieldname: 'rate', label: __('Rate'), fieldtype: 'Currency', default: 0 },
			],
			primary_action_label: __('Create'),
			primary_action(values) {
				frappe.call({
					method: 'construction_management.construction_management.page.project_process_home.project_process_home.create_project_process_boq_item',
					args: {
						project,
						parent_bill: values.parent_bill,
						description: values.description,
						total_qty: values.total_qty || 0,
						custom_skirting: values.custom_skirting || 0,
						start_date: values.start_date,
						end_date: values.end_date,
						rate: values.rate || 0,
					},
					callback(r) {
						if (r.message) {
							dialog.hide();
							delete me.process_cache[project];
							me.load_process_rows(project);
							frappe.show_alert({ message: __('BOQ Item created'), indicator: 'green' });
						}
					},
				});
			},
		});
		dialog.show();
	}
}
