/**
 * Project — Approved Materials HTML editor (stores JSON on Project).
 */
frappe.provide("construction_management.project_approved_materials");

construction_management.project_approved_materials.render = function (frm) {
	const wrapper = frm.fields_dict.custom_approved_materials_html?.$wrapper;
	if (!wrapper) {
		return;
	}

	let materials = construction_management.project_approved_materials.parse_data(
		frm.doc.custom_approved_materials_data
	);
	construction_management.project_approved_materials.render_table(wrapper, frm, materials);
};

construction_management.project_approved_materials.parse_data = function (raw) {
	if (!raw) {
		return [];
	}
	try {
		const data = typeof raw === "string" ? JSON.parse(raw) : raw;
		return Array.isArray(data) ? data : [];
	} catch (e) {
		console.error("Approved materials JSON parse error", e);
		return [];
	}
};

construction_management.project_approved_materials.save = function (frm, materials) {
	frm.set_value("custom_approved_materials_data", JSON.stringify(materials || []));
	frm.dirty();
};

construction_management.project_approved_materials.render_table = function (wrapper, frm, materials) {
	const read_only = frm.doc.docstatus !== 0;
	const rows_html = (materials || [])
		.map((row, idx) => construction_management.project_approved_materials.render_row(row, idx, read_only))
		.join("");

	const html = `
		<style>
			.approved-materials-wrap {
				font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
				padding: 10px 12px 200px;
				min-height: 360px;
				background: #fff;
				border: 1px solid #e5e7eb;
				border-radius: 8px;
				margin: 8px 0;
				overflow: visible;
				position: relative;
			}
			.approved-materials-toolbar {
				display: flex;
				justify-content: space-between;
				align-items: center;
				margin-bottom: 10px;
				gap: 8px;
				flex-wrap: wrap;
			}
			.approved-materials-title {
				font-size: 13px;
				font-weight: 700;
				color: #111827;
			}
			.approved-materials-table-wrap {
				overflow: visible !important;
				min-height: 240px;
			}
			.approved-materials-table {
				width: 100%;
				border-collapse: collapse;
				font-size: 12px;
			}
			.approved-materials-table th,
			.approved-materials-table td {
				border: 1px solid #e5e7eb;
				padding: 6px 8px;
				vertical-align: top;
				overflow: visible;
				position: relative;
			}
			.approved-materials-table th {
				background: #f9fafb;
				font-weight: 600;
				color: #374151;
			}
			.approved-materials-table input,
			.approved-materials-table textarea {
				width: 100%;
				border: 1px solid #d1d5db;
				border-radius: 4px;
				padding: 4px 6px;
				font-size: 12px;
				box-sizing: border-box;
			}
			.approved-materials-table textarea {
				min-height: 42px;
				resize: vertical;
			}
			.approved-materials-table .boq-item-link {
				position: relative;
				z-index: 2;
			}
			.approved-materials-wrap .awesomplete {
				position: relative;
				display: block;
				width: 100%;
			}
			.approved-materials-wrap .awesomplete > ul {
				position: absolute;
				top: calc(100% + 2px);
				left: 0;
				right: 0;
				z-index: 2000;
				max-height: 240px;
				overflow-y: auto;
				background: #fff;
				border: 1px solid #d1d5db;
				border-radius: 6px;
				box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
				margin: 0;
				padding: 4px 0;
			}
			.approved-materials-wrap .awesomplete > ul > li {
				padding: 6px 10px;
				font-size: 12px;
				white-space: normal;
				line-height: 1.35;
			}
			.approved-materials-wrap .awesomplete > ul > li:hover,
			.approved-materials-wrap .awesomplete > ul > li[aria-selected="true"] {
				background: #eef2ff;
			}
			.approved-materials-empty {
				color: #6b7280;
				font-size: 12px;
				padding: 8px 0;
				min-height: 120px;
			}
		</style>
		<div class="approved-materials-wrap">
			<div class="approved-materials-toolbar">
				<div class="approved-materials-title">${__("Approved Materials List")}</div>
				${
					read_only
						? ""
						: `<button type="button" class="btn btn-primary btn-xs btn-add-approved-material">
							${__("Add Material")}
						</button>`
				}
			</div>
			${
				(materials || []).length
					? `<div class="approved-materials-table-wrap">
						<table class="approved-materials-table">
							<thead>
								<tr>
									<th style="width:28px;">#</th>
									<th>${__("Material / Item")}</th>
									<th style="width:18%;">${__("Approved Brand / Make")}</th>
									<th style="width:22%;">${__("Specification")}</th>
									<th style="width:10%;">${__("Unit")}</th>
									<th style="width:14%;">${__("BOQ Item")}</th>
									<th style="width:14%;">${__("Remarks")}</th>
									${read_only ? "" : '<th style="width:36px;"></th>'}
								</tr>
							</thead>
							<tbody>${rows_html}</tbody>
						</table>
					</div>`
					: `<div class="approved-materials-empty">${__(
							"No approved materials added yet. Click Add Material to start."
					  )}</div>`
			}
		</div>
	`;

	wrapper.html(html);
	wrapper.css({ overflow: "visible", "min-height": "380px" });
	wrapper.closest(".form-section, .tab-pane, .form-page").css("overflow", "visible");
	construction_management.project_approved_materials.bind_events(wrapper, frm, materials, read_only);
};

