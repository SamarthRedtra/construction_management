// Copyright (c) 2024, Construction Management
// License: MIT
// Modern BOQ Progressive Billing Dashboard with Revenue & Cost Tracking

frappe.ui.form.on('Project', {
	refresh(frm) {
		if (frm.doc.enable_progressive_boq) {
			render_construction_dashboard(frm);
		}
	},
	
	enable_progressive_boq(frm) {
		if (frm.doc.enable_progressive_boq) {
			render_construction_dashboard(frm);
		} else {
			const wrapper = frm.fields_dict.construction_dashboard?.$wrapper;
			if (wrapper) wrapper.html('');
		}
	}
});

function render_construction_dashboard(frm) {
	const wrapper = frm.fields_dict.construction_dashboard?.$wrapper;
	if (!wrapper) return;
	
	wrapper.html(`
		<div class="boq-dashboard-loading">
			<div class="loading-spinner"></div>
			<p>Loading BOQ Dashboard...</p>
		</div>
		${get_dashboard_styles()}
	`);
	
	frappe.call({
		method: 'construction_management.api.boq_tree.get_boq_tree_data',
		args: { project: frm.doc.name },
		callback: function(r) {
			if (r.message && r.message.bills && r.message.bills.length > 0) {
				render_modern_dashboard(wrapper, frm, r.message);
			} else {
				render_empty_state(wrapper, frm);
			}
		},
		error: function() {
			render_empty_state(wrapper, frm);
		}
	});
}

function get_dashboard_styles() {
	return `<style>
		.boq-dashboard-modern { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
		.boq-dashboard-loading { text-align: center; padding: 60px 20px; color: #6c757d; }
		.loading-spinner { width: 40px; height: 40px; border: 3px solid #f3f3f3; border-top: 3px solid #5e64ff; border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 15px; }
		@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
	</style>`;
}

function render_empty_state(wrapper, frm) {
	wrapper.html(`
		${get_dashboard_styles()}
		${get_modern_styles()}
		<div class="boq-empty-state">
			<div class="empty-icon">
				<svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
					<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
					<polyline points="14 2 14 8 20 8"></polyline>
					<line x1="16" y1="13" x2="8" y2="13"></line>
					<line x1="16" y1="17" x2="8" y2="17"></line>
				</svg>
			</div>
			<h3>No BOQ Found</h3>
			<p>Create a Project BOQ to start tracking progressive billing for this project.</p>
			<button class="btn-modern btn-primary-modern" onclick="create_project_boq('${frm.doc.name}')">
				<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<line x1="12" y1="5" x2="12" y2="19"></line>
					<line x1="5" y1="12" x2="19" y2="12"></line>
				</svg>
				Create Project BOQ
			</button>
		</div>
	`);
}

function render_modern_dashboard(wrapper, frm, data) {
	const kpi = data.kpi || {};
	const progress = kpi.total_boq_value > 0 ? ((kpi.total_billed / kpi.total_boq_value) * 100).toFixed(1) : 0;
	const collectionRate = kpi.total_billed > 0 ? ((kpi.total_collected / kpi.total_billed) * 100).toFixed(1) : 0;
	
	wrapper.html(`
		${get_dashboard_styles()}
		${get_modern_styles()}
		<div class="boq-dashboard-modern">
			<div class="dashboard-header">
				<div class="header-left">
					<h2 class="dashboard-title">
						<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
							<polyline points="14 2 14 8 20 8"></polyline>
						</svg>
						Bill of Quantities
					</h2>
					<span class="boq-status-badge status-${(data.project_boq?.status || 'Draft').toLowerCase()}">${data.project_boq?.status || 'Draft'}</span>
				</div>
				<div class="header-actions">
					<button class="btn-modern btn-outline" onclick="window.open('/app/project-boq/${data.project_boq?.name}', '_blank')">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
						Open BOQ
					</button>
					<button class="btn-modern btn-outline" onclick="cur_frm.reload_doc()">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
						Refresh
					</button>
				</div>
			</div>
			
			<div class="kpi-grid" id="kpi-grid"></div>
			<div class="action-bar" id="action-bar"></div>
			<div class="bills-container" id="bills-container"></div>
		</div>
	`);
	
	render_kpi_grid(wrapper.find('#kpi-grid'), kpi, progress, collectionRate);
	render_action_bar(wrapper.find('#action-bar'), frm);
	render_bills_accordion(wrapper.find('#bills-container'), frm, data.bills);
}

