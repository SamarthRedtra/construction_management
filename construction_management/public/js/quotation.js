/**
 * BOQ-style Quotation — simple child-table grid (like BOQ Management)
 */

frappe.provide("construction_management");

const QUOTATION_BOQ_ITEM = "QUOTATION-BOQ";
const HIERARCHY_TWO_LEVEL = "2 Level (Parent + Sub)";
const HIERARCHY_THREE_LEVEL = "3 Level (Section + Parent + Sub)";

frappe.ui.form.on("Quotation", {
	onload(frm) {
		clear_blank_items(frm);
	},

	refresh(frm) {
		clear_blank_items(frm);
		setup_amendment_action(frm);
		setup_boq_buttons(frm);
		setup_boq_grid(frm);
		setup_print_hint(frm);
		setup_sales_manager_approver_field(frm);
		setup_approval_actions(frm);
		if (typeof construction_management !== "undefined" && construction_management.quotation_boq_easy_entry) {
			construction_management.quotation_boq_easy_entry.setup(frm);
		}
		render_boq_preview(frm);
	},

	company(frm) {
		setup_boq_buttons(frm);
		setup_sales_manager_approver_field(frm);
	},

	validate(frm) {
		// Runs before Frappe check_mandatory — fill Items so Item Name / UOM pass
		return ensure_placeholder_item(frm);
	},

	custom_project(frm) {
		prefill_header_from_project(frm);
	},

	custom_include_vat(frm) {
		if (typeof construction_management !== "undefined" && construction_management.quotation_boq_easy_entry) {
			construction_management.quotation_boq_easy_entry.render_total(frm);
		}
	},

	party_name(frm) {
		prefill_header_from_party(frm);
	},

	quotation_to(frm) {
		prefill_header_from_party(frm);
	},

	tc_name(frm) {
		if (!frm.doc.tc_name) {
			frm.set_value("terms", "");
			return;
		}
		frappe.db.get_value("Terms and Conditions", frm.doc.tc_name, "terms").then((r) => {
			if (r && r.message && r.message.terms) {
				frm.set_value("terms", r.message.terms);
			}
		});
	},

	custom_payment_terms_tc(frm) {
		if (!frm.doc.custom_payment_terms_tc) {
			frm.set_value("custom_payment_terms", "");
			return;
		}
		frappe.db.get_value("Terms and Conditions", frm.doc.custom_payment_terms_tc, "terms").then((r) => {
			if (r && r.message && r.message.terms) {
				frm.set_value("custom_payment_terms", r.message.terms);
			}
		});
	},

	custom_exclusion_tc(frm) {
		if (!frm.doc.custom_exclusion_tc) {
			frm.set_value("custom_exclusion", "");
			return;
		}
		frappe.db.get_value("Terms and Conditions", frm.doc.custom_exclusion_tc, "terms").then((r) => {
			if (r && r.message && r.message.terms) {
				frm.set_value("custom_exclusion", r.message.terms);
			}
		});
	},

	custom_validity_tc(frm) {
		if (!frm.doc.custom_validity_tc) {
			frm.set_value("custom_validity", "");
			return;
		}
		frappe.db.get_value("Terms and Conditions", frm.doc.custom_validity_tc, "terms").then((r) => {
			if (r && r.message && r.message.terms) {
				frm.set_value("custom_validity", r.message.terms);
			}
		});
	},
});

function setup_amendment_action(frm) {
	if (frm.doc.docstatus !== 2) {
		return;
	}

	const create_amendment = () => frappe.call({
		method: "construction_management.overrides.quotation.create_quotation_amendment",
		args: { quotation: frm.doc.name },
		freeze: true,
		freeze_message: __("Creating amendment"),
		callback: (r) => {
			if (!(r.message && r.message.name)) {
				return;
			}
			const name = r.message.name;
			// Force a clean Form load so Cancel/cancelled toolbar does not stick on the -1 draft.
			frappe.set_route("Form", "Quotation", name).then(() => {
				const open = () => {
					if (cur_frm && cur_frm.doctype === "Quotation" && cur_frm.docname === name) {
						cur_frm.reload_doc();
					}
				};
				if (cur_frm && cur_frm.docname === name) {
					open();
				} else {
					frappe.after_ajax(open);
				}
			});
		},
	});

	// Override the standard local-copy action. The server draft reliably opens
	// with Save / Submit actions instead of retaining the cancelled form state.
	frm.amend_doc = create_amendment;
	frm.page.set_primary_action(__("Amend"), create_amendment);
}