construction_management.project_approved_materials.render_row = function (row, idx, read_only) {
	if (read_only) {
		return `<tr>
			<td>${idx + 1}</td>
			<td>${frappe.utils.escape_html(row.material_name || "")}</td>
			<td>${frappe.utils.escape_html(row.brand || "")}</td>
			<td>${frappe.utils.escape_html(row.specification || "")}</td>
			<td>${frappe.utils.escape_html(row.uom || "")}</td>
			<td>${frappe.utils.escape_html(row.boq_item || "")}</td>
			<td>${frappe.utils.escape_html(row.remarks || "")}</td>
		</tr>`;
	}

	return `<tr data-idx="${idx}">
		<td>${idx + 1}</td>
		<td><input type="text" data-field="material_name" value="${frappe.utils.escape_html(
			row.material_name || ""
		)}" placeholder="${__("e.g. SBS Membrane")}"></td>
		<td><input type="text" data-field="brand" value="${frappe.utils.escape_html(
			row.brand || ""
		)}" placeholder="${__("e.g. Awazel or Equivalent")}"></td>
		<td><textarea data-field="specification" placeholder="${__(
			"Technical spec / approval reference"
		)}">${frappe.utils.escape_html(row.specification || "")}</textarea></td>
		<td><input type="text" data-field="uom" value="${frappe.utils.escape_html(row.uom || "")}" placeholder="m2"></td>
		<td><input type="text" data-field="boq_item" class="boq-item-link" value="${frappe.utils.escape_html(
			row.boq_item || ""
		)}" placeholder="${__("BOQ Item")}"></td>
		<td><input type="text" data-field="remarks" value="${frappe.utils.escape_html(row.remarks || "")}"></td>
		<td><button type="button" class="btn btn-xs btn-danger btn-remove-approved-material" data-idx="${idx}">✕</button></td>
	</tr>`;
};

construction_management.project_approved_materials.collect_rows = function (wrapper) {
	const materials = [];
	wrapper.find(".approved-materials-table tbody tr").each(function () {
		const $row = $(this);
		materials.push({
			material_name: $row.find('[data-field="material_name"]').val() || "",
			brand: $row.find('[data-field="brand"]').val() || "",
			specification: $row.find('[data-field="specification"]').val() || "",
			uom: $row.find('[data-field="uom"]').val() || "",
			boq_item: $row.find('[data-field="boq_item"]').val() || "",
			remarks: $row.find('[data-field="remarks"]').val() || "",
		});
	});
	return materials.filter((row) =>
		Object.values(row).some((value) => (value || "").toString().trim())
	);
};

construction_management.project_approved_materials.bind_events = function (wrapper, frm, materials, read_only) {
	if (read_only) {
		return;
	}

	const persist = () => {
		const updated = construction_management.project_approved_materials.collect_rows(wrapper);
		construction_management.project_approved_materials.save(frm, updated);
	};

	wrapper.find(".btn-add-approved-material").on("click", () => {
		const updated = construction_management.project_approved_materials.collect_rows(wrapper);
		updated.push({
			material_name: "",
			brand: "",
			specification: "",
			uom: "",
			boq_item: "",
			remarks: "",
		});
		construction_management.project_approved_materials.render_table(wrapper, frm, updated);
	});

	wrapper.on("click", ".btn-remove-approved-material", function () {
		const idx = parseInt($(this).attr("data-idx"), 10);
		const updated = construction_management.project_approved_materials.collect_rows(wrapper);
		updated.splice(idx, 1);
		construction_management.project_approved_materials.save(frm, updated);
		construction_management.project_approved_materials.render_table(wrapper, frm, updated);
	});

	wrapper.on("change blur", "input, textarea", function () {
		persist();
	});

	wrapper.on("focus", ".boq-item-link", function () {
		const input = this;
		if (input._boq_awesomplete) {
			return;
		}
		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "BOQ Item",
				filters: { project: frm.doc.name },
				fields: ["name", "item_code", "description"],
				limit_page_length: 0,
			},
			callback(r) {
				const items = (r.message || []).map((item) => ({
					label: `${item.name} — ${item.item_code || ""} ${item.description || ""}`.trim(),
					value: item.name,
				}));
				input._boq_awesomplete = new Awesomplete(input, {
					minChars: 0,
					maxItems: 50,
					autoFirst: true,
					list: items,
				});
				input._boq_awesomplete.open();
			},
		});
	});
};
