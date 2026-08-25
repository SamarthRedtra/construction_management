(() => {
	const FORMAT = "Sales Order BOQ Progress";

	function selectedFormat(view) {
		return view.selected_format ? view.selected_format() : "";
	}

	function exportExcel(view) {
		const doctype = view.frm && view.frm.doctype;
		const name = view.frm && (view.frm.docname || (view.frm.doc && view.frm.doc.name));
		if (doctype !== "Sales Order" || !name) {
			frappe.msgprint(__("Excel export is only available for Sales Order"));
			return;
		}
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
	}

	function toggleExcelButton(view) {
		if (!view._boq_progress_excel_btn) {
			return;
		}
		const show =
			view.frm &&
			view.frm.doctype === "Sales Order" &&
			selectedFormat(view) === FORMAT;
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
