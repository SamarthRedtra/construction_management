/**
 * Project — Management structure / team allocation tree on Details tab.
 */
frappe.provide("construction_management.project_team_allocation");

/**
 * Save Project so on_update syncs team Employees into the linked Raven channel.
 */
construction_management.project_team_allocation.persist_and_sync_raven = function (frm) {
	frm.dirty();
	if (frm.is_new() || !frm.doc.name) {
		return Promise.resolve();
	}
	if (frm._pma_saving_raven) {
		return frm._pma_saving_raven;
	}
	frm._pma_saving_raven = frm
		.save()
		.then(() => {
			frappe.show_alert({
				message: __("Team saved. Raven channel members updated."),
				indicator: "green",
			});
		})
		.catch(() => {
			frappe.show_alert({
				message: __("Team changed locally. Save the Project to update the Raven channel."),
				indicator: "orange",
			});
		})
		.finally(() => {
			frm._pma_saving_raven = null;
		});
	return frm._pma_saving_raven;
};

construction_management.project_team_allocation.GROUPS = [
	{
		id: "sales",
		title: "Sales Manager",
		managerRole: "Sales Manager",
		staff: [{ role: "Salesman", label: "Salesman" }],
	},
	{
		id: "document_control",
		title: "Document Controller",
		managerRole: "Document Controller",
		staff: [{ role: "DC Officer", label: "DC" }],
	},
	{
		id: "project_coordination",
		title: "Project Coordinator",
		managerRole: "Project Coordinator",
		staff: [{ role: "PC Officer", label: "PC" }],
	},
	{
		id: "operations",
		title: "Operations Manager",
		managerRole: "Operations Manager",
		staff: [
			{ role: "Division Manager", label: "Division Manager", needsDivision: true },
			{ role: "Engineer", label: "Engineer", needsDivision: true, nested: true },
		],
		nested: true,
	},
	{
		id: "accounts",
		title: "Accounts Manager",
		managerRole: "Accounts Manager",
		staff: [{ role: "Accountant", label: "Accountant" }],
	},
	{
		id: "director",
		title: "Director",
		managerRole: "Director",
		staff: [],
		single: true,
	},
	{
		id: "hr",
		title: "HR Manager",
		managerRole: "HR Manager",
		staff: [],
		single: true,
	},
	{
		id: "qs",
		title: "QS Manager",
		managerRole: "QS Manager",
		staff: [{ role: "QS", label: "QS" }],
	},
	{
		id: "purchase",
		title: "Purchase Manager",
		managerRole: "Purchase Manager",
		staff: [{ role: "Purchase Officer", label: "Purchase Officer" }],
	},
];

construction_management.project_team_allocation.render = function (frm) {
	const wrapper = frm.fields_dict.custom_project_team_html?.$wrapper;
	if (!wrapper) {
		return;
	}

	if (frm._pma_rendering) {
		return;
	}
	frm._pma_rendering = true;

	const read_only = frm.doc.docstatus !== 0;

	construction_management.project_team_allocation
		.prepare_members(frm)
		.then((members) => {
			wrapper.html(construction_management.project_team_allocation.build_html(members, read_only));
			construction_management.project_team_allocation.bind_events(wrapper, frm, read_only);
		})
		.finally(() => {
			frm._pma_rendering = false;
		});
};

construction_management.project_team_allocation.LEGACY_FIELD_MAP = [
	{ field: "custom_sales_engineer", role: "Salesman" },
	{ field: "custom_project_engineer", role: "Engineer" },
];

construction_management.project_team_allocation.prepare_members = function (frm) {
	return construction_management.project_team_allocation.sync_legacy_fields(frm).then(() => {
		const members = (frm.doc.custom_project_team || []).map((row, idx) => ({
			...row,
			idx,
		}));
		return construction_management.project_team_allocation.resolve_member_names(members);
	});
};

