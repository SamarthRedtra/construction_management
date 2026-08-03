// Copyright (c) 2026, Construction Management
// License: MIT

frappe.provide('construction_management.project_tab_access');

construction_management.project_tab_access._config_cache = null;

construction_management.project_tab_access.BYPASS_ROLES = ['Administrator', 'System Manager'];

construction_management.project_tab_access.ALWAYS_HIDDEN_TABS = ['costing_tab', 'monitor_progress_tab'];

construction_management.project_tab_access.TAB_OPTIONS = [
	'Details',
	'Connections',
	'Construction',
	'Approved Materials',
	'Accounting',
	'Project SOA',
	'Project Commission',
	'Dashboard',
	'More Info',
];

construction_management.project_tab_access.fetch_config = function (force) {
	if (!force && construction_management.project_tab_access._config_cache) {
		return Promise.resolve(construction_management.project_tab_access._config_cache);
	}

	return frappe.call({
		method: 'construction_management.construction_management.doctype.project_tab_access.project_tab_access.get_project_tab_access_config',
		freeze: false,
	}).then((r) => {
		construction_management.project_tab_access._config_cache = r.message || {
			enabled: false,
			restricted_tabs: {},
			always_hidden_tabs: construction_management.project_tab_access.ALWAYS_HIDDEN_TABS,
			can_edit_estimation_costs: true,
		};
		return construction_management.project_tab_access._config_cache;
	});
};

construction_management.project_tab_access.can_edit_estimation_costs = function () {
	if (construction_management.project_tab_access.is_bypass_user()) {
		return true;
	}
	if (construction_management.project_tab_access._config_cache) {
		return construction_management.project_tab_access._config_cache.can_edit_estimation_costs !== false;
	}
	return true;
};

construction_management.project_tab_access.user_can_access_tab = function (rules) {
	if (!rules || !rules.length) {
		return true;
	}

	const user = frappe.session.user;
	const roles = frappe.user_roles || [];

	return rules.some((rule) => {
		const mode = String(rule.access_mode || 'Y').toUpperCase();
		let matches = false;
		if (rule.user && rule.user === user) {
			matches = true;
		} else if (rule.role && roles.includes(rule.role)) {
			matches = true;
		}
		if (!matches) {
			return false;
		}
		if (mode === 'S') {
			const required = rule.required_role || 'Sales Manager';
			return roles.includes(required);
		}
		return true;
	});
};

construction_management.project_tab_access.hide_tab = function (frm, fieldname) {
	if (fieldname && fieldname !== '__details' && frm.fields_dict[fieldname]) {
		frm.set_df_property(fieldname, 'hidden', 1);
	}

	const tab = (frm.layout?.tabs || []).find((t) => t.df?.fieldname === fieldname);
	if (tab) {
		tab.hide();
	}
};

construction_management.project_tab_access.show_tab = function (frm, fieldname) {
	if (fieldname && fieldname !== '__details' && frm.fields_dict[fieldname]) {
		frm.set_df_property(fieldname, 'hidden', 0);
	}

	const tab = (frm.layout?.tabs || []).find((t) => t.df?.fieldname === fieldname);
	if (tab) {
		tab.show();
	}
};

construction_management.project_tab_access.is_bypass_user = function () {
	const roles = frappe.user_roles || [];
	return (
		frappe.session.user === 'Administrator'
		|| roles.includes('Administrator')
		|| roles.includes('System Manager')
	);
};

construction_management.project_tab_access.apply = function (frm) {
	// Administrator and System Manager see every tab, including Costing/Progress.
	if (construction_management.project_tab_access.is_bypass_user()) {
		const always_hidden = construction_management.project_tab_access.ALWAYS_HIDDEN_TABS || [];
		always_hidden.forEach((fieldname) => {
			construction_management.project_tab_access.show_tab(frm, fieldname);
		});
		return;
	}

	const always_hidden = construction_management.project_tab_access.ALWAYS_HIDDEN_TABS || [];
	always_hidden.forEach((fieldname) => {
		construction_management.project_tab_access.hide_tab(frm, fieldname);
	});

	construction_management.project_tab_access.fetch_config().then((config) => {
		(config.always_hidden_tabs || always_hidden).forEach((fieldname) => {
			construction_management.project_tab_access.hide_tab(frm, fieldname);
		});

		if (!config.enabled) {
			return;
		}

		const restricted_tabs = config.restricted_tabs || {};
		Object.keys(restricted_tabs).forEach((fieldname) => {
			const rules = restricted_tabs[fieldname];
			if (!construction_management.project_tab_access.user_can_access_tab(rules)) {
				construction_management.project_tab_access.hide_tab(frm, fieldname);
			}
		});
	});
};