function setup_print_hint(frm) {
	if (frm.is_new()) {
		return;
	}
	frm.add_custom_button(
		__("Preview BOQ Print"),
		() => {
			const url = `/printview?doctype=Quotation&name=${encodeURIComponent(
				frm.doc.name
			)}&format=${encodeURIComponent("BOQ Quotation")}&no_letterhead=0&_lang=en`;
			window.open(url, "_blank");
		},
		__("BOQ")
	);
}

function setup_sales_manager_approver_field(frm) {
	const editable = frm.doc.docstatus === 0;

	// Keep field as Link → User (do not convert to Select — that breaks
	// Frappe "Ignore User Permissions" validation on submit).
	frm.set_df_property("custom_sales_manager_approver", "fieldtype", "Link");
	frm.set_df_property("custom_sales_manager_approver", "options", "User");
	frm.set_df_property("custom_sales_manager_approver", "read_only", editable ? 0 : 1);
	frm.set_df_property(
		"custom_sales_manager_approver",
		"description",
		__("Only this Sales Manager is assigned on submit. All Quotation Directors are also assigned.")
	);
	setup_terms_template_queries(frm);

	frm.set_query("custom_sales_manager_approver", () => ({
		query: "construction_management.overrides.quotation.sales_manager_approver_query",
		filters: { company: frm.doc.company || "" },
	}));

	if (!editable || !frm.doc.company) {
		frm.set_df_property("custom_sales_manager_approver", "reqd", 0);
		return;
	}

	frappe.call({
		method: "construction_management.overrides.quotation.get_quotation_approver_options",
		args: { company: frm.doc.company },
		callback: (r) => {
			const managers = (r.message && r.message.managers) || [];
			frm.set_df_property("custom_sales_manager_approver", "reqd", managers.length ? 1 : 0);
			if (!managers.length) {
				frm.set_df_property(
					"custom_sales_manager_approver",
					"description",
					__(
						"Configure Quotation Sales Managers on Company {0} before selecting an approver.",
						[frm.doc.company]
					)
				);
				frappe.show_alert({
					message: __(
						"No Quotation Sales Managers configured on Company {0}. Add them under Quotation Sales Managers.",
						[frm.doc.company]
					),
					indicator: "orange",
				});
				return;
			}
			if (
				frm.doc.custom_sales_manager_approver &&
				!managers.includes(frm.doc.custom_sales_manager_approver)
			) {
				frm.set_value("custom_sales_manager_approver", "");
			}
			frm.refresh_field("custom_sales_manager_approver");
		},
	});
}

function setup_terms_template_queries(frm) {
	const typed = (tc_type) => () => ({
		filters: {
			disabled: 0,
			selling: 1,
			custom_tc_type: tc_type,
		},
	});
	frm.set_query("custom_payment_terms_tc", typed("Payment Terms"));
	frm.set_query("custom_exclusion_tc", typed("Exclusion"));
	frm.set_query("custom_validity_tc", typed("Validity"));
	frm.set_query("tc_name", () => ({
		filters: {
			disabled: 0,
			selling: 1,
		},
	}));
}

function setup_approval_actions(frm) {
	if (frm.doc.docstatus !== 1) return;

	frappe.call({
		method: "construction_management.overrides.quotation.get_quotation_approval_access",
		args: { quotation: frm.doc.name },
		callback: (r) => setup_approval_buttons(frm, r.message || {}),
	});
}

