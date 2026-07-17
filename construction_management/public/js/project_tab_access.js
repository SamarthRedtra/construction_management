// Copyright (c) 2026, Construction Management
// License: MIT

frappe.provide('construction_management.project_tab_access');

construction_management.project_tab_access._config_cache = null;

construction_management.project_tab_access.BYPASS_ROLES = ['Administrator', 'System Manager'];

construction_management.project_tab_access.ALWAYS_HIDDEN_TABS = ['costing_tab', 'monitor_progress_tab'];

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
		};
		return construction_management.project_tab_access._config_cache;
	});
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

construction_management.project_tab_access.patch_rule_row_docfields = function (docfields) {
	(docfields || []).forEach((df) => {
		if (df.fieldname === 'tabs') {
			df.fieldtype = 'MultiSelect';
			df.options = 'Details\nConnections\nConstruction\nApproved Materials\nAccounting\nProject SOA\nProject Commission\nCommission\nDashboard\nMore Info';
		}
		if (df.fieldname === 'allowed_projects') {
			df.fieldtype = 'MultiSelectList';
			df.placeholder = __('Leave empty for all projects');
			df.options = 'Project';
			df.get_data = function (txt) {
				return frappe.db.get_link_options('Project', txt);
			};
		}
	});
};

construction_management.project_tab_access.enhance_allowed_projects_control = function (row) {
	const field = row.grid_form?.fields_dict?.allowed_projects;
	if (!field || field._cm_allowed_projects_enhanced) {
		return;
	}
	field._cm_allowed_projects_enhanced = true;

	field.parse_validate_and_set_in_model = function () {
		const serialized = (this.values || []).join(', ');
		return this.validate_and_set_in_model(serialized);
	};

	field.set_input = function (value) {
		this.last_value = this.value;
		this.value = value;
		const values = value
			? String(value).split(',').map((item) => item.trim()).filter(Boolean)
			: [];
		return this.set_options().then(() => this.set_value(values));
	};

	if (row.doc.allowed_projects) {
		field.set_input(row.doc.allowed_projects);
	}
};

construction_management.project_tab_access.patch_rule_grid_row = function (row) {
	if (!row || row._tab_access_rule_row_ready) {
		return;
	}
	row._tab_access_rule_row_ready = true;

	construction_management.project_tab_access.patch_rule_row_docfields(row.docfields);

	const original_show_form = row.show_form.bind(row);
	row.show_form = function () {
		construction_management.project_tab_access.patch_rule_row_docfields(row.docfields);
		original_show_form();
		construction_management.project_tab_access.enhance_allowed_projects_control(row);
	};
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
};

frappe.ui.form.on('Project Tab Access', {
	refresh(frm) {
		construction_management.project_tab_access.setup_rule_grid(frm);
	},
	after_save() {
		construction_management.project_tab_access._config_cache = null;
	},
});