construction_management.project_tab_access.parse_tabs_value = function (value) {
	if (!value) {
		return [];
	}
	if (Array.isArray(value)) {
		return value.map((v) => String(v).trim()).filter(Boolean);
	}
	return String(value)
		.split(',')
		.map((item) => item.trim())
		.filter(Boolean);
};

construction_management.project_tab_access.serialize_tabs_value = function (values) {
	const unique = [];
	(values || []).forEach((value) => {
		const tab = String(value || '').trim();
		if (tab && !unique.includes(tab)) {
			unique.push(tab);
		}
	});
	return unique.join(', ');
};

construction_management.project_tab_access.patch_rule_row_docfields = function (docfields) {
	(docfields || []).forEach((df) => {
		if (df.fieldname === 'tabs') {
			// Keep Small Text storage; UI is replaced with checkboxes.
			df.fieldtype = 'Small Text';
			df.options = '';
			df.description = __('Tick the Project tabs this role/user can open');
		}
		if (df.fieldname === 'allowed_projects') {
			// Keep Small Text storage; UI is replaced with searchable checkboxes.
			df.fieldtype = 'Small Text';
			df.options = '';
			df.description = __('Leave empty to allow all projects. Tick projects to restrict.');
		}
	});
};

construction_management.project_tab_access.parse_projects_value = function (value) {
	return construction_management.project_tab_access.parse_tabs_value(value);
};

construction_management.project_tab_access.serialize_projects_value = function (values) {
	return construction_management.project_tab_access.serialize_tabs_value(values);
};

construction_management.project_tab_access.load_project_options = function (force) {
	if (!force && construction_management.project_tab_access._project_options_promise) {
		return construction_management.project_tab_access._project_options_promise;
	}

	construction_management.project_tab_access._project_options_promise = frappe.db
		.get_list('Project', {
			fields: ['name', 'project_name', 'custom_project_no', 'status', 'company'],
			filters: { is_active: 'Yes' },
			order_by: 'custom_project_no asc, name asc',
			limit: 1000,
		})
		.then((rows) => {
			construction_management.project_tab_access._project_options = (rows || []).map((row) => ({
				name: row.name,
				label: row.custom_project_no || row.name,
				title: row.project_name || '',
				company: row.company || '',
				status: row.status || '',
				search: [
					row.name,
					row.custom_project_no,
					row.project_name,
					row.company,
					row.status,
				]
					.filter(Boolean)
					.join(' ')
					.toLowerCase(),
			}));
			return construction_management.project_tab_access._project_options;
		});

	return construction_management.project_tab_access._project_options_promise;
};

