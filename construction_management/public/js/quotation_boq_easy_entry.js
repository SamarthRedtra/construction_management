/**
 * Easy BOQ entry for Quotation — paste from Excel or quick parent + sub rows.
 */
frappe.provide("construction_management.quotation_boq_easy_entry");

construction_management.quotation_boq_easy_entry.PASTE_EXAMPLE = `# THERMAL AND MOISTURE PROTECTION
1\t1000 gauge polythene sheets; all in accordance with drawings
A\tTo Raft Slab\tm2\t2259\t-
B\tBelow Grade Slab\tm2\t1800\t-
2\t2 layers of 4mm SBS waterproofing membrane
A\tHorizontally to Raft Slab\tm2\t2184\t62.00
B\tVertically to Retaining Wall\tm2\t450\t75.00`;

construction_management.quotation_boq_easy_entry.QUICK_EXAMPLE = {
	section_title: "THERMAL AND MOISTURE PROTECTION",
	parent_description:
		"1000 gauge polythene sheets; all in accordance with the drawings and specification",
	sub_rows: [
		{
			description: "To Raft Slab",
			uom: "m2",
			qty: 2259,
			rate: 0,
			display_mode: "N/A",
		},
		{
			description: "Below Grade Slab",
			uom: "m2",
			qty: 1800,
			rate: 0,
			display_mode: "N/A",
		},
		{
			description: "Horizontally to Raft Slab (SBS membrane)",
			uom: "m2",
			qty: 2184,
			rate: 62,
			display_mode: "Normal",
		},
	],
};

construction_management.quotation_boq_easy_entry.setup = function (frm) {
	if (frm.doc.docstatus !== 0) {
		return;
	}

	frm.add_custom_button(
		__("Easy BOQ Entry"),
		() => construction_management.quotation_boq_easy_entry.open_dialog(frm),
		__("BOQ")
	);

	frm.add_custom_button(
		__("Add Sub to Last Parent"),
		() => construction_management.quotation_boq_easy_entry.add_sub_to_last_parent(frm),
		__("BOQ")
	);

	construction_management.quotation_boq_easy_entry.render_total(frm);
};

construction_management.quotation_boq_easy_entry.render_total = function (frm) {
	const wrapper = frm.fields_dict.custom_boq_lines && frm.fields_dict.custom_boq_lines.wrapper;
	if (!wrapper) {
		return;
	}

	let total = 0;
	(frm.doc.custom_boq_lines || []).forEach((row) => {
		if (row.line_type === "Sub" && (row.display_mode || "Normal") === "Normal") {
			total += is_manual_amount_line(row) ? flt(row.amount) : flt(row.qty) * flt(row.rate);
		}
	});

	wrapper.find(".quotation-boq-total-banner").remove();
	if (!total) {
		return;
	}

	const html = `<div class="quotation-boq-total-banner text-muted small" style="margin:6px 0 10px;">
		${__("BOQ Total (excl. VAT):")} <strong>${format_currency(total, frm.doc.currency)}</strong>
	</div>`;
	wrapper.prepend(html);
};

construction_management.quotation_boq_easy_entry.add_sub_to_last_parent = function (frm) {
	const parent_no = construction_management.quotation_boq_easy_entry.get_last_parent_no(frm);
	if (!parent_no) {
		frappe.msgprint(__("Add a Parent row first."));
		return;
	}

	const row = frm.add_child("custom_boq_lines", {
		line_type: "Sub",
		parent_no,
		sub_no: construction_management.quotation_boq_easy_entry.get_next_sub_no(frm, parent_no),
		display_mode: "Normal",
		is_fixed_rate: 0,
		uom: "Nos",
	});
	frm.refresh_field("custom_boq_lines");
	if (construction_management.render_boq_preview) {
		construction_management.render_boq_preview(frm);
	}
	frm.fields_dict.custom_boq_lines.grid.open_row(row.idx);
};

construction_management.quotation_boq_easy_entry.get_last_parent_no = function (frm) {
	const lines = frm.doc.custom_boq_lines || [];
	for (let i = lines.length - 1; i >= 0; i--) {
		if (lines[i].line_type === "Parent" && lines[i].parent_no) {
			return lines[i].parent_no;
		}
	}
	return "";
};

function is_manual_amount_line(row) {
	return cint(row.is_fixed_rate) === 1;
}

construction_management.quotation_boq_easy_entry.get_next_parent_no = function (frm) {
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
};