function render_kpi_grid(container, kpi, progress, collectionRate) {
	const totalCost = (kpi.total_labour_cost || 0) + (kpi.total_material_cost || 0) + (kpi.total_asset_cost || 0) + (kpi.total_subcontract_cost || 0) + (kpi.total_expense_cost || 0);
	const margin = (kpi.total_billed || 0) - totalCost;
	
	container.html(`
		<div class="kpi-card kpi-primary">
			<div class="kpi-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="1" y="4" width="22" height="16" rx="2" ry="2"></rect><line x1="1" y1="10" x2="23" y2="10"></line></svg></div>
			<div class="kpi-content">
				<span class="kpi-label">Total BOQ Value</span>
				<span class="kpi-value">${format_currency(kpi.total_boq_value || 0)}</span>
			</div>
		</div>
		<div class="kpi-card kpi-info">
			<div class="kpi-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg></div>
			<div class="kpi-content">
				<span class="kpi-label">Total Revenue</span>
				<span class="kpi-value">${format_currency(kpi.total_billed || 0)}</span>
				<div class="kpi-progress"><div class="kpi-progress-bar" style="width: ${progress}%"></div></div>
				<span class="kpi-sub">${progress}% of BOQ</span>
			</div>
		</div>
		<div class="kpi-card kpi-success">
			<div class="kpi-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg></div>
			<div class="kpi-content">
				<span class="kpi-label">Collected</span>
				<span class="kpi-value">${format_currency(kpi.total_collected || 0)}</span>
				<div class="kpi-progress"><div class="kpi-progress-bar" style="width: ${collectionRate}%"></div></div>
				<span class="kpi-sub">${collectionRate}% collected</span>
			</div>
		</div>
		<div class="kpi-card kpi-warning">
			<div class="kpi-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg></div>
			<div class="kpi-content">
				<span class="kpi-label">Total Expenses</span>
				<span class="kpi-value">${format_currency(totalCost)}</span>
				<span class="kpi-sub">Margin: ${format_currency(margin)}</span>
			</div>
		</div>
	`);
}

function render_action_bar(container, frm) {
	container.html(`
		<div class="action-bar-left">
			<button class="btn-modern btn-primary-modern" onclick="add_bill_number('${frm.doc.name}')">
				<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
				Add Bill
			</button>
			<button class="btn-modern btn-success-modern" onclick="generate_invoice_for_all('${frm.doc.name}')">
				<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
				Generate Invoice
			</button>
			<button class="btn-modern btn-outline" onclick="record_advance_payment('${frm.doc.name}')">
				<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"></line><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg>
				Record Advance
			</button>
		</div>
		<div class="action-bar-right">
			<button class="btn-modern btn-outline" onclick="print_invoice_till_date('${frm.doc.name}')">
				<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 6 2 18 2 18 9"></polyline><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path><rect x="6" y="14" width="12" height="8"></rect></svg>
				Print Till Date
			</button>
			<button class="btn-modern btn-outline" onclick="print_monthly_invoice('${frm.doc.name}')">
				<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
				Monthly Invoice
			</button>
			<button class="btn-modern btn-outline" onclick="export_boq_excel('${frm.doc.name}')">
				<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
				Export Excel
			</button>
		</div>
	`);
}

function render_bills_accordion(container, frm, bills) {
	if (!bills || bills.length === 0) {
		container.html('<div class="no-bills-message">No bills found. Click "Add Bill" to get started.</div>');
		return;
	}
	
	let html = '<div class="bills-accordion">';
	bills.forEach((bill, idx) => {
		const totals = bill.totals || {};
		const qty = totals.qty || {};
		const amount = totals.amount || {};
		const isExpanded = idx === 0;
		
		html += `
			<div class="bill-card ${isExpanded ? 'expanded' : ''}" data-bill="${bill.name}">
				<div class="bill-header" onclick="toggleBill(this)">
					<div class="bill-header-left">
						<svg class="chevron-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>
						<div class="bill-info">
							<span class="bill-title">${bill.bill_no}</span>
							${bill.description ? `<span class="bill-desc">${bill.description}</span>` : ''}
						</div>
					</div>
					<div class="bill-header-right">
						<div class="bill-stat"><span class="stat-label">Items</span><span class="stat-value">${(bill.items || []).length}</span></div>
						<div class="bill-stat"><span class="stat-label">Total</span><span class="stat-value">${format_currency(amount.total)}</span></div>
						<div class="bill-stat"><span class="stat-label">Revenue</span><span class="stat-value">${format_currency(amount.to_date)}</span></div>
						<div class="bill-stat"><span class="stat-label">Balance</span><span class="stat-value balance-value">${format_currency(amount.balance)}</span></div>
					</div>
				</div>
				<div class="bill-content" style="${isExpanded ? '' : 'display: none;'}">
					<div class="bill-toolbar">
						<button class="btn-modern btn-sm btn-outline" onclick="add_boq_item('${bill.name}', '${frm.doc.name}'); event.stopPropagation();">
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
							Add Item
						</button>
					</div>
					<div class="items-table-wrapper">
						${render_items_table(bill.items || [], frm)}
					</div>
				</div>
			</div>
		`;
	});
	html += '</div>';
	container.html(html);
	attach_item_events(container, frm);
}