function setup_approval_buttons(frm, access) {
	const state = frm.doc.custom_approval_status;
	const can_manage_cost_sheet = access.is_manager || access.is_director;
	const show_approval_alert = (message) => frm.set_intro(
		`${__("Approval alert")}: ${message}`,
		"blue"
	);
	frm.set_intro("");
	frm.set_df_property(
		"custom_cost_sheet",
		"read_only",
		state !== "Pending Sales Manager Approval" || !can_manage_cost_sheet
	);
	const call = (method, args = {}) => frappe.call({
		method: `construction_management.overrides.quotation.${method}`,
		args: { quotation: frm.doc.name, ...args },
		freeze: true,
		callback: () => frm.reload_doc(),
	});
	const reject = (method) => frappe.prompt(
		[{ fieldname: "reason", fieldtype: "Small Text", label: __("Rejection reason"), reqd: 1 }],
		(values) => call(method, values),
		__("Reject Quotation"),
		__("Reject")
	);

	if (state === "Pending Sales Manager Approval" && access.is_manager) {
		show_approval_alert(__("Sales Manager action required. Upload the cost sheet, then approve or reject this quotation."));
		frm.add_custom_button(__("Approve"), () => call("sales_manager_approve_quotation"), __("Approval"));
		frm.add_custom_button(__("Reject"), () => reject("sales_manager_reject_quotation"), __("Approval"));
	}
	if (state === "Pending Sales Manager Approval" && access.is_director) {
		show_approval_alert(__("Sales Manager approval is pending. You can approve or reject on behalf of the Sales Manager."));
		frm.add_custom_button(
			__("Approve on behalf of Sales Manager"),
			() => call("director_approve_sales_manager_on_behalf"),
			__("Director Escalation")
		);
		frm.add_custom_button(
			__("Reject on behalf of Sales Manager"),
			() => reject("director_reject_sales_manager_on_behalf"),
			__("Director Escalation")
		);
	}
	if (state === "Pending Director Approval" && access.is_director) {
		show_approval_alert(__("Director action required. Review the cost sheet, then approve or reject this quotation."));
		frm.add_custom_button(__("Approve"), () => call("director_approve_quotation"), __("Approval"));
		frm.add_custom_button(__("Reject"), () => reject("director_reject_quotation"), __("Approval"));
	}
	if (
		state === "Approved" &&
		frm.doc.custom_agreement_status === "Pending" &&
		(access.is_manager || access.is_director || frm.doc.owner === frappe.session.user)
	) {
		show_approval_alert(__("Director approval is complete. Record whether the customer agreed or not agreed."));
		frm.add_custom_button(__("Mark Agreed"), () => call("set_quotation_agreement", { agreed: 1 }), __("Agreement"));
		frm.add_custom_button(
			__("Mark Not Agreed"),
			() => frappe.prompt(
				[{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason") }],
				(values) => call("set_quotation_agreement", { agreed: 0, ...values }),
				__("Mark Not Agreed"),
				__("Confirm")
			),
			__("Agreement")
		);
	}
}

frappe.ui.form.on("Quotation BOQ Line", {
	line_type(frm, cdt, cdn) {
		update_boq_row_amount(frm, cdt, cdn);
	},

	display_mode(frm, cdt, cdn) {
		update_boq_row_amount(frm, cdt, cdn);
	},

	qty(frm, cdt, cdn) {
		update_boq_row_amount(frm, cdt, cdn);
		if (typeof construction_management !== "undefined" && construction_management.quotation_boq_easy_entry) {
			construction_management.quotation_boq_easy_entry.render_total(frm);
		}
		render_boq_preview(frm);
	},

	rate(frm, cdt, cdn) {
		update_boq_row_amount(frm, cdt, cdn);
		if (typeof construction_management !== "undefined" && construction_management.quotation_boq_easy_entry) {
			construction_management.quotation_boq_easy_entry.render_total(frm);
		}
		render_boq_preview(frm);
	},

	is_fixed_rate(frm, cdt, cdn) {
		update_boq_row_amount(frm, cdt, cdn);
		frm.refresh_field("custom_boq_lines");
		if (typeof construction_management !== "undefined" && construction_management.quotation_boq_easy_entry) {
			construction_management.quotation_boq_easy_entry.render_total(frm);
		}
		render_boq_preview(frm);
	},

	amount(frm) {
		if (typeof construction_management !== "undefined" && construction_management.quotation_boq_easy_entry) {
			construction_management.quotation_boq_easy_entry.render_total(frm);
		}
		render_boq_preview(frm);
	},

	description(frm) {
		render_boq_preview(frm);
	},

	parent_no(frm) {
		render_boq_preview(frm);
	},

	sub_no(frm) {
		render_boq_preview(frm);
	},
});

function setup_boq_buttons(frm) {
	if (frm.doc.docstatus !== 0) {
		return;
	}

	const company = frm.doc.company;
	const render_buttons = (hierarchy) => {
		if (frm.doc.company !== company) {
			return;
		}
		const two_level = hierarchy === HIERARCHY_TWO_LEVEL;

		if (!two_level) {
			frm.add_custom_button(__("Add Section"), () => add_boq_row(frm, "Section"), __("BOQ"));
		}
		frm.add_custom_button(__("Add Parent"), () => add_boq_row(frm, "Parent"), __("BOQ"));
		frm.add_custom_button(__("Add Sub"), () => add_boq_row(frm, "Sub"), __("BOQ"));

		const estimation = frm.doc.custom_project_estimation;
		if (estimation) {
			frm.add_custom_button(
				__("Import from Estimation"),
				() => import_boq_lines_from_estimation(frm, estimation),
				__("BOQ")
			);
		}
	};

	if (!company) {
		render_buttons(HIERARCHY_THREE_LEVEL);
		return;
	}

	frappe.db.get_value("BOQ Settings", company, "quotation_boq_hierarchy", (r) => {
		render_buttons((r && r.message && r.message.quotation_boq_hierarchy) || HIERARCHY_THREE_LEVEL);
	});
}

function add_boq_row(frm, line_type) {
	const values = {
		line_type,
	};

	if (line_type === "Parent") {
		values.parent_no = String(next_parent_no(frm));
	} else if (line_type === "Sub") {
		values.parent_no = last_parent_no(frm) || "1";
		values.sub_no = next_sub_no(frm, values.parent_no);
		values.display_mode = "Normal";
		values.is_fixed_rate = 0;
	}

	frm.add_child("custom_boq_lines", values);
	frm.refresh_field("custom_boq_lines");
	render_boq_preview(frm);
}

function next_parent_no(frm) {
	let max = 0;
	(frm.doc.custom_boq_lines || []).forEach((row) => {
		if (row.line_type === "Parent" && row.parent_no) {
			const n = parseInt(row.parent_no, 10);
			if (!isNaN(n) && n > max) {
				max = n;
			}
		}
	});
	return max + 1;
}

function last_parent_no(frm) {
	const lines = frm.doc.custom_boq_lines || [];
	for (let i = lines.length - 1; i >= 0; i--) {
		if (lines[i].line_type === "Parent" && lines[i].parent_no) {
			return lines[i].parent_no;
		}
	}
	return "";
}

function next_sub_no(frm, parent_no) {
	const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
	let count = 0;
	(frm.doc.custom_boq_lines || []).forEach((row) => {
		if (row.line_type === "Sub" && row.parent_no === parent_no) {
			count += 1;
		}
	});
	return letters[count] || String(count + 1);
}

function import_boq_lines_from_estimation(frm, estimation_name) {
	frappe.call({
		method: "construction_management.api.quotation_boq.import_boq_lines_from_estimation",
		args: { estimation_name },
		freeze: true,
		callback(r) {
			const lines = r.message || [];
			if (!lines.length) {
				frappe.msgprint(__("No estimation lines found to import."));
				return;
			}

			const apply = () => {
				frm.clear_table("custom_boq_lines");
				lines.forEach((line) => {
					const row = frm.add_child("custom_boq_lines");
					Object.assign(row, line);
				});
				backfill_boq_numbering(frm);
				frm.refresh_field("custom_boq_lines");
				render_boq_preview(frm);
				frappe.show_alert({
					message: __("Imported {0} BOQ rows from Project Estimation", [lines.length]),
					indicator: "green",
				});
			};

			if ((frm.doc.custom_boq_lines || []).length) {
				frappe.confirm(__("Replace existing BOQ lines with imported rows?"), apply);
			} else {
				apply();
			}
		},
	});
}

function setup_boq_grid(frm) {
	const grid = frm.fields_dict.custom_boq_lines && frm.fields_dict.custom_boq_lines.grid;
	if (!grid) {
		return;
	}

	grid.wrapper.off("grid-row-render.boq").on("grid-row-render.boq", (_e, grid_row) => {
		toggle_boq_row_fields(grid_row);
	});
	grid.wrapper.off("grid-add-row.boq grid-remove-rows.boq").on(
		"grid-add-row.boq grid-remove-rows.boq",
		() => {
			backfill_boq_numbering(frm);
			render_boq_preview(frm);
		}
	);
}

function backfill_boq_numbering(frm) {
	const lines = frm.doc.custom_boq_lines || [];
	let parent_counter = 0;
	const sub_counts = {};
	lines.forEach((row) => {
		if (row.line_type === "Parent") {
			if (!row.parent_no) {
				parent_counter += 1;
				row.parent_no = String(parent_counter);
			} else {
				const n = parseInt(row.parent_no, 10);
				if (!isNaN(n)) {
					parent_counter = Math.max(parent_counter, n);
				}
			}
		} else if (row.line_type === "Sub") {
			if (!row.parent_no) {
				row.parent_no = last_parent_no(frm) || "1";
			}
			if (!row.sub_no) {
				const key = row.parent_no;
				const count = sub_counts[key] || 0;
				row.sub_no = next_sub_letter(count);
				sub_counts[key] = count + 1;
			} else {
				const key = row.parent_no;
				sub_counts[key] = (sub_counts[key] || 0) + 1;
			}
		}
	});
}

function next_sub_letter(count) {
	const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
	return letters[count] || String(count + 1);
}

function render_boq_preview(frm) {
	construction_management.render_boq_preview = render_boq_preview;
	const field = frm.fields_dict.custom_boq_lines;
	if (!field || !field.$wrapper) {
		return;
	}

	let $preview = field.$wrapper.find(".boq-live-preview");
	if (!$preview.length) {
		$preview = $(`
			<div class="boq-live-preview" style="margin-top:14px;">
				<div style="font-weight:600;margin-bottom:8px;">${__("BOQ Table Preview")}</div>
				<div class="boq-live-preview-body border rounded p-2" style="background:#fff;overflow:auto;"></div>
			</div>
		`);
		field.$wrapper.append($preview);
	}

	const lines = (frm.doc.custom_boq_lines || []).map((row) => ({
		idx: row.idx,
		line_type: row.line_type,
		section_title: row.section_title,
		parent_no: row.parent_no,
		sub_no: row.sub_no,
		description: row.description,
		uom: row.uom,
		qty: row.qty,
		rate: row.rate,
		amount: row.amount,
		display_mode: row.display_mode,
		is_fixed_rate: row.is_fixed_rate,
	}));

	if (!lines.length) {
		$preview.find(".boq-live-preview-body").html(
			`<p class="text-muted text-center" style="margin:12px 0;">${__("Add BOQ lines to see the table preview.")}</p>`
		);
		return;
	}

	frappe.call({
		method: "construction_management.api.quotation_boq.preview_boq_html_from_lines",
		args: {
			lines: JSON.stringify(lines),
			company: frm.doc.company,
			include_vat: frm.doc.custom_include_vat,
		},
		callback: (r) => {
			$preview.find(".boq-live-preview-body").html(r.message || "");
		},
	});
}

function toggle_boq_row_fields(grid_row) {
	const line_type = grid_row.doc.line_type || "Parent";
	const display_mode = grid_row.doc.display_mode || "Normal";
	const show_for_sub = line_type === "Sub";
	const show_section = line_type === "Section";
	const show_parent = line_type === "Parent";

	grid_row.toggle_editable("section_title", show_section || show_parent);
	grid_row.toggle_display("section_title", show_section || show_parent);
	grid_row.toggle_editable("parent_no", show_parent || show_for_sub);
	grid_row.toggle_editable("sub_no", show_for_sub);
	grid_row.toggle_editable("uom", show_for_sub);
	grid_row.toggle_editable("qty", show_for_sub);
	const is_manual_amount = cint(grid_row.doc.is_fixed_rate) === 1;
	grid_row.toggle_editable("rate", show_for_sub && display_mode !== "N/A" && !is_manual_amount);
	grid_row.toggle_editable("is_fixed_rate", show_for_sub);
	grid_row.toggle_display("is_fixed_rate", show_for_sub);
	grid_row.toggle_editable("display_mode", show_for_sub);
	grid_row.toggle_display("amount", show_for_sub);
	grid_row.toggle_editable("amount", show_for_sub && display_mode === "Normal" && is_manual_amount);
}

function update_boq_row_amount(frm, cdt, cdn) {
	const row = frappe.get_doc(cdt, cdn);
	if (row.line_type !== "Sub") {
		frappe.model.set_value(cdt, cdn, "amount", 0);
		return;
	}

	const display_mode = row.display_mode || "Normal";
	let amount = 0;
	if (display_mode === "Normal" && !is_manual_amount_line(row)) {
		amount = flt(row.qty) * flt(row.rate);
	} else if (display_mode === "Normal") {
		amount = flt(row.amount);
	}

	frappe.model.set_value(cdt, cdn, "amount", amount);
}

function is_manual_amount_line(row) {
	return cint(row.is_fixed_rate) === 1;
}

function clear_blank_items(frm) {
	const keep = (frm.doc.items || []).filter((row) => row.item_code || row.item_name);
	if (keep.length === (frm.doc.items || []).length) {
		return;
	}
	frm.clear_table("items");
	keep.forEach((row) => {
		const child = frm.add_child("items");
		Object.keys(row).forEach((key) => {
			if (!key.startsWith("__") && !["name", "idx", "parent", "parenttype", "parentfield", "doctype"].includes(key)) {
				child[key] = row[key];
			}
		});
	});
	frm.refresh_field("items");
}

function boq_total(frm) {
	let total = 0;
	(frm.doc.custom_boq_lines || []).forEach((row) => {
		if (row.line_type === "Sub" && (row.display_mode || "Normal") === "Normal") {
			total += is_manual_amount_line(row) ? flt(row.amount) : flt(row.qty) * flt(row.rate);
		}
	});
	return total;
}

function apply_placeholder_row(frm, meta, total) {
	const item_code = (meta && meta.name) || QUOTATION_BOQ_ITEM;
	const item_name = (meta && meta.item_name) || "Quotation BOQ";
	const uom = (meta && meta.stock_uom) || "Nos";
	const description = (meta && meta.description) || "Quotation Bill of Quantities";

	frm.clear_table("items");
	const row = frm.add_child("items");
	row.item_code = item_code;
	row.item_name = item_name;
	row.description = description;
	row.uom = uom;
	row.qty = 1;
	row.rate = total;
	row.amount = total;
	frm.refresh_field("items");
}

function ensure_placeholder_item(frm) {
	clear_blank_items(frm);

	const has_boq = (frm.doc.custom_boq_lines || []).length > 0;
	if (!has_boq) {
		return;
	}

	const total = boq_total(frm);

	// Sync path first so mandatory check never sees empty Item Name / UOM
	apply_placeholder_row(frm, null, total);

	return frappe
		.call({
			method:
				"construction_management.overrides.quotation.ensure_quotation_boq_placeholder_item",
			args: { company: frm.doc.company },
		})
		.then((r) => {
			const item_code = (r && r.message) || QUOTATION_BOQ_ITEM;
			return frappe.db.get_value("Item", item_code, [
				"name",
				"item_name",
				"stock_uom",
				"description",
			]);
		})
		.then((r) => {
			const meta = (r && r.message) || {};
			apply_placeholder_row(frm, meta, total);
		})
		.catch(() => {
			apply_placeholder_row(frm, null, total);
		});
}

function prefill_header_from_party(frm) {
	const apply = (label) => {
		if (!label) {
			return;
		}
		if (!frm.doc.custom_client_name) {
			frm.set_value("custom_client_name", label);
		}
		// Main Contractor comes from Customer/Lead name when left blank.
		if (!frm.doc.custom_main_contractor) {
			frm.set_value("custom_main_contractor", label);
		}
	};

	if (frm.doc.customer_name) {
		apply(frm.doc.customer_name);
		return;
	}

	if (frm.doc.quotation_to === "Lead" && frm.doc.party_name) {
		frappe.db.get_value("Lead", frm.doc.party_name, "lead_name").then((r) => {
			apply((r && r.message && r.message.lead_name) || frm.doc.party_name);
		});
		return;
	}

	if (frm.doc.quotation_to === "Customer" && frm.doc.party_name) {
		frappe.db.get_value("Customer", frm.doc.party_name, "customer_name").then((r) => {
			apply((r && r.message && r.message.customer_name) || frm.doc.party_name);
		});
		return;
	}

	apply(frm.doc.party_name);
}

function prefill_header_from_project(frm) {
	if (!frm.doc.custom_project) {
		return;
	}

	frappe.db.get_doc("Project", frm.doc.custom_project).then((project) => {
		if (!frm.doc.custom_project_title && project.project_name) {
			frm.set_value("custom_project_title", project.project_name);
		}
		if (project.customer) {
			frappe.db.get_value("Customer", project.customer, "customer_name").then((r) => {
				const label = (r && r.message && r.message.customer_name) || project.customer;
				if (!frm.doc.custom_client_name) {
					frm.set_value("custom_client_name", label);
				}
				if (!frm.doc.custom_main_contractor) {
					frm.set_value("custom_main_contractor", label);
				}
			});
		}
	});
}
