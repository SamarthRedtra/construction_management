// Adds a minimize toggle to quick entry dialogs without touching core
(function () {
	// Preserve original and wrap
	const original_make_quick_entry = frappe.ui.form.make_quick_entry;

	frappe.ui.form.make_quick_entry = function (...args) {
		const qe = original_make_quick_entry.apply(this, args);

		// qe is a promise (from setup) or a QuickEntryForm instance; normalize to promise
		if (qe && typeof qe.then === "function") {
			return qe.then((instance) => {
				add_minimize_button(instance);
				return instance;
			});
		} else {
			add_minimize_button(qe);
			return qe;
		}
	};

	function add_minimize_button(qe_instance) {
		if (!qe_instance || !qe_instance.$wrapper) return;

		const dialog = qe_instance.$wrapper;
		if (dialog.data("__cm_minimize_bound")) return;
		dialog.data("__cm_minimize_bound", true);

		let header = dialog.find(".modal-header .modal-actions");
		if (!header.length) {
			// Fallback: place beside the close button in header
			header = dialog.find(".modal-header");
		}
		if (!header.length) return;

		// Create minimize button
		const $btn = $(`
			<a class="btn btn-xs btn-default cm-quick-minimize" title="${__("Minimize")}">
				<i class="fa fa-minus"></i>
			</a>
		`);

		let minimized = false;
		let stub;

		$btn.on("click", () => {
			if (!minimized) {
				const title = dialog.find(".modal-title").text() || __("Quick Entry");
				dialog.hide();
				stub = create_stub(title, () => {
					dialog.show();
					stub.remove();
					minimized = false;
				});
				minimized = true;
			} else {
				dialog.show();
				stub && stub.remove();
				minimized = false;
			}
		});

		header.prepend($btn);
	}

	function create_stub(title, restore) {
		const $stub = $(`
			<div class="cm-quick-minimize-stub">
				<span class="cm-quick-minimize-title">${title}</span>
				<a class="btn btn-xs btn-default" title="${__("Restore")}">
					<i class="fa fa-window-restore"></i>
				</a>
			</div>
		`);

		$stub.css({
			position: "fixed",
			right: "16px",
			bottom: "16px",
			zIndex: 1055,
			background: "#fff",
			border: "1px solid #d1d8dd",
			borderRadius: "4px",
			padding: "6px 8px",
			boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
			display: "flex",
			alignItems: "center",
			gap: "8px",
		});

		$stub.find("a").on("click", () => restore());
		$("body").append($stub);
		return $stub;
	}
})();