construction_management.project_team_allocation.sync_legacy_fields = function (frm) {
	if (frm.doc.docstatus !== 0 || frm._pma_syncing_legacy) {
		return Promise.resolve();
	}
	frm._pma_syncing_legacy = true;

	const mappings = construction_management.project_team_allocation.LEGACY_FIELD_MAP.filter(
		(item) => frm.doc[item.field]
	);

	const cleanup_promise = construction_management.project_team_allocation.fix_misplaced_legacy_roles(frm);

	if (!mappings.length) {
		return cleanup_promise.finally(() => {
			frm._pma_syncing_legacy = false;
		});
	}

	const employee_ids = [...new Set(mappings.map((item) => frm.doc[item.field]))];

	return cleanup_promise
		.then(() => construction_management.project_team_allocation.fetch_employees(employee_ids))
		.then((employee_map) => {
			let changed = false;

			mappings.forEach(({ field, role }) => {
				const employee = frm.doc[field];
				if (!employee) {
					return;
				}

				const emp = employee_map[employee] || {};
				const has_role_row = (frm.doc.custom_project_team || []).some(
					(item) => item.role === role && item.employee === employee
				);

				if (!has_role_row) {
					frm.add_child("custom_project_team", {
						role,
						employee,
						employee_name: emp.employee_name || "",
						designation: emp.designation || "",
					});
					changed = true;
				} else {
					const row = (frm.doc.custom_project_team || []).find(
						(item) => item.role === role && item.employee === employee
					);
					if (row && emp.employee_name && !row.employee_name) {
						row.employee_name = emp.employee_name;
						row.designation = row.designation || emp.designation || "";
						changed = true;
					}
				}
			});

			if (changed) {
				frm.refresh_field("custom_project_team");
				frm.dirty();
			}
		})
		.finally(() => {
			frm._pma_syncing_legacy = false;
		});
};

construction_management.project_team_allocation.fix_misplaced_legacy_roles = function (frm) {
	let changed = false;
	const sales_employee = frm.doc.custom_sales_engineer;
	const engineer_employee = frm.doc.custom_project_engineer;

	(frm.doc.custom_project_team || []).forEach((row) => {
		if (sales_employee && row.role === "Sales Manager" && row.employee === sales_employee) {
			row.role = "Salesman";
			changed = true;
		}
	});

	if (sales_employee) {
		let seen_salesman = false;
		frm.doc.custom_project_team = (frm.doc.custom_project_team || []).filter((row) => {
			if (row.role === "Salesman" && row.employee === sales_employee) {
				if (seen_salesman) {
					changed = true;
					return false;
				}
				seen_salesman = true;
			}
			return true;
		});
	}

	if (engineer_employee) {
		let seen_engineer = false;
		frm.doc.custom_project_team = (frm.doc.custom_project_team || []).filter((row) => {
			if (row.role === "Engineer" && row.employee === engineer_employee) {
				if (seen_engineer) {
					changed = true;
					return false;
				}
				seen_engineer = true;
			}
			return true;
		});
	}

	if (changed) {
		frm.refresh_field("custom_project_team");
		frm.dirty();
	}
	return Promise.resolve();
};

construction_management.project_team_allocation.sync_team_to_legacy_fields = function (frm) {
	if (frm.doc.docstatus !== 0) {
		return;
	}

	const salesman = (frm.doc.custom_project_team || []).find((row) => row.role === "Salesman");
	const engineer = (frm.doc.custom_project_team || []).find((row) => row.role === "Engineer");

	if (salesman?.employee && frm.doc.custom_sales_engineer !== salesman.employee) {
		frm.set_value("custom_sales_engineer", salesman.employee);
	} else if (!salesman && frm.doc.custom_sales_engineer) {
		frm.set_value("custom_sales_engineer", "");
	}

	if (engineer?.employee && frm.doc.custom_project_engineer !== engineer.employee) {
		frm.set_value("custom_project_engineer", engineer.employee);
	} else if (!engineer && frm.doc.custom_project_engineer) {
		frm.set_value("custom_project_engineer", "");
	}
};

construction_management.project_team_allocation.fetch_employees = function (employee_ids) {
	const ids = [...new Set((employee_ids || []).filter(Boolean))];
	if (!ids.length) {
		return Promise.resolve({});
	}

	return frappe
		.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Employee",
				filters: { name: ["in", ids] },
				fields: ["name", "employee_name", "designation"],
				limit_page_length: 0,
			},
		})
		.then((r) => {
			const map = {};
			(r.message || []).forEach((emp) => {
				map[emp.name] = emp;
			});
			return map;
		});
};

construction_management.project_team_allocation.resolve_member_names = function (members) {
	const missing_ids = [
		...new Set(
			(members || []).filter((row) => row.employee && !row.employee_name).map((row) => row.employee)
		),
	];

	if (!missing_ids.length) {
		return Promise.resolve(members || []);
	}

	return construction_management.project_team_allocation
		.fetch_employees(missing_ids)
		.then((employee_map) =>
			(members || []).map((row) => {
				const emp = employee_map[row.employee];
				if (!emp) {
					return row;
				}
				return {
					...row,
					employee_name: row.employee_name || emp.employee_name || row.employee,
					designation: row.designation || emp.designation || "",
				};
			})
		);
};

construction_management.project_team_allocation.get_display_name = function (row) {
	return row.employee_name || row.employee || "";
};