function render_items_table(items, frm) {
	if (!items || items.length === 0) {
		return '<div class="no-items-message">No items in this bill. Click "Add Item" to add BOQ items.</div>';
	}
	
	let html = `
		<table class="items-table">
			<thead>
				<tr>
					<th rowspan="2" class="col-desc">Description</th>
					<th rowspan="2" class="col-unit">Unit</th>
					<th rowspan="2" class="col-num">Qty</th>
					<th rowspan="2" class="col-num">Rate</th>
					<th rowspan="2" class="col-num">Amount</th>
					<th colspan="2" class="col-group col-highlight-blue">Current Billing</th>
					<th colspan="3" class="col-group col-highlight-green">Revenue</th>
					<th rowspan="2" class="col-num">Balance</th>
					<th rowspan="2" class="col-status">Status</th>
					<th rowspan="2" class="col-actions">Actions</th>
				</tr>
				<tr>
					<th class="col-num col-highlight-blue">Qty</th>
					<th class="col-num col-highlight-blue">Value</th>
					<th class="col-num col-highlight-green">Prev</th>
					<th class="col-num col-highlight-green">Curr</th>
					<th class="col-num col-highlight-green">Accum</th>
				</tr>
			</thead>
			<tbody>
	`;
	
	items.forEach(item => {
		const qty = item.qty || {};
		const amount = item.amount || {};
		const statusClass = get_status_class(item.billing_status);
		const isFullyBilled = item.billing_status === 'Fully Billed';
		
		html += `
			<tr class="item-row ${isFullyBilled ? 'fully-billed' : ''}" data-item="${item.name}">
				<td class="col-desc">
					<div class="item-desc-wrapper">
						${item.item_code ? `<code class="item-code">${item.item_code}</code>` : ''}
						<span class="item-desc">${item.description || 'No description'}</span>
					</div>
				</td>
				<td class="col-unit">${item.unit || '-'}</td>
				<td class="col-num">${format_number(qty.total)}</td>
				<td class="col-num">${format_currency(amount.rate)}</td>
				<td class="col-num">${format_currency(amount.total)}</td>
				<td class="col-num col-highlight-blue">
					<input type="number" class="current-qty-input" value="${qty.current || 0}" 
						data-item="${item.name}" data-max="${qty.balance + (qty.current || 0)}" data-rate="${amount.rate || 0}"
						step="0.001" min="0" ${isFullyBilled ? 'disabled' : ''}>
				</td>
				<td class="col-num col-highlight-blue">
					<input type="number" class="current-value-input" value="${amount.current || 0}" 
						data-item="${item.name}" data-max="${amount.balance + (amount.current || 0)}" data-rate="${amount.rate || 0}"
						step="0.01" min="0" ${isFullyBilled ? 'disabled' : ''}>
				</td>
				<td class="col-num col-highlight-green">${format_currency(amount.prev)}</td>
				<td class="col-num col-highlight-green">${format_currency(amount.current)}</td>
				<td class="col-num col-highlight-green font-bold">${format_currency(amount.to_date)}</td>
				<td class="col-num balance-cell">${format_currency(amount.balance)}</td>
				<td class="col-status"><span class="status-pill ${statusClass}">${item.billing_status || 'Not Billed'}</span></td>
				<td class="col-actions">
					<div class="action-icons">
						<button class="action-icon-btn action-invoice" onclick="create_item_invoice('${item.name}')" title="Create Invoice" ${isFullyBilled ? 'disabled' : ''}>
							<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
						</button>
						<button class="action-icon-btn action-history" onclick="view_item_invoices('${item.name}')" title="View Invoice History">
							<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
						</button>
						<button class="action-icon-btn action-cost" onclick="view_cost_details('${item.name}')" title="View Cost Details">
							<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"></line><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg>
						</button>
						<button class="action-icon-btn action-edit" onclick="edit_boq_item('${item.name}')" title="Edit Item">
							<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
						</button>
					</div>
				</td>
			</tr>
		`;
	});
	
	html += '</tbody></table>';
	return html;
}

function attach_item_events(container, frm) {
	// Handle Qty input change - auto-calculate Value
	container.find('.current-qty-input').on('change', function() {
		const input = $(this);
		const itemName = input.data('item');
		const maxQty = parseFloat(input.data('max')) || 0;
		const rate = parseFloat(input.data('rate')) || 0;
		let newQty = parseFloat(input.val()) || 0;
		
		if (newQty < 0) { newQty = 0; input.val(0); }
		if (newQty > maxQty) {
			frappe.show_alert({message: __('Quantity cannot exceed balance ({0})', [maxQty]), indicator: 'orange'});
			newQty = maxQty;
			input.val(maxQty);
		}
		
		// Auto-update value input
		const valueInput = input.closest('tr').find('.current-value-input');
		const newValue = newQty * rate;
		valueInput.val(newValue.toFixed(2));
		
		update_boq_item_current(itemName, newQty, frm);
	});
	
	// Handle Value input change - auto-calculate Qty
	container.find('.current-value-input').on('change', function() {
		const input = $(this);
		const itemName = input.data('item');
		const maxValue = parseFloat(input.data('max')) || 0;
		const rate = parseFloat(input.data('rate')) || 0;
		let newValue = parseFloat(input.val()) || 0;
		
		if (newValue < 0) { newValue = 0; input.val(0); }
		if (newValue > maxValue) {
			frappe.show_alert({message: __('Value cannot exceed balance'), indicator: 'orange'});
			newValue = maxValue;
			input.val(maxValue.toFixed(2));
		}
		
		// Auto-update qty input
		const qtyInput = input.closest('tr').find('.current-qty-input');
		const newQty = rate > 0 ? newValue / rate : 0;
		qtyInput.val(newQty.toFixed(3));
		
		update_boq_item_current(itemName, newQty, frm);
	});
}

function update_boq_item_current(itemName, newQty, frm) {
	frappe.call({
		method: 'construction_management.api.boq_tree.update_boq_item_current',
		args: { boq_item: itemName, current_qty: newQty },
		callback: function(r) {
			if (r.message) {
				frappe.show_alert({message: __('Updated'), indicator: 'green'});
				frappe.call({
					method: 'construction_management.api.boq_tree.get_boq_kpi',
					args: { project: frm.doc.name },
					callback: function(kpiRes) {
						if (kpiRes.message) {
							const kpi = kpiRes.message;
							const progress = kpi.total_boq_value > 0 ? ((kpi.total_billed / kpi.total_boq_value) * 100).toFixed(1) : 0;
							const collectionRate = kpi.total_billed > 0 ? ((kpi.total_collected / kpi.total_billed) * 100).toFixed(1) : 0;
							render_kpi_grid($('#kpi-grid'), kpi, progress, collectionRate);
						}
					}
				});
			}
		}
	});
}