construction_management.quotation_boq_easy_entry.get_next_sub_no = function (frm, parent_no) {
	const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
	let count = 0;
	(frm.doc.custom_boq_lines || []).forEach((row) => {
		if (row.line_type === "Sub" && row.parent_no === parent_no) {
			count += 1;
		}
	});
	return letters[count] || String(count + 1);
};

construction_management.quotation_boq_easy_entry.open_dialog = function (frm) {
	if (!frm.doc.company) {
		frappe.msgprint(__("Please set Company first."));
		return;
	}

	const d = new frappe.ui.Dialog({
		title: __("Easy BOQ Entry"),
		size: "extra-large",
		fields: [
			{
				fieldtype: "Select",
				fieldname: "entry_mode",
				label: __("Entry Mode"),
				options: "Quick Add Parent + Subs\nPaste from Excel\nImport Excel File",
				default: "Quick Add Parent + Subs",
			},
			{
				fieldtype: "Section Break",
				fieldname: "quick_section",
				label: __("Quick Add"),
				depends_on: 'eval:doc.entry_mode == "Quick Add Parent + Subs"',
			},
			{
				fieldtype: "Data",
				fieldname: "section_title",
				label: __("Section Title"),
				description: __("Optional. Used as BOQ section header."),
				depends_on: 'eval:doc.entry_mode == "Quick Add Parent + Subs"',
			},
			{
				fieldtype: "Small Text",
				fieldname: "parent_description",
				label: __("Parent Description"),
				mandatory_depends_on: 'eval:doc.entry_mode == "Quick Add Parent + Subs"',
				depends_on: 'eval:doc.entry_mode == "Quick Add Parent + Subs"',
			},
			{
				fieldtype: "HTML",
				fieldname: "quick_example_hint",
				depends_on: 'eval:doc.entry_mode == "Quick Add Parent + Subs"',
				options: `<div class="text-muted small" style="margin-bottom:6px;">
					<strong>${__("Example:")}</strong>
					${__("Section")} = <em>THERMAL AND MOISTURE PROTECTION</em>,
					${__("Parent")} = <em>1000 gauge polythene sheets...</em>,
					${__("Subs")} = To Raft Slab (m2, 2259, N/A) + Below Grade Slab (m2, 1800, N/A).
					${__("Click Load Example to fill this form.")}
				</div>`,
			},
			{
				fieldtype: "Table",
				fieldname: "sub_rows",
				label: __("Sub Items"),
				depends_on: 'eval:doc.entry_mode == "Quick Add Parent + Subs"',
				fields: [
					{
						fieldtype: "Small Text",
						fieldname: "description",
						label: __("Description"),
						in_list_view: 1,
						reqd: 1,
					},
					{
						fieldtype: "Link",
						fieldname: "uom",
						label: __("Unit"),
						options: "UOM",
						in_list_view: 1,
						default: "Nos",
					},
					{
						fieldtype: "Float",
						fieldname: "qty",
						label: __("Qty"),
						in_list_view: 1,
					},
					{
						fieldtype: "Currency",
						fieldname: "rate",
						label: __("Rate"),
						in_list_view: 1,
					},
					{
						fieldtype: "Select",
						fieldname: "display_mode",
						label: __("Display"),
						options: "Normal\nN/A\nRate Only",
						default: "Normal",
						in_list_view: 1,
					},
				],
			},
			{
				fieldtype: "Section Break",
				fieldname: "paste_section",
				label: __("Paste from Excel"),
				depends_on: 'eval:doc.entry_mode == "Paste from Excel"',
			},
			{
				fieldtype: "HTML",
				fieldname: "paste_help",
				depends_on: 'eval:doc.entry_mode == "Paste from Excel"',
				options: `<div class="text-muted small" style="margin-bottom:8px;">
					<p>${__(
						"Copy rows from Excel and paste below. Supported patterns:"
					)}</p>
					<ul style="margin-left:18px;">
						<li><code># SECTION NAME</code> = Section header</li>
						<li><code>1</code> + description = Parent row</li>
						<li><code>A</code> + description + unit + qty + rate = Sub row</li>
					</ul>
					<p><strong>${__("Example (copy this):")}</strong></p>
					<pre style="background:#f6f6f6;border:1px solid #d1d8dd;padding:8px;font-size:11px;white-space:pre-wrap;margin:6px 0;"># THERMAL AND MOISTURE PROTECTION
1\t1000 gauge polythene sheets
A\tTo Raft Slab\tm2\t2259\t-
B\tBelow Grade Slab\tm2\t1800\t-
2\t2 layers of 4mm SBS waterproofing membrane
A\tHorizontally to Raft Slab\tm2\t2184\t62.00</pre>
					<p class="text-muted">${__(
						"Tip: use Load Example, or switch to Import Excel File to upload a .xlsx template."
					)}</p>
				</div>`,
			},
			{
				fieldtype: "Code",
				fieldname: "paste_text",
				label: __("Paste Data"),
				options: "Text",
				mandatory_depends_on: 'eval:doc.entry_mode == "Paste from Excel"',
				depends_on: 'eval:doc.entry_mode == "Paste from Excel"',
			},
			{
				fieldtype: "Section Break",
				fieldname: "excel_section",
				label: __("Import Excel File"),
				depends_on: 'eval:doc.entry_mode == "Import Excel File"',
			},
			{
				fieldtype: "HTML",
				fieldname: "excel_help",
				depends_on: 'eval:doc.entry_mode == "Import Excel File"',
				options: `<div class="text-muted small" style="margin-bottom:8px;">
					<p>${__(
						"Upload an Excel file (.xlsx) with these columns:"
					)}</p>
					<table class="table table-bordered table-condensed" style="font-size:11px;background:#fff;">
						<thead><tr><th>${__("Column")}</th><th>${__("Required")}</th><th>${__("Values")}</th></tr></thead>
						<tbody>
							<tr><td>Type</td><td>${__("Yes")}</td><td>Section / Parent / Sub</td></tr>
							<tr><td>Section</td><td>${__("No")}</td><td>${__("Optional section title (2-level BOQ)")}</td></tr>
							<tr><td>No</td><td>${__("No")}</td><td>${__("Parent: 1,2... | Sub: A,B...")}</td></tr>
							<tr><td>Description</td><td>${__("Yes")}</td><td>${__("Work description")}</td></tr>
							<tr><td>Unit</td><td>${__("No")}</td><td>m2, nos, etc.</td></tr>
							<tr><td>Qty</td><td>${__("No")}</td><td>${__("Quantity")}</td></tr>
							<tr><td>Rate</td><td>${__("No")}</td><td>${__("Unit rate")}</td></tr>
							<tr><td>Display</td><td>${__("No")}</td><td>Normal / N/A / Rate Only</td></tr>
						</tbody>
					</table>
					<button type="button" class="btn btn-xs btn-default btn-download-boq-excel-example" style="margin-top:6px;">
						${__("Download Example Excel")}
					</button>
				</div>`,
			},
			{
				fieldtype: "Attach",
				fieldname: "excel_file",
				label: __("Select Excel File"),
				mandatory_depends_on: 'eval:doc.entry_mode == "Import Excel File"',
				depends_on: 'eval:doc.entry_mode == "Import Excel File"',
				options: {
					restrictions: {
						allowed_file_types: [".xlsx", ".xls"],
					},
				},
			},
		],
		primary_action_label: __("Add to BOQ"),
		primary_action(values) {
			construction_management.quotation_boq_easy_entry.apply_dialog(frm, d, values);
		},
		secondary_action_label: __("Load Example"),
		secondary_action() {
			construction_management.quotation_boq_easy_entry.load_example(d, frm);
		},
	});

	d.show();

	d.$wrapper.on("click", ".btn-download-boq-excel-example", () => {
		construction_management.quotation_boq_easy_entry.download_example_excel(frm);
	});

	d.fields_dict.entry_mode.$input.on("change", () => {
		construction_management.quotation_boq_easy_entry.on_entry_mode_change(d);
	});

	construction_management.quotation_boq_easy_entry.on_entry_mode_change(d);
};

