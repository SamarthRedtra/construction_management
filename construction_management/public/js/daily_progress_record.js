// Copyright (c) 2024, Construction Management
// License: MIT
// Daily Progress Record client-side logic

frappe.ui.form.on('Daily Progress Record', {
	refresh(frm) {
		// Add custom buttons
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__('Fetch All Rates'), function () {
				fetch_all_rates(frm);
			});
		}

		// Set warehouse filter by project for materials (Site field)
		if (frm.doc.project) {
			frm.set_query('warehouse', 'materials', function () {
				return {
					filters: {
						custom_project: frm.doc.project
					}
				};
			});

			// Asset filter: only assets with Project Asset Billing for this project
			frm.set_query('asset', 'assets', function () {
				return {
					query: 'construction_management.api.asset_billing.get_assets_with_billing',
					filters: { project: frm.doc.project }
				};
			});

			// Set item_code query to filter by warehouse stock
			frm.set_query('item_code', 'materials', function (doc, cdt, cdn) {
				let row = locals[cdt][cdn];
				if (!row.warehouse) {
					frappe.show_alert({
						message: __('Please select a Site/Warehouse first'),
						indicator: 'orange'
					});
					return {
						filters: {
							name: ['in', []]  // Return empty to prevent selection
						}
					};
				}
				return {
					query: 'construction_management.api.dpr_utils.get_warehouse_items_query',
					filters: {
						warehouse: row.warehouse
					}
				};
			});
		}
		// Filter employees by Active status
		frm.set_query('employee', 'employees', function () {
			return {
				filters: {
					status: 'Active'
				}
			};
		});
		// Render Connections Dashboard and Accounting Links
		render_connections(frm);
		render_accounting_links(frm);

	},

	project(frm) {
		// Clear BOQ Item when project changes
		frm.set_value('boq_item', '');

		// Set filter for BOQ Item based on project
		frm.set_query('boq_item', function () {
			return {
				filters: {
					project: frm.doc.project
				}
			};
		});

		// Update warehouse filter for materials
		if (frm.doc.project) {
			frm.set_query('warehouse', 'materials', function () {
				return {
					filters: {
						custom_project: frm.doc.project
					}
				};
			});

			// Asset filter: only assets with Project Asset Billing configured for this project
			frm.set_query('asset', 'assets', function () {
				return {
					query: 'construction_management.api.asset_billing.get_assets_with_billing',
					filters: { project: frm.doc.project }
				};
			});

			// Set item_code query to filter by warehouse stock
			frm.set_query('item_code', 'materials', function (doc, cdt, cdn) {
				let row = locals[cdt][cdn];
				if (!row.warehouse) {
					return {
						filters: {
							name: ['in', []]  // Return empty to prevent selection
						}
					};
				}
				return {
					query: 'construction_management.api.dpr_utils.get_warehouse_items_query',
					filters: {
						warehouse: row.warehouse
					}
				};
			});
		}
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
			// Fetch hourly rate from Project Asset Billing
			frappe.call({
				method: 'construction_management.construction_management.doctype.project_asset_billing.project_asset_billing.get_asset_hourly_rate',
				args: {
					project: frm.doc.project,
					asset: row.asset,
					date: frm.doc.date
				},
				callback: function (r) {
					// Update rate even if 0, to reflect current billing config
					let rate = flt(r.message);
					if (rate > 0) {
						frappe.model.set_value(cdt, cdn, 'rate_per_hour', rate);
						frappe.model.set_value(cdt, cdn, 'rate_per_day', rate * 8); // Default 8h day
						frappe.show_alert({
							message: __('Asset rate loaded: {0} per hour', [format_currency(rate)]),
							indicator: 'green'
						});
					} else {
						// Optional: warn user no rate found
						frappe.show_alert({
							message: __('No billing rate found for asset {0} on {1}').format(row.asset, frm.doc.date),
							indicator: 'orange'
						});
						// Reset to 0 if no rate found to avoid stale data? 
						// Or leave it open for manual entry. Choosing to reset for clarity.
						frappe.model.set_value(cdt, cdn, 'rate_per_hour', 0);
						frappe.model.set_value(cdt, cdn, 'rate_per_day', 0);
					}
					calculate_asset_amount(frm, cdt, cdn);
				}
			});
		}
	},

	hours(frm, cdt, cdn) {
		calculate_asset_amount(frm, cdt, cdn);
	},

	rate_per_hour(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		// Update rate_per_day for backward compatibility
		frappe.model.set_value(cdt, cdn, 'rate_per_day', flt(row.rate_per_hour) * 8);
		calculate_asset_amount(frm, cdt, cdn);
	},

	rate_per_day(frm, cdt, cdn) {
		// If user manually updates daily rate, we could back-calc hourly, 
		// but 'rate_per_hour' is the primary driver in new logic.
		// For now, let's keep them synced loosely or just respect the manual entry.
		let row = locals[cdt][cdn];
		if (flt(row.hours) > 0) {
			// Optional: back calculate hourly rate? 
			// frappe.model.set_value(cdt, cdn, 'rate_per_hour', flt(row.rate_per_day) / 8);
		}
		calculate_asset_amount(frm, cdt, cdn);
	},

	assets_remove(frm) {
		calculate_total_asset_cost(frm);
	}
});

