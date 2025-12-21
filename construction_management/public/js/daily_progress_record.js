// Copyright (c) 2024, Construction Management
// License: MIT
// Daily Progress Record client-side logic

frappe.ui.form.on('Daily Progress Record', {
	refresh(frm) {
		// Add custom buttons
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__('Fetch All Rates'), function() {
				fetch_all_rates(frm);
			});
		}
	},
	
	project(frm) {
		// Clear BOQ Item when project changes
		frm.set_value('boq_item', '');
		
		// Set filter for BOQ Item based on project
		frm.set_query('boq_item', function() {
			return {
				filters: {
					project: frm.doc.project
				}
			};
		});
	},
	
	boq_item(frm) {
		// Fetch Bill No from BOQ Item
		if (frm.doc.boq_item) {
			frappe.db.get_value('BOQ Item', frm.doc.boq_item, 'parent_bill', (r) => {
				if (r && r.parent_bill) {
					frm.set_value('bill_no', r.parent_bill);
				}
			});
		}
	}
});

// Asset child table events
frappe.ui.form.on('DPR Asset', {
	asset(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.asset && frm.doc.project) {
			// Fetch rate from Project Asset Billing
			frappe.call({
				method: 'construction_management.construction_management.doctype.project_asset_billing.project_asset_billing.get_asset_daily_rate',
				args: {
					project: frm.doc.project,
					asset: row.asset,
					date: frm.doc.date
				},
				callback: function(r) {
					if (r.message) {
						frappe.model.set_value(cdt, cdn, 'rate_per_day', r.message);
						calculate_asset_amount(frm, cdt, cdn);
					}
				}
			});
		}
	},
	
	hours(frm, cdt, cdn) {
		calculate_asset_amount(frm, cdt, cdn);
	},
	
	rate_per_day(frm, cdt, cdn) {
		calculate_asset_amount(frm, cdt, cdn);
	},
	
	assets_remove(frm) {
		calculate_total_asset_cost(frm);
	}
});

function calculate_asset_amount(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	let hours = flt(row.hours) || 8;
	let rate = flt(row.rate_per_day);
	let amount = rate * (hours / 8);
	frappe.model.set_value(cdt, cdn, 'amount', amount);
	calculate_total_asset_cost(frm);
}

function calculate_total_asset_cost(frm) {
	let total = 0;
	(frm.doc.assets || []).forEach(row => {
		total += flt(row.amount);
	});
	frm.set_value('asset_cost', total);
}

// Employee child table events
frappe.ui.form.on('DPR Employee', {
	employee(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.employee) {
			// Fetch rate from Salary Structure Assignment
			frappe.call({
				method: 'construction_management.api.dpr_utils.get_employee_daily_rate',
				args: {
					employee: row.employee
				},
				callback: function(r) {
					if (r.message) {
						frappe.model.set_value(cdt, cdn, 'rate_per_day', r.message);
						calculate_employee_amount(frm, cdt, cdn);
					}
				}
			});
		}
	},
	
	hours(frm, cdt, cdn) {
		calculate_employee_amount(frm, cdt, cdn);
	},
	
	rate_per_day(frm, cdt, cdn) {
		calculate_employee_amount(frm, cdt, cdn);
	},
	
	employees_remove(frm) {
		calculate_total_labour_cost(frm);
	}
});

function calculate_employee_amount(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	let hours = flt(row.hours) || 8;
	let rate = flt(row.rate_per_day);
	let amount = rate * (hours / 8);
	frappe.model.set_value(cdt, cdn, 'amount', amount);
	calculate_total_labour_cost(frm);
}

function calculate_total_labour_cost(frm) {
	let total = 0;
	(frm.doc.employees || []).forEach(row => {
		total += flt(row.amount);
	});
	frm.set_value('labour_cost', total);
}

