(() => {
	const SO_FORMAT = "Sales Order BOQ Progress";
	const SI_FORMAT = "Sales Invoice";

	function selectedFormat(view) {
		return view.selected_format ? view.selected_format() : "";
	}

	function exportExcel(view) {
		const doctype = view.frm && view.frm.doctype;
		const name = view.frm && (view.frm.docname || (view.frm.doc && view.frm.doc.name));
		if (!name) {
			return;
		}
		if (doctype === "Sales Order") {
			frappe.call({
				method:
					"construction_management.api.so_boq_progress_excel.export_sales_order_boq_progress_excel",
				args: { sales_order: name },
				freeze: true,
				freeze_message: __("Exporting Excel..."),
				callback(r) {
					if (r.message) {
						window.open(r.message);
						frappe.show_alert({ message: __("Excel exported"), indicator: "green" });
					}
				},
			});
			return;
		}
		if (doctype === "Sales Invoice") {
			frappe.call({
				method:
					"construction_management.api.so_boq_progress_excel.export_sales_invoice_boq_progress_excel",
				args: { sales_invoice: name },
				freeze: true,
				freeze_message: __("Exporting Excel..."),
				callback(r) {
					if (r.message) {
						window.open(r.message);
						frappe.show_alert({ message: __("Excel exported"), indicator: "green" });
					}
				},
			});
			return;
		}
		frappe.msgprint(__("Excel export is only available for Sales Order and Sales Invoice"));
	}

	function toggleExcelButton(view) {
		if (!view._boq_progress_excel_btn) {
			return;
		}
		const format = selectedFormat(view);
		const show =
			view.frm &&
			((view.frm.doctype === "Sales Order" && format === SO_FORMAT) ||
				(view.frm.doctype === "Sales Invoice" && format === SI_FORMAT));
		view._boq_progress_excel_btn.toggle(show);
	}

	if (!frappe.ui.form.PrintView) {
		return;
	}

	const origSetup = frappe.ui.form.PrintView.prototype.setup_toolbar;
	frappe.ui.form.PrintView.prototype.setup_toolbar = function () {
		origSetup.call(this);
		this._boq_progress_excel_btn = this.page.add_button(__("Excel"), () => exportExcel(this), {
			icon: "file-spreadsheet",
		});
		this._boq_progress_excel_btn.hide();
	};

	const origRefresh = frappe.ui.form.PrintView.prototype.refresh_print_format;
	frappe.ui.form.PrintView.prototype.refresh_print_format = function () {
		const result = origRefresh.call(this);
		toggleExcelButton(this);
		return result;
	};

	const origShow = frappe.ui.form.PrintView.prototype.show;
	frappe.ui.form.PrintView.prototype.show = function (frm) {
		const result = origShow.call(this, frm);
		if (result && typeof result.then === "function") {
			return result.then(() => toggleExcelButton(this));
		}
		toggleExcelButton(this);
		return result;
	};
})();
