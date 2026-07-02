frappe.ui.form.on("Daily Roster", {
	project(frm) {
		if (!frm.doc.project) {
			frm.set_value("custom_project_short_name", "");
			return;
		}

		frappe.db.get_value(
			"Project",
			frm.doc.project,
			"custom_project_short_name",
			(r) => {
				frm.set_value("custom_project_short_name", r?.custom_project_short_name || "");
			}
		);
	},
});