// Material child table events
frappe.ui.form.on('DPR Material', {
	item_code(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.item_code && row.warehouse) {
			fetch_item_rate(frm, cdt, cdn);
		}
	},
	
	warehouse(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.item_code && row.warehouse) {
			fetch_item_rate(frm, cdt, cdn);
		}
	},
	
	qty(frm, cdt, cdn) {
		calculate_material_amount(frm, cdt, cdn);
	},
	
	rate(frm, cdt, cdn) {
		calculate_material_amount(frm, cdt, cdn);
	},
	
	materials_remove(frm) {
		calculate_total_material_cost(frm);
	}
});

function fetch_item_rate(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	frappe.call({
		method: 'construction_management.api.dpr_utils.get_item_valuation_rate',
		args: {
			item_code: row.item_code,
			warehouse: row.warehouse
		},
		callback: function(r) {
			if (r.message) {
				frappe.model.set_value(cdt, cdn, 'rate', r.message);
				calculate_material_amount(frm, cdt, cdn);
			}
		}
	});
}

function calculate_material_amount(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	let amount = flt(row.qty) * flt(row.rate);
	frappe.model.set_value(cdt, cdn, 'amount', amount);
	calculate_total_material_cost(frm);
}

function calculate_total_material_cost(frm) {
	let total = 0;
	(frm.doc.materials || []).forEach(row => {
		total += flt(row.amount);
	});
	frm.set_value('material_cost', total);
}

// Overhead child table events
frappe.ui.form.on('DPR Overhead', {
	amount(frm, cdt, cdn) {
		calculate_total_overhead_cost(frm);
	},
	
	overheads_remove(frm) {
		calculate_total_overhead_cost(frm);
	}
});

function calculate_total_overhead_cost(frm) {
	let total = 0;
	(frm.doc.overheads || []).forEach(row => {
		total += flt(row.amount);
	});
	frm.set_value('overhead_cost', total);
}

// Expense child table events
frappe.ui.form.on('DPR Expense', {
	amount(frm, cdt, cdn) {
		calculate_total_expense_cost(frm);
	},
	
	expenses_remove(frm) {
		calculate_total_expense_cost(frm);
	}
});

function calculate_total_expense_cost(frm) {
	let total = 0;
	(frm.doc.expenses || []).forEach(row => {
		total += flt(row.amount);
	});
	frm.set_value('expense_cost', total);
}

// Utility function to fetch all rates
function fetch_all_rates(frm) {
	// Fetch asset rates
	(frm.doc.assets || []).forEach((row, idx) => {
		if (row.asset && frm.doc.project) {
			frappe.call({
				method: 'construction_management.construction_management.doctype.project_asset_billing.project_asset_billing.get_asset_daily_rate',
				args: {
					project: frm.doc.project,
					asset: row.asset,
					date: frm.doc.date
				},
				async: false,
				callback: function(r) {
					if (r.message) {
						frappe.model.set_value('DPR Asset', row.name, 'rate_per_day', r.message);
					}
				}
			});
		}
	});
	
	// Fetch employee rates
	(frm.doc.employees || []).forEach((row, idx) => {
		if (row.employee) {
			frappe.call({
				method: 'construction_management.api.dpr_utils.get_employee_daily_rate',
				args: {
					employee: row.employee
				},
				async: false,
				callback: function(r) {
					if (r.message) {
						frappe.model.set_value('DPR Employee', row.name, 'rate_per_day', r.message);
					}
				}
			});
		}
	});
	
	// Fetch material rates
	(frm.doc.materials || []).forEach((row, idx) => {
		if (row.item_code && row.warehouse) {
			frappe.call({
				method: 'construction_management.api.dpr_utils.get_item_valuation_rate',
				args: {
					item_code: row.item_code,
					warehouse: row.warehouse
				},
				async: false,
				callback: function(r) {
					if (r.message) {
						frappe.model.set_value('DPR Material', row.name, 'rate', r.message);
					}
				}
			});
		}
	});
	
	frm.refresh_fields();
	frappe.show_alert({message: __('Rates fetched'), indicator: 'green'});
}