function prompt_manual_asset_rate(frm, cdt, cdn, asset) {
	frappe.prompt([
		{
			fieldname: 'rate_per_hour',
			fieldtype: 'Currency',
			label: __('Hourly Rate'),
			reqd: 1,
			description: __('No rate found in Project Asset Billing for this asset. Please enter the hourly rate manually.')
		}
	], function (values) {
		frappe.model.set_value(cdt, cdn, 'rate_per_hour', values.rate_per_hour);
		frappe.model.set_value(cdt, cdn, 'rate_per_day', flt(values.rate_per_hour) * 8);
		calculate_asset_amount(frm, cdt, cdn);

		// Offer to create Project Asset Billing entry
		frappe.confirm(
			__('Would you like to save this rate to Project Asset Billing for future use?'),
			function () {
				frappe.call({
					method: 'frappe.client.insert',
					args: {
						doc: {
							doctype: 'Project Asset Billing',
							project: frm.doc.project,
							asset: asset,
							value_per_hour: values.rate_per_hour
						}
					},
					callback: function (r) {
						if (r.message) {
							frappe.show_alert({ message: __('Project Asset Billing created'), indicator: 'green' });
						}
					}
				});
			}
		);
	}, __('Enter Asset Hourly Rate'), __('Set Rate'));
}