construction_management.project_team_allocation.build_html = function (members, read_only) {
	const grouped = construction_management.project_team_allocation.group_members(members);
	const groups_html = construction_management.project_team_allocation.GROUPS.map((group) =>
		construction_management.project_team_allocation.render_group(group, grouped[group.id] || {}, read_only)
	).join("");

	return `
		<style>
			.pma-wrap {
				font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
				padding: 12px;
				background: #fff;
				border: 1px solid #e5e7eb;
				border-radius: 8px;
				margin: 8px 0;
			}
			.pma-title {
				font-size: 13px;
				font-weight: 700;
				color: #111827;
				margin-bottom: 12px;
			}
			.pma-group {
				border: 1px solid #e5e7eb;
				border-radius: 8px;
				margin-bottom: 10px;
				overflow: hidden;
			}
			.pma-group-head {
				background: #f8fafc;
				padding: 8px 12px;
				font-weight: 600;
				font-size: 12px;
				color: #1f2937;
				display: flex;
				justify-content: space-between;
				align-items: center;
			}
			.pma-group-body {
				padding: 8px 12px 10px 24px;
			}
			.pma-node {
				display: flex;
				align-items: center;
				justify-content: space-between;
				gap: 8px;
				padding: 4px 0;
				font-size: 12px;
				color: #374151;
			}
			.pma-node.manager {
				font-weight: 600;
				color: #111827;
			}
			.pma-node.staff {
				padding-left: 16px;
			}
			.pma-node.nested {
				padding-left: 28px;
			}
			.pma-node.empty {
				color: #9ca3af;
				font-style: italic;
			}
			.pma-branch {
				border-left: 2px solid #dbeafe;
				margin: 4px 0 4px 8px;
				padding-left: 12px;
			}
			.pma-division-title {
				font-size: 11px;
				font-weight: 600;
				color: #2563eb;
				margin: 6px 0 2px;
			}
			.pma-actions {
				display: flex;
				gap: 4px;
				flex-shrink: 0;
			}
		</style>
		<div class="pma-wrap">
			<div class="pma-title">${__("Project Allocation Structure")}</div>
			${groups_html}
		</div>
	`;
};

construction_management.project_team_allocation.group_members = function (members) {
	const grouped = {};
	(members || []).forEach((row, idx) => {
		const group = construction_management.project_team_allocation.get_group_for_role(row.role);
		if (!group) {
			return;
		}
		if (!grouped[group.id]) {
			grouped[group.id] = { manager: null, staff: [], divisions: {} };
		}
		const entry = { ...row, idx: row.idx != null ? row.idx : idx };
		if (row.role === group.managerRole) {
			grouped[group.id].manager = entry;
			return;
		}
		grouped[group.id].staff.push(entry);
		if (row.division) {
			grouped[group.id].divisions[row.division] = grouped[group.id].divisions[row.division] || {
				managers: [],
				engineers: [],
			};
			if (row.role === "Division Manager") {
				grouped[group.id].divisions[row.division].managers.push(entry);
			}
			if (row.role === "Engineer") {
				grouped[group.id].divisions[row.division].engineers.push(entry);
			}
		}
	});
	return grouped;
};

construction_management.project_team_allocation.get_group_for_role = function (role) {
	return construction_management.project_team_allocation.GROUPS.find((group) => {
		if (group.managerRole === role) {
			return true;
		}
		return (group.staff || []).some((staff) => staff.role === role);
	});
};

construction_management.project_team_allocation.render_group = function (group, data, read_only) {
	data = data || { manager: null, staff: [], divisions: {} };
	const manager_html = construction_management.project_team_allocation.render_member_node(
		data.manager,
		group.managerRole,
		"manager",
		read_only,
		group
	);

	let body_html = "";
	if (group.nested) {
		body_html = construction_management.project_team_allocation.render_operations_body(data, read_only, group);
	} else if (group.staff.length) {
		const staff_nodes = (group.staff || [])
			.map((staff_def) => {
				const rows = (data.staff || []).filter((row) => row.role === staff_def.role);
				if (!rows.length) {
					return construction_management.project_team_allocation.render_empty_staff(staff_def.label, read_only, group, staff_def);
				}
				return rows
					.map((row) =>
						construction_management.project_team_allocation.render_member_node(row, staff_def.label, "staff", read_only, group, staff_def)
					)
					.join("");
			})
			.join("");
		body_html = `<div class="pma-branch">${staff_nodes}</div>`;
	} else if (group.single && !data.manager) {
		body_html = `<div class="pma-branch"><div class="pma-node empty staff">${__("Not assigned")}</div></div>`;
	}

	const add_btn = read_only
		? ""
		: `<button type="button" class="btn btn-xs btn-default btn-pma-add" data-group="${group.id}" data-role="${frappe.utils.escape_html(
				group.managerRole
		  )}">${__("Assign")}</button>`;

	return `
		<div class="pma-group" data-group-id="${group.id}">
			<div class="pma-group-head">
				<span>${__(group.title)}</span>
				${add_btn}
			</div>
			<div class="pma-group-body">
				${manager_html}
				${body_html}
			</div>
		</div>
	`;
};

