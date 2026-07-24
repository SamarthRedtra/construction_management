// Copyright (c) 2026, Construction Management
// License: MIT

frappe.ui.form.on("Project Estimate", {
	setup(frm) {
		frm.set_query("boq_bill", () => {
			return {
				filters: {
					project: frm.doc.project || "",
				},
			};
		});
		frm.set_query("boq_item", () => {
			const filters = {};
			if (frm.doc.boq_bill) {
				filters.parent_bill = frm.doc.boq_bill;
			} else if (frm.doc.project) {
				filters.project = frm.doc.project;
			}
			return { filters };
		});
	},

	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Apply Template"), () => {
				apply_template_to_form(frm);
			});
		}
	},

	project(frm) {
		if (frm.doc.boq_bill) {
			frm.set_value("boq_bill", "");
		}
		if (frm.doc.boq_item) {
			frm.set_value("boq_item", "");
		}
	},

	boq_bill(frm) {
		if (frm.doc.boq_item) {
			frm.set_value("boq_item", "");
		}
	},

	boq_item(frm) {
		if (frm.doc.estimation_template && frm.doc.boq_item) {
			apply_template_to_form(frm);
		} else if (frm.doc.boq_item && (frm.doc.activities || []).length) {
			set_area_from_boq(frm);
		}
	},

	estimation_template(frm) {
		if (frm.doc.estimation_template) {
			apply_template_to_form(frm);
		}
	},
});

frappe.ui.form.on("Project Estimate Activity", {
	est_area(frm, cdt, cdn) {
		recalc_row(frm, cdt, cdn);
	},
	est_qty(frm, cdt, cdn) {
		recalc_row(frm, cdt, cdn);
	},
	unit_price(frm, cdt, cdn) {
		recalc_row(frm, cdt, cdn);
	},
	skilled(frm, cdt, cdn) {
		recalc_row(frm, cdt, cdn);
	},
	unskilled(frm, cdt, cdn) {
		recalc_row(frm, cdt, cdn);
	},
	skilled_rate(frm, cdt, cdn) {
		recalc_row(frm, cdt, cdn);
	},
	unskilled_rate(frm, cdt, cdn) {
		recalc_row(frm, cdt, cdn);
	},
	activities_remove(frm) {
		recalc_header_totals(frm);
	},
});

function recalc_row(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const material_cost = flt(row.est_qty) * flt(row.unit_price);
	const labour_cost =
		flt(row.skilled) * flt(row.skilled_rate) + flt(row.unskilled) * flt(row.unskilled_rate);
	const area = flt(row.est_area);
	const total_cost = material_cost + labour_cost;

	frappe.model.set_value(cdt, cdn, "material_cost", material_cost);
	frappe.model.set_value(cdt, cdn, "labour_cost", labour_cost);
	frappe.model.set_value(cdt, cdn, "labour_cost_per_m2", area ? labour_cost / area : 0);
	frappe.model.set_value(cdt, cdn, "total_cost", total_cost);
	frappe.model.set_value(cdt, cdn, "cost_per_m2", area ? total_cost / area : 0);

	recalc_header_totals(frm);
}

function recalc_header_totals(frm) {
	let total_material = 0;
	let total_labour = 0;
	let primary_area = 0;

	(frm.doc.activities || []).forEach((row) => {
		total_material += flt(row.material_cost);
		total_labour += flt(row.labour_cost);
		if (!primary_area && flt(row.est_area)) {
			primary_area = flt(row.est_area);
		}
	});

	const total = total_material + total_labour;
	frm.set_value("total_material_cost", total_material);
	frm.set_value("total_labour_cost", total_labour);
	frm.set_value("total_estimated_cost", total);
	frm.set_value("cost_per_m2", primary_area ? total / primary_area : 0);
}

function apply_template_to_form(frm) {
	if (!frm.doc.estimation_template) {
		frappe.msgprint(__("Please select an Estimation Template"));
		return;
	}

	frappe.call({
		method: "construction_management.api.project_estimate.apply_estimation_template",
		args: {
			estimation_template: frm.doc.estimation_template,
			boq_item: frm.doc.boq_item,
			project_estimate: frm.doc.name,
		},
		freeze: true,
		freeze_message: __("Loading template..."),
		callback(r) {
			if (!r.message || !r.message.activities) {
				return;
			}
			frm.clear_table("activities");
			r.message.activities.forEach((row) => {
				frm.add_child("activities", row);
			});
			frm.refresh_field("activities");
			recalc_header_totals(frm);
		},
	});
}

function set_area_from_boq(frm) {
	if (!frm.doc.boq_item) {
		return;
	}
	frappe.db.get_value("BOQ Item", frm.doc.boq_item, "total_qty").then((r) => {
		const area = flt(r.message && r.message.total_qty);
		(frm.doc.activities || []).forEach((row) => {
			frappe.model.set_value(row.doctype, row.name, "est_area", area);
			recalc_row(frm, row.doctype, row.name);
		});
	});
}