window.toggleBill = function(header) {
	const card = $(header).closest('.bill-card');
	const content = card.find('.bill-content');
	const isExpanded = card.hasClass('expanded');
	
	if (isExpanded) {
		content.slideUp(200);
		card.removeClass('expanded');
	} else {
		content.slideDown(200);
		card.addClass('expanded');
	}
};

function get_status_class(status) {
	switch(status) {
		case 'Fully Billed': return 'status-success';
		case 'Partially Billed': return 'status-warning';
		default: return 'status-default';
	}
}

function format_currency(value) {
	if (value === null || value === undefined) return '-';
	return frappe.format(value, { fieldtype: 'Currency' });
}

function format_number(value) {
	if (value === null || value === undefined) return '-';
	return frappe.format(value, { fieldtype: 'Float', precision: 3 });
}

// Global functions
window.create_project_boq = function(project) {
	const d = new frappe.ui.Dialog({
		title: 'Create Project BOQ',
		fields: [{fieldname: 'boq_name', label: 'BOQ Name', fieldtype: 'Data', reqd: 1, default: `BOQ - ${project}`}],
		primary_action_label: 'Create',
		primary_action(values) {
			frappe.call({
				method: 'frappe.client.insert',
				args: { doc: { doctype: 'Project BOQ', project: project, boq_name: values.boq_name, status: 'Draft' }},
				callback: function(r) {
					if (r.message) { d.hide(); frappe.show_alert({message: __('Project BOQ created'), indicator: 'green'}); cur_frm.reload_doc(); }
				}
			});
		}
	});
	d.show();
};

window.add_bill_number = function(project) {
	const d = new frappe.ui.Dialog({
		title: 'Add Bill Number',
		fields: [
			{fieldname: 'bill_no', label: 'Bill Number', fieldtype: 'Data', reqd: 1, description: 'e.g., Bill No. 1 - Substructure Works'},
			{fieldname: 'description', label: 'Description', fieldtype: 'Small Text'}
		],
		primary_action_label: 'Create',
		primary_action(values) {
			frappe.call({
				method: 'construction_management.api.boq_tree.create_bill_number',
				args: { project: project, bill_no: values.bill_no, description: values.description },
				callback: function(r) {
					if (r.message) { d.hide(); frappe.show_alert({message: __('Bill Number created'), indicator: 'green'}); cur_frm.reload_doc(); }
				}
			});
		}
	});
	d.show();
};

window.add_boq_item = function(bill_name, project) {
	const d = new frappe.ui.Dialog({
		title: 'Add BOQ Item',
		fields: [
			{fieldname: 'item_code', label: 'Item Code', fieldtype: 'Data'},
			{fieldname: 'description', label: 'Description', fieldtype: 'Text', reqd: 1},
			{fieldtype: 'Column Break'},
			{fieldname: 'unit', label: 'Unit', fieldtype: 'Link', options: 'UOM', reqd: 1},
			{fieldname: 'total_qty', label: 'Total Quantity', fieldtype: 'Float', reqd: 1},
			{fieldname: 'rate', label: 'Rate', fieldtype: 'Currency', reqd: 1}
		],
		primary_action_label: 'Create',
		primary_action(values) {
			frappe.call({
				method: 'frappe.client.insert',
				args: { doc: { doctype: 'BOQ Item', parent_bill: bill_name, item_code: values.item_code, description: values.description, unit: values.unit, total_qty: values.total_qty, rate: values.rate }},
				callback: function(r) {
					if (r.message) { d.hide(); frappe.show_alert({message: __('BOQ Item created'), indicator: 'green'}); cur_frm.reload_doc(); }
				}
			});
		}
	});
	d.show();
};

window.edit_boq_item = function(item_name) { frappe.set_route('Form', 'BOQ Item', item_name); };

window.create_item_invoice = function(boq_item) {
	const input = $(`.current-qty-input[data-item="${boq_item}"]`);
	const currentQty = parseFloat(input.val()) || 0;
	
	if (currentQty <= 0) {
		frappe.show_alert({message: __('Please enter a quantity to bill'), indicator: 'orange'});
		return;
	}
	
	frappe.confirm(__('Create invoice for {0} units?', [currentQty]), function() {
		frappe.call({
			method: 'construction_management.api.boq_invoice.create_invoice_from_boq_item',
			args: { project: cur_frm.doc.name, boq_item: boq_item, current_qty: currentQty },
			callback: function(r) {
				if (r.message) {
					frappe.show_alert({message: __('Invoice {0} created', [r.message.invoice]), indicator: 'green'});
					frappe.set_route('Form', 'Sales Invoice', r.message.invoice);
				}
			}
		});
	});
};

window.view_item_invoices = function(boq_item) {
	frappe.call({
		method: 'construction_management.api.boq_invoice.get_boq_invoice_history',
		args: { boq_item: boq_item },
		callback: function(r) { if (r.message) show_invoice_dialog(boq_item, r.message); }
	});
};