construction_management.project_team_allocation.render_operations_body = function (data, read_only, group) {
	const division_names = Object.keys(data.divisions || {});
	const unassigned_dms = (data.staff || []).filter((row) => row.role === "Division Manager" && !row.division);
	const unassigned_engineers = (data.staff || []).filter((row) => row.role === "Engineer" && !row.division);

	let html = "";
	if (!division_names.length && !unassigned_dms.length && !unassigned_engineers.length) {
		html += construction_management.project_team_allocation.render_empty_staff(
			"Division Manager",
			read_only,
			group,
			{ role: "Division Manager", label: "Division Manager", needsDivision: true }
		);
	}

	division_names.forEach((division) => {
		const block = data.divisions[division];
		html += `<div class="pma-division-title">${frappe.utils.escape_html(division)}</div>`;
		html += `<div class="pma-branch">`;
		(block.managers || []).forEach((row) => {
			html += construction_management.project_team_allocation.render_member_node(
				row,
				"Division Manager",
				"staff",
				read_only,
				group,
				{ role: "Division Manager", label: "Division Manager", needsDivision: true }
			);
		});
		if (!(block.managers || []).length) {
			html += construction_management.project_team_allocation.render_empty_staff(
				"Division Manager",
				read_only,
				group,
				{ role: "Division Manager", label: "Division Manager", needsDivision: true },
				division
			);
		}
		(block.engineers || []).forEach((row) => {
			html += construction_management.project_team_allocation.render_member_node(
				row,
				"Engineer",
				"nested",
				read_only,
				group,
				{ role: "Engineer", label: "Engineer", needsDivision: true, nested: true },
				division
			);
		});
		if (!(block.engineers || []).length) {
			html += construction_management.project_team_allocation.render_empty_staff(
				"Engineer",
				read_only,
				group,
				{ role: "Engineer", label: "Engineer", needsDivision: true, nested: true },
				division
			);
		}
		html += `</div>`;
	});

	if (unassigned_dms.length || unassigned_engineers.length) {
		html += `<div class="pma-division-title">${__("Unassigned")}</div><div class="pma-branch">`;
		unassigned_dms.forEach((row) => {
			html += construction_management.project_team_allocation.render_member_node(
				row,
				"Division Manager",
				"staff",
				read_only,
				group,
				{ role: "Division Manager", label: "Division Manager", needsDivision: true }
			);
		});
		unassigned_engineers.forEach((row) => {
			html += construction_management.project_team_allocation.render_member_node(
				row,
				"Engineer",
				"nested",
				read_only,
				group,
				{ role: "Engineer", label: "Engineer", needsDivision: true, nested: true }
			);
		});
		html += `</div>`;
	}

	const add_division_btn = read_only
		? ""
		: `<div style="margin-top:6px;"><button type="button" class="btn btn-xs btn-primary btn-pma-add-division" data-group="${group.id}">${__(
				"Add Division"
		  )}</button></div>`;
	return html + add_division_btn;
};

construction_management.project_team_allocation.render_member_node = function (
	row,
	label,
	css_class,
	read_only,
	group,
	staff_def,
	division
) {
	if (!row) {
		return `<div class="pma-node ${css_class} empty">${__(
			"Not assigned"
		)} <span class="text-muted">(${label})</span></div>`;
	}

	const name = frappe.utils.escape_html(
		construction_management.project_team_allocation.get_display_name(row)
	);
	const designation = row.designation ? ` <span class="text-muted">— ${frappe.utils.escape_html(row.designation)}</span>` : "";
	const remove_btn = read_only
		? ""
		: `<button type="button" class="btn btn-xs btn-danger btn-pma-remove" data-idx="${row.idx}">✕</button>`;

	return `
		<div class="pma-node ${css_class}">
			<span>${label}: <strong>${name}</strong>${designation}</span>
			<div class="pma-actions">${remove_btn}</div>
		</div>
	`;
};