function calculate_asset_amount(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	let hours = flt(row.hours) || 8;
	let rate = flt(row.rate_per_hour);
	// Calculate: hourly_rate × hours
	let amount = rate * hours;
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
				callback: function (r) {
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

// Material child table events - Warehouse First Flow
frappe.ui.form.on('DPR Material', {
	warehouse(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		// Clear item when warehouse changes
		frappe.model.set_value(cdt, cdn, 'item_code', '');
		frappe.model.set_value(cdt, cdn, 'rate', 0);
		frappe.model.set_value(cdt, cdn, 'amount', 0);

		// Check if warehouse has stock
		if (row.warehouse) {
			frappe.call({
				method: 'construction_management.api.dpr_utils.get_warehouse_items_with_stock',
				args: { warehouse: row.warehouse },
				callback: function (r) {
					if (!r.message || r.message.length === 0) {
						frappe.show_alert({
							message: __('No items with stock found in this warehouse/site. Please select a different site or add stock first.'),
							indicator: 'orange'
						});
					}
				}
			});
		}
	},

	item_code(frm, cdt, cdn) {
		let row = locals[cdt][cdn];

		// Validate warehouse is selected first
		if (row.item_code && !row.warehouse) {
			frappe.model.set_value(cdt, cdn, 'item_code', '');
			frappe.show_alert({
				message: __('Please select a Site/Warehouse first before selecting an item'),
				indicator: 'red'
			});
			return;
		}

		if (row.item_code && row.warehouse) {
			// Fetch valuation rate and make it read-only
			frappe.call({
				method: 'construction_management.api.dpr_utils.get_item_valuation_rate',
				args: {
					item_code: row.item_code,
					warehouse: row.warehouse
				},
				callback: function (r) {
					if (r.message) {
						frappe.model.set_value(cdt, cdn, 'rate', r.message);
						calculate_material_amount(frm, cdt, cdn);
					}
				}
			});

			// Also validate stock availability
			frappe.call({
				method: 'construction_management.api.dpr_utils.validate_material_stock',
				args: {
					warehouse: row.warehouse,
					item_code: row.item_code,
					qty: row.qty || 1
				},
				callback: function (r) {
					if (r.message && !r.message.is_valid) {
						frappe.show_alert({
							message: __('Warning: {0}', [r.message.message]),
							indicator: 'orange'
						});
					}
				}
			});

			// Show inline stock snapshot
			frappe.call({
				method: 'construction_management.api.dpr_utils.get_bin_snapshot',
				args: {
					warehouse: row.warehouse,
					item_code: row.item_code
				},
				callback: function (r) {
					if (!r.message) return;
					const bin = r.message;
					const msg = __('Stock @ {0}: On-hand {1}, Reserved {2}, Projected {3}, Valuation {4}', [
						row.warehouse,
						flt(bin.actual_qty || 0),
						flt(bin.reserved_qty || 0),
						flt(bin.projected_qty || 0),
						format_currency(bin.valuation_rate || 0)
					]);
					frappe.show_alert({ message: msg, indicator: 'blue' });
				}
			});
		}
	},

	qty(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		// Validate stock availability
		if (row.warehouse && row.item_code && row.qty > 0) {
			frappe.call({
				method: 'construction_management.api.dpr_utils.validate_material_stock',
				args: {
					warehouse: row.warehouse,
					item_code: row.item_code,
					qty: row.qty
				},
				callback: function (r) {
					if (r.message && !r.message.is_valid) {
						frappe.show_alert({
							message: r.message.message,
							indicator: 'orange'
						});
					}
				}
			});
		}
		calculate_material_amount(frm, cdt, cdn);
	},

	rate(frm, cdt, cdn) {
		calculate_material_amount(frm, cdt, cdn);
	},

	materials_remove(frm) {
		calculate_total_material_cost(frm);
	},

	materials_add(frm, cdt, cdn) {
		// Check if project has warehouses
		if (frm.doc.project) {
			frappe.call({
				method: 'construction_management.api.dpr_utils.get_project_warehouses',
				args: { project: frm.doc.project },
				callback: function (r) {
					if (!r.message || r.message.length === 0) {
						frappe.show_alert({
							message: __('No warehouses/sites linked to this project. Please create a warehouse and link it to the project first.'),
							indicator: 'orange'
						});
					}
				}
			});
		}
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
		callback: function (r) {
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
	// Fetch asset rates (hourly)
	(frm.doc.assets || []).forEach((row) => {
		if (row.asset && frm.doc.project) {
			frappe.call({
				method: 'construction_management.construction_management.doctype.project_asset_billing.project_asset_billing.get_asset_hourly_rate',
				args: {
					project: frm.doc.project,
					asset: row.asset,
					date: frm.doc.date
				},
				async: false,
				callback: function (r) {
					if (r.message) {
						frappe.model.set_value('DPR Asset', row.name, 'rate_per_hour', r.message);
						frappe.model.set_value('DPR Asset', row.name, 'rate_per_day', flt(r.message) * 8);
					}
				}
			});
		}
	});

	// Fetch employee rates
	(frm.doc.employees || []).forEach((row) => {
		if (row.employee) {
			frappe.call({
				method: 'construction_management.api.dpr_utils.get_employee_daily_rate',
				args: {
					employee: row.employee
				},
				async: false,
				callback: function (r) {
					if (r.message) {
						frappe.model.set_value('DPR Employee', row.name, 'rate_per_day', r.message);
					}
				}
			});
		}
	});

	// Fetch material rates
	(frm.doc.materials || []).forEach((row) => {
		if (row.item_code && row.warehouse) {
			frappe.call({
				method: 'construction_management.api.dpr_utils.get_item_valuation_rate',
				args: {
					item_code: row.item_code,
					warehouse: row.warehouse
				},
				async: false,
				callback: function (r) {
					if (r.message) {
						frappe.model.set_value('DPR Material', row.name, 'rate', r.message);
					}
				}
			});
		}
	});

	frm.refresh_fields();
	frappe.show_alert({ message: __('Rates fetched'), indicator: 'green' });
}

function render_connections(frm) {
	if (!frm.fields_dict.connections) return;

	let stock_entries = (frm.doc.stock_entries || "").split(",").filter(v => v.trim());
	let journal_entries = (frm.doc.journal_entries || "").split(",").filter(v => v.trim());

	let html = `
		<div class="dpr-connections-dashboard" style="display: flex; gap: 15px; padding: 10px 0;">
			<div class="connection-card" data-doctype="Stock Entry" data-filters='${JSON.stringify({ "name": ["in", stock_entries] })}'>
				<div class="card-label">${__('Stock Entries')}</div>
				<div class="card-value">${stock_entries.length}</div>
			</div>
			<div class="connection-card" data-doctype="Journal Entry" data-filters='${JSON.stringify({ "name": ["in", journal_entries] })}'>
				<div class="card-label">${__('Journal Entries')}</div>
				<div class="card-value">${journal_entries.length}</div>
			</div>
		</div>
		<style>
			.dpr-connections-dashboard .connection-card {
				background: #f8fafc;
				border: 1px solid #e2e8f0;
				border-radius: 8px;
				padding: 12px 20px;
				min-width: 140px;
				cursor: pointer;
				transition: all 0.2s;
				box-shadow: 0 1px 2px rgba(0,0,0,0.05);
			}
			.dpr-connections-dashboard .connection-card:hover {
				background: #f1f5f9;
				border-color: #cbd5e1;
				transform: translateY(-1px);
				box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
			}
			.dpr-connections-dashboard .card-label {
				font-size: 11px;
				text-transform: uppercase;
				letter-spacing: 0.5px;
				color: #64748b;
				font-weight: 600;
				margin-bottom: 4px;
			}
			.dpr-connections-dashboard .card-value {
				font-size: 20px;
				font-weight: 700;
				color: #1e293b;
			}
		</style>
	`;
	frm.fields_dict.connections.$wrapper.html(html);

	// Bind click events
	frm.fields_dict.connections.$wrapper.on('click', '.connection-card', function () {
		const doctype = $(this).data('doctype');
		const filters = $(this).data('filters');
		frappe.set_route('List', doctype, filters);
	});
}

function render_accounting_links(frm) {
	const fields = ['stock_entries', 'journal_entries'];
	const doctypes = {
		'stock_entries': 'Stock Entry',
		'journal_entries': 'Journal Entry'
	};

	fields.forEach(field => {
		let value = frm.doc[field];
		if (value && typeof value === 'string') {
			let names = value.split(',').map(v => v.trim()).filter(v => v);
			let links_html = names.map(name => {
				return `<a class="badge badge-info dpr-ref-link" data-doctype="${doctypes[field]}" data-name="${name}" style="margin-right: 5px; cursor: pointer; font-size: 12px; padding: 4px 8px;">
					${name}
				</a>`;
			}).join(' ');

			frm.get_field(field).$wrapper.find('.control-value').html(links_html);

			frm.get_field(field).$wrapper.on('click', '.dpr-ref-link', function (e) {
				e.preventDefault();
				let doctype = $(this).attr('data-doctype');
				let name = $(this).attr('data-name');
				frappe.set_route('Form', doctype, name);
			});
		}
	});
}
