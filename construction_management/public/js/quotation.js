/**
 * BOQ-style Quotation — simple child-table grid (like BOQ Management)
 */

const QUOTATION_BOQ_ITEM = "QUOTATION-BOQ";

frappe.ui.form.on("Quotation", {
	onload(frm) {
		clear_blank_items(frm);
	},

	refresh(frm) {
		clear_blank_items(frm);
		setup_boq_buttons(frm);
		setup_boq_grid(frm);
		setup_print_hint(frm);
	},

	validate(frm) {
		// Runs before Frappe check_mandatory — fill Items so Item Name / UOM pass
		return ensure_placeholder_item(frm);
	},

	custom_project(frm) {
		prefill_header_from_project(frm);
	},

	party_name(frm) {
		if (!frm.doc.custom_client_name && frm.doc.customer_name) {
			frm.set_value("custom_client_name", frm.doc.customer_name);
		}
	},

	tc_name(frm) {
		if (!frm.doc.tc_name) {
			return;
		}
		frappe.db.get_value("Terms and Conditions", frm.doc.tc_name, "terms").then((r) => {
			if (r && r.message && r.message.terms) {
				frm.set_value("terms", r.message.terms);
			}
		});
	},
});

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

frappe.ui.form.on("Quotation BOQ Line", {
	line_type(frm, cdt, cdn) {
		update_boq_row_amount(frm, cdt, cdn);
	},

	display_mode(frm, cdt, cdn) {
		update_boq_row_amount(frm, cdt, cdn);
	},

	qty(frm, cdt, cdn) {
		update_boq_row_amount(frm, cdt, cdn);
	},

	rate(frm, cdt, cdn) {
		update_boq_row_amount(frm, cdt, cdn);
	},
});

function setup_boq_buttons(frm) {
	if (frm.doc.docstatus !== 0) {
		return;
	}

	frm.add_custom_button(__("Add Section"), () => add_boq_row(frm, "Section"), __("BOQ"));
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
	}

	frm.add_child("custom_boq_lines", values);
	frm.refresh_field("custom_boq_lines");
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
				frm.refresh_field("custom_boq_lines");
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
}

function toggle_boq_row_fields(grid_row) {
	const line_type = grid_row.doc.line_type || "Parent";
	const display_mode = grid_row.doc.display_mode || "Normal";
	const show_for_sub = line_type === "Sub";
	const show_section = line_type === "Section";
	const show_parent = line_type === "Parent";

	grid_row.toggle_editable("section_title", show_section || show_parent);
	grid_row.toggle_editable("parent_no", show_parent || show_for_sub);
	grid_row.toggle_editable("sub_no", show_for_sub);
	grid_row.toggle_editable("uom", show_for_sub);
	grid_row.toggle_editable("qty", show_for_sub);
	grid_row.toggle_editable("rate", show_for_sub && display_mode !== "N/A");
	grid_row.toggle_editable("display_mode", show_for_sub);
	grid_row.toggle_display("amount", show_for_sub);
}

function update_boq_row_amount(frm, cdt, cdn) {
	const row = frappe.get_doc(cdt, cdn);
	if (row.line_type !== "Sub") {
		frappe.model.set_value(cdt, cdn, "amount", 0);
		return;
	}

	const display_mode = row.display_mode || "Normal";
	let amount = 0;
	if (display_mode === "Normal") {
		amount = flt(row.qty) * flt(row.rate);
	}

	frappe.model.set_value(cdt, cdn, "amount", amount);
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
			total += flt(row.qty) * flt(row.rate);
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

	return frappe.db
		.get_value("Item", QUOTATION_BOQ_ITEM, ["name", "item_name", "stock_uom", "description"])
		.then((r) => {
			const meta = (r && r.message) || {};
			if (meta.name || meta.item_name) {
				apply_placeholder_row(frm, meta, total);
			}
		})
		.catch(() => {
			/* server will create QUOTATION-BOQ if missing */
		});
}

function prefill_header_from_project(frm) {
	if (!frm.doc.custom_project) {
		return;
	}

	frappe.db.get_doc("Project", frm.doc.custom_project).then((project) => {
		if (!frm.doc.custom_project_title && project.project_name) {
			frm.set_value("custom_project_title", project.project_name);
		}
		if (!frm.doc.custom_client_name && project.customer) {
			frappe.db.get_value("Customer", project.customer, "customer_name").then((r) => {
				if (r && r.message) {
					frm.set_value("custom_client_name", r.message.customer_name || project.customer);
				}
			});
		}
	});
}