function show_invoice_dialog(boq_item, data) {
	const summary = data.summary || {};
	const invoices = data.invoices || [];
	
	let invoiceRows = invoices.length > 0 ? invoices.map(inv => `
		<tr>
			<td><a href="/app/sales-invoice/${inv.name}" class="invoice-link">${inv.name}</a></td>
			<td>${inv.posting_date}</td>
			<td>${inv.unit || '-'}</td>
			<td class="text-right">${format_number(inv.qty)}</td>
			<td class="text-right">${format_currency(inv.rate)}</td>
			<td class="text-right">${format_currency(inv.amount)}</td>
			<td class="text-center">${inv.pay_cert || '-'}</td>
			<td><span class="status-pill ${inv.status === 'Paid' ? 'status-success' : 'status-warning'}">${inv.status}</span></td>
		</tr>
	`).join('') : '<tr><td colspan="8" class="text-center text-muted">No invoices found</td></tr>';
	
	const d = new frappe.ui.Dialog({ title: __('Invoice History - Payment Plan'), size: 'extra-large', fields: [{fieldtype: 'HTML', fieldname: 'invoice_html'}] });
	d.fields_dict.invoice_html.$wrapper.html(`
		<div class="invoice-summary-grid">
			<div class="summary-card"><span class="summary-label">Total Invoices</span><span class="summary-value">${summary.invoice_count || 0}</span></div>
			<div class="summary-card"><span class="summary-label">Total Invoiced</span><span class="summary-value">${format_currency(summary.total_invoiced)}</span></div>
			<div class="summary-card success"><span class="summary-label">Collected</span><span class="summary-value">${format_currency(summary.total_collected)}</span></div>
			<div class="summary-card warning"><span class="summary-label">Pending</span><span class="summary-value">${format_currency(summary.pending)}</span></div>
		</div>
		<h4 style="margin: 20px 0 10px; font-size: 14px; font-weight: 600;">Child Payment Plan</h4>
		<table class="invoice-history-table">
			<thead><tr><th>Invoice No</th><th>Date</th><th>Unit</th><th class="text-right">Qty</th><th class="text-right">Rate</th><th class="text-right">Amount</th><th class="text-center">Pay Cert</th><th>Status</th></tr></thead>
			<tbody>${invoiceRows}</tbody>
		</table>
		<style>
			.invoice-summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
			.summary-card { background: #f8f9fa; border-radius: 8px; padding: 16px; text-align: center; }
			.summary-card.success { background: #d4edda; }
			.summary-card.warning { background: #fff3cd; }
			.summary-label { display: block; font-size: 11px; color: #6c757d; margin-bottom: 4px; text-transform: uppercase; }
			.summary-value { display: block; font-size: 20px; font-weight: 600; }
			.invoice-history-table { width: 100%; border-collapse: collapse; }
			.invoice-history-table th, .invoice-history-table td { padding: 12px; border-bottom: 1px solid #e9ecef; }
			.invoice-history-table th { background: #f8f9fa; font-weight: 500; font-size: 11px; text-transform: uppercase; }
			.invoice-link { color: #5e64ff; text-decoration: none; font-weight: 500; }
		</style>
	`);
	d.show();
}

window.view_cost_details = function(boq_item) {
	frappe.call({
		method: 'construction_management.api.boq_tree.get_boq_item_cost_details',
		args: { boq_item: boq_item },
		callback: function(r) { if (r.message) show_cost_dialog(boq_item, r.message); }
	});
};