construction_management.project_tab_access.enhance_tabs_control = function (row) {
	const field = row.grid_form?.fields_dict?.tabs;
	if (!field || !field.$wrapper || !field.$wrapper.length) {
		return;
	}

	const $wrapper = field.$wrapper;
	let $picker = $wrapper.find('.cm-tab-access-picker');

	if (!$picker.length) {
		// Hide awkward textarea; keep model sync via set_value.
		$wrapper.find('.control-input').hide();
		$wrapper.find('textarea').hide();

		$picker = $(`
			<div class="cm-tab-access-picker">
				<div class="cm-tab-access-toolbar">
					<button type="button" class="btn btn-xs btn-default cm-tab-select-all">${__('Select All')}</button>
					<button type="button" class="btn btn-xs btn-default cm-tab-clear">${__('Clear')}</button>
					<span class="cm-tab-access-hint text-muted">${__('Click tabs to allow access')}</span>
				</div>
				<div class="cm-tab-access-grid"></div>
			</div>
		`);
		$wrapper.find('.control-input-wrapper, .form-group').first().append($picker);

		if (!$wrapper.find('.cm-tab-access-picker-style').length) {
			$wrapper.append(`
				<style class="cm-tab-access-picker-style">
					.cm-tab-access-picker { margin-top: 6px; }
					.cm-tab-access-toolbar {
						display: flex;
						align-items: center;
						gap: 8px;
						margin-bottom: 8px;
						flex-wrap: wrap;
					}
					.cm-tab-access-hint { font-size: 12px; }
					.cm-tab-access-grid {
						display: grid;
						grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
						gap: 8px;
					}
					.cm-tab-access-option {
						display: flex;
						align-items: center;
						gap: 8px;
						margin: 0;
						padding: 8px 10px;
						border: 1px solid var(--border-color, #d1d8dd);
						border-radius: 8px;
						background: var(--fg-color, #fff);
						cursor: pointer;
						user-select: none;
						font-weight: 500;
					}
					.cm-tab-access-option:hover { border-color: var(--primary, #2490ef); }
					.cm-tab-access-option.is-checked {
						border-color: var(--primary, #2490ef);
						background: color-mix(in srgb, var(--primary, #2490ef) 10%, white);
					}
					.cm-tab-access-option input { margin: 0; }
				</style>
			`);
		}

		const $grid = $picker.find('.cm-tab-access-grid');
		construction_management.project_tab_access.TAB_OPTIONS.forEach((tab) => {
			$grid.append(`
				<label class="cm-tab-access-option" data-tab="${frappe.utils.escape_html(tab)}">
					<input type="checkbox" value="${frappe.utils.escape_html(tab)}">
					<span>${frappe.utils.escape_html(tab)}</span>
				</label>
			`);
		});

		const sync_from_checks = () => {
			const selected = [];
			$picker.find('input[type="checkbox"]:checked').each(function () {
				selected.push(this.value);
			});
			const serialized = construction_management.project_tab_access.serialize_tabs_value(selected);
			field.set_model_value(serialized);
			$picker.find('.cm-tab-access-option').each(function () {
				const checked = $(this).find('input').is(':checked');
				$(this).toggleClass('is-checked', checked);
			});
		};

		$picker.on('change', 'input[type="checkbox"]', sync_from_checks);
		$picker.on('click', '.cm-tab-select-all', function (e) {
			e.preventDefault();
			$picker.find('input[type="checkbox"]').prop('checked', true);
			sync_from_checks();
		});
		$picker.on('click', '.cm-tab-clear', function (e) {
			e.preventDefault();
			$picker.find('input[type="checkbox"]').prop('checked', false);
			sync_from_checks();
		});

		field._cm_tabs_sync_from_checks = sync_from_checks;
	}

	const selected = construction_management.project_tab_access.parse_tabs_value(
		row.doc.tabs || field.value || ''
	);
	$picker.find('input[type="checkbox"]').each(function () {
		const checked = selected.includes(this.value);
		$(this).prop('checked', checked);
		$(this).closest('.cm-tab-access-option').toggleClass('is-checked', checked);
	});
};