construction_management.project_team_allocation.render_empty_staff = function (label, read_only, group, staff_def, division) {
	const add_btn = read_only
		? ""
		: `<button type="button" class="btn btn-xs btn-default btn-pma-add-staff" data-group="${group.id}" data-role="${staff_def.role}" ${
				division ? `data-division="${frappe.utils.escape_html(division)}"` : ""
		  }>${__("Add")} ${label}</button>`;
	return `<div class="pma-node staff empty">${label}: ${__("Not assigned")} ${add_btn}</div>`;
};

construction_management.project_team_allocation.bind_events = function (wrapper, frm, read_only) {
	if (read_only) {
		return;
	}

	wrapper.off("click.pma");

	wrapper.on("click.pma", ".btn-pma-add", function (e) {
		e.preventDefault();
		e.stopImmediatePropagation();
		const role = $(this).attr("data-role");
		construction_management.project_team_allocation.open_assign_dialog(frm, role);
	});

	wrapper.on("click.pma", ".btn-pma-add-staff", function (e) {
		e.preventDefault();
		e.stopImmediatePropagation();
		const role = $(this).attr("data-role");
		const division = $(this).attr("data-division") || "";
		construction_management.project_team_allocation.open_assign_dialog(frm, role, division);
	});

	wrapper.on("click.pma", ".btn-pma-add-division", function (e) {
		e.preventDefault();
		e.stopImmediatePropagation();
		if (frm._pma_division_prompt_open) {
			return;
		}
		frm._pma_division_prompt_open = true;
		frappe.prompt(
			[
				{
					fieldtype: "Data",
					fieldname: "division",
					label: __("Division Name"),
					reqd: 1,
				},
			],
			(values) => {
				frm._pma_division_prompt_open = false;
				construction_management.project_team_allocation.open_assign_dialog(
					frm,
					"Division Manager",
					values.division
				);
			},
			__("Add Division"),
			__("Continue"),
			() => {
				frm._pma_division_prompt_open = false;
			}
		);
	});

	wrapper.on("click.pma", ".btn-pma-remove", function (e) {
		e.preventDefault();
		e.stopImmediatePropagation();
		const idx = parseInt($(this).attr("data-idx"), 10);
		if (isNaN(idx)) {
			return;
		}
		frm.doc.custom_project_team.splice(idx, 1);
		frm.refresh_field("custom_project_team");
		construction_management.project_team_allocation.sync_team_to_legacy_fields(frm);
		construction_management.project_team_allocation.render(frm);
		construction_management.project_team_allocation.persist_and_sync_raven(frm);
	});
};

construction_management.project_team_allocation.open_assign_dialog = function (frm, role, division) {
	if (frm._pma_dialog_open) {
		return;
	}
	frm._pma_dialog_open = true;

	const group = construction_management.project_team_allocation.GROUPS.find((g) => {
		if (g.managerRole === role) {
			return true;
		}
		return (g.staff || []).some((staff) => staff.role === role);
	});
	const staff_def = (group?.staff || []).find((staff) => staff.role === role);
	const needs_division = staff_def?.needsDivision && !division;

	const fields = [
		{
			fieldtype: "Link",
			fieldname: "employee",
			label: __("Employee"),
			options: "Employee",
			reqd: 1,
		},
	];
	if (needs_division) {
		fields.push({
			fieldtype: "Data",
			fieldname: "division",
			label: __("Division"),
			reqd: 1,
		});
	}

	const d = new frappe.ui.Dialog({
		title: __("Assign {0}", [role]),
		fields,
		primary_action_label: __("Assign"),
		primary_action(values) {
			const duplicate = (frm.doc.custom_project_team || []).some(
				(row) => row.role === role && row.employee === values.employee
			);
			if (duplicate) {
				frappe.msgprint(__("This employee is already assigned to this role."));
				return;
			}

			if (group?.single || group?.managerRole === role) {
				const existing_manager = (frm.doc.custom_project_team || []).find((row) => row.role === role);
				if (existing_manager) {
					frappe.msgprint(__("{0} is already assigned. Remove the current one first.", [role]));
					return;
				}
			}

			d.disable_primary_action();
			construction_management.project_team_allocation.fetch_employees([values.employee]).then((employee_map) => {
				const emp = employee_map[values.employee] || {};
				frm.add_child("custom_project_team", {
					role,
					employee: values.employee,
					employee_name: emp.employee_name || "",
					designation: emp.designation || "",
					division: division || values.division || "",
				});
				frm.refresh_field("custom_project_team");
				construction_management.project_team_allocation.sync_team_to_legacy_fields(frm);
				construction_management.project_team_allocation.render(frm);
				construction_management.project_team_allocation.persist_and_sync_raven(frm);
				d.hide();
			});
		},
	});

	d.onhide = () => {
		frm._pma_dialog_open = false;
	};

	d.show();
};
