// Copyright (c) 2024, Construction Management
// License: MIT

frappe.provide("construction_management.deduction_summary");

construction_management.deduction_summary.RETENTION_ITEM = "RETENTION-DEDUCTION";
construction_management.deduction_summary.ADVANCE_ITEM = "ADVANCE-DEDUCTION";

construction_management.deduction_summary.get_totals = function (items) {
	const retention_rows = (items || []).filter(
		(row) => row.item_code === construction_management.deduction_summary.RETENTION_ITEM
	);
	const advance_rows = (items || []).filter(
		(row) => row.item_code === construction_management.deduction_summary.ADVANCE_ITEM
	);

	const sum_amount = (rows) =>
		rows.reduce((total, row) => total + Math.abs(flt(row.amount || row.rate)), 0);

	return {
		retention_count: retention_rows.length,
		retention_total: sum_amount(retention_rows),
		advance_count: advance_rows.length,
		advance_total: sum_amount(advance_rows),
	};
};

construction_management.deduction_summary.render = function (frm) {
	if (!frm.fields_dict.items) {
		return;
	}

	const totals = construction_management.deduction_summary.get_totals(frm.doc.items);
	const $wrapper = $(frm.fields_dict.items.wrapper);
	$wrapper.find(".cm-deduction-summary").remove();

	if (!totals.retention_count && !totals.advance_count) {
		return;
	}

	const currency = frm.doc.currency || frappe.boot.sysdefaults.currency;
	const fmt = (value) => format_currency(value, currency, 2);
	const combined_total = totals.retention_total + totals.advance_total;
	const combined_count = totals.retention_count + totals.advance_count;

	const html = `
		<div class="cm-deduction-summary" style="margin:0 0 10px 0;padding:10px 12px;border:1px solid #dbeafe;border-radius:6px;background:#f8fbff;font-size:12px;">
			<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:8px;">
				<strong style="color:#1e3a8a;">${__("Deduction Summary")}</strong>
				<span style="color:#475569;">
					${__("{0} deduction line(s)", [combined_count])}
					&nbsp;|&nbsp;
					${__("Total")}: <b>${fmt(combined_total)}</b>
				</span>
			</div>
			<div style="display:flex;gap:16px;flex-wrap:wrap;">
				<span style="color:#92400e;">
					${__("Retention")}:
					<b>${totals.retention_count}</b> ${__("line(s)")}
					&nbsp;|&nbsp;
					${__("Total")}: <b>${fmt(totals.retention_total)}</b>
				</span>
				<span style="color:#1d4ed8;">
					${__("Advance")}:
					<b>${totals.advance_count}</b> ${__("line(s)")}
					&nbsp;|&nbsp;
					${__("Total")}: <b>${fmt(totals.advance_total)}</b>
				</span>
			</div>
		</div>`;

	$wrapper.prepend(html);
};