function show_cost_dialog(boq_item, data) {
	const cost = data.cost || {};
	const revenue = data.revenue || {};
	const margin = (revenue.to_date || 0) - (cost.total || 0);
	const marginPercent = revenue.to_date > 0 ? ((margin / revenue.to_date) * 100).toFixed(1) : 0;
	
	const d = new frappe.ui.Dialog({ title: __('Cost Details - Expenses Breakdown'), size: 'large', fields: [{fieldtype: 'HTML', fieldname: 'cost_html'}] });
	d.fields_dict.cost_html.$wrapper.html(`
		<div class="cost-summary-section">
			<h4>Revenue vs Cost Summary</h4>
			<div class="cost-summary-grid">
				<div class="summary-card info"><span class="summary-label">Total Revenue</span><span class="summary-value">${format_currency(revenue.to_date)}</span></div>
				<div class="summary-card warning"><span class="summary-label">Total Cost</span><span class="summary-value">${format_currency(cost.total)}</span></div>
				<div class="summary-card ${margin >= 0 ? 'success' : 'danger'}"><span class="summary-label">Margin</span><span class="summary-value">${format_currency(margin)}</span><span class="summary-sub">${marginPercent}%</span></div>
			</div>
		</div>
		<div class="cost-breakdown-section">
			<h4>Expenses by Breakup</h4>
			<table class="cost-breakdown-table">
				<thead><tr><th>Cost Type</th><th class="text-right">Amount</th><th class="text-right">% of Total</th></tr></thead>
				<tbody>
					<tr><td><span class="cost-badge labour">Labour</span></td><td class="text-right">${format_currency(cost.labour)}</td><td class="text-right">${cost.total > 0 ? ((cost.labour / cost.total) * 100).toFixed(1) : 0}%</td></tr>
					<tr><td><span class="cost-badge material">Material</span></td><td class="text-right">${format_currency(cost.material)}</td><td class="text-right">${cost.total > 0 ? ((cost.material / cost.total) * 100).toFixed(1) : 0}%</td></tr>
					<tr><td><span class="cost-badge asset">Asset</span></td><td class="text-right">${format_currency(cost.asset)}</td><td class="text-right">${cost.total > 0 ? ((cost.asset / cost.total) * 100).toFixed(1) : 0}%</td></tr>
					<tr><td><span class="cost-badge subcontract">Subcontract (S/C)</span></td><td class="text-right">${format_currency(cost.subcontract)}</td><td class="text-right">${cost.total > 0 ? ((cost.subcontract / cost.total) * 100).toFixed(1) : 0}%</td></tr>
					<tr><td><span class="cost-badge expense">Other Expense</span></td><td class="text-right">${format_currency(cost.expense)}</td><td class="text-right">${cost.total > 0 ? ((cost.expense / cost.total) * 100).toFixed(1) : 0}%</td></tr>
					<tr class="total-row"><td><strong>Total</strong></td><td class="text-right"><strong>${format_currency(cost.total)}</strong></td><td class="text-right"><strong>100%</strong></td></tr>
				</tbody>
			</table>
		</div>
		<style>
			.cost-summary-section, .cost-breakdown-section { margin-bottom: 24px; }
			.cost-summary-section h4, .cost-breakdown-section h4 { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: #374151; }
			.cost-summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
			.summary-card { background: #f8f9fa; border-radius: 8px; padding: 16px; text-align: center; }
			.summary-card.info { background: #dbeafe; }
			.summary-card.success { background: #d1fae5; }
			.summary-card.warning { background: #fef3c7; }
			.summary-card.danger { background: #fee2e2; }
			.summary-label { display: block; font-size: 11px; color: #6c757d; margin-bottom: 4px; text-transform: uppercase; }
			.summary-value { display: block; font-size: 20px; font-weight: 600; }
			.summary-sub { display: block; font-size: 12px; color: #6b7280; margin-top: 4px; }
			.cost-breakdown-table { width: 100%; border-collapse: collapse; }
			.cost-breakdown-table th, .cost-breakdown-table td { padding: 12px; border-bottom: 1px solid #e9ecef; }
			.cost-breakdown-table th { background: #f8f9fa; font-weight: 500; font-size: 11px; text-transform: uppercase; }
			.cost-breakdown-table .total-row { background: #f8f9fa; }
			.cost-badge { display: inline-block; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 500; }
			.cost-badge.labour { background: #dbeafe; color: #1e40af; }
			.cost-badge.material { background: #fef3c7; color: #92400e; }
			.cost-badge.asset { background: #e0e7ff; color: #3730a3; }
			.cost-badge.subcontract { background: #d1fae5; color: #065f46; }
			.cost-badge.expense { background: #fce7f3; color: #9d174d; }
		</style>
	`);
	d.show();
}

window.generate_invoice_for_all = function(project) {
	const items = [];
	$('.current-qty-input').each(function() {
		const qty = parseFloat($(this).val()) || 0;
		if (qty > 0) items.push({ boq_item: $(this).data('item'), current_qty: qty });
	});
	
	if (items.length === 0) {
		frappe.show_alert({message: __('No items with current quantity to bill'), indicator: 'orange'});
		return;
	}
	
	frappe.confirm(__('Create invoice for {0} items?', [items.length]), function() {
		frappe.call({
			method: 'construction_management.api.boq_invoice.create_invoice_from_multiple_items',
			args: { project: project, items: items },
			callback: function(r) {
				if (r.message) {
					frappe.show_alert({message: __('Invoice {0} created', [r.message.invoice]), indicator: 'green'});
					frappe.set_route('Form', 'Sales Invoice', r.message.invoice);
				}
			}
		});
	});
};

window.export_boq_excel = function(project) {
	frappe.call({
		method: 'construction_management.api.boq_excel.export_boq_to_excel',
		args: { project: project },
		callback: function(r) {
			if (r.message) { window.open(r.message); frappe.show_alert({message: __('Excel exported'), indicator: 'green'}); }
		}
	});
};

window.print_invoice_till_date = function(project) {
	frappe.call({
		method: 'construction_management.api.boq_invoice.print_consolidated_invoice',
		args: { project: project, invoice_type: 'till_date' },
		callback: function(r) {
			if (r.message) {
				const printWindow = window.open('', '_blank');
				printWindow.document.write(r.message);
				printWindow.document.close();
				printWindow.focus();
				setTimeout(() => printWindow.print(), 500);
			}
		}
	});
};

