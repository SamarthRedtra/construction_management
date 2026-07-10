// Copyright (c) 2026, Construction Management
// License: MIT

frappe.provide('construction_management.project_tab_access');

construction_management.project_tab_access._config_cache = null;

construction_management.project_tab_access.BYPASS_ROLES = ['Administrator', 'System Manager'];

construction_management.project_tab_access.fetch_config = function (force) {
	if (!force && construction_management.project_tab_access._config_cache) {
		return Promise.resolve(construction_management.project_tab_access._config_cache);
	}

	return frappe.call({
		method: 'construction_management.construction_management.doctype.project_tab_access.project_tab_access.get_project_tab_access_config',
		freeze: false,
	}).then((r) => {
		construction_management.project_tab_access._config_cache = r.message || { enabled: false, restricted_tabs: {} };
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
		if (rule.user && rule.user === user) {
			return true;
		}
		if (rule.role && roles.includes(rule.role)) {
			return true;
		}
		return false;
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

construction_management.project_tab_access.apply = function (frm) {
	const roles = frappe.user_roles || [];
	if (
		frappe.session.user === 'Administrator'
		|| roles.includes('Administrator')
		|| roles.includes('System Manager')
	) {
		return;
	}

	construction_management.project_tab_access.fetch_config().then((config) => {
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

frappe.ui.form.on('Project Tab Access', {
	after_save() {
		construction_management.project_tab_access._config_cache = null;
	},
});