construction_management.project_tab_access.enhance_allowed_projects_control = function (row) {
	const field = row.grid_form?.fields_dict?.allowed_projects;
	if (!field || !field.$wrapper || !field.$wrapper.length) {
		return;
	}

	const $wrapper = field.$wrapper;
	let $picker = $wrapper.find('.cm-project-access-picker');

	if (!$picker.length) {
		$wrapper.find('.control-input').hide();
		$wrapper.find('textarea').hide();

		$picker = $(`
			<div class="cm-project-access-picker">
				<div class="cm-project-access-toolbar">
					<input type="search" class="form-control cm-project-search" placeholder="${__('Search project no / name / company...')}" />
					<button type="button" class="btn btn-xs btn-default cm-project-select-filtered">${__('Select Filtered')}</button>
					<button type="button" class="btn btn-xs btn-default cm-project-clear">${__('Clear')}</button>
				</div>
				<div class="cm-project-access-meta text-muted">
					<span class="cm-project-selected-count">0</span> ${__('selected')} ·
					<span class="cm-project-access-hint">${__('Leave empty for all projects')}</span>
				</div>
				<div class="cm-project-access-grid"></div>
			</div>
		`);
		$wrapper.find('.control-input-wrapper, .form-group').first().append($picker);

		if (!$wrapper.find('.cm-project-access-picker-style').length) {
			$wrapper.append(`
				<style class="cm-project-access-picker-style">
					.cm-project-access-picker { margin-top: 6px; }
					.cm-project-access-toolbar {
						display: flex;
						gap: 8px;
						align-items: center;
						margin-bottom: 8px;
						flex-wrap: wrap;
					}
					.cm-project-access-toolbar .cm-project-search {
						flex: 1 1 220px;
						min-width: 180px;
						height: 32px;
					}
					.cm-project-access-meta {
						font-size: 12px;
						margin-bottom: 8px;
					}
					.cm-project-access-grid {
						display: grid;
						grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
						gap: 8px;
						max-height: 280px;
						overflow: auto;
						padding: 4px 2px 8px;
						border: 1px solid var(--border-color, #d1d8dd);
						border-radius: 8px;
						background: var(--control-bg, #fafbfc);
					}
					.cm-project-access-option {
						display: flex;
						align-items: flex-start;
						gap: 8px;
						margin: 0;
						padding: 8px 10px;
						border: 1px solid var(--border-color, #d1d8dd);
						border-radius: 8px;
						background: var(--fg-color, #fff);
						cursor: pointer;
						user-select: none;
					}
					.cm-project-access-option:hover { border-color: var(--primary, #2490ef); }
					.cm-project-access-option.is-checked {
						border-color: var(--primary, #2490ef);
						background: color-mix(in srgb, var(--primary, #2490ef) 10%, white);
					}
					.cm-project-access-option input { margin-top: 2px; }
					.cm-project-access-option .cm-project-main {
						font-weight: 600;
						line-height: 1.2;
					}
					.cm-project-access-option .cm-project-sub {
						font-size: 11px;
						color: var(--text-muted, #6c7680);
						margin-top: 2px;
					}
					.cm-project-access-empty {
						grid-column: 1 / -1;
						padding: 16px;
						text-align: center;
						color: var(--text-muted, #6c7680);
					}
				</style>
			`);
		}

		const sync_from_checks = () => {
			const selected = [];
			$picker.find('input[type="checkbox"]:checked').each(function () {
				selected.push(this.value);
			});
			// Keep selections that are not in the current filtered DOM.
			const previous = construction_management.project_tab_access.parse_projects_value(
				row.doc.allowed_projects || field.value || ''
			);
			const visible = new Set();
			$picker.find('input[type="checkbox"]').each(function () {
				visible.add(this.value);
			});
			previous.forEach((name) => {
				if (!visible.has(name) && !selected.includes(name)) {
					selected.push(name);
				}
			});

			const serialized = construction_management.project_tab_access.serialize_projects_value(selected);
			field.set_model_value(serialized);
			row.doc.allowed_projects = serialized;
			$picker.find('.cm-project-selected-count').text(selected.length);
			$picker.find('.cm-project-access-hint').text(
				selected.length
					? __('Only these projects are allowed')
					: __('Leave empty for all projects')
			);
			$picker.find('.cm-project-access-option').each(function () {
				const checked = $(this).find('input').is(':checked');
				$(this).toggleClass('is-checked', checked);
			});
		};

		const render_options = (projects, selected) => {
			const $grid = $picker.find('.cm-project-access-grid');
			const needle = String($picker.find('.cm-project-search').val() || '')
				.trim()
				.toLowerCase();
			const filtered = needle
				? projects.filter((p) => p.search.includes(needle))
				: projects;

			if (!filtered.length) {
				$grid.html(`<div class="cm-project-access-empty">${__('No projects match your search')}</div>`);
				return;
			}

			const html = filtered
				.map((project) => {
					const checked = selected.includes(project.name) ? 'checked' : '';
					const checkedClass = checked ? 'is-checked' : '';
					const sub = [project.title, project.company, project.status]
						.filter(Boolean)
						.join(' · ');
					return `
						<label class="cm-project-access-option ${checkedClass}" data-project="${frappe.utils.escape_html(project.name)}">
							<input type="checkbox" value="${frappe.utils.escape_html(project.name)}" ${checked}>
							<span>
								<span class="cm-project-main">${frappe.utils.escape_html(project.label)} <span class="text-muted">(${frappe.utils.escape_html(project.name)})</span></span>
								${sub ? `<div class="cm-project-sub">${frappe.utils.escape_html(sub)}</div>` : ''}
							</span>
						</label>
					`;
				})
				.join('');
			$grid.html(html);
			$picker.find('.cm-project-selected-count').text(selected.length);
		};

		field._cm_project_picker = {
			render_options,
			sync_from_checks,
			get_selected: () =>
				construction_management.project_tab_access.parse_projects_value(
					row.doc.allowed_projects || field.value || ''
				),
		};

		$picker.on('change', 'input[type="checkbox"]', sync_from_checks);
		$picker.on('input', '.cm-project-search', function () {
			const selected = field._cm_project_picker.get_selected();
			render_options(construction_management.project_tab_access._project_options || [], selected);
		});
		$picker.on('click', '.cm-project-select-filtered', function (e) {
			e.preventDefault();
			const selected = new Set(field._cm_project_picker.get_selected());
			$picker.find('.cm-project-access-option input[type="checkbox"]').each(function () {
				selected.add(this.value);
				$(this).prop('checked', true);
			});
			const serialized = construction_management.project_tab_access.serialize_projects_value([
				...selected,
			]);
			field.set_model_value(serialized);
			row.doc.allowed_projects = serialized;
			field._cm_project_picker.render_options(
				construction_management.project_tab_access._project_options || [],
				[...selected]
			);
			$picker.find('.cm-project-selected-count').text(selected.size);
			$picker.find('.cm-project-access-hint').text(
				selected.size
					? __('Only these projects are allowed')
					: __('Leave empty for all projects')
			);
		});
		$picker.on('click', '.cm-project-clear', function (e) {
			e.preventDefault();
			field.set_model_value('');
			row.doc.allowed_projects = '';
			field._cm_project_picker.render_options(
				construction_management.project_tab_access._project_options || [],
				[]
			);
			$picker.find('.cm-project-selected-count').text(0);
			$picker.find('.cm-project-access-hint').text(__('Leave empty for all projects'));
		});
	}

	const selected = construction_management.project_tab_access.parse_projects_value(
		row.doc.allowed_projects || field.value || ''
	);

	$picker.find('.cm-project-access-grid').html(
		`<div class="cm-project-access-empty">${__('Loading projects...')}</div>`
	);

	construction_management.project_tab_access.load_project_options().then((projects) => {
		field._cm_project_picker.render_options(projects, selected);
		$picker.find('.cm-project-selected-count').text(selected.length);
		$picker.find('.cm-project-access-hint').text(
			selected.length
				? __('Only these projects are allowed')
				: __('Leave empty for all projects')
		);
	});
};