window.print_monthly_invoice = function(project) {
	const currentDate = new Date();
	const currentMonth = currentDate.getMonth() + 1;
	const currentYear = currentDate.getFullYear();
	
	const d = new frappe.ui.Dialog({
		title: 'Monthly Invoice',
		fields: [
			{
				fieldname: 'month',
				label: 'Month',
				fieldtype: 'Select',
				options: [
					{value: '1', label: 'January'},
					{value: '2', label: 'February'},
					{value: '3', label: 'March'},
					{value: '4', label: 'April'},
					{value: '5', label: 'May'},
					{value: '6', label: 'June'},
					{value: '7', label: 'July'},
					{value: '8', label: 'August'},
					{value: '9', label: 'September'},
					{value: '10', label: 'October'},
					{value: '11', label: 'November'},
					{value: '12', label: 'December'}
				],
				default: currentMonth.toString(),
				reqd: 1
			},
			{
				fieldname: 'year',
				label: 'Year',
				fieldtype: 'Int',
				default: currentYear,
				reqd: 1
			}
		],
		primary_action_label: 'Print',
		primary_action(values) {
			d.hide();
			frappe.call({
				method: 'construction_management.api.boq_invoice.print_consolidated_invoice',
				args: { 
					project: project, 
					invoice_type: 'monthly',
					month: values.month,
					year: values.year
				},
				callback: function(r) {
					if (r.message) {
						const printWindow = window.open('', '_blank');
						printWindow.document.write(r.message);
						printWindow.document.close();
						printWindow.focus();
						setTimeout(() => printWindow.print(), 500);
					}
				}
			});
		}
	});
	d.show();
};

window.record_advance_payment = function(project) {
	const d = new frappe.ui.Dialog({
		title: 'Record Advance Payment',
		fields: [
			{fieldname: 'amount', label: 'Amount', fieldtype: 'Currency', reqd: 1},
			{fieldname: 'date', label: 'Date', fieldtype: 'Date', default: frappe.datetime.get_today(), reqd: 1},
			{fieldname: 'reference', label: 'Reference', fieldtype: 'Data', description: 'Payment reference or receipt number'},
			{fieldname: 'remarks', label: 'Remarks', fieldtype: 'Small Text'}
		],
		primary_action_label: 'Record',
		primary_action(values) {
			frappe.call({
				method: 'frappe.client.insert',
				args: {
					doc: {
						doctype: 'BOQ Advance Payment',
						project: project,
						amount: values.amount,
						date: values.date,
						reference: values.reference,
						remarks: values.remarks
					}
				},
				callback: function(r) {
					if (r.message) {
						d.hide();
						frappe.show_alert({message: __('Advance payment recorded'), indicator: 'green'});
						// Submit the advance payment
						frappe.call({
							method: 'frappe.client.submit',
							args: { doc: r.message },
							callback: function() {
								cur_frm.reload_doc();
							}
						});
					}
				}
			});
		}
	});
	d.show();
};

