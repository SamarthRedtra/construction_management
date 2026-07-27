// Copyright (c) 2026, Construction Management and contributors
// For license information, please see license.txt

frappe.ui.form.on("BOQ Settings", {
	onload: function (frm) {
		set_account_queries(frm);
	},
	refresh: function (frm) {
		set_account_queries(frm);
	},
	company: function (frm) {
		set_account_queries(frm);
	}
});

function set_account_queries(frm) {
	if (!frm.doc.company) return;

	// List of account link fields to filter by company
	const account_fields = [
		"retention_account",
		"advance_account",
		"default_warehouse",
		"asset_labor_cost_account",
		"asset_cost_account",
		"expenses_account",
		"overhead_account",
		"salary_labor_account",
		"asset_cost_credit",
		"varience_account_debit",
		"purchase_retention_account",
		"purchase_advance_account",
		"sales_person_commission_account",
		"sales_commission_payable_account",
		"so_unearned_revenue_credit_account",
		"so_unearned_revenue_debit_account",
		"sales_partner_commission_account"
	];

	account_fields.forEach((fieldname) => {
		frm.set_query(fieldname, function () {
			return {
				filters: {
					company: frm.doc.company,
					is_group: 0
				}
			};
		});
	});
}