construction_management.project_tab_access.patch_rule_grid_row = function (row) {
	if (!row) {
		return;
	}

	construction_management.project_tab_access.patch_rule_row_docfields(row.docfields);

	if (!row._tab_access_rule_row_ready) {
		row._tab_access_rule_row_ready = true;
		const original_show_form = row.show_form.bind(row);
		row.show_form = function () {
			construction_management.project_tab_access.patch_rule_row_docfields(row.docfields);
			original_show_form();
			construction_management.project_tab_access.enhance_tabs_control(row);
			construction_management.project_tab_access.enhance_allowed_projects_control(row);
		};
	}

	if (row.grid_form) {
		construction_management.project_tab_access.enhance_tabs_control(row);
		construction_management.project_tab_access.enhance_allowed_projects_control(row);
	}
};

construction_management.project_tab_access.setup_rule_grid = function (frm) {
	const grid = frm.fields_dict.rules?.grid;
	if (!grid) {
		return;
	}

	construction_management.project_tab_access.patch_rule_row_docfields(grid.docfields);
	(grid.grid_rows || []).forEach((row) => {
		construction_management.project_tab_access.patch_rule_grid_row(row);
	});

	if (grid._tab_access_rule_grid_ready) {
		return;
	}
	grid._tab_access_rule_grid_ready = true;

	const original_add_new_row = grid.add_new_row.bind(grid);
	grid.add_new_row = function (...args) {
		const row = original_add_new_row(...args);
		construction_management.project_tab_access.patch_rule_grid_row(row);
		return row;
	};

	frm.fields_dict.rules.grid.wrapper.on('grid-row-render', function (_e, row) {
		construction_management.project_tab_access.patch_rule_grid_row(row);
	});
};

frappe.ui.form.on('Project Tab Access', {
	refresh(frm) {
		construction_management.project_tab_access.setup_rule_grid(frm);
	},
	after_save() {
		construction_management.project_tab_access._config_cache = null;
	},
});

frappe.ui.form.on('Project Tab Access Rule', {
	form_render(frm, cdt, cdn) {
		const grid = frm.fields_dict.rules?.grid;
		const row = grid?.grid_rows_by_docname?.[cdn];
		if (row) {
			construction_management.project_tab_access.patch_rule_grid_row(row);
		}
	},
});