function get_modern_styles() {
	return `<style>
		/* Modern Dashboard Styles */
		.boq-dashboard-modern { padding: 0; }
		
		/* Header */
		.dashboard-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; flex-wrap: wrap; gap: 16px; }
		.header-left { display: flex; align-items: center; gap: 12px; }
		.dashboard-title { font-size: 20px; font-weight: 600; color: #1a1a2e; margin: 0; display: flex; align-items: center; gap: 10px; }
		.dashboard-title svg { color: #5e64ff; }
		.boq-status-badge { padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 500; }
		.status-draft { background: #e3e8ef; color: #4a5568; }
		.status-approved { background: #c6f6d5; color: #22543d; }
		.status-closed { background: #fed7d7; color: #742a2a; }
		.header-actions { display: flex; gap: 8px; }
		
		/* Buttons */
		.btn-modern { display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; border-radius: 8px; font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.2s; border: none; }
		.btn-modern svg { flex-shrink: 0; }
		.btn-primary-modern { background: linear-gradient(135deg, #5e64ff 0%, #7c3aed 100%); color: white; }
		.btn-primary-modern:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(94, 100, 255, 0.4); }
		.btn-success-modern { background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; }
		.btn-success-modern:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(16, 185, 129, 0.4); }
		.btn-outline { background: white; border: 1px solid #e2e8f0; color: #4a5568; }
		.btn-outline:hover { background: #f7fafc; border-color: #cbd5e0; }
		.btn-sm { padding: 6px 12px; font-size: 12px; }
		
		/* KPI Grid */
		.kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
		@media (max-width: 992px) { .kpi-grid { grid-template-columns: repeat(2, 1fr); } }
		@media (max-width: 576px) { .kpi-grid { grid-template-columns: 1fr; } }
		.kpi-card { background: white; border-radius: 12px; padding: 20px; display: flex; align-items: flex-start; gap: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); border: 1px solid #e2e8f0; transition: all 0.2s; }
		.kpi-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
		.kpi-icon { width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
		.kpi-primary .kpi-icon { background: linear-gradient(135deg, #e0e7ff 0%, #c7d2fe 100%); color: #4f46e5; }
		.kpi-info .kpi-icon { background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%); color: #2563eb; }
		.kpi-success .kpi-icon { background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%); color: #059669; }
		.kpi-warning .kpi-icon { background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); color: #d97706; }
		.kpi-content { flex: 1; min-width: 0; }
		.kpi-label { display: block; font-size: 12px; color: #6b7280; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
		.kpi-value { display: block; font-size: 22px; font-weight: 700; color: #1f2937; line-height: 1.2; }
		.kpi-progress { height: 4px; background: #e5e7eb; border-radius: 2px; margin-top: 8px; overflow: hidden; }
		.kpi-progress-bar { height: 100%; border-radius: 2px; transition: width 0.3s; }
		.kpi-info .kpi-progress-bar { background: linear-gradient(90deg, #3b82f6, #2563eb); }
		.kpi-success .kpi-progress-bar { background: linear-gradient(90deg, #10b981, #059669); }
		.kpi-sub { display: block; font-size: 11px; color: #9ca3af; margin-top: 4px; }
		
		/* Action Bar */
		.action-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding: 12px 16px; background: #f8fafc; border-radius: 10px; flex-wrap: wrap; gap: 12px; }
		.action-bar-left, .action-bar-right { display: flex; gap: 8px; flex-wrap: wrap; }
		
		/* Bills Accordion */
		.bills-accordion { display: flex; flex-direction: column; gap: 12px; }
		.bill-card { background: white; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; transition: all 0.2s; }
		.bill-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
		.bill-card.expanded { box-shadow: 0 4px 16px rgba(0,0,0,0.1); }
		.bill-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; cursor: pointer; background: #fafbfc; transition: background 0.2s; }
		.bill-header:hover { background: #f1f5f9; }
		.bill-header-left { display: flex; align-items: center; gap: 12px; }
		.chevron-icon { transition: transform 0.2s; color: #9ca3af; }
		.bill-card.expanded .chevron-icon { transform: rotate(180deg); }
		.bill-info { display: flex; flex-direction: column; }
		.bill-title { font-size: 15px; font-weight: 600; color: #1f2937; }
		.bill-desc { font-size: 12px; color: #6b7280; margin-top: 2px; }
		.bill-header-right { display: flex; gap: 24px; }
		.bill-stat { display: flex; flex-direction: column; align-items: flex-end; }
		.stat-label { font-size: 10px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.5px; }
		.stat-value { font-size: 14px; font-weight: 600; color: #374151; }
		.balance-value { color: #059669; }
		.bill-content { border-top: 1px solid #e2e8f0; }
		.bill-toolbar { padding: 12px 20px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; }
		.no-bills-message, .no-items-message { text-align: center; padding: 40px 20px; color: #9ca3af; font-size: 14px; }

		/* Items Table */
		.items-table-wrapper { overflow-x: auto; }
		.items-table { width: 100%; border-collapse: collapse; font-size: 12px; }
		.items-table th { background: #f8fafc; padding: 8px 10px; text-align: left; font-weight: 500; color: #6b7280; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #e2e8f0; white-space: nowrap; }
		.items-table td { padding: 10px; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }
		.items-table tr:hover { background: #fafbfc; }
		.items-table tr.fully-billed { opacity: 0.6; }
		.col-desc { min-width: 180px; }
		.col-unit { width: 50px; text-align: center; }
		.col-num { width: 80px; text-align: right; white-space: nowrap; }
		.col-group { text-align: center; background: #f1f5f9; }
		.col-highlight-blue { background: #eff6ff !important; }
		.col-highlight-green { background: #f0fdf4 !important; }
		.col-status { width: 90px; }
		.col-actions { width: 140px; }
		.font-bold { font-weight: 600; }
		.item-desc-wrapper { display: flex; flex-direction: column; gap: 2px; }
		.item-code { font-size: 9px; color: #6366f1; background: #eef2ff; padding: 2px 6px; border-radius: 4px; display: inline-block; margin-bottom: 2px; }
		.item-desc { color: #374151; line-height: 1.3; font-size: 12px; }
		.current-qty-input, .current-value-input { width: 70px; padding: 5px 6px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 12px; text-align: right; transition: all 0.2s; }
		.current-qty-input:focus, .current-value-input:focus { outline: none; border-color: #5e64ff; box-shadow: 0 0 0 3px rgba(94, 100, 255, 0.1); }
		.current-qty-input:disabled, .current-value-input:disabled { background: #f3f4f6; color: #9ca3af; }
		.balance-cell { color: #059669; font-weight: 500; }
		
		/* Status Pills */
		.status-pill { display: inline-block; padding: 3px 8px; border-radius: 20px; font-size: 10px; font-weight: 500; }
		.status-success { background: #d1fae5; color: #065f46; }
		.status-warning { background: #fef3c7; color: #92400e; }
		.status-default { background: #f3f4f6; color: #6b7280; }
		
		/* Action Icon Buttons */
		.action-icons { display: flex; gap: 4px; justify-content: center; }
		.action-icon-btn { width: 30px; height: 30px; border-radius: 6px; border: 1px solid #e2e8f0; background: white; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.2s; color: #6b7280; }
		.action-icon-btn:hover:not(:disabled) { transform: scale(1.05); }
		.action-icon-btn:disabled { opacity: 0.4; cursor: not-allowed; }
		.action-invoice:hover:not(:disabled) { background: #eff6ff; color: #2563eb; border-color: #bfdbfe; }
		.action-history:hover:not(:disabled) { background: #fef3c7; color: #d97706; border-color: #fde68a; }
		.action-cost:hover:not(:disabled) { background: #d1fae5; color: #059669; border-color: #a7f3d0; }
		.action-edit:hover:not(:disabled) { background: #f3e8ff; color: #7c3aed; border-color: #ddd6fe; }
		
		/* Empty State */
		.boq-empty-state { text-align: center; padding: 60px 20px; background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%); border-radius: 16px; border: 2px dashed #e2e8f0; }
		.empty-icon { margin-bottom: 20px; color: #cbd5e0; }
		.boq-empty-state h3 { font-size: 20px; font-weight: 600; color: #374151; margin-bottom: 8px; }
		.boq-empty-state p { color: #6b7280; margin-bottom: 24px; max-width: 400px; margin-left: auto; margin-right: auto; }
	</style>`;
}
