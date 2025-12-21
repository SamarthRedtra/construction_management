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
			if (r.message && r.message.has_boq) {
				// BOQ exists - show dashboard even if no bills yet
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
			<button class="btn-modern btn-warning-modern" onclick="create_dpr_quick('${frm.doc.name}')">
				<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
				Add DPR
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
						data-prev-amount="${amount.prev || 0}"
						step="0.001" min="0" ${isFullyBilled ? 'disabled' : ''}>
				</td>
				<td class="col-num col-highlight-blue">
					<input type="number" class="current-value-input" value="${amount.current || 0}" 
						data-item="${item.name}" data-max="${amount.balance + (amount.current || 0)}" data-rate="${amount.rate || 0}"
						data-prev-amount="${amount.prev || 0}" data-total-amount="${amount.total || 0}"
						step="0.01" min="0" ${isFullyBilled ? 'disabled' : ''}>
				</td>
				<td class="col-num col-highlight-green">${format_currency(amount.prev)}</td>
				<td class="col-num col-highlight-green curr-amount-cell" data-item="${item.name}">${format_currency(amount.current)}</td>
				<td class="col-num col-highlight-green font-bold accum-amount-cell" data-item="${item.name}">${format_currency(amount.to_date)}</td>
				<td class="col-num balance-cell" data-item="${item.name}">${format_currency(amount.balance)}</td>
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
	container.find('.current-qty-input').on('change input', function() {
		const input = $(this);
		const itemName = input.data('item');
		const maxQty = parseFloat(input.data('max')) || 0;
		const rate = parseFloat(input.data('rate')) || 0;
		const prevAmount = parseFloat(input.data('prev-amount')) || 0;
		let newQty = parseFloat(input.val()) || 0;
		
		if (newQty < 0) { newQty = 0; input.val(0); }
		if (newQty > maxQty) {
			frappe.show_alert({message: __('Quantity cannot exceed balance ({0})', [maxQty]), indicator: 'orange'});
			newQty = maxQty;
			input.val(maxQty);
		}
		
		// Auto-update value input
		const row = input.closest('tr');
		const valueInput = row.find('.current-value-input');
		const newValue = newQty * rate;
		valueInput.val(newValue.toFixed(2));
		
		// Update display cells in real-time
		const totalAmount = parseFloat(valueInput.data('total-amount')) || 0;
		const accumAmount = prevAmount + newValue;
		const balanceAmount = totalAmount - accumAmount;
		
		row.find('.curr-amount-cell').text(format_currency(newValue));
		row.find('.accum-amount-cell').text(format_currency(accumAmount));
		row.find('.balance-cell').text(format_currency(balanceAmount));
		
		// Debounce the server update
		clearTimeout(input.data('timeout'));
		input.data('timeout', setTimeout(() => {
			update_boq_item_current(itemName, newQty, frm);
		}, 500));
	});
	
	// Handle Value input change - auto-calculate Qty
	container.find('.current-value-input').on('change input', function() {
		const input = $(this);
		const itemName = input.data('item');
		const maxValue = parseFloat(input.data('max')) || 0;
		const rate = parseFloat(input.data('rate')) || 0;
		const prevAmount = parseFloat(input.data('prev-amount')) || 0;
		const totalAmount = parseFloat(input.data('total-amount')) || 0;
		let newValue = parseFloat(input.val()) || 0;
		
		if (newValue < 0) { newValue = 0; input.val(0); }
		if (newValue > maxValue) {
			frappe.show_alert({message: __('Value cannot exceed balance'), indicator: 'orange'});
			newValue = maxValue;
			input.val(maxValue.toFixed(2));
		}
		
		// Auto-update qty input
		const row = input.closest('tr');
		const qtyInput = row.find('.current-qty-input');
		const newQty = rate > 0 ? newValue / rate : 0;
		qtyInput.val(newQty.toFixed(3));
		
		// Update display cells in real-time
		const accumAmount = prevAmount + newValue;
		const balanceAmount = totalAmount - accumAmount;
		
		row.find('.curr-amount-cell').text(format_currency(newValue));
		row.find('.accum-amount-cell').text(format_currency(accumAmount));
		row.find('.balance-cell').text(format_currency(balanceAmount));
		
		// Debounce the server update
		clearTimeout(input.data('timeout'));
		input.data('timeout', setTimeout(() => {
			update_boq_item_current(itemName, newQty, frm);
		}, 500));
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
	// Use only_value option to get plain text without HTML wrapper
	return frappe.format(value, { fieldtype: 'Currency' }, { only_value: true });
}

function format_number(value) {
	if (value === null || value === undefined) return '-';
	return frappe.format(value, { fieldtype: 'Float', precision: 3 }, { only_value: true });
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
			{fieldname: 'total_qty', label: 'Total Quantity', fieldtype: 'Float', reqd: 1, change: function() {
				let qty = d.get_value('total_qty') || 0;
				let rate = d.get_value('rate') || 0;
				d.set_value('total_amount', qty * rate);
			}},
			{fieldname: 'rate', label: 'Rate', fieldtype: 'Currency', reqd: 1, change: function() {
				let qty = d.get_value('total_qty') || 0;
				let rate = d.get_value('rate') || 0;
				d.set_value('total_amount', qty * rate);
			}},
			{fieldname: 'total_amount', label: 'Total Amount', fieldtype: 'Currency', read_only: 1}
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
	const boqItem = data.boq_item || {};
	const ledgerEntries = data.ledger_entries || [];
	
	// Build ledger entries table with prev/curr/accumulated columns
	let ledgerRows = ledgerEntries.length > 0 ? ledgerEntries.map((entry, idx) => {
		const refLink = entry.reference_doctype === 'Sales Invoice' && entry.reference_name 
			? `<a href="/app/sales-invoice/${entry.reference_name}" class="invoice-link">${entry.reference_name}</a>`
			: (entry.reference_name || '-');
		
		const statusClass = entry.invoice_status === 'Paid' ? 'status-success' : 
			(entry.invoice_status === 'Unpaid' || entry.invoice_status === 'Overdue') ? 'status-warning' : 'status-default';
		
		return `
		<tr>
			<td class="text-center">${idx + 1}</td>
			<td>${entry.posting_date}</td>
			<td>${refLink}</td>
			<td class="text-center">${entry.source || '-'}</td>
			<td class="text-center">${entry.unit || '-'}</td>
			<td class="text-right col-prev">${format_number(entry.prev_qty)}</td>
			<td class="text-right col-curr">${format_number(entry.current_qty)}</td>
			<td class="text-right col-accum font-bold">${format_number(entry.accumulated_qty)}</td>
			<td class="text-right col-prev">${format_currency(entry.prev_amount)}</td>
			<td class="text-right col-curr">${format_currency(entry.current_amount)}</td>
			<td class="text-right col-accum font-bold">${format_currency(entry.accumulated_amount)}</td>
			<td class="text-center">${entry.pay_cert || '-'}</td>
			<td><span class="status-pill ${statusClass}">${entry.invoice_status || entry.source}</span></td>
		</tr>
		`;
	}).join('') : '<tr><td colspan="13" class="text-center text-muted">No billing history found</td></tr>';
	
	const d = new frappe.ui.Dialog({ title: __('Invoice History - Progressive Billing'), size: 'extra-large', fields: [{fieldtype: 'HTML', fieldname: 'invoice_html'}] });
	d.fields_dict.invoice_html.$wrapper.html(`
		<div class="boq-item-header">
			<div class="boq-item-desc">${boqItem.description || 'BOQ Item'}</div>
			<div class="boq-item-meta">
				<span><strong>Unit:</strong> ${boqItem.unit || '-'}</span>
				<span><strong>Rate:</strong> ${format_currency(boqItem.rate)}</span>
				<span><strong>Total Qty:</strong> ${format_number(boqItem.total_qty)}</span>
				<span><strong>Total Amount:</strong> ${format_currency(boqItem.total_amount)}</span>
			</div>
		</div>
		<div class="invoice-summary-grid">
			<div class="summary-card"><span class="summary-label">Total Invoices</span><span class="summary-value">${summary.invoice_count || 0}</span></div>
			<div class="summary-card info"><span class="summary-label">Accumulated Qty</span><span class="summary-value">${format_number(summary.accumulated_qty)}</span></div>
			<div class="summary-card info"><span class="summary-label">Accumulated Amount</span><span class="summary-value">${format_currency(summary.accumulated_amount)}</span></div>
			<div class="summary-card success"><span class="summary-label">Collected</span><span class="summary-value">${format_currency(summary.total_collected)}</span></div>
			<div class="summary-card warning"><span class="summary-label">Pending Payment</span><span class="summary-value">${format_currency(summary.pending)}</span></div>
			<div class="summary-card balance"><span class="summary-label">Balance Qty</span><span class="summary-value">${format_number(summary.balance_qty)}</span></div>
			<div class="summary-card balance"><span class="summary-label">Balance Amount</span><span class="summary-value">${format_currency(summary.balance_amount)}</span></div>
		</div>
		<h4 style="margin: 20px 0 10px; font-size: 14px; font-weight: 600;">📋 BOQ Progress Ledger</h4>
		<div class="ledger-table-wrapper">
			<table class="invoice-history-table ledger-table">
				<thead>
					<tr>
						<th rowspan="2" class="text-center">#</th>
						<th rowspan="2">Date</th>
						<th rowspan="2">Reference</th>
						<th rowspan="2" class="text-center">Source</th>
						<th rowspan="2" class="text-center">Unit</th>
						<th colspan="3" class="text-center col-group-qty">Quantity</th>
						<th colspan="3" class="text-center col-group-amt">Amount</th>
						<th rowspan="2" class="text-center">Pay Cert</th>
						<th rowspan="2">Status</th>
					</tr>
					<tr>
						<th class="text-right col-prev">Prev</th>
						<th class="text-right col-curr">Curr</th>
						<th class="text-right col-accum">Accum</th>
						<th class="text-right col-prev">Prev</th>
						<th class="text-right col-curr">Curr</th>
						<th class="text-right col-accum">Accum</th>
					</tr>
				</thead>
				<tbody>${ledgerRows}</tbody>
			</table>
		</div>
		<style>
			.boq-item-header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 16px; border-radius: 8px; margin-bottom: 16px; }
			.boq-item-desc { font-size: 15px; font-weight: 600; margin-bottom: 8px; }
			.boq-item-meta { display: flex; gap: 20px; font-size: 12px; opacity: 0.9; flex-wrap: wrap; }
			.invoice-summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; margin-bottom: 20px; }
			.summary-card { background: #f8f9fa; border-radius: 8px; padding: 14px; text-align: center; }
			.summary-card.info { background: #e0f2fe; }
			.summary-card.success { background: #d1fae5; }
			.summary-card.warning { background: #fef3c7; }
			.summary-card.balance { background: #ede9fe; }
			.summary-label { display: block; font-size: 10px; color: #6c757d; margin-bottom: 4px; text-transform: uppercase; }
			.summary-value { display: block; font-size: 16px; font-weight: 600; }
			.ledger-table-wrapper { overflow-x: auto; }
			.invoice-history-table { width: 100%; border-collapse: collapse; font-size: 12px; }
			.invoice-history-table th, .invoice-history-table td { padding: 10px 8px; border-bottom: 1px solid #e9ecef; }
			.invoice-history-table th { background: #f8f9fa; font-weight: 500; font-size: 10px; text-transform: uppercase; white-space: nowrap; }
			.col-group-qty { background: #eff6ff !important; }
			.col-group-amt { background: #f0fdf4 !important; }
			.col-prev { background: #fafafa; }
			.col-curr { background: #fffbeb; }
			.col-accum { background: #f0fdf4; }
			.font-bold { font-weight: 600; }
			.invoice-link { color: #5e64ff; text-decoration: none; font-weight: 500; }
			.invoice-link:hover { text-decoration: underline; }
			.status-pill { display: inline-block; padding: 3px 8px; border-radius: 12px; font-size: 10px; font-weight: 500; }
			.status-success { background: #d1fae5; color: #065f46; }
			.status-warning { background: #fef3c7; color: #92400e; }
			.status-default { background: #f3f4f6; color: #6b7280; }
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
					<tr><td><span class="cost-badge overhead">Overhead</span></td><td class="text-right">${format_currency(cost.overhead || 0)}</td><td class="text-right">${cost.total > 0 ? (((cost.overhead || 0) / cost.total) * 100).toFixed(1) : 0}%</td></tr>
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
			.cost-badge.overhead { background: #f3e8ff; color: #7c3aed; }
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
		.btn-warning-modern { background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; }
		.btn-warning-modern:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(245, 158, 11, 0.4); }
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


// Quick DPR Creation with Modern UI - Multi-select for Employees/Assets
window.create_dpr_quick = function(project) {
	// First fetch BOQ items for the project
	frappe.call({
		method: 'construction_management.api.dpr_utils.get_boq_items_for_project',
		args: { project: project },
		callback: function(r) {
			if (r.message && r.message.length > 0) {
				show_dpr_dialog(project, r.message);
			} else {
				frappe.msgprint(__('No BOQ Items found for this project. Please create BOQ Items first.'));
			}
		}
	});
};

function show_dpr_dialog(project, boq_items) {
	// Build BOQ Item options
	const boq_options = boq_items.map(item => ({
		value: item.name,
		label: `${item.bill_number} - ${item.description.substring(0, 50)}${item.description.length > 50 ? '...' : ''}`
	}));
	
	const d = new frappe.ui.Dialog({
		title: __('Quick Daily Progress Record'),
		size: 'large',
		fields: [
			{
				fieldtype: 'HTML',
				fieldname: 'dpr_header',
				options: `
					<div style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; padding: 16px; border-radius: 8px; margin-bottom: 20px;">
						<h4 style="margin: 0; font-size: 16px;">📋 Record Daily Progress</h4>
						<p style="margin: 8px 0 0 0; font-size: 13px; opacity: 0.9;">Enter costs for today's work. Select a BOQ Item and add costs below.</p>
					</div>
				`
			},
			{
				fieldname: 'date',
				label: __('Date'),
				fieldtype: 'Date',
				default: frappe.datetime.get_today(),
				reqd: 1
			},
			{
				fieldname: 'boq_item',
				label: __('BOQ Item'),
				fieldtype: 'Link',
				options: 'BOQ Item',
				reqd: 1,
				get_query: function() {
					return {
						filters: { project: project }
					};
				}
			},
			{
				fieldtype: 'Section Break',
				label: __('Cost Entry'),
				fieldname: 'cost_section'
			},
			{
				fieldtype: 'HTML',
				fieldname: 'cost_tabs',
				options: `
					<div class="dpr-cost-tabs">
						<button type="button" class="dpr-tab active" data-tab="labour">👷 Labour</button>
						<button type="button" class="dpr-tab" data-tab="material">📦 Material</button>
						<button type="button" class="dpr-tab" data-tab="asset">🚜 Asset</button>
						<button type="button" class="dpr-tab" data-tab="subcontract">🏗️ Subcontract</button>
						<button type="button" class="dpr-tab" data-tab="expense">💰 Expense</button>
					</div>
					<style>
						.dpr-cost-tabs { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
						.dpr-tab { padding: 10px 16px; border: 1px solid #e2e8f0; border-radius: 8px; background: white; cursor: pointer; font-size: 13px; transition: all 0.2s; }
						.dpr-tab:hover { background: #f8fafc; }
						.dpr-tab.active { background: linear-gradient(135deg, #5e64ff 0%, #7c3aed 100%); color: white; border-color: transparent; }
						.dpr-cost-panel { display: none; padding: 16px; background: #f8fafc; border-radius: 8px; }
						.dpr-cost-panel.active { display: block; }
						.cost-input-row { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }
						.cost-input-row label { min-width: 100px; font-size: 13px; color: #4a5568; }
						.cost-input-row input, .cost-input-row select { flex: 1; padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px; }
						.cost-input-row input:focus, .cost-input-row select:focus { outline: none; border-color: #5e64ff; box-shadow: 0 0 0 3px rgba(94, 100, 255, 0.1); }
						.total-display { background: white; padding: 12px 16px; border-radius: 8px; margin-top: 16px; display: flex; justify-content: space-between; align-items: center; }
						.total-label { font-size: 14px; color: #6b7280; }
						.total-value { font-size: 20px; font-weight: 700; color: #1f2937; }
					</style>
				`
			},
			{
				fieldtype: 'HTML',
				fieldname: 'cost_panels',
				options: `
					<div id="labour-panel" class="dpr-cost-panel active">
						<div class="cost-input-row">
							<label>Labour Cost</label>
							<input type="number" id="dpr-labour-cost" placeholder="Enter amount" value="0" step="0.01">
						</div>
						<p style="font-size: 12px; color: #6b7280; margin: 0;">💡 For detailed employee-wise entry, use the full DPR form</p>
					</div>
					<div id="material-panel" class="dpr-cost-panel">
						<div class="cost-input-row">
							<label>Material Cost</label>
							<input type="number" id="dpr-material-cost" placeholder="Enter amount" value="0" step="0.01">
						</div>
						<p style="font-size: 12px; color: #6b7280; margin: 0;">💡 For stock entry with items, use the full DPR form</p>
					</div>
					<div id="asset-panel" class="dpr-cost-panel">
						<div class="cost-input-row">
							<label>Asset Cost</label>
							<input type="number" id="dpr-asset-cost" placeholder="Enter amount" value="0" step="0.01">
						</div>
						<p style="font-size: 12px; color: #6b7280; margin: 0;">💡 For asset-wise entry with rates, use the full DPR form</p>
					</div>
					<div id="subcontract-panel" class="dpr-cost-panel">
						<div class="cost-input-row">
							<label>Subcontract Cost</label>
							<input type="number" id="dpr-subcontract-cost" placeholder="Enter amount" value="0" step="0.01">
						</div>
					</div>
					<div id="expense-panel" class="dpr-cost-panel">
						<div class="cost-input-row">
							<label>Other Expense</label>
							<input type="number" id="dpr-expense-cost" placeholder="Enter amount" value="0" step="0.01">
						</div>
						<p style="font-size: 12px; color: #6b7280; margin: 0;">💡 For expense-wise entry with accounts, use the full DPR form</p>
					</div>
					<div class="total-display">
						<span class="total-label">Total Cost</span>
						<span class="total-value" id="dpr-total-cost">0.00</span>
					</div>
				`
			},
			{
				fieldtype: 'Section Break',
				fieldname: 'remarks_section'
			},
			{
				fieldname: 'remarks',
				label: __('Remarks'),
				fieldtype: 'Small Text'
			}
		],
		primary_action_label: __('Create DPR'),
		primary_action: function() {
			const values = d.get_values();
			if (!values) return;
			
			const labour_cost = parseFloat($('#dpr-labour-cost').val()) || 0;
			const material_cost = parseFloat($('#dpr-material-cost').val()) || 0;
			const asset_cost = parseFloat($('#dpr-asset-cost').val()) || 0;
			const subcontract_cost = parseFloat($('#dpr-subcontract-cost').val()) || 0;
			const expense_cost = parseFloat($('#dpr-expense-cost').val()) || 0;
			const total_cost = labour_cost + material_cost + asset_cost + subcontract_cost + expense_cost;
			
			if (total_cost <= 0) {
				frappe.show_alert({message: __('Please enter at least one cost value'), indicator: 'orange'});
				return;
			}
			
			frappe.call({
				method: 'frappe.client.insert',
				args: {
					doc: {
						doctype: 'Daily Progress Record',
						project: project,
						boq_item: values.boq_item,
						date: values.date,
						labour_cost: labour_cost,
						material_cost: material_cost,
						asset_cost: asset_cost,
						subcontract_cost: subcontract_cost,
						expense_cost: expense_cost,
						remarks: values.remarks
					}
				},
				callback: function(r) {
					if (r.message) {
						d.hide();
						frappe.show_alert({message: __('DPR {0} created', [r.message.name]), indicator: 'green'});
						
						// Ask if user wants to submit
						frappe.confirm(
							__('DPR created successfully. Do you want to submit it now?'),
							function() {
								frappe.call({
									method: 'frappe.client.submit',
									args: { doc: r.message },
									callback: function() {
										frappe.show_alert({message: __('DPR submitted'), indicator: 'green'});
										cur_frm.reload_doc();
									}
								});
							},
							function() {
								cur_frm.reload_doc();
							}
						);
					}
				}
			});
		},
		secondary_action_label: __('Open Full Form'),
		secondary_action: function() {
			d.hide();
			frappe.new_doc('Daily Progress Record', {
				project: project
			});
		}
	});
	
	d.show();
	
	// Attach tab switching logic
	setTimeout(() => {
		d.$wrapper.find('.dpr-tab').on('click', function() {
			const tab = $(this).data('tab');
			d.$wrapper.find('.dpr-tab').removeClass('active');
			$(this).addClass('active');
			d.$wrapper.find('.dpr-cost-panel').removeClass('active');
			d.$wrapper.find(`#${tab}-panel`).addClass('active');
		});
		
		// Attach cost calculation
		d.$wrapper.find('input[type="number"]').on('input', function() {
			const labour = parseFloat($('#dpr-labour-cost').val()) || 0;
			const material = parseFloat($('#dpr-material-cost').val()) || 0;
			const asset = parseFloat($('#dpr-asset-cost').val()) || 0;
			const subcontract = parseFloat($('#dpr-subcontract-cost').val()) || 0;
			const expense = parseFloat($('#dpr-expense-cost').val()) || 0;
			const total = labour + material + asset + subcontract + expense;
			$('#dpr-total-cost').text(format_currency(total));
		});
	}, 100);
}


// ============================================
// Clean DPR Dialog using Frappe Native Fields
// ============================================

// Store selected items for DPR
let dpr_selected_employees = [];
let dpr_selected_assets = [];
let dpr_selected_materials = [];
let dpr_selected_expenses = [];
let dpr_selected_overheads = [];

// Override the show_dpr_dialog function with clean Frappe-native version
window.show_dpr_dialog_enhanced = function(project) {
	// Reset selections
	dpr_selected_employees = [];
	dpr_selected_assets = [];
	dpr_selected_materials = [];
	dpr_selected_expenses = [];
	dpr_selected_overheads = [];
	
	const d = new frappe.ui.Dialog({
		title: __('Quick Daily Progress Record'),
		size: 'extra-large',
		fields: [
			{
				fieldtype: 'HTML',
				fieldname: 'dpr_header',
				options: '<div style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; padding: 16px; border-radius: 8px; margin-bottom: 16px;"><h4 style="margin: 0; font-size: 16px;">📋 Record Daily Progress</h4><p style="margin: 8px 0 0 0; font-size: 13px; opacity: 0.9;">Add employees, materials, assets, expenses and overheads. Rates are auto-fetched from system.</p></div>'
			},
			{ fieldname: 'date', label: __('Date'), fieldtype: 'Date', default: frappe.datetime.get_today(), reqd: 1 },
			{ fieldname: 'boq_item', label: __('BOQ Item'), fieldtype: 'Link', options: 'BOQ Item', reqd: 1, 
				get_query: () => ({ filters: { project: project } }) 
			},
			// Labour Section
			{ fieldtype: 'Section Break', label: __('👷 Labour Cost') },
			{ fieldname: 'employee', label: __('Add Employee'), fieldtype: 'Link', options: 'Employee',
				get_query: () => ({ filters: { status: 'Active' } }),
				change: function() {
					const emp = d.get_value('employee');
					if (emp) add_employee_to_list(d, emp, project);
				}
			},
			{ fieldtype: 'HTML', fieldname: 'employees_list', options: '<div id="dpr-employees-list"></div>' },
			// Material Section
			{ fieldtype: 'Section Break', label: __('📦 Material Cost') },
			{ fieldname: 'item_code', label: __('Add Item'), fieldtype: 'Link', options: 'Item',
				get_query: () => ({ filters: { is_stock_item: 1 } }),
				change: function() {
					const item = d.get_value('item_code');
					if (item) show_material_qty_dialog(d, item, project);
				}
			},
			{ fieldtype: 'HTML', fieldname: 'materials_list', options: '<div id="dpr-materials-list"></div>' },
			// Asset Section
			{ fieldtype: 'Section Break', label: __('🚜 Asset Cost') },
			{ fieldname: 'asset', label: __('Add Asset'), fieldtype: 'Link', options: 'Asset',
				get_query: () => ({ filters: { status: ['in', ['Submitted', 'Partially Depreciated']] } }),
				change: function() {
					const asset = d.get_value('asset');
					if (asset) add_asset_to_list(d, asset, project);
				}
			},
			{ fieldtype: 'HTML', fieldname: 'assets_list', options: '<div id="dpr-assets-list"></div>' },
			// Expense Section
			{ fieldtype: 'Section Break', label: __('💰 Expenses') },
			{ fieldname: 'expense_type', label: __('Add Expense'), fieldtype: 'Link', options: 'Expense Claim Type',
				change: function() {
					const expType = d.get_value('expense_type');
					if (expType) show_expense_dialog(d, expType);
				}
			},
			{ fieldtype: 'HTML', fieldname: 'expenses_list', options: '<div id="dpr-expenses-list"></div>' },
			// Overhead Section
			{ fieldtype: 'Section Break', label: __('📊 Overheads') },
			{ fieldname: 'overhead_account', label: __('Add Overhead'), fieldtype: 'Link', options: 'Account',
				get_query: () => ({ filters: { account_type: ['in', ['Expense Account', 'Cost of Goods Sold']], is_group: 0 } }),
				change: function() {
					const acc = d.get_value('overhead_account');
					if (acc) show_overhead_dialog(d, acc);
				}
			},
			{ fieldtype: 'HTML', fieldname: 'overheads_list', options: '<div id="dpr-overheads-list"></div>' },
			// Subcontract Section
			{ fieldtype: 'Section Break', label: __('🏗️ Subcontract') },
			{ fieldname: 'subcontract_cost', label: __('Subcontract Cost'), fieldtype: 'Currency', default: 0,
				change: function() { update_dpr_totals(d); }
			},
			// Totals Section
			{ fieldtype: 'Section Break' },
			{ fieldtype: 'HTML', fieldname: 'totals_display', options: '<div id="dpr-totals" style="background: #f0fdf4; padding: 16px; border-radius: 8px; margin-top: 8px;"><div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 16px;"><div><span style="font-size: 11px; color: #6b7280; text-transform: uppercase;">Labour</span><div id="dpr-labour-total" style="font-size: 16px; font-weight: 600; color: #1f2937;">0.00</div></div><div><span style="font-size: 11px; color: #6b7280; text-transform: uppercase;">Material</span><div id="dpr-material-total" style="font-size: 16px; font-weight: 600; color: #1f2937;">0.00</div></div><div><span style="font-size: 11px; color: #6b7280; text-transform: uppercase;">Asset</span><div id="dpr-asset-total" style="font-size: 16px; font-weight: 600; color: #1f2937;">0.00</div></div><div><span style="font-size: 11px; color: #6b7280; text-transform: uppercase;">Expense</span><div id="dpr-expense-total" style="font-size: 16px; font-weight: 600; color: #1f2937;">0.00</div></div><div><span style="font-size: 11px; color: #6b7280; text-transform: uppercase;">Overhead</span><div id="dpr-overhead-total" style="font-size: 16px; font-weight: 600; color: #1f2937;">0.00</div></div><div><span style="font-size: 11px; color: #6b7280; text-transform: uppercase;">Subcontract</span><div id="dpr-subcontract-total" style="font-size: 16px; font-weight: 600; color: #1f2937;">0.00</div></div><div style="border-left: 2px solid #059669; padding-left: 16px;"><span style="font-size: 11px; color: #059669; font-weight: 600; text-transform: uppercase;">TOTAL COST</span><div id="dpr-grand-total" style="font-size: 22px; font-weight: 700; color: #059669;">0.00</div></div></div></div>' },
			{ fieldtype: 'Section Break' },
			{ fieldname: 'remarks', label: __('Remarks'), fieldtype: 'Small Text' }
		],
		primary_action_label: __('Create DPR'),
		primary_action: function() { create_dpr_from_dialog(d, project); },
		secondary_action_label: __('Open Full Form'),
		secondary_action: function() { d.hide(); frappe.new_doc('Daily Progress Record', { project: project }); }
	});
	
	d.show();
	
	// Add styles and render lists
	setTimeout(() => {
		$('<style>.dpr-item-card{display:flex;align-items:center;gap:12px;padding:10px 12px;background:white;border-radius:8px;margin-bottom:8px;border:1px solid #e2e8f0;transition:all 0.2s}.dpr-item-card:hover{border-color:#cbd5e1;box-shadow:0 2px 4px rgba(0,0,0,0.05)}.dpr-item-info{flex:1;min-width:0}.dpr-item-name{font-weight:500;color:#1f2937;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.dpr-item-sub{font-size:12px;color:#6b7280;margin-top:2px}.dpr-item-input{width:70px;padding:6px 8px;border:1px solid #d1d5db;border-radius:6px;text-align:right;font-size:13px}.dpr-item-input:focus{outline:none;border-color:#5e64ff;box-shadow:0 0 0 2px rgba(94,100,255,0.1)}.dpr-item-amount{min-width:90px;text-align:right;font-weight:600;color:#059669;font-size:14px}.dpr-remove-btn{background:#fee2e2;color:#dc2626;border:none;width:28px;height:28px;border-radius:6px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.2s}.dpr-remove-btn:hover{background:#fecaca}.dpr-empty{text-align:center;padding:24px;color:#9ca3af;font-size:13px;background:#f9fafb;border-radius:8px;border:1px dashed #e2e8f0}.rate-source-tag{display:inline-block;padding:1px 6px;border-radius:4px;font-size:9px;font-weight:500;background:#e0f2fe;color:#0369a1;margin-left:4px;text-transform:uppercase}</style>').appendTo(d.$wrapper);
		render_employees_list();
		render_materials_list();
		render_assets_list();
		render_expenses_list();
		render_overheads_list();
	}, 100);
};

// Helper functions for DPR dialog

function add_employee_to_list(d, employee, project) {
	if (dpr_selected_employees.find(e => e.employee === employee)) {
		frappe.show_alert({message: __('Employee already added'), indicator: 'orange'});
		d.set_value('employee', '');
		return;
	}
	
	frappe.call({
		method: 'construction_management.api.dpr_utils.get_employee_with_rate',
		args: { employee: employee },
		callback: function(r) {
			if (r.message) {
				const emp = r.message;
				const rate = emp.rate_per_day || 0;
				const source = emp.source || 'unknown';
				
				// If rate is 0 or source is manual_required, ask for manual entry
				if (!rate || source === 'manual_required') {
					frappe.prompt([
						{ fieldname: 'rate', label: __('Daily Rate'), fieldtype: 'Currency', reqd: 1, 
						  description: __('No salary rate found in Salary Structure Assignment or Salary Structure. Please enter daily rate manually.') }
					], function(values) {
						dpr_selected_employees.push({
							employee: employee, employee_name: emp.employee_name, designation: emp.designation || '',
							hours: 8, rate_per_day: values.rate, amount: values.rate, source: 'manual'
						});
						render_employees_list();
						update_dpr_totals(d);
					}, __('Enter Daily Rate for ' + emp.employee_name), __('Add'));
				} else {
					// Show source indicator
					const sourceLabel = source === 'cache' ? 'cached' : 
						(source === 'salary_structure_assignment' ? 'SSA' : 
						(source === 'salary_structure' ? 'SS' : source));
					
					dpr_selected_employees.push({
						employee: employee, employee_name: emp.employee_name, designation: emp.designation || '',
						hours: 8, rate_per_day: rate, amount: rate, source: sourceLabel
					});
					render_employees_list();
					update_dpr_totals(d);
				}
			}
			d.set_value('employee', '');
		}
	});
}

function add_asset_to_list(d, asset, project) {
	if (dpr_selected_assets.find(a => a.asset === asset)) {
		frappe.show_alert({message: __('Asset already added'), indicator: 'orange'});
		d.set_value('asset', '');
		return;
	}
	
	frappe.call({
		method: 'construction_management.api.dpr_utils.get_asset_with_rate',
		args: { asset: asset, project: project, date: d.get_value('date') },
		callback: function(r) {
			if (r.message) {
				const assetData = r.message;
				const rate = assetData.rate_per_day || 0;
				
				if (!rate) {
					frappe.prompt([
						{ fieldname: 'rate', label: __('Daily Rate'), fieldtype: 'Currency', reqd: 1,
						  description: __('No rate configured in Project Asset Billing. Please enter daily rate manually.') }
					], function(values) {
						dpr_selected_assets.push({
							asset: asset, asset_name: assetData.asset_name, hours: 8, rate_per_day: values.rate, amount: values.rate
						});
						render_assets_list();
						update_dpr_totals(d);
					}, __('Enter Daily Rate for ' + assetData.asset_name), __('Add'));
				} else {
					dpr_selected_assets.push({
						asset: asset, asset_name: assetData.asset_name, hours: 8, rate_per_day: rate, amount: rate
					});
					render_assets_list();
					update_dpr_totals(d);
				}
			}
			d.set_value('asset', '');
		}
	});
}

function show_material_qty_dialog(d, item_code, project) {
	if (dpr_selected_materials.find(m => m.item_code === item_code)) {
		frappe.show_alert({message: __('Item already added'), indicator: 'orange'});
		d.set_value('item_code', '');
		return;
	}
	
	frappe.call({
		method: 'construction_management.api.dpr_utils.get_item_details',
		args: { item_code: item_code },
		callback: function(r) {
			if (r.message) {
				const item = r.message;
				frappe.prompt([
					{ fieldname: 'qty', label: __('Quantity'), fieldtype: 'Float', reqd: 1, default: 1 },
					{ fieldname: 'warehouse', label: __('Source Warehouse'), fieldtype: 'Link', options: 'Warehouse', reqd: 1,
					  description: __('Stock will be transferred from this warehouse on submit') },
					{ fieldname: 'rate', label: __('Rate'), fieldtype: 'Currency', default: item.rate || item.valuation_rate || 0,
					  description: item.rate ? __('Rate from Price List') : __('Valuation Rate') }
				], function(values) {
					const amount = flt(values.qty) * flt(values.rate);
					dpr_selected_materials.push({
						item_code: item_code, item_name: item.item_name, warehouse: values.warehouse,
						qty: values.qty, uom: item.stock_uom, rate: values.rate, amount: amount
					});
					render_materials_list();
					update_dpr_totals(d);
				}, __('Add Material: ' + item.item_name), __('Add'));
			}
			d.set_value('item_code', '');
		}
	});
}

function show_expense_dialog(d, expense_type) {
	frappe.prompt([
		{ fieldname: 'description', label: __('Description'), fieldtype: 'Small Text' },
		{ fieldname: 'amount', label: __('Amount'), fieldtype: 'Currency', reqd: 1 }
	], function(values) {
		dpr_selected_expenses.push({
			expense_type: expense_type, description: values.description || '', amount: values.amount
		});
		render_expenses_list();
		update_dpr_totals(d);
	}, __('Add Expense: ' + expense_type), __('Add'));
	d.set_value('expense_type', '');
}

function show_overhead_dialog(d, account) {
	frappe.db.get_value('Account', account, 'account_name', (r) => {
		const account_name = r ? r.account_name : account;
		frappe.prompt([
			{ fieldname: 'description', label: __('Description'), fieldtype: 'Small Text' },
			{ fieldname: 'amount', label: __('Amount'), fieldtype: 'Currency', reqd: 1 }
		], function(values) {
			dpr_selected_overheads.push({
				account: account, account_name: account_name, description: values.description || '', amount: values.amount
			});
			render_overheads_list();
			update_dpr_totals(d);
		}, __('Add Overhead: ' + account_name), __('Add'));
	});
	d.set_value('overhead_account', '');
}

function render_employees_list() {
	let html = dpr_selected_employees.length === 0 
		? '<div class="dpr-empty">No employees added. Select an employee above to add.</div>'
		: '';
	dpr_selected_employees.forEach((emp, idx) => {
		const sourceTag = emp.source ? `<span class="rate-source-tag">${emp.source}</span>` : '';
		html += '<div class="dpr-item-card"><div class="dpr-item-info"><div class="dpr-item-name">' + emp.employee_name + '</div><div class="dpr-item-sub">' + (emp.designation || 'No designation') + ' • ' + format_currency(emp.rate_per_day) + '/day ' + sourceTag + '</div></div><div><input type="number" class="dpr-item-input emp-hours" value="' + emp.hours + '" step="0.5" min="0" max="24" data-idx="' + idx + '"> hrs</div><div class="dpr-item-amount">' + format_currency(emp.amount) + '</div><button type="button" class="dpr-remove-btn" onclick="remove_dpr_employee(' + idx + ')">✕</button></div>';
	});
	$('#dpr-employees-list').html(html);
	$('.emp-hours').off('input').on('input', function() {
		const idx = $(this).data('idx');
		const hours = parseFloat($(this).val()) || 8;
		dpr_selected_employees[idx].hours = hours;
		dpr_selected_employees[idx].amount = dpr_selected_employees[idx].rate_per_day * (hours / 8);
		render_employees_list();
		update_dpr_totals();
	});
}

function render_materials_list() {
	let html = dpr_selected_materials.length === 0 
		? '<div class="dpr-empty">No materials added. Select an item above to add.</div>'
		: '';
	dpr_selected_materials.forEach((mat, idx) => {
		html += '<div class="dpr-item-card"><div class="dpr-item-info"><div class="dpr-item-name">' + mat.item_name + '</div><div class="dpr-item-sub">' + mat.item_code + ' • ' + mat.warehouse + ' • ' + mat.qty + ' ' + mat.uom + ' @ ' + format_currency(mat.rate) + '</div></div><div class="dpr-item-amount">' + format_currency(mat.amount) + '</div><button type="button" class="dpr-remove-btn" onclick="remove_dpr_material(' + idx + ')">✕</button></div>';
	});
	$('#dpr-materials-list').html(html);
}

function render_assets_list() {
	let html = dpr_selected_assets.length === 0 
		? '<div class="dpr-empty">No assets added. Select an asset above to add.</div>'
		: '';
	dpr_selected_assets.forEach((asset, idx) => {
		html += '<div class="dpr-item-card"><div class="dpr-item-info"><div class="dpr-item-name">' + asset.asset_name + '</div><div class="dpr-item-sub">' + asset.asset + ' • ' + format_currency(asset.rate_per_day) + '/day</div></div><div><input type="number" class="dpr-item-input asset-hours" value="' + asset.hours + '" step="0.5" min="0" max="24" data-idx="' + idx + '"> hrs</div><div class="dpr-item-amount">' + format_currency(asset.amount) + '</div><button type="button" class="dpr-remove-btn" onclick="remove_dpr_asset(' + idx + ')">✕</button></div>';
	});
	$('#dpr-assets-list').html(html);
	$('.asset-hours').off('input').on('input', function() {
		const idx = $(this).data('idx');
		const hours = parseFloat($(this).val()) || 8;
		dpr_selected_assets[idx].hours = hours;
		dpr_selected_assets[idx].amount = dpr_selected_assets[idx].rate_per_day * (hours / 8);
		render_assets_list();
		update_dpr_totals();
	});
}

function render_expenses_list() {
	let html = dpr_selected_expenses.length === 0 
		? '<div class="dpr-empty">No expenses added. Select an expense type above to add.</div>'
		: '';
	dpr_selected_expenses.forEach((exp, idx) => {
		html += '<div class="dpr-item-card"><div class="dpr-item-info"><div class="dpr-item-name">' + exp.expense_type + '</div>' + (exp.description ? '<div class="dpr-item-sub">' + exp.description + '</div>' : '') + '</div><div class="dpr-item-amount">' + format_currency(exp.amount) + '</div><button type="button" class="dpr-remove-btn" onclick="remove_dpr_expense(' + idx + ')">✕</button></div>';
	});
	$('#dpr-expenses-list').html(html);
}

function render_overheads_list() {
	let html = dpr_selected_overheads.length === 0 
		? '<div class="dpr-empty">No overheads added. Select an account above to add.</div>'
		: '';
	dpr_selected_overheads.forEach((ovh, idx) => {
		html += '<div class="dpr-item-card"><div class="dpr-item-info"><div class="dpr-item-name">' + ovh.account_name + '</div>' + (ovh.description ? '<div class="dpr-item-sub">' + ovh.description + '</div>' : '') + '</div><div class="dpr-item-amount">' + format_currency(ovh.amount) + '</div><button type="button" class="dpr-remove-btn" onclick="remove_dpr_overhead(' + idx + ')">✕</button></div>';
	});
	$('#dpr-overheads-list').html(html);
}

window.remove_dpr_employee = function(idx) { dpr_selected_employees.splice(idx, 1); render_employees_list(); update_dpr_totals(); };
window.remove_dpr_material = function(idx) { dpr_selected_materials.splice(idx, 1); render_materials_list(); update_dpr_totals(); };
window.remove_dpr_asset = function(idx) { dpr_selected_assets.splice(idx, 1); render_assets_list(); update_dpr_totals(); };
window.remove_dpr_expense = function(idx) { dpr_selected_expenses.splice(idx, 1); render_expenses_list(); update_dpr_totals(); };
window.remove_dpr_overhead = function(idx) { dpr_selected_overheads.splice(idx, 1); render_overheads_list(); update_dpr_totals(); };

function update_dpr_totals(d) {
	const labourTotal = dpr_selected_employees.reduce((sum, e) => sum + flt(e.amount), 0);
	const materialTotal = dpr_selected_materials.reduce((sum, m) => sum + flt(m.amount), 0);
	const assetTotal = dpr_selected_assets.reduce((sum, a) => sum + flt(a.amount), 0);
	const expenseTotal = dpr_selected_expenses.reduce((sum, e) => sum + flt(e.amount), 0);
	const overheadTotal = dpr_selected_overheads.reduce((sum, o) => sum + flt(o.amount), 0);
	const subcontractTotal = d ? flt(d.get_value('subcontract_cost')) : flt($('[data-fieldname="subcontract_cost"] input').val());
	const grandTotal = labourTotal + materialTotal + assetTotal + expenseTotal + overheadTotal + subcontractTotal;
	
	// Use simple number formatting for totals display (not HTML)
	const fmt = (val) => frappe.format(val, {fieldtype: 'Currency'}, {only_value: true});
	
	$('#dpr-labour-total').text(fmt(labourTotal));
	$('#dpr-material-total').text(fmt(materialTotal));
	$('#dpr-asset-total').text(fmt(assetTotal));
	$('#dpr-expense-total').text(fmt(expenseTotal));
	$('#dpr-overhead-total').text(fmt(overheadTotal));
	$('#dpr-subcontract-total').text(fmt(subcontractTotal));
	$('#dpr-grand-total').text(fmt(grandTotal));
}

function create_dpr_from_dialog(d, project) {
	const values = d.get_values();
	if (!values) return;
	
	const labourTotal = dpr_selected_employees.reduce((sum, e) => sum + flt(e.amount), 0);
	const materialTotal = dpr_selected_materials.reduce((sum, m) => sum + flt(m.amount), 0);
	const assetTotal = dpr_selected_assets.reduce((sum, a) => sum + flt(a.amount), 0);
	const expenseTotal = dpr_selected_expenses.reduce((sum, e) => sum + flt(e.amount), 0);
	const overheadTotal = dpr_selected_overheads.reduce((sum, o) => sum + flt(o.amount), 0);
	const total = labourTotal + materialTotal + assetTotal + expenseTotal + overheadTotal + flt(values.subcontract_cost);
	
	if (total <= 0) {
		frappe.show_alert({message: __('Please add at least one cost entry'), indicator: 'orange'});
		return;
	}
	
	frappe.call({
		method: 'construction_management.api.dpr_utils.create_dpr_with_details',
		args: {
			project: project, 
			boq_item: values.boq_item, 
			date: values.date,
			employees: JSON.stringify(dpr_selected_employees),
			assets: JSON.stringify(dpr_selected_assets),
			materials: JSON.stringify(dpr_selected_materials),
			expenses: JSON.stringify(dpr_selected_expenses),
			overheads: JSON.stringify(dpr_selected_overheads),
			subcontract_cost: values.subcontract_cost || 0,
			remarks: values.remarks
		},
		callback: function(r) {
			if (r.message) {
				d.hide();
				frappe.show_alert({message: __('DPR {0} created successfully!', [r.message.name]), indicator: 'green'});
				frappe.confirm(__('DPR created. Submit now to create Stock Entries for materials?'), 
					function() {
						frappe.call({
							method: 'frappe.client.submit',
							args: { doctype: 'Daily Progress Record', name: r.message.name },
							callback: function() {
								frappe.show_alert({message: __('DPR submitted. Stock entries created.'), indicator: 'green'});
								cur_frm.reload_doc();
							}
						});
					},
					function() { cur_frm.reload_doc(); }
				);
			}
		}
	});
}

// Override the original create_dpr_quick to use clean version
window.create_dpr_quick = function(project) {
	window.show_dpr_dialog_enhanced(project);
};