construction_management.quotation_boq_easy_entry.on_entry_mode_change = function (dialog) {
	const mode = dialog.get_value("entry_mode");
	if (mode !== "Quick Add Parent + Subs") {
		return;
	}
	const grid = dialog.fields_dict.sub_rows?.grid;
	if (!grid || (dialog.get_value("sub_rows") || []).length) {
		return;
	}
	for (let i = 0; i < 3; i++) {
		const row = grid.add_new_row();
		row.uom = "Nos";
		row.display_mode = "Normal";
	}
	grid.refresh();
};

construction_management.quotation_boq_easy_entry.load_example = function (dialog, frm) {
	const mode = dialog.get_value("entry_mode");

	if (mode === "Import Excel File") {
		construction_management.quotation_boq_easy_entry.download_example_excel(frm);
		return;
	}

	if (mode === "Paste from Excel") {
		dialog.set_value("paste_text", construction_management.quotation_boq_easy_entry.PASTE_EXAMPLE);
		frappe.show_alert({ message: __("Example pasted — edit and click Add to BOQ"), indicator: "blue" });
		return;
	}

	const example = construction_management.quotation_boq_easy_entry.QUICK_EXAMPLE;
	dialog.set_value("section_title", example.section_title);
	dialog.set_value("parent_description", example.parent_description);

	const grid = dialog.fields_dict.sub_rows.grid;
	grid.df.data = [];
	example.sub_rows.forEach((row) => {
		const child = grid.add_new_row();
		Object.assign(child, row);
	});
	grid.refresh();
	frappe.show_alert({ message: __("Example loaded — edit and click Add to BOQ"), indicator: "blue" });
};

