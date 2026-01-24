
// Copyright (c) 2026, Construction Management
// License: MIT

frappe.ui.form.on("Project Sites", {
	refresh(frm) {
		// Setup cascading filters
		setup_filters(frm);
	},

	onload(frm) {
		// Setup cascading filters
		setup_filters(frm);
	},

	project(frm) {
		// Clear bill_no and boq_item when project changes
		if (frm.doc.bill_no) {
			frm.set_value("bill_no", "");
		}
		if (frm.doc.boq_item) {
			frm.set_value("boq_item", "");
		}
	},

	bill_no(frm) {
		// Clear boq_item when bill_no changes
		if (frm.doc.boq_item) {
			frm.set_value("boq_item", "");
		}
	}
});

function setup_filters(frm) {
	// Filter bill_no by project
	frm.set_query("bill_no", function () {
		if (frm.doc.project) {
			return {
				filters: {
					project: frm.doc.project
				}
			};
		}
		return {};
	});

	// Filter boq_item by bill_no
	frm.set_query("boq_item", function () {
		if (frm.doc.bill_no) {
			return {
				filters: {
					parent_bill: frm.doc.bill_no
				}
			};
		} else if (frm.doc.project) {
			return {
				filters: {
					project: frm.doc.project
				}
			};
		}
		return {};
	});
}