construction_management.quotation_boq_easy_entry.download_example_excel = function (frm) {
	frappe.call({
		method: "construction_management.api.quotation_boq.download_quotation_boq_example_template",
		args: { company: frm.doc.company },
		freeze: true,
		callback(r) {
			if (r.message) {
				window.open(r.message);
				frappe.show_alert({
					message: __("Example Excel downloaded — fill it and upload here"),
					indicator: "blue",
				});
			}
		},
	});
};

construction_management.quotation_boq_easy_entry.apply_dialog = function (frm, dialog, values) {
	const mode = values.entry_mode;

	const finish_import = (lines) => {
		if (!lines.length) {
			frappe.msgprint(__("No BOQ rows could be parsed."));
			return;
		}
		construction_management.quotation_boq_easy_entry.append_lines(frm, lines, dialog);
	};

	if (mode === "Import Excel File") {
		if (!values.excel_file) {
			frappe.msgprint(__("Select an Excel file first, or download the example template."));
			return;
		}

		dialog.disable_primary_action();
		frappe.call({
			method: "construction_management.api.quotation_boq.import_boq_lines_from_excel",
			args: {
				file_url: values.excel_file,
				company: frm.doc.company,
			},
			freeze: true,
			callback(r) {
				dialog.enable_primary_action();
				frappe.dom.unfreeze();
				finish_import(r.message || []);
			},
			error() {
				dialog.enable_primary_action();
				frappe.dom.unfreeze();
			},
		});
		return;
	}

	if (mode === "Paste from Excel") {
		if (!(values.paste_text || "").trim()) {
			frappe.msgprint(__("Paste Excel data first."));
			return;
		}

		dialog.disable_primary_action();
		frappe.call({
			method: "construction_management.api.quotation_boq.parse_pasted_boq_text",
			args: {
				text: values.paste_text,
				company: frm.doc.company,
			},
			freeze: true,
			callback(r) {
				dialog.enable_primary_action();
				frappe.dom.unfreeze();
				finish_import(r.message || []);
			},
			error() {
				dialog.enable_primary_action();
				frappe.dom.unfreeze();
			},
		});
		return;
	}

	if (!(values.parent_description || "").trim()) {
		frappe.msgprint(__("Parent Description is required."));
		return;
	}

	dialog.disable_primary_action();
	frappe.call({
		method: "construction_management.api.quotation_boq.build_quick_boq_lines",
		args: {
			company: frm.doc.company,
			section_title: values.section_title,
			parent_description: values.parent_description,
			parent_no: String(construction_management.quotation_boq_easy_entry.get_next_parent_no(frm)),
			sub_rows: values.sub_rows || [],
		},
		freeze: true,
		callback(r) {
			dialog.enable_primary_action();
			frappe.dom.unfreeze();
			finish_import(r.message || []);
		},
		error() {
			dialog.enable_primary_action();
			frappe.dom.unfreeze();
		},
	});
};

construction_management.quotation_boq_easy_entry.append_lines = function (frm, lines, dialog) {
	const close_dialog = () => {
		frappe.dom.unfreeze();
		if (!dialog) {
			return;
		}
		// Defer hide so frappe.confirm modal can dismiss first.
		setTimeout(() => {
			if (dialog.$wrapper && dialog.$wrapper.is(":visible")) {
				dialog.hide();
			}
		}, 0);
	};

	const apply = () => {
		lines.forEach((line) => {
			const row = frm.add_child("custom_boq_lines");
			Object.assign(row, line);
		});
		frm.refresh_field("custom_boq_lines");
		construction_management.quotation_boq_easy_entry.render_total(frm);
		if (construction_management.render_boq_preview) {
			construction_management.render_boq_preview(frm);
		}
		close_dialog();
		frappe.show_alert({
			message: __("Added {0} BOQ rows", [lines.length]),
			indicator: "green",
		});
	};

	if ((frm.doc.custom_boq_lines || []).length) {
		frappe.confirm(
			__("Append {0} rows to existing BOQ lines?", [lines.length]),
			() => apply(),
			() => frappe.dom.unfreeze()
		);
		return;
	}

	apply();
};
