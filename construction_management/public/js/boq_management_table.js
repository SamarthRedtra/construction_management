// Copyright (c) 2024, Construction Management
// License: MIT
// Comprehensive BOQ Management Table with Revenue, Cost, and Profitability columns

/**
 * Helper function to safely convert to float (matches Frappe's flt)
 * Moved to top to ensure it's available for all functions
 */
function flt(value, precision = 5) {
	if (typeof frappe !== 'undefined' && frappe.utils && frappe.utils.flt) {
		return frappe.utils.flt(value, precision);
	}
	const num = parseFloat(value);
	if (isNaN(num)) return 0;
	return parseFloat(num.toFixed(precision));
}

const BOQ_QTY_PRECISION = 8;
const BOQ_QTY_STEP = '0.00000001';

/**
 * Render comprehensive BOQ management table
 * Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
 */
function render_boq_management_table(container, frm, bills) {
	if (!bills || bills.length === 0) {
		container.html('<div class="no-bills-message">No bills found. Click "Add Bill" to get started.</div>');
		return;
	}

	let html = '<div class="boq-management-table-container">';
	html += `
		<div class="boq-management-topbar">
			<div class="boq-search-container">
				<input type="text" class="form-control boq-search-input" placeholder="Search items or bills..." aria-label="Search BOQ items">
				<svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line>
				</svg>
			</div>
			<a class="variance-report-link" href="#" onclick="frappe.set_route('query-report', 'Project Sales Order Analysis'); return false;">
				View Variance Balance Report
				<svg class="variance-report-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
					<path d="M14 3h7v7"></path>
					<path d="M10 14L21 3"></path>
					<path d="M21 14v7h-7"></path>
					<path d="M3 10V3h7"></path>
					<path d="M3 21h7v-7"></path>
				</svg>
			</a>
		</div>
	`;

	// Render each bill as a collapsible section
	bills.forEach((bill, idx) => {
		const isExpanded = idx === 0;
		html += render_bill_section(bill, frm, isExpanded);
	});

	html += '</div>';
	html += get_table_styles();

	container.html(html);
	attach_table_events(container, frm);
}

/**
 * Render a single bill section with header and items table
 * Requirements: 7.5 - Bill-level financial summary display
 */
function render_bill_section(bill, frm, isExpanded) {
	const totals = bill.totals || {};
	const revenue = totals.revenue || {};
	const actual = totals.actual_costs || {};
	const profitability = totals.profitability || {};

	return `
		<div class="bill-section ${isExpanded ? 'expanded' : ''}" data-bill="${bill.name}">
			<div class="bill-header-row" onclick="toggleBillSection(this)">
				<div class="bill-header-left">
					<svg class="chevron-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<polyline points="6 9 12 15 18 9"></polyline>
					</svg>
					<div class="bill-info">
						<span class="bill-title">${bill.bill_no}</span>
						<span class="bill-title"> <a href="/app/boq-bill/${bill.name}" onclick="event.stopPropagation()">${bill.name}</a></span>
						${bill.description ? `<span class="bill-desc"><a href="/app/boq-bill/${bill.name}" onclick="event.stopPropagation()">${bill.description}</a></span>` : ''}
					</div>
				</div>
				<div class="bill-header-stats">
					<div class="bill-stat"><span class="stat-label">ITEMS</span><span class="stat-value">${(bill.items || []).length}</span></div>
					<div class="bill-stat"><span class="stat-label">REVENUE</span><span class="stat-value">${format_currency(revenue.total || 0)}</span></div>
					<div class="bill-stat"><span class="stat-label">COST</span><span class="stat-value">${format_currency(actual.total || 0)}</span></div>
					<div class="bill-stat"><span class="stat-label">GP</span><span class="stat-value ${profitability.gp >= 0 ? 'positive' : 'negative'}">${format_currency(profitability.gp || 0)}</span></div>
					<div class="bill-stat"><span class="stat-label">GP%</span><span class="stat-value">${(profitability.gp_percent || 0).toFixed(1)}%</span></div>
					<div class="bill-stat"><span class="stat-label">EST. GP</span><span class="stat-value ${profitability.estimated_gp >= 0 ? 'positive' : 'negative'}">${format_currency(profitability.estimated_gp || 0)}</span></div>
					<div class="bill-stat"><span class="stat-label">EST. GP%</span><span class="stat-value">${(profitability.estimated_gp_percent || 0).toFixed(1)}%</span></div>
					<div class="bill-stat"><span class="stat-label">RETENTION</span><span class="stat-value">${format_currency(totals.retention_amount || 0)}</span></div>
					<div class="bill-stat"><span class="stat-label">ADVANCE</span><span class="stat-value">${format_currency(totals.advance_amount || 0)}</span></div>
				</div>
			</div>
			<div class="bill-items-container" style="${isExpanded ? '' : 'display: none;'}">
				<div class="bill-toolbar">
					<button class="btn-frappe btn-sm" onclick="add_boq_item('${bill.name}', '${frm.doc.name}'); event.stopPropagation();">
						<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line>
						</svg>
						Add Item
					</button>
					<button class="btn-frappe btn-sm btn-delete-bill" onclick="delete_boq_bill('${bill.name}'); event.stopPropagation();">
						<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<polyline points="3 6 5 6 21 6"></polyline>
							<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
						</svg>
						Delete Bill
					</button>
				</div>
				${render_comprehensive_items_table(bill.items || [], frm)}
			</div>
		</div>
	`;
}


/**
 * Render comprehensive items table with all columns matching Excel format
 * Requirements: 1.1, 1.2, 1.3 - Column order: Qty Breakdown before Value Breakdown
 */
function render_comprehensive_items_table(items, frm) {
	if (!items || items.length === 0) {
		return '<div class="no-items-message">No items in this bill. Click "Add Item" to add BOQ items.</div>';
	}

	let html = `
		<div class="comprehensive-table-wrapper">
			<table class="comprehensive-items-table">
				<thead>
					<tr class="header-row-main">
						<th rowspan="2" class="col-expand sticky-col"></th>
						<th rowspan="2" class="col-checkbox sticky-col"><input type="checkbox" class="select-all-items"></th>
						<th rowspan="2" class="col-desc sticky-col">Description</th>
						<th rowspan="2" class="col-unit sticky-col">Unit</th>
						<th rowspan="2" class="col-total-qty sticky-col">Qty</th>
						<th rowspan="2" class="col-rate sticky-col">Rate</th>
						<th rowspan="2" class="col-amount sticky-col sticky-col-last">Amount</th>
						<th colspan="3" class="col-group col-group-qty">Qty Breakdown</th>
						<th colspan="3" class="col-group col-group-value">Value Breakdown</th>
						<th colspan="3" class="col-group col-group-billing">Current Billing</th>
						<th colspan="6" class="col-group col-group-revenue">Revenue</th>
						<th colspan="6" class="col-group col-group-estimated">Estimated Cost</th>
					<th colspan="7" class="col-group col-group-actual">Actual Cost</th>
					<th colspan="4" class="col-group col-group-profit">Profitability</th>
						<th colspan="3" class="col-group col-group-financial">Financial Summary</th>
						<th rowspan="2" class="col-actions">Actions</th>
					</tr>
					<tr class="header-row-sub">
						<!-- Qty Breakdown -->
						<th class="col-num">Previous</th>
						<th class="col-num">Current</th>
						<th class="col-num">Accumulated</th>
						<!-- Value Breakdown -->
						<th class="col-num">Previous</th>
						<th class="col-num">Current</th>
						<th class="col-num">Accumulated</th>
						<th class="col-num">%</th>
						<th class="col-num">Qty</th>
						<th class="col-num">Value</th>
						<!-- Revenue -->
						<th class="col-num">PI</th>
						<th class="col-num">PC</th>
						<th class="col-num">Tax Inv</th>
						<th class="col-num">Variance</th>
						<th class="col-num">BOQ Balance PI</th>
						<th class="col-num">BOQ Balance TI</th>
						<!-- Estimated Cost -->
						<th class="col-num">Material</th>
						<th class="col-num">Labour</th>
						<th class="col-num">Asset</th>
						<th class="col-num">S/C</th>
						<th class="col-num">Other</th>
						<th class="col-num">Total</th>
					<!-- Actual Cost -->
					<th class="col-num">Material</th>
					<th class="col-num">Labour</th>
					<th class="col-num">Asset</th>
					<th class="col-num">S/C</th>
					<th class="col-num">Other</th>
					<th class="col-num">Expense</th>
					<th class="col-num">Total</th>
						<!-- Profitability -->
						<th class="col-num">Actual GP</th>
						<th class="col-num">Actual GP%</th>
						<th class="col-num">Est. GP</th>
						<th class="col-num">Est. GP%</th>
						<!-- Financial Summary -->
						<th class="col-num">Retention</th>
						<th class="col-num">Advances</th>
						<th class="col-num">Net Amount</th>
					</tr>
				</thead>
				<tbody>
	`;

	items.forEach(item => {
		html += render_item_row(item, frm);
	});

	html += `
				</tbody>
			</table>
		</div>
	`;

	return html;
}


/**
 * Render a single item row with all columns
 * Requirements: 1.3 - Data cells aligned with reordered headers (Qty before Value)
 */
function render_item_row(item, frm) {
	const revenue = item.revenue || {};
	const ledgerQty = item.qty || {};
	const ledgerAmount = item.amount || {};
	const estimated = item.estimated_costs || {};
	const actual = item.actual_costs || {};
	const profitability = item.profitability || {};
	// Only disable inputs when Sales Order (Proforma) exists AND item is fully billed.
	// Avoid disabling when user has entered qty/value that makes balance 0 but hasn't created SO yet.
	const hasProforma = flt(revenue.proforma || 0) > 0;
	const isFullyBilled = item.billing_status === 'Fully Billed' && hasProforma;
	const totalQty = item.total_qty ?? ledgerQty.total ?? 0;

	const varianceClass = revenue.variance > 0 ? 'text-danger' : '';

	// Determine row status for highlighting (Issue #3)
	const hasPC = flt(revenue.pc || 0) > 0;
	const hasTaxInvoice = flt(revenue.tax_invoice || 0) > 0;

	let rowStatusClass = '';
	let rowStatusIcon = '';
	let rowStatusTooltip = '';

	if (hasProforma && !hasPC && !isFullyBilled) {
		// SO exists, PC pending
		rowStatusClass = 'row-status-pc-pending';
		rowStatusIcon = '⏳';
		rowStatusTooltip = 'Sales Order created - Payment Certificate pending';
	} else if (hasProforma && hasPC && !hasTaxInvoice && !isFullyBilled) {
		// PC exists, Tax Invoice pending
		rowStatusClass = 'row-status-invoice-pending';
		rowStatusIcon = '📄';
		rowStatusTooltip = 'Payment Certificate created - Tax Invoice pending';
	}

	return `
		<tr class="item-row ${isFullyBilled ? 'fully-billed' : ''} ${rowStatusClass}" data-item="${item.name}" role="row">
			<td class="col-expand sticky-col">
				<button class="expand-btn" onclick="toggleTransactionHistory('${item.name}'); event.stopPropagation();" title="View Transactions" aria-label="Expand transaction history for ${item.description || item.name}" aria-expanded="false" tabindex="0">
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
						<polyline points="6 9 12 15 18 9"></polyline>
					</svg>
				</button>
			</td>
			<td class="col-checkbox sticky-col"><input type="checkbox" class="item-checkbox" data-item="${item.name}" aria-label="Select item ${item.description || item.name}" tabindex="0"></td>
			<td class="col-desc sticky-col">
				<div class="item-desc-wrapper">
					${rowStatusIcon ? `<span class="row-status-icon" title="${rowStatusTooltip}">${rowStatusIcon}</span>` : ''}
					${item.item_code ? `<span class="item-code">${item.item_code}</span>` : ''}
					<span class="item-desc"><a href="/app/boq-item/${item.name}" onclick="event.stopPropagation()">${item.name || 'No description'}</a></span>
					<span class="item-desc">${item.description || 'No description'}</span>
				</div>
				<!-- Profit/Loss Indicator - Requirements: 8.1, 8.2, 8.3, 8.4 -->
				<div class="profit-indicator-container" data-item-id="${item.name}"></div>
			</td>
			<td class="col-unit sticky-col">${item.unit || '-'}</td>
			<td class="col-total-qty sticky-col">
				<input type="number" class="boq-qty-input" value="${totalQty}" 
					data-item="${item.name}" step="${BOQ_QTY_STEP}" min="0" 
					aria-label="Total quantity" tabindex="0">
			</td>
			<td class="col-rate sticky-col">
				<input type="number" class="boq-rate-input" value="${ledgerAmount.rate || 0}" 
					data-item="${item.name}" step="0.01" min="0" 
					aria-label="Rate" tabindex="0">
			</td>
			<td class="col-amount sticky-col sticky-col-last">${format_currency(ledgerAmount.total || 0)}</td>
			
			<!-- Qty Breakdown (moved before Value) -->
	<td class="col-num">${format_number(ledgerQty.prev || 0)}</td>
	<td class="col-num curr-qty-cell" data-item="${item.name}">${format_number(ledgerQty.current || 0)}</td>
	<td class="col-num font-bold">${format_number(ledgerQty.to_date || 0)}</td>
			
			<!-- Value Breakdown -->
	<td class="col-num">${format_currency(ledgerAmount.prev || 0)}</td>
	<td class="col-num curr-value-cell" data-item="${item.name}">${format_currency(ledgerAmount.current || 0)}</td>
	<td class="col-num font-bold accum-value-cell" data-item="${item.name}">${format_currency(ledgerAmount.to_date || 0)}</td>
			
			<!-- Current Billing Inputs: pre-populate with ledger current when no SO, allow override -->
			<!-- When no Proforma: max = balance + current so user can edit/override saved value -->
			${(function () {
				const currQty = flt(ledgerQty.current || 0, BOQ_QTY_PRECISION);
				const currAmount = flt(ledgerAmount.current || 0);
				const balQty = flt(ledgerQty.balance || 0, BOQ_QTY_PRECISION);
				const balAmount = flt(ledgerAmount.balance || 0);
				const maxQty = hasProforma ? balQty : (balQty + currQty);
				const maxAmount = hasProforma ? balAmount : (balAmount + currAmount);
				const pct = (ledgerAmount.total || 0) > 0 ? (currAmount / (ledgerAmount.total || 1) * 100) : 0;
				return `
			<td class="col-num">
				<input type="number" class="current-percentage-input" value="${pct.toFixed(2)}"
					data-item="${item.name}" data-max="100"
					data-total-qty="${totalQty}" data-total-amount="${ledgerAmount.total || 0}"
					step="0.01" min="0" max="100" ${isFullyBilled ? 'disabled' : ''} aria-label="Current billing percentage" tabindex="0">
			</td>
			<td class="col-num">
				<input type="number" class="current-qty-input" value="${currQty}"
					data-item="${item.name}" data-max="${maxQty}" data-rate="${ledgerAmount.rate || 0}"
					data-total-qty="${totalQty}" data-total-amount="${ledgerAmount.total || 0}"
					data-prev-amount="${ledgerAmount.prev || 0}" data-prev-qty="${ledgerQty.prev || 0}"
					step="${BOQ_QTY_STEP}" min="0" ${isFullyBilled ? 'disabled' : ''} aria-label="Current billing quantity" tabindex="0">
			</td>
			<td class="col-num">
				<input type="number" class="current-value-input" value="${currAmount.toFixed(2)}"
					data-item="${item.name}" data-max="${maxAmount}" data-rate="${ledgerAmount.rate || 0}"
					data-total-qty="${totalQty}" data-total-amount="${ledgerAmount.total || 0}"
					data-prev-amount="${ledgerAmount.prev || 0}" data-prev-qty="${ledgerQty.prev || 0}"
					step="0.01" min="0" ${isFullyBilled ? 'disabled' : ''} aria-label="Current billing value" tabindex="0">
			</td>
				`;
			})()}
			
			<!-- Revenue columns -->
			<td class="col-num">${format_currency(revenue.proforma || 0)}</td>
			<td class="col-num">${format_currency(revenue.pc || 0)}</td>
			<td class="col-num">${format_currency(revenue.tax_invoice || 0)}</td>
			<td class="col-num ${varianceClass}">${format_currency(revenue.variance || 0)}</td>
			<td class="col-num balance-value">${format_currency(revenue.balance || 0)}</td>
			<td class="col-num font-bold">${format_currency((ledgerAmount.total || 0) - ((revenue.tax_invoice || 0) + (revenue.variance || 0)))}</td>
			
			<!-- Estimated Cost -->
			<td class="col-num">${format_currency(estimated.material || 0)}</td>
			<td class="col-num">${format_currency(estimated.labour || 0)}</td>
			<td class="col-num">${format_currency(estimated.asset || 0)}</td>
			<td class="col-num">${format_currency(estimated.subcontract || 0)}</td>
			<td class="col-num">${format_currency(estimated.other || 0)}</td>
			<td class="col-num font-bold">${format_currency(estimated.total || 0)}</td>
			
		<!-- Actual Cost -->
		<td class="col-num">${format_currency(actual.material || 0)}</td>
		<td class="col-num">${format_currency(actual.labour || 0)}</td>
		<td class="col-num">${format_currency(actual.asset || 0)}</td>
		<td class="col-num">${format_currency(actual.subcontract || 0)}</td>
		<td class="col-num">${format_currency(actual.other || 0)}</td>
		<td class="col-num">${format_currency(actual.expense || 0)}</td>
		<td class="col-num font-bold">${format_currency(actual.total || 0)}</td>
			
			<!-- Profitability -->
			<td class="col-num ${profitability.gp >= 0 ? 'text-success' : 'text-danger'} font-bold">${format_currency(profitability.gp || 0)}</td>
			<td class="col-num ${profitability.gp_percent >= 0 ? 'text-success' : 'text-danger'}">${(profitability.gp_percent || 0).toFixed(1)}%</td>
			
			<!-- Estimated GP -->
			<!-- Estimated GP -->
			<td class="col-num ${(profitability.estimated_gp || 0) >= 0 ? 'text-success' : 'text-danger'} font-bold">${format_currency(profitability.estimated_gp || 0)}</td>
			<td class="col-num ${(profitability.estimated_gp_percent || 0) >= 0 ? 'text-success' : 'text-danger'}">${(profitability.estimated_gp_percent || 0).toFixed(1)}%</td>
			
			<!-- Financial Summary -->
			<td class="col-num text-warning">${format_currency(item.retention_amount || 0)}</td>
			<td class="col-num text-info">${format_currency(item.advance_amount || 0)}</td>
			<td class="col-num text-success font-bold">${format_currency((revenue.total || 0) - (item.retention_amount || 0) - (item.advance_amount || 0))}</td>
			
			<!-- Actions - Requirements: 3.2, 3.3 -->
			<td class="col-actions" role="cell">
				<div class="action-icons" role="group" aria-label="Item actions">
					<button class="action-btn action-btn-tasks" onclick="showTasksPopup('${item.name}'); event.stopPropagation();" title="View Tasks" aria-label="View tasks for this item" tabindex="0">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
							<rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
							<line x1="16" y1="2" x2="16" y2="6"></line>
							<line x1="8" y1="2" x2="8" y2="6"></line>
							<line x1="3" y1="10" x2="21" y2="10"></line>
						</svg>
					</button>
					<button class="action-btn action-btn-costs" onclick="showCostsPopup('${item.name}'); event.stopPropagation();" title="View Costs" aria-label="View costs for this item" tabindex="0">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
							<line x1="18" y1="20" x2="18" y2="10"></line>
							<line x1="12" y1="20" x2="12" y2="4"></line>
							<line x1="6" y1="20" x2="6" y2="14"></line>
						</svg>
					</button>
					<button class="action-btn action-btn-edit" onclick="edit_boq_item('${item.name}'); event.stopPropagation();" title="Edit Item" aria-label="Edit this item" tabindex="0">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
							<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
							<path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
						</svg>
					</button>
					<button class="action-btn action-btn-reload" onclick="reload_boq_item('${item.name}'); event.stopPropagation();" title="Reload Values" aria-label="Reload financial values for this item" tabindex="0">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
							<polyline points="23 4 23 10 17 10"></polyline>
							<polyline points="1 20 1 14 7 14"></polyline>
							<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
						</svg>
					</button>
					<button class="action-btn action-btn-delete" onclick="delete_boq_item('${item.name}'); event.stopPropagation();" title="Delete Item" aria-label="Delete this item" tabindex="0" ${isFullyBilled ? 'disabled aria-disabled="true"' : ''}>
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
							<polyline points="3 6 5 6 21 6"></polyline>
							<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
							<line x1="10" y1="11" x2="10" y2="17"></line>
							<line x1="14" y1="11" x2="14" y2="17"></line>
						</svg>
					</button>
					<button class="action-btn action-btn-invoice" onclick="create_item_invoice('${item.name}'); event.stopPropagation();" title="Create Invoice" aria-label="Create invoice for this item" tabindex="0" ${isFullyBilled ? 'disabled aria-disabled="true"' : ''}>
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
							<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
							<polyline points="14 2 14 8 20 8"></polyline>
						</svg>
					</button>
				</div>
			</td>
		</tr>
	`;
}


/**
 * Sync row's current billing inputs with ledger values from server.
 * Called after update_boq_item_base so data-max reflects new balance (e.g. after total qty increase).
 */
function sync_row_ledger_from_server(row, ledger) {
	if (!ledger || !ledger.qty || !ledger.amount) return;
	const qty = ledger.qty;
	const amt = ledger.amount;
	const currQty = flt(qty.current || 0, BOQ_QTY_PRECISION);
	const currAmt = flt(amt.current || 0);
	const balQty = flt(qty.balance || 0, BOQ_QTY_PRECISION);
	const balAmt = flt(amt.balance || 0);
	const maxQty = balQty + currQty;
	const maxAmt = balAmt + currAmt;

	const qtyInput = row.find('.current-qty-input');
	const valInput = row.find('.current-value-input');
	const pctInput = row.find('.current-percentage-input');
	qtyInput.data('max', maxQty);
	valInput.data('max', maxAmt);
	qtyInput.data('total-qty', qty.total || 0);
	valInput.data('total-qty', qty.total || 0);
	qtyInput.data('total-amount', amt.total || 0);
	valInput.data('total-amount', amt.total || 0);
	qtyInput.data('prev-amount', amt.prev || 0);
	qtyInput.data('prev-qty', qty.prev || 0);
	valInput.data('prev-amount', amt.prev || 0);
	valInput.data('prev-qty', qty.prev || 0);

	const pct = (amt.total || 0) > 0 ? (currAmt / (amt.total || 1) * 100) : 0;
	pctInput.data('total-qty', qty.total || 0);
	pctInput.data('total-amount', amt.total || 0);
	pctInput.val(pct.toFixed(2));
}


/**
 * Attach event handlers for the table
 */
function attach_table_events(container, frm) {
	// Handle Percentage input change
	container.find('.current-percentage-input').on('change input', function () {
		const input = $(this);
		let percentage = parseFloat(input.val()) || 0;
		if (percentage < 0) { percentage = 0; input.val(0); }
		if (percentage > 100) { percentage = 100; input.val(100); }

		const totalQty = parseFloat(input.data('total-qty')) || 0;
		const totalAmount = parseFloat(input.data('total-amount')) || 0;
		const itemName = input.data('item');

		const newQty = totalQty * (percentage / 100);
		const newValue = totalAmount * (percentage / 100);

		const row = input.closest('tr');
		const qtyInput = row.find('.current-qty-input');
		const valueInput = row.find('.current-value-input');

		qtyInput.val(newQty.toFixed(BOQ_QTY_PRECISION));
		valueInput.val(newValue.toFixed(2));

		// Update display cells
		const prevAmount = parseFloat(qtyInput.data('prev-amount')) || 0;
		const accumValue = prevAmount + newValue;
		row.find('.curr-qty-cell').text(format_number(newQty));
		row.find('.curr-value-cell').text(format_currency(newValue));
		row.find('.accum-value-cell').text(format_currency(accumValue));

		clearTimeout(input.data('timeout'));
		input.data('timeout', setTimeout(() => {
			update_boq_item_current(itemName, newQty, frm);
		}, 500));
	});

	// Handle Qty input change
	container.find('.current-qty-input').on('change input', function () {
		const input = $(this);
		const itemName = input.data('item');
		const maxQty = parseFloat(input.data('max')) || 0;
		const rate = parseFloat(input.data('rate')) || 0;
		const totalQty = parseFloat(input.data('total-qty')) || 0;
		const prevAmount = parseFloat(input.data('prev-amount')) || 0;
		let newQty = parseFloat(input.val()) || 0;

		if (newQty < 0) { newQty = 0; input.val(0); }
		if (newQty > maxQty) {
			frappe.show_alert({ message: __('Quantity cannot exceed available ({0})', [maxQty]), indicator: 'orange' });
			newQty = maxQty;
			input.val(maxQty);
		}

		const row = input.closest('tr');
		const valueInput = row.find('.current-value-input');
		const percentageInput = row.find('.current-percentage-input');

		const newValue = newQty * rate;
		const newPercentage = totalQty > 0 ? (newQty / totalQty) * 100 : 0;

		valueInput.val(newValue.toFixed(2));
		percentageInput.val(newPercentage.toFixed(2));

		// Update display cells
		const accumValue = prevAmount + newValue;
		row.find('.curr-qty-cell').text(format_number(newQty));
		row.find('.curr-value-cell').text(format_currency(newValue));
		row.find('.accum-value-cell').text(format_currency(accumValue));

		clearTimeout(input.data('timeout'));
		input.data('timeout', setTimeout(() => {
			update_boq_item_current(itemName, newQty, frm);
		}, 500));
	});

	// Handle Value input change
	container.find('.current-value-input').on('change input', function () {
		const input = $(this);
		const itemName = input.data('item');
		const maxValue = parseFloat(input.data('max')) || 0;
		const rate = parseFloat(input.data('rate')) || 0;
		const totalAmount = parseFloat(input.data('total-amount')) || 0;
		const prevAmount = parseFloat(input.data('prev-amount')) || 0;
		let newValue = parseFloat(input.val()) || 0;

		if (newValue < 0) { newValue = 0; input.val(0); }
		if (newValue > maxValue) {
			frappe.show_alert({ message: __('Value cannot exceed available ({0})', [maxValue]), indicator: 'orange' });
			newValue = maxValue;
			input.val(maxValue.toFixed(2));
		}

		const row = input.closest('tr');
		const qtyInput = row.find('.current-qty-input');
		const percentageInput = row.find('.current-percentage-input');

		const newQty = rate > 0 ? newValue / rate : 0;
		const newPercentage = totalAmount > 0 ? (newValue / totalAmount) * 100 : 0;

		qtyInput.val(newQty.toFixed(BOQ_QTY_PRECISION));
		percentageInput.val(newPercentage.toFixed(2));

		const accumValue = prevAmount + newValue;
		row.find('.curr-qty-cell').text(format_number(newQty));
		row.find('.curr-value-cell').text(format_currency(newValue));
		row.find('.accum-value-cell').text(format_currency(accumValue));

		clearTimeout(input.data('timeout'));
		input.data('timeout', setTimeout(() => {
			update_boq_item_current(itemName, newQty, frm);
		}, 500));
	});

	// Handle select all checkbox
	container.find('.select-all-items').on('change', function () {
		const isChecked = $(this).prop('checked');
		container.find('.item-checkbox:visible:not(:disabled)').prop('checked', isChecked);
		updateSelectionToolbar(container);
	});

	// Handle individual item checkbox
	container.find('.item-checkbox').on('change', function () {
		updateSelectionToolbar(container);
	});

	// Handle BOQ Qty input change
	container.find('.boq-qty-input').on('change', function () {
		const input = $(this);
		const itemName = input.data('item');
		const newQty = flt(input.val(), BOQ_QTY_PRECISION);

		frappe.call({
			method: 'construction_management.api.boq_tree.update_boq_item_base',
			args: {
				boq_item: itemName,
				total_qty: newQty
			},
			callback: function (r) {
				if (r.message) {
					frappe.show_alert({ message: __('Total Quantity updated'), indicator: 'green' });
					const row = input.closest('tr');
					const rate = flt(row.find('.boq-rate-input').val());
					row.find('.col-amount').text(format_currency(newQty * rate));
					sync_row_ledger_from_server(row, r.message);
				}
			}
		});
	});

	// Handle BOQ Rate input change
	container.find('.boq-rate-input').on('change', function () {
		const input = $(this);
		const itemName = input.data('item');
		const newRate = flt(input.val());

		frappe.call({
			method: 'construction_management.api.boq_tree.update_boq_item_base',
			args: {
				boq_item: itemName,
				rate: newRate
			},
			callback: function (r) {
				if (r.message) {
					frappe.show_alert({ message: __('Rate updated'), indicator: 'green' });
					const row = input.closest('tr');
					const qty = flt(row.find('.boq-qty-input').val(), BOQ_QTY_PRECISION);
					row.find('.col-amount').text(format_currency(qty * newRate));
					row.find('.current-qty-input, .current-value-input').data('rate', newRate);
					sync_row_ledger_from_server(row, r.message);
				}
			}
		});
	});

	// Handle Search Input
	container.find('.boq-search-input').on('keyup', function () {
		const searchTerm = $(this).val().toLowerCase();

		if (!searchTerm) {
			container.find('.bill-section, .item-row').show();
			return;
		}

		container.find('.bill-section').each(function () {
			const billSection = $(this);
			const billTitle = billSection.find('.bill-title').text().toLowerCase();
			const billDesc = billSection.find('.bill-desc').text().toLowerCase();

			let billMatches = billTitle.includes(searchTerm) || billDesc.includes(searchTerm);
			let anyItemMatches = false;

			billSection.find('.item-row').each(function () {
				const itemRow = $(this);
				const itemDesc = itemRow.find('.item-desc').text().toLowerCase();
				const itemCode = itemRow.find('.item-code').text().toLowerCase();

				if (itemDesc.includes(searchTerm) || itemCode.includes(searchTerm)) {
					itemRow.show();
					anyItemMatches = true;
				} else {
					itemRow.hide();
				}
			});

			if (billMatches || anyItemMatches) {
				billSection.show();
				if (anyItemMatches && !billSection.hasClass('expanded')) {
					// Optionally expand if items match?
				}
			} else {
				billSection.hide();
			}
		});
	});
}

/**
 * Reload BOQ Item values to recalculate progressive billing
 */
window.reload_boq_item = function (item_name) {
	frappe.confirm(
		__('Are you sure you want to recalculate progressive billing for this item? This will fix accumulated values from the ledger.'),
		function () {
			frappe.call({
				method: 'construction_management.construction_management.doctype.boq_item.boq_item.recalculate_progressive_billing',
				args: {
					boq_item_name: item_name
				},
				freeze: true,
				freeze_message: __('Recalculating values...'),
				callback: function (r) {
					if (r.message && r.message.success) {
						frappe.show_alert({ message: __('BOQ Item {0} values recalculated successfully', [item_name]), indicator: 'green' });
						if (cur_frm) {
							cur_frm.reload_doc();
						}
					} else {
						frappe.show_alert({ message: r.message?.error || __('Failed to recalculate values'), indicator: 'red' });
					}
				}
			});
		}
	);
};


/**
 * Update selection toolbar - Frappe style (black/white/subtle)
 */
function updateSelectionToolbar(container) {
	const selectedItems = container.find('.item-checkbox:checked');
	const selectedCount = selectedItems.length;
	let toolbar = container.find('.selection-action-toolbar');

	if (selectedCount > 0) {
		if (toolbar.length === 0) {
			const toolbarHtml = `
				<div class="selection-action-toolbar">
					<div class="toolbar-info">
						<span class="selection-count">${selectedCount} item(s) selected</span>
					</div>
					<div class="toolbar-actions">
						<button class="btn-toolbar btn-primary-toolbar" onclick="generateBulkSalesOrder()">
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
								<polyline points="14 2 14 8 20 8"></polyline>
							</svg>
							Generate Sales Order
						</button>
						<button class="btn-toolbar btn-secondary-toolbar" onclick="generateSalesInvoiceFromSelection()">
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
								<polyline points="14 2 14 8 20 8"></polyline>
							</svg>
							Generate Sales Invoice
						</button>
						<button class="btn-toolbar btn-danger-toolbar" onclick="deleteSelectedBOQItems()">
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<polyline points="3 6 5 6 21 6"></polyline>
								<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
							</svg>
							Delete Selected
						</button>
						<button class="btn-toolbar btn-clear-toolbar" onclick="clearSelection()">
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<line x1="18" y1="6" x2="6" y2="18"></line>
								<line x1="6" y1="6" x2="18" y2="18"></line>
							</svg>
							Clear
						</button>
					</div>
				</div>
			`;
			container.find('.boq-management-table-container').prepend(toolbarHtml);
		} else {
			toolbar.find('.selection-count').text(`${selectedCount} item(s) selected`);
			toolbar.slideDown(200);
		}
	} else {
		toolbar.slideUp(200);
	}
}

window.generateBulkSalesOrder = function () {
	const selectedItems = $('.item-checkbox:checked');
	if (selectedItems.length === 0) {
		frappe.show_alert({ message: __('Please select items first'), indicator: 'orange' });
		return;
	}

	const items = [];
	selectedItems.each(function () {
		const itemName = $(this).data('item');
		const row = $(this).closest('tr');
		const qtyInput = row.find('.current-qty-input');
		const percentageInput = row.find('.current-percentage-input');
		const qty = parseFloat(qtyInput.val()) || 0;
		const percentage = parseFloat(percentageInput.val()) || 0;
		if (qty > 0) {
			items.push({ boq_item: itemName, qty: qty, percentage: percentage });
		}
	});

	if (items.length === 0) {
		frappe.show_alert({ message: __('Please enter billing quantities for selected items'), indicator: 'orange' });
		return;
	}

	const project = cur_frm.doc.name;
	frappe.call({
		method: 'construction_management.api.boq_invoice.create_sales_order_from_selected_items',
		args: { project: project, items: JSON.stringify(items), auto_submit: 1 },
		freeze: true,
		freeze_message: __('Creating and Submitting Sales Order...'),
		callback: function (r) {
			if (r.message && r.message.status === 'success') {
				const statusMsg = r.message.docstatus === 1
					? __('Sales Order {0} created and submitted', [r.message.name])
					: __('Sales Order {0} created', [r.message.name]);
				frappe.show_alert({ message: statusMsg, indicator: 'green' });
				// Clear selection and refresh the table
				clearSelection();
				if (cur_frm) {
					cur_frm.reload_doc();
				}
				window.open(`/app/sales-order/${r.message.name}`, '_blank');
			} else if (r.message && r.message.status === 'error') {
				frappe.show_alert({ message: r.message.error_message || __('Failed to create sales order'), indicator: 'red' });
			}
		}
	});
};

window.createPaymentCertificate = function () {
	const selectedItems = $('.item-checkbox:checked');
	if (selectedItems.length === 0) {
		frappe.show_alert({ message: __('Please select items first'), indicator: 'orange' });
		return;
	}

	frappe.call({
		method: 'construction_management.construction_management.doctype.payment_certificate.payment_certificate.get_pending_sales_orders',
		args: { project: cur_frm.doc.name },
		callback: function (r) {
			const pending_sos = r.message || [];
			if (pending_sos.length === 0) {
				frappe.show_alert({ message: __('No pending Sales Orders found for this project'), indicator: 'orange' });
				return;
			}

			frappe.prompt([
				{
					fieldname: 'sales_order', fieldtype: 'Select', label: 'Sales Order',
					options: pending_sos.map(so => ({ label: `${so.name} (${format_currency(so.amount)})`, value: so.name })),
					reqd: 1
				},
				{ fieldname: 'posting_date', fieldtype: 'Date', label: 'Posting Date', default: frappe.datetime.get_today(), reqd: 1 }
			], function (values) {
				frappe.call({
					method: 'construction_management.api.boq_invoice.create_payment_certificate_from_sales_order',
					args: { sales_order: values.sales_order, posting_date: values.posting_date },
					freeze: true,
					freeze_message: __('Creating Payment Certificate...'),
					callback: function (r) {
						if (r.message) {
							frappe.show_alert({ message: __('Payment Certificate {0} created', [r.message.name]), indicator: 'green' });
							window.open(`/app/payment-certificate/${r.message.name}`, '_blank');
						}
					}
				});
			}, __('Create Payment Certificate'), __('Create'));
		}
	});
};

window.generateSalesInvoiceFromSelection = function () {
	const selectedItems = $('.item-checkbox:checked');
	if (selectedItems.length === 0) {
		frappe.show_alert({ message: __('Please select items first'), indicator: 'orange' });
		return;
	}

	frappe.call({
		method: 'construction_management.construction_management.doctype.payment_certificate.payment_certificate.get_pending_sales_orders',
		args: { project: cur_frm.doc.name },
		callback: function (r) {
			const pending_sos = r.message || [];
			if (pending_sos.length === 0) {
				frappe.show_alert({ message: __('No Sales Orders found for this project'), indicator: 'orange' });
				return;
			}

			frappe.prompt([
				{
					fieldname: 'sales_order', fieldtype: 'Select', label: 'Sales Order',
					options: pending_sos.map(so => ({ label: `${so.name} (${format_currency(so.amount)})`, value: so.name })),
					reqd: 1
				}
			], function (values) {
				frappe.model.open_mapped_doc({
					method: 'erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice',
					source_name: values.sales_order
				});
			}, __('Generate Sales Invoice'), __('Generate'));
		}
	});
};

window.clearSelection = function () {
	$('.item-checkbox').prop('checked', false);
	$('.select-all-items').prop('checked', false);
	$('.selection-action-toolbar').slideUp(200);
};


window.toggleBillSection = function (header) {
	const section = $(header).closest('.bill-section');
	const itemsContainer = section.find('.bill-items-container');
	const isExpanded = section.hasClass('expanded');

	if (isExpanded) {
		itemsContainer.slideUp(200, function () { section.removeClass('expanded'); });
	} else {
		section.addClass('expanded');
		itemsContainer.slideDown(200);
	}
};

/**
 * Toggle transaction history for an item - Shows inline expandable section with BOQ Progress Ledger entries
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7
 */
window.toggleTransactionHistory = function (itemName) {
	let row;
	// Context-aware selection to support Full Screen mode (Issue #6)
	if ((window.boqFullScreenManager && typeof window.boqFullScreenManager.isActive === 'function' && window.boqFullScreenManager.isActive()) ||
		$('.boq-fullscreen-modal').is(':visible')) {
		row = $('.boq-fullscreen-modal').find(`tr.item-row[data-item="${itemName}"]`);
	} else {
		row = $(`tr.item-row[data-item="${itemName}"]`).not('.boq-fullscreen-modal *');
	}

	if (row.length === 0) {
		row = $(`tr.item-row[data-item="${itemName}"]`);
	}

	const expandBtn = row.find('.expand-btn');
	const existingInline = row.next('.inline-breakdown-row');

	// If inline section exists, toggle it
	if (existingInline.length > 0) {
		if (existingInline.is(':visible')) {
			existingInline.hide();
			expandBtn.removeClass('expanded');
			expandBtn.attr('aria-expanded', 'false');
		} else {
			existingInline.show();
			expandBtn.addClass('expanded');
			expandBtn.attr('aria-expanded', 'true');
		}
		return;
	}

	// Fetch and create inline section using BOQ invoice history API with grouped view
	expandBtn.addClass('loading');

	frappe.call({
		method: 'construction_management.api.boq_invoice.get_boq_invoice_history',
		args: {
			boq_item: itemName,
			grouped_view: 1  // Request grouped view
		},
		callback: function (r) {
			expandBtn.removeClass('loading');
			if (r.message) {
				const inlineHtml = renderTransactionHistorySection(itemName, r.message, row.find('td').length);
				const inlineRow = $(inlineHtml);
				row.after(inlineRow);
				inlineRow.show();
				expandBtn.addClass('expanded');
				expandBtn.attr('aria-expanded', 'true');
			} else {
				frappe.show_alert({ message: __('No transaction history found'), indicator: 'blue' });
			}
		},
		error: function () {
			expandBtn.removeClass('loading');
			frappe.show_alert({ message: __('Failed to load transaction history'), indicator: 'red' });
		}
	});
};

/**
 * Render transaction history section for a BOQ Item with support for grouped transactions
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
 */
function renderTransactionHistorySection(itemName, data, colSpan) {
	const boqItem = data.boq_item || {};
	const summary = data.summary || {};
	const ledgerEntries = data.ledger_entries || [];
	const paymentCertificates = data.payment_certificates || [];
	const pendingProformas = data.pending_proformas || [];
	const groupedTransactions = data.grouped_transactions || [];
	const viewMode = data.view_mode || 'raw';

	const latestEntry = (ledgerEntries || [])
		.slice()
		.sort((a, b) => {
			const aDate = new Date(a.creation || a.posting_date || 0);
			const bDate = new Date(b.creation || b.posting_date || 0);
			return bDate - aDate;
		})[0] || {};

	const latestQty = {
		prev: flt(latestEntry.prev_qty || 0, BOQ_QTY_PRECISION),
		curr: flt(latestEntry.current_qty || 0, BOQ_QTY_PRECISION),
		accum: flt(latestEntry.accumulated_qty || summary.accumulated_qty || 0, BOQ_QTY_PRECISION)
	};

	const latestAmount = {
		prev: flt(latestEntry.prev_amount || 0),
		curr: flt(latestEntry.current_amount || 0),
		accum: flt(latestEntry.accumulated_amount || summary.accumulated_amount || 0)
	};

	// Get column count from parent table if not provided
	const finalColSpan = colSpan || $(`tr.item-row[data-item="${itemName}"]`).first().find('td').length;

	return `
		<tr class="inline-breakdown-row" data-item="${itemName}">
			<td colspan="${finalColSpan}">
				<div class="transaction-history-container">
					<!-- Header with BOQ Item Summary -->
					<div class="transaction-header">
						<div class="transaction-header-left">
							<span class="transaction-title">Transaction History</span>
							<span class="transaction-item-desc">${boqItem.description || itemName}</span>
							${viewMode === 'grouped' ? '<span class="view-mode-badge">Grouped View</span>' : '<span class="view-mode-badge">Raw View</span>'}
						</div>
						<div class="transaction-header-right">
							<div class="summary-stats">
								<div class="stat-item">
									<span class="stat-label">Total BOQ</span>
									<span class="stat-value">${format_currency(boqItem.total_amount || 0)}</span>
								</div>
								<div class="stat-item">
									<span class="stat-label">Billed To Date</span>
									<span class="stat-value">${format_currency(summary.accumulated_amount || 0)}</span>
								</div>
								<div class="stat-item">
									<span class="stat-label">Balance</span>
									<span class="stat-value">${format_currency(summary.balance_amount || 0)}</span>
								</div>
								<div class="stat-item triple">
									<span class="stat-label">Qty (Prev / Curr / Accum)</span>
									<span class="stat-value">${format_number(latestQty.prev)} / ${format_number(latestQty.curr)} / ${format_number(latestQty.accum)}</span>
								</div>
								<div class="stat-item triple">
									<span class="stat-label">Value (Prev / Curr / Accum)</span>
									<span class="stat-value">${format_currency(latestAmount.prev)} / ${format_currency(latestAmount.curr)} / ${format_currency(latestAmount.accum)}</span>
								</div>
								${viewMode === 'grouped' && data.grouping_summary ? `
								<div class="stat-item">
									<span class="stat-label">Billing Cycles</span>
									<span class="stat-value">${data.grouping_summary.total_billing_cycles}</span>
								</div>
								` : ''}
							</div>
							<div class="view-toggle-container">
								<button class="btn btn-xs btn-default" onclick="toggleViewMode('${itemName}', '${viewMode}')">
									${viewMode === 'grouped' ? 'Show Raw View' : 'Show Grouped View'}
								</button>
							</div>
						</div>
					</div>
					
					${viewMode === 'grouped' && groupedTransactions.length > 0 ?
			renderGroupedTransactionsSection(groupedTransactions) :
			renderRawTransactionsSection(ledgerEntries, paymentCertificates, pendingProformas)
		}
				</div>
				${getTransactionHistoryStyles()}
			</td>
		</tr>
	`;
}

/**
 * Render grouped transactions section
 */
function renderGroupedTransactionsSection(groupedTransactions) {
	return `
		<div class="transaction-section">
			<div class="transaction-section-title">
				Billing Cycles
				<span class="entry-count-badge">${groupedTransactions.length}</span>
				<span class="section-subtitle">Grouped by Proforma → Payment Certificate → Tax Invoice workflow</span>
			</div>
			${renderGroupedTransactionsTable(groupedTransactions)}
		</div>
	`;
}

/**
 * Render raw transactions section (original view)
 */
function renderRawTransactionsSection(ledgerEntries, paymentCertificates, pendingProformas) {
	return `
		<!-- BOQ Progress Ledger Entries -->
		<div class="transaction-section">
			<div class="transaction-section-title">
				BOQ Progress Ledger Entries
				<span class="entry-count-badge">${ledgerEntries.length}</span>
			</div>
			${ledgerEntries.length > 0 ? renderLedgerEntriesTable(ledgerEntries) : '<div class="no-entries">No ledger entries found</div>'}
		</div>
		
		<!-- Payment Certificates Section -->
		${paymentCertificates.length > 0 ? `
		<div class="transaction-section">
			<div class="transaction-section-title">
				Payment Certificates
				<span class="entry-count-badge">${paymentCertificates.length}</span>
			</div>
			${renderPaymentCertificatesTable(paymentCertificates)}
		</div>
		` : ''}
		
	`;
}

/**
 * Render grouped transactions table
 */
function renderGroupedTransactionsTable(groupedTransactions) {
	let html = `
		<table class="grouped-transactions-table">
			<thead>
				<tr>
					<th>Billing Cycle</th>
					<th>Order</th>
					<th>Payment Certificate</th>
					<th>Tax Invoice</th>
					<th class="text-right">Prev Qty</th>
					<th class="text-right">Curr Qty</th>
					<th class="text-right">Accum Qty</th>
					<th class="text-right">Prev Amount</th>
					<th class="text-right">Curr Amount</th>
					<th class="text-right">Accum Amount</th>
					<th class="text-right">Variance</th>
					<th>Status</th>
					<th>Actions</th>
				</tr>
			</thead>
			<tbody>
	`;

	groupedTransactions.forEach((cycle, index) => {
		const consolidated = cycle.consolidated_values || {};
		const variance = cycle.variance || {};
		const varianceClass = getVarianceClass(variance.amount);
		const statusClass = getWorkflowStatusClass(cycle.workflow_status);

		html += `
			<tr class="grouped-transaction-row" data-cycle-id="${cycle.cycle_id}">
				<td class="cycle-id">
					<div class="cycle-info">
						<span class="cycle-number">#${index + 1}</span>
						<button class="btn btn-xs btn-default expand-cycle-btn" onclick="toggleCycleDetails('${cycle.cycle_id}')">
							<i class="fa fa-chevron-down"></i>
						</button>
					</div>
				</td>
				<td class="doc-name">
					${cycle.proforma_invoice ?
				`<a href="/app/sales-invoice/${cycle.proforma_invoice.name}" target="_blank" title="${cycle.proforma_invoice.date}">
							${cycle.proforma_invoice.name}
						</a>` : '-'
			}
				</td>
				<td class="doc-name">
					${cycle.payment_certificate ?
				`<a href="/app/payment-certificate/${cycle.payment_certificate.name}" target="_blank" title="${cycle.payment_certificate.date}">
							${cycle.payment_certificate.name}
						</a>` : '-'
			}
				</td>
				<td class="doc-name">
					${cycle.tax_invoice ?
				`<a href="/app/sales-invoice/${cycle.tax_invoice.name}" target="_blank" title="${cycle.tax_invoice.date}">
							${cycle.tax_invoice.name}
						</a>` : '-'
			}
				</td>
				<td class="text-right">${format_number(consolidated.prev_qty || 0)}</td>
				<td class="text-right highlight-current">${format_number(consolidated.current_qty || 0)}</td>
				<td class="text-right font-bold">${format_number(consolidated.accumulated_qty || 0)}</td>
				<td class="text-right">${format_currency(consolidated.prev_amount || 0)}</td>
				<td class="text-right highlight-current">${format_currency(consolidated.current_amount || 0)}</td>
				<td class="text-right font-bold">${format_currency(consolidated.accumulated_amount || 0)}</td>
				<td class="text-right ${varianceClass}">
					<span class="variance-tooltip" data-tooltip="Proforma: ${format_currency(cycle.proforma_invoice ? cycle.proforma_invoice.amount : 0)} | PC: ${format_currency(cycle.payment_certificate ? cycle.payment_certificate.accepted_amount : 0)}">
						${variance.amount ? format_currency(variance.amount) : '-'}
						${variance.percentage ? `<br><small class="variance-percent">(${variance.percentage > 0 ? '+' : ''}${variance.percentage}%)</small>` : ''}
					</span>
				</td>
				<td>
					<span class="status-badge ${statusClass}">${getWorkflowStatusLabel(cycle.workflow_status)}</span>
				</td>
				<td>
					<div class="cycle-actions">
						${cycle.adjustments && cycle.adjustments.length > 0 ?
				`<button class="btn btn-xs btn-info" onclick="showAdjustments('${cycle.cycle_id}')" title="View Adjustments">
								<i class="fa fa-list"></i> ${cycle.adjustments.length}
							</button>` : ''
			}
					</div>
				</td>
			</tr>
			<tr class="cycle-details-row" id="cycle-details-${cycle.cycle_id}" style="display: none;">
				<td colspan="13">
					${renderCycleDetails(cycle)}
				</td>
			</tr>
		`;
	});

	html += `
			</tbody>
		</table>
	`;

	return html;
}

/**
 * Render cycle details (expandable section)
 */
function renderCycleDetails(cycle) {
	return `
		<div class="cycle-details-container">
			<div class="cycle-workflow">
				<h5>Workflow Progress</h5>
				${renderWorkflowProgressBar(cycle)}
				<div class="workflow-steps">
					${cycle.documents.map(doc => `
						<div class="workflow-step ${doc.type}">
							<div class="step-icon">
								<i class="fa ${getDocumentIcon(doc.type)}"></i>
							</div>
							<div class="step-content">
								<div class="step-title">${getDocumentTypeLabel(doc.type)}</div>
								<div class="step-details">
									<a href="/app/${getDocumentRoute(doc.type)}/${doc.name}" target="_blank">${doc.name}</a>
									<span class="step-date">${doc.date}</span>
									<span class="step-amount">${format_currency(doc.amount)}</span>
								</div>
							</div>
						</div>
					`).join('')}
				</div>
			</div>
			
			${cycle.adjustments && cycle.adjustments.length > 0 ? `
			<div class="cycle-adjustments">
				<h5>Adjustments & Deductions</h5>
				<table class="adjustments-table">
					<thead>
						<tr>
							<th>Date</th>
							<th>Type</th>
							<th class="text-right">Qty</th>
							<th class="text-right">Amount</th>
							<th>Reference</th>
							<th>Remarks</th>
						</tr>
					</thead>
					<tbody>
						${cycle.adjustments.map(adj => `
							<tr>
								<td>${adj.date}</td>
								<td><span class="adjustment-type-badge ${adj.type}">${adj.type}</span></td>
								<td class="text-right">${format_number(adj.qty || 0)}</td>
								<td class="text-right">${format_currency(adj.amount || 0)}</td>
								<td>${adj.reference || '-'}</td>
								<td>${adj.remarks || '-'}</td>
							</tr>
						`).join('')}
					</tbody>
				</table>
			</div>
			` : ''}
		</div>
	`;
}

/**
 * Toggle view mode between grouped and raw
 */
window.toggleViewMode = function (itemName, currentMode) {
	const row = $(`tr.item-row[data-item="${itemName}"]`);
	const inlineRow = row.next('.inline-breakdown-row');

	if (inlineRow.length === 0) return;

	const newMode = currentMode === 'grouped' ? 0 : 1;

	// Show loading state
	inlineRow.find('.transaction-history-container').html('<div class="loading-state">Switching view...</div>');

	frappe.call({
		method: 'construction_management.api.boq_invoice.get_boq_invoice_history',
		args: {
			boq_item: itemName,
			grouped_view: newMode
		},
		callback: function (r) {
			if (r.message) {
				const colSpan = inlineRow.find('td').attr('colspan');
				const newHtml = renderTransactionHistorySection(itemName, r.message, colSpan);
				const newInlineRow = $(newHtml);
				inlineRow.replaceWith(newInlineRow);
			}
		},
		error: function () {
			frappe.show_alert({ message: __('Failed to switch view mode'), indicator: 'red' });
		}
	});
};

/**
 * Toggle cycle details
 */
window.toggleCycleDetails = function (cycleId) {
	const detailsRow = $(`#cycle-details-${cycleId}`);
	const expandBtn = $(`.grouped-transaction-row[data-cycle-id="${cycleId}"] .expand-cycle-btn i`);

	if (detailsRow.is(':visible')) {
		detailsRow.slideUp(200);
		expandBtn.removeClass('fa-chevron-up').addClass('fa-chevron-down');
	} else {
		detailsRow.slideDown(200);
		expandBtn.removeClass('fa-chevron-down').addClass('fa-chevron-up');
	}
};

/**
 * Helper functions for grouped transactions
 */
function getWorkflowStatusClass(status) {
	const statusClasses = {
		'proforma_created': 'status-draft',
		'pc_draft': 'status-draft',
		'pc_approved': 'status-submitted',
		'tax_invoice_generated': 'status-paid'
	};
	return statusClasses[status] || 'status-draft';
}

function getWorkflowStatusLabel(status) {
	const statusLabels = {
		'proforma_created': 'Proforma Created',
		'pc_draft': 'PC Draft',
		'pc_approved': 'PC Approved',
		'tax_invoice_generated': 'Tax Invoice Generated'
	};
	return statusLabels[status] || status;
}

function getDocumentIcon(docType) {
	const icons = {
		'proforma_invoice': 'fa-file-text-o',
		'payment_certificate': 'fa-certificate',
		'tax_invoice': 'fa-file-text'
	};
	return icons[docType] || 'fa-file';
}

function getDocumentTypeLabel(docType) {
	const labels = {
		'sales_order': 'Sales Order',
		'payment_certificate': 'Payment Certificate',
		'tax_invoice': 'Tax Invoice'
	};
	return labels[docType] || docType;
}

function getDocumentRoute(docType) {
	const routes = {
		'proforma_invoice': 'sales-invoice',
		'payment_certificate': 'payment-certificate',
		'tax_invoice': 'sales-invoice'
	};
	return routes[docType] || docType;
}
function renderLedgerEntriesTable(entries) {
	let html = `
		<table class="ledger-entries-table">
			<thead>
				<tr>
					<th>Date</th>
					<th>Document</th>
					<th>Type</th>
					<th class="text-right">Prev Qty</th>
					<th class="text-right">Curr Qty</th>
					<th class="text-right">Accum Qty</th>
					<th class="text-right">Prev Amount</th>
					<th class="text-right">Curr Amount</th>
					<th class="text-right">Accum Amount</th>
					<th class="text-right">Rate</th>
					<th>Status</th>
					<th>PC</th>
				</tr>
			</thead>
			<tbody>
	`;

	entries.forEach(entry => {
		const hasTaxInvoice = !!entry.tax_invoice;
		let docTypeLabel = entry.reference_doctype || '-';
		let docName = hasTaxInvoice ? entry.tax_invoice : entry.reference_name;
		let docRouteType = hasTaxInvoice ? 'Sales Invoice' : entry.reference_doctype;

		if (hasTaxInvoice) {
			docTypeLabel = 'Tax Invoice';
			docRouteType = 'Sales Invoice';
		} else if (entry.reference_doctype === 'Sales Invoice') {
			const isOrder = entry.source === 'Order';
			docTypeLabel = isOrder ? 'Sales Order' : (entry.reference_doctype || 'Invoice');
		}

		const displayStatus = hasTaxInvoice
			? 'Tax Invoiced'
			: (entry.reference_doctype === 'Sales Order' ? 'Order' : (entry.invoice_status || 'Draft'));

		const docTypeClass = getDocTypeClass(docTypeLabel);
		const statusClass = getStatusClass(displayStatus);
		const pcLink = entry.payment_certificate || entry.pay_cert;

		html += `
			<tr class="ledger-entry-row" onclick="openDocument('${docRouteType}', '${docName}')">
				<td>${entry.posting_date || '-'}</td>
				<td class="doc-name">${docName || '-'}</td>
				<td><span class="doc-type-badge ${docTypeClass}">${docTypeLabel}</span></td>
				<td class="text-right">${format_number(entry.prev_qty || 0)}</td>
				<td class="text-right highlight-current">${format_number(entry.current_qty || 0)}</td>
				<td class="text-right font-bold">${format_number(entry.accumulated_qty || 0)}</td>
				<td class="text-right">${format_currency(entry.prev_amount || 0)}</td>
				<td class="text-right highlight-current">${format_currency(entry.current_amount || 0)}</td>
				<td class="text-right font-bold">${format_currency(entry.accumulated_amount || 0)}</td>
				<td class="text-right">${format_currency(entry.rate || 0)}</td>
				<td><span class="status-badge ${statusClass}">${displayStatus}</span></td>
				<td>${pcLink ? `<a href="/app/payment-certificate/${pcLink}" target="_blank">${pcLink}</a>` : '-'}</td>
			</tr>
		`;
	});

	html += `
			</tbody>
		</table>
	`;

	return html;
}

/**
 * Render Payment Certificates table
 */
function renderPaymentCertificatesTable(certificates) {
	let html = `
		<table class="payment-certificates-table">
			<thead>
				<tr>
					<th>PC No</th>
					<th>Date</th>
					<th>Order</th>
					<th class="text-right">PI Amount</th>
					<th class="text-right">Accepted Amount</th>
					<th class="text-right">Variance</th>
					<th class="text-right">Variance %</th>
					<th>Tax Invoice</th>
					<th>Status</th>
				</tr>
			</thead>
			<tbody>
	`;

	certificates.forEach(pc => {
		const variance = flt(pc.proforma_amount || 0) - flt(pc.accepted_amount || 0);
		const variancePercent = pc.proforma_amount > 0 ? (variance / pc.proforma_amount * 100).toFixed(2) : 0;
		const varianceClass = variance > 0 ? 'text-danger' : variance < 0 ? 'text-success' : '';

		html += `
			<tr class="pc-row" onclick="openDocument('Payment Certificate', '${pc.name}')">
				<td class="doc-name">${pc.name}</td>
				<td>${pc.posting_date || '-'}</td>
				<td>${pc.proforma_invoice ? `<a href="/app/sales-invoice/${pc.proforma_invoice}" target="_blank">${pc.proforma_invoice}</a>` : '-'}</td>
				<td class="text-right">${format_currency(pc.proforma_amount || 0)}</td>
				<td class="text-right">${format_currency(pc.accepted_amount || 0)}</td>
				<td class="text-right ${varianceClass}">${format_currency(variance)}</td>
				<td class="text-right ${varianceClass}">${variancePercent}%</td>
				<td>${pc.tax_invoice ? `<a href="/app/sales-invoice/${pc.tax_invoice}" target="_blank">${pc.tax_invoice}</a>` : '-'}</td>
				<td><span class="status-badge ${getStatusClass(pc.status)}">${pc.status || 'Draft'}</span></td>
			</tr>
		`;
	});

	html += `
			</tbody>
		</table>
	`;

	return html;
}

/**
 * Render Pending Proformas table
 */
function renderPendingProformasTable(proformas) {
	let html = `
		<table class="pending-orders-table">
			<thead>
				<tr>
					<th>Order No</th>
					<th>Date</th>
					<th class="text-right">Amount</th>
					<th>Customer</th>
					<th class="text-right">Age (Days)</th>
					<th>Action</th>
				</tr>
			</thead>
			<tbody>
	`;

	proformas.forEach(pi => {
		const ageClass = pi.age_days > 30 ? 'text-danger' : pi.age_days > 15 ? 'text-warning' : '';

		html += `
			<tr class="proforma-row">
				<td class="doc-name"><a href="/app/sales-order/${pi.name}" target="_blank">${pi.name}</a></td>
				<td>${pi.posting_date || '-'}</td>
				<td class="text-right">${format_currency(pi.grand_total || 0)}</td>
				<td>${pi.customer || '-'}</td>
				<td class="text-right ${ageClass}">${pi.age_days || 0}</td>
				<td>
				</td>
			</tr>
		`;
	});

	html += `
			</tbody>
		</table>
	`;

	return html;
}

/**
 * Get document type CSS class
 */
function getDocTypeClass(doctype) {
	const classMap = {
		'Sales Invoice': 'doc-type-invoice',
		'Tax Invoice': 'doc-type-invoice',
		'Sales Order': 'doc-type-proforma',
		'Payment Certificate': 'doc-type-pc'
	};
	return classMap[doctype] || 'doc-type-default';
}

/**
 * Get status CSS class
 */
function getStatusClass(status) {
	const classMap = {
		'Draft': 'status-draft',
		'Proforma': 'status-draft',
		'Submitted': 'status-submitted',
		'Tax Invoiced': 'status-submitted',
		'Paid': 'status-paid',
		'Cancelled': 'status-cancelled',
		'Approved': 'status-approved',
		'Pending': 'status-pending'
	};
	return classMap[status] || 'status-default';
}

/**
 * Open document in new tab
 */
window.openDocument = function (doctype, name) {
	if (name && name !== '-') {
		const route = doctype.toLowerCase().replace(' ', '-');
		window.open(`/app/${route}/${name}`, '_blank');
	}
};

/**
 * Create Payment Certificate from Proforma
 */
window.createPCFromProforma = function (proformaName) {
	frappe.prompt([
		{
			fieldname: 'accepted_amount',
			fieldtype: 'Currency',
			label: 'Accepted Amount',
			reqd: 1
		},
		{
			fieldname: 'posting_date',
			fieldtype: 'Date',
			label: 'Posting Date',
			default: frappe.datetime.get_today(),
			reqd: 1
		}
	], function (values) {
		frappe.call({
			method: 'construction_management.api.boq_invoice.create_payment_certificate',
			args: {
				proforma_invoice: proformaName,
				accepted_amount: values.accepted_amount,
				posting_date: values.posting_date
			},
			callback: function (r) {
				if (r.message) {
					frappe.show_alert({
						message: __('Payment Certificate {0} created', [r.message]),
						indicator: 'green'
					});
					// Refresh the transaction history
					const itemName = $('.inline-breakdown-row:visible').data('item');
					if (itemName) {
						$('.inline-breakdown-row:visible').remove();
						toggleTransactionHistory(itemName);
					}
				}
			}
		});
	}, __('Create Payment Certificate'), __('Create'));
};

/**
 * Get transaction history styles
 */
function getTransactionHistoryStyles() {
	return `<style>
		.transaction-history-container {
			padding: 16px;
			background: #fafbfc;
			border-radius: 8px;
			margin: 8px 0;
		}
		
		.transaction-header {
			display: flex;
			justify-content: space-between;
			align-items: flex-start;
			margin-bottom: 20px;
			padding-bottom: 12px;
			border-bottom: 1px solid #e8e8e8;
		}
		
		.transaction-title {
			font-size: 14px;
			font-weight: 600;
			color: #1f272e;
			display: block;
			margin-bottom: 4px;
		}
		
		.transaction-item-desc {
			font-size: 12px;
			color: #6c7680;
		}
		
		.summary-stats {
			display: flex;
			gap: 14px;
			flex-wrap: wrap;
		}
		
		.stat-item {
			text-align: right;
		}

		.stat-item.triple .stat-value {
			white-space: nowrap;
		}
		
		.stat-label {
			display: block;
			font-size: 10px;
			color: #6c7680;
			text-transform: uppercase;
			margin-bottom: 2px;
		}
		
		.stat-value {
			display: block;
			font-size: 13px;
			font-weight: 600;
			color: #1f272e;
		}
		
		.transaction-section {
			margin-bottom: 20px;
		}
		
		.transaction-section:last-child {
			margin-bottom: 0;
		}
		
		.transaction-section-title {
			font-size: 12px;
			font-weight: 600;
			color: #1f272e;
			margin-bottom: 12px;
			display: flex;
			align-items: center;
			gap: 8px;
		}
		
		.entry-count-badge {
			background: #e3f2fd;
			color: #1565c0;
			padding: 2px 8px;
			border-radius: 10px;
			font-size: 10px;
			font-weight: 500;
		}
		
		.ledger-entries-table,
		.payment-certificates-table,
		.pending-orders-table {
			width: 100%;
			border-collapse: collapse;
			background: white;
			border-radius: 6px;
			overflow: hidden;
			border: 1px solid #e8e8e8;
			table-layout: fixed;
		}
		
		.ledger-entries-table th,
		.payment-certificates-table th,
		.pending-proformas-table th {
			background: #f7f7f7;
			padding: 6px 8px;
			font-size: 10px;
			font-weight: 500;
			color: #6c7680;
			text-transform: uppercase;
			border-bottom: 1px solid #e8e8e8;
		}
		
		.ledger-entries-table td,
		.payment-certificates-table td,
		.pending-proformas-table td {
			padding: 6px 8px;
			font-size: 11px;
			border-bottom: 1px solid #f0f0f0;
			white-space: normal;
			word-break: break-word;
		}

		.ledger-entries-table th:nth-child(4),
		.ledger-entries-table th:nth-child(5),
		.ledger-entries-table th:nth-child(6),
		.ledger-entries-table th:nth-child(7),
		.ledger-entries-table th:nth-child(8),
		.ledger-entries-table th:nth-child(9),
		.ledger-entries-table td:nth-child(4),
		.ledger-entries-table td:nth-child(5),
		.ledger-entries-table td:nth-child(6),
		.ledger-entries-table td:nth-child(7),
		.ledger-entries-table td:nth-child(8),
		.ledger-entries-table td:nth-child(9) {
			min-width: 60px;
			text-align: right;
		}

		.ledger-entries-table th:nth-child(2),
		.ledger-entries-table td:nth-child(2) {
			max-width: 120px;
		}
		
		.ledger-entry-row,
		.pc-row,
		.proforma-row {
			cursor: pointer;
			transition: background 0.15s;
		}
		
		.ledger-entry-row:hover,
		.pc-row:hover,
		.proforma-row:hover {
			background: #f5f7fa;
		}
		
		.doc-name {
			font-weight: 500;
			color: #2490ef;
		}
		
		.doc-type-badge {
			padding: 2px 6px;
			border-radius: 4px;
			font-size: 9px;
			font-weight: 600;
			text-transform: uppercase;
		}
		
		.doc-type-invoice {
			background: #e8f5e9;
			color: #2e7d32;
		}
		
		.doc-type-proforma {
			background: #e3f2fd;
			color: #1565c0;
		}
		
		.doc-type-pc {
			background: #fff3e0;
			color: #e65100;
		}
		
		.doc-type-default {
			background: #f7f7f7;
			color: #6c7680;
		}
		
		.status-badge {
			padding: 2px 6px;
			border-radius: 4px;
			font-size: 9px;
			font-weight: 500;
		}
		
		.status-draft {
			background: #f7f7f7;
			color: #6c7680;
		}
		
		.status-submitted {
			background: #e3f2fd;
			color: #1565c0;
		}
		
		.status-paid {
			background: #e8f5e9;
			color: #2e7d32;
		}
		
		.status-cancelled {
			background: #ffebee;
			color: #c62828;
		}
		
		.status-approved {
			background: #e8f5e9;
			color: #2e7d32;
		}
		
		.status-pending {
			background: #fff3e0;
			color: #e65100;
		}
		
		.status-default {
			background: #f7f7f7;
			color: #6c7680;
		}
		
		.highlight-current {
			background: #e3f2fd;
			color: #1565c0;
			font-weight: 600;
		}
		
		.text-right {
			text-align: right;
		}
		
		.font-bold {
			font-weight: 600;
		}
		
		.text-danger {
			color: #ff5630;
		}
		
		.text-success {
			color: #36b37e;
		}
		
		.text-warning {
			color: #ff8f00;
		}
		
		.no-entries {
			text-align: center;
			padding: 20px;
			color: #8d99a6;
			font-size: 12px;
			background: white;
			border-radius: 6px;
			border: 1px solid #e8e8e8;
		}
		
		/* Grouped Transactions Styles */
		.view-mode-badge {
			background: #e8f5e9;
			color: #2e7d32;
			padding: 2px 8px;
			border-radius: 10px;
			font-size: 10px;
			font-weight: 500;
			margin-left: 8px;
		}
		
		.view-toggle-container {
			margin-left: 16px;
		}
		
		.section-subtitle {
			font-size: 10px;
			color: #8d99a6;
			font-weight: normal;
			margin-left: 8px;
		}
		
		.grouped-transactions-table {
			width: 100%;
			border-collapse: collapse;
			background: white;
			border-radius: 6px;
			overflow: hidden;
			border: 1px solid #e8e8e8;
		}
		
		.grouped-transactions-table th {
			background: #f7f7f7;
			padding: 8px 10px;
			font-size: 10px;
			font-weight: 500;
			color: #6c7680;
			text-transform: uppercase;
			border-bottom: 1px solid #e8e8e8;
		}
		
		.grouped-transactions-table td {
			padding: 8px 10px;
			font-size: 11px;
			border-bottom: 1px solid #f0f0f0;
		}
		
		.grouped-transaction-row {
			cursor: pointer;
			transition: background 0.15s;
		}
		
		.grouped-transaction-row:hover {
			background: #f5f7fa;
		}
		
		.cycle-id {
			font-weight: 500;
		}
		
		.cycle-info {
			display: flex;
			align-items: center;
			gap: 8px;
		}
		
		.cycle-number {
			font-weight: 600;
			color: #1565c0;
		}
		
		.expand-cycle-btn {
			padding: 2px 4px;
			border: none;
			background: transparent;
			cursor: pointer;
			color: #6c7680;
		}
		
		.expand-cycle-btn:hover {
			color: #1565c0;
		}
		
		.cycle-details-container {
			padding: 16px;
			background: #fafbfc;
			border-radius: 6px;
			margin: 8px 0;
		}
		
		.cycle-workflow h5 {
			margin: 0 0 12px 0;
			font-size: 12px;
			font-weight: 600;
			color: #1f272e;
		}
		
		.workflow-steps {
			display: flex;
			gap: 16px;
			flex-wrap: wrap;
		}
		
		.workflow-step {
			display: flex;
			align-items: flex-start;
			gap: 8px;
			padding: 12px;
			background: white;
			border-radius: 6px;
			border: 1px solid #e8e8e8;
			min-width: 200px;
			position: relative;
		}
		
		.workflow-step::after {
			content: '';
			position: absolute;
			right: -8px;
			top: 50%;
			transform: translateY(-50%);
			width: 0;
			height: 0;
			border-left: 8px solid #e8e8e8;
			border-top: 8px solid transparent;
			border-bottom: 8px solid transparent;
		}
		
		.workflow-step:last-child::after {
			display: none;
		}
		
		.step-icon {
			width: 24px;
			height: 24px;
			border-radius: 50%;
			display: flex;
			align-items: center;
			justify-content: center;
			font-size: 10px;
		}
		
		.workflow-step.proforma_invoice .step-icon {
			background: #e3f2fd;
			color: #1565c0;
		}
		
		.workflow-step.payment_certificate .step-icon {
			background: #fff3e0;
			color: #e65100;
		}
		
		.workflow-step.tax_invoice .step-icon {
			background: #e8f5e9;
			color: #2e7d32;
		}
		
		.step-content {
			flex: 1;
		}
		
		.step-title {
			font-size: 11px;
			font-weight: 600;
			color: #1f272e;
			margin-bottom: 4px;
		}
		
		.step-details {
			font-size: 10px;
			color: #6c7680;
		}
		
		.step-details a {
			color: #2490ef;
			text-decoration: none;
			font-weight: 500;
		}
		
		.step-details a:hover {
			text-decoration: underline;
		}
		
		.step-date, .step-amount {
			display: block;
			margin-top: 2px;
		}
		
		.step-amount {
			font-weight: 600;
			color: #1f272e;
		}
		
		.cycle-adjustments {
			margin-top: 16px;
		}
		
		.cycle-adjustments h5 {
			margin: 0 0 12px 0;
			font-size: 12px;
			font-weight: 600;
			color: #1f272e;
		}
		
		.adjustments-table {
			width: 100%;
			border-collapse: collapse;
			background: white;
			border-radius: 6px;
			overflow: hidden;
			border: 1px solid #e8e8e8;
		}
		
		.adjustments-table th {
			background: #f7f7f7;
			padding: 6px 8px;
			font-size: 10px;
			font-weight: 500;
			color: #6c7680;
			text-transform: uppercase;
			border-bottom: 1px solid #e8e8e8;
		}
		
		.adjustments-table td {
			padding: 6px 8px;
			font-size: 10px;
			border-bottom: 1px solid #f0f0f0;
		}
		
		.adjustment-type-badge {
			padding: 2px 6px;
			border-radius: 4px;
			font-size: 9px;
			font-weight: 600;
			text-transform: uppercase;
		}
		
		.adjustment-type-badge.deduction {
			background: #ffebee;
			color: #c62828;
		}
		
		.adjustment-type-badge.adjustment {
			background: #fff3e0;
			color: #e65100;
		}
		
		.cycle-actions {
			display: flex;
			gap: 4px;
		}
		
		.loading-state {
			text-align: center;
			padding: 40px;
			color: #8d99a6;
			font-size: 12px;
		}
		
		/* Variance Highlighting */
		.variance-positive {
			color: #ff5630 !important;
			font-weight: 600;
		}
		
		.variance-negative {
			color: #36b37e !important;
			font-weight: 600;
		}
		
		.variance-zero {
			color: #6c7680;
		}
		
		.variance-tooltip {
			position: relative;
			cursor: help;
		}
		
		.variance-tooltip:hover::after {
			content: attr(data-tooltip);
			position: absolute;
			bottom: 100%;
			left: 50%;
			transform: translateX(-50%);
			background: #1f272e;
			color: white;
			padding: 4px 8px;
			border-radius: 4px;
			font-size: 10px;
			white-space: nowrap;
			z-index: 1000;
		}
		
		/* Workflow Progress Indicators */
		.workflow-progress-bar {
			display: flex;
			align-items: center;
			gap: 8px;
			margin: 12px 0;
		}
		
		.progress-step {
			display: flex;
			align-items: center;
			gap: 4px;
			padding: 4px 8px;
			border-radius: 12px;
			font-size: 10px;
			font-weight: 500;
		}
		
		.progress-step.completed {
			background: #e8f5e9;
			color: #2e7d32;
		}
		
		.progress-step.current {
			background: #e3f2fd;
			color: #1565c0;
		}
		
		.progress-step.pending {
			background: #f7f7f7;
			color: #6c7680;
		}
		
		.progress-arrow {
			color: #e8e8e8;
			font-size: 12px;
		}
		
		/* Enhanced Status Badges */
		.status-badge.workflow-proforma-created {
			background: #e3f2fd;
			color: #1565c0;
		}
		
		.status-badge.workflow-pc-draft {
			background: #fff3e0;
			color: #e65100;
		}
		
		.status-badge.workflow-pc-approved {
			background: #e8f5e9;
			color: #2e7d32;
		}
		
		.status-badge.workflow-tax-invoice-generated {
			background: #e8f5e9;
			color: #2e7d32;
			border: 1px solid #4caf50;
		}
	</style>`;
}

/**
 * Get proforma/PC status from transactions
 */
function getProformaStatus(transactions) {
	if (!transactions || transactions.length === 0) {
		return 'none';
	}

	// Find latest proforma and PC
	let hasProforma = false;
	let hasPC = false;
	let pcStatus = null;
	let pcDocstatus = null;

	for (const txn of transactions) {
		if (txn.doctype === 'Sales Order' || txn.doctype === 'Sales Invoice') {
			if (txn.is_proforma || txn.custom_is_proforma) {
				hasProforma = true;
			}
		}
		if (txn.doctype === 'Payment Certificate') {
			hasPC = true;
			pcStatus = txn.status;
			pcDocstatus = txn.docstatus;
		}
	}

	if (!hasProforma) {
		return 'none';
	}

	if (!hasPC) {
		return 'pi_pending_pc';
	}

	if (pcDocstatus === 0 || pcStatus === 'Draft') {
		return 'pc_draft';
	}

	if (pcDocstatus === 1 || pcStatus === 'Submitted') {
		return 'pc_submitted';
	}

	return 'invoiced';
}

/**
 * Get status indicator HTML
 */
function getStatusIndicatorHtml(status) {
	const statusConfig = {
		'none': { label: 'No Proforma', class: 'status-none' },
		'pi_pending_pc': { label: 'PI Created - PC Pending', class: 'status-pi-pending' },
		'pc_draft': { label: 'PC Draft', class: 'status-pc-draft' },
		'pc_submitted': { label: 'PC Submitted', class: 'status-pc-submitted' },
		'invoiced': { label: 'Invoiced', class: 'status-invoiced' }
	};

	const config = statusConfig[status] || statusConfig['none'];
	return `<span class="inline-status-indicator ${config.class}">${config.label}</span>`;
}

/**
 * Render inline transactions table
 */
function renderInlineTransactionsTable(transactions) {
	let html = `
		<table class="inline-txn-table">
			<thead>
				<tr>
					<th>Type</th>
					<th>Document</th>
					<th>Date</th>
					<th class="text-right">Qty</th>
					<th class="text-right">PI Amount</th>
					<th class="text-right">PC Amount</th>
					<th class="text-right">Variance</th>
					<th>Status</th>
				</tr>
			</thead>
			<tbody>
	`;

	transactions.forEach(txn => {
		const typeClass = get_transaction_type_class(txn.doctype);
		const statusClass = get_status_class(txn.status);
		const varianceClass = (txn.variance || 0) > 0 ? 'variance-loss' : '';

		html += `
			<tr class="inline-txn-row" onclick="frappe.set_route('Form', '${txn.doctype}', '${txn.name}')">
				<td><span class="txn-type-badge ${typeClass}">${get_short_doctype(txn.doctype)}</span></td>
				<td class="txn-doc-name">${txn.name}</td>
				<td>${txn.date || '-'}</td>
				<td class="text-right">${format_number(txn.qty || 0)}</td>
				<td class="text-right">${format_currency(txn.proforma_amount || txn.amount || 0)}</td>
				<td class="text-right">${format_currency(txn.pc_amount || 0)}</td>
				<td class="text-right ${varianceClass}">${format_currency(txn.variance || 0)}</td>
				<td><span class="status-badge ${statusClass}">${txn.status || '-'}</span></td>
			</tr>
		`;
	});

	html += '</tbody></table>';
	return html;
}

/**
 * Render transactions table for popup
 */
function renderTransactionsTable(transactions) {
	let html = `
		<table class="txn-popup-table">
			<thead>
				<tr>
					<th>Type</th>
					<th>Document</th>
					<th>Date</th>
					<th class="text-right">Qty</th>
					<th class="text-right">PI Amount</th>
					<th class="text-right">PC Amount</th>
					<th class="text-right">Variance</th>
					<th>Status</th>
				</tr>
			</thead>
			<tbody>
	`;

	transactions.forEach(txn => {
		const typeClass = get_transaction_type_class(txn.doctype);
		const statusClass = get_status_class(txn.status);
		const varianceClass = (txn.variance || 0) > 0 ? 'variance-loss' : '';

		html += `
			<tr class="txn-popup-row" data-doctype="${txn.doctype}" data-name="${txn.name}">
				<td><span class="txn-type-badge ${typeClass}">${get_short_doctype(txn.doctype)}</span></td>
				<td class="txn-doc-name">${txn.name}</td>
				<td>${txn.date || '-'}</td>
				<td class="text-right">${format_number(txn.qty || 0)}</td>
				<td class="text-right">${format_currency(txn.proforma_amount || txn.amount || 0)}</td>
				<td class="text-right">${format_currency(txn.pc_amount || 0)}</td>
				<td class="text-right ${varianceClass}">${format_currency(txn.variance || 0)}</td>
				<td><span class="status-badge-popup ${statusClass}">${txn.status || '-'}</span></td>
			</tr>
		`;
	});

	html += '</tbody></table>';
	return html;
}

/**
 * Show enhanced tasks popup for a BOQ item with add/edit capabilities
 * Requirements: 2.1, 2.2, 2.3, 2.4, 4.1, 4.2, 4.5
 */
window.showTasksPopup = function (itemName) {
	window._current_boq_item = itemName;
	const existing = window._current_task_dialog;
	if (
		existing &&
		existing.$wrapper &&
		existing.$wrapper.is(':visible') &&
		window._current_boq_item === itemName &&
		typeof window.refresh_boq_tasks_dialog === 'function'
	) {
		return window.refresh_boq_tasks_dialog(itemName);
	}
	frappe.call({
		method: 'construction_management.api.boq_tasks.get_boq_item_tasks_tree',
		args: { boq_item: itemName },
		callback: function (r) {
			const data = r.message || {};
			showTaskManagementDialog(itemName, data);
		}
	});
};

function showTaskManagementDialog(itemName, data) {
	let boqItem = data.boq_item || {};
	let tasks = data.tasks || [];
	let hasTasks = data.has_tasks || false;
	let linkedTask = data.linked_task;

	const dialog = new frappe.ui.Dialog({
		title: __('Task Management - {0}', [boqItem.description?.substring(0, 50) || itemName]),
		size: 'extra-large',
		fields: [
			{
				fieldtype: 'HTML',
				fieldname: 'task_content'
			}
		]
	});

	function renderTaskManagement() {
		let content = `
			<div class="task-management-container">
				<div class="task-header">
					<div class="task-header-info">
						<h4>${boqItem.description || 'BOQ Item'}</h4>
						<div class="task-meta">
							<span><strong>${__('Rate')}:</strong> ${format_currency(boqItem.rate || 0)}</span>
							<span><strong>${__('Amount')}:</strong> ${format_currency(boqItem.total_amount || 0)}</span>
						</div>
					</div>
					<div class="task-header-actions">
						${!hasTasks ? `
							<button class="btn btn-primary btn-sm" onclick="createTaskForBOQ('${itemName}', this)">
								<i class="fa fa-plus"></i> Create Task
							</button>
						` : `
							<button class="btn btn-success btn-sm" onclick="addChildTask('${linkedTask}', '${boqItem.project}', this)">
								<i class="fa fa-plus"></i> Add Sub-Task
							</button>
						`}
					</div>
				</div>
				${typeof renderBoqTaskQtyBanner === 'function' ? renderBoqTaskQtyBanner(boqItem, itemName, tasks) : ''}
		`;

		if (hasTasks && tasks.length > 0) {
			const unitLabel = boqItem.unit || __('Area');
			content += `
				<div class="task-tree-header">
					<span class="task-col-name">${__('Task')}</span>
					<span class="task-col-area">${__('BOQ Total / Expected / Done')} (${unitLabel})</span>
					<span class="task-col-progress">${__('Progress')}</span>
					<span class="task-col-status">${__('Status')}</span>
					<span class="task-col-actions">${__('Actions')}</span>
				</div>
				<div class="task-tree">${renderTaskTree(tasks, boqItem)}</div>`;
		} else {
			content += `
				<div class="no-tasks-message">
					<i class="fa fa-tasks" style="font-size: 48px; color: #ccc; margin-bottom: 15px;"></i>
					<p>No tasks linked to this BOQ Item yet.</p>
					<p class="text-muted">Click "Create Task" to create a group task for this BOQ Item.</p>
				</div>
			`;
		}

		content += `</div>`;
		if (typeof ensureTaskTreeStyles === 'function') {
			ensureTaskTreeStyles();
		}
		dialog.fields_dict.task_content.$wrapper.html(content);
	}

	function renderTaskTree(taskNodes, boqItemData, level = 0) {
		let html = '';
		const totalArea = parseFloat(boqItemData?.total_qty || 0);
		const unitLabel = boqItemData?.unit || '';

		for (const task of taskNodes) {
			const statusClass = getTaskStatusClass(task.status);
			const expectedForProgress = parseFloat(task.expected_area || 0);
			const doneForProgress = parseFloat(task.completed_qty || 0);
			const progressWidth = expectedForProgress > 0
				? Math.min(100, Math.max(0, (doneForProgress / expectedForProgress) * 100))
				: Math.min(100, Math.max(0, task.progress || 0));
			const hasChildren = task.children && task.children.length > 0;
			const areaDone = parseFloat(task.completed_qty || 0);
			const isGroup = task.is_group;

			const areaField = typeof renderTaskAreaFields === 'function'
				? renderTaskAreaFields(task, boqItemData)
				: '';

			html += `
				<div class="task-node" data-task="${task.name}" data-level="${level}">
					<div class="task-node-content" style="padding-left: ${level * 24 + 12}px;">
						${hasChildren ? `
							<span class="task-toggle" onclick="toggleTaskChildren(this)">
								<i class="fa fa-chevron-down"></i>
							</span>
						` : `<span class="task-toggle-placeholder"></span>`}
						<div class="task-info">
							<div class="task-subject">
								<a href="/app/task/${task.name}" target="_blank">${task.subject}</a>
								${isGroup ? '<span class="badge badge-info">Group</span>' : ''}
							</div>
							<div class="task-details">
								${task.exp_start_date ? `<span><i class="fa fa-calendar"></i> ${frappe.datetime.str_to_user(task.exp_start_date)}</span>` : ''}
								${task.exp_end_date ? `<span>→ ${frappe.datetime.str_to_user(task.exp_end_date)}</span>` : ''}
							</div>
						</div>
						${areaField}
						<div class="task-progress-container">
							<div class="progress-bar-wrapper">
								<div class="progress-bar-mini">
									<div class="progress-fill" data-task="${task.name}" style="width: ${progressWidth}%"></div>
								</div>
								<input type="range" class="progress-slider" data-task="${task.name}" 
									min="0" max="100" value="${progressWidth}" 
									onchange="updateTaskProgress('${task.name}', this.value, this)"
									oninput="previewTaskProgress('${task.name}', this.value, this)">
							</div>
							<input type="number" class="progress-input" data-task="${task.name}" 
								min="0" max="100" value="${progressWidth}" 
								onchange="updateTaskProgress('${task.name}', this.value, this)">
							<span class="progress-percent">%</span>
						</div>
						<div class="task-status">
							<select class="status-select ${statusClass}" onchange="updateTaskStatusWithProgress('${task.name}', this.value, this)">
								<option value="Open" ${task.status === 'Open' ? 'selected' : ''}>Open</option>
								<option value="Working" ${task.status === 'Working' ? 'selected' : ''}>Working</option>
								<option value="Pending Review" ${task.status === 'Pending Review' ? 'selected' : ''}>Pending Review</option>
								<option value="Overdue" ${task.status === 'Overdue' ? 'selected' : ''}>Overdue</option>
								<option value="Completed" ${task.status === 'Completed' ? 'selected' : ''}>Completed</option>
								<option value="Cancelled" ${task.status === 'Cancelled' ? 'selected' : ''}>Cancelled</option>
							</select>
						</div>
						<div class="task-actions">
							<button class="btn btn-xs btn-default" onclick="addChildTask('${task.name}', '${boqItemData.project}', this)" title="${__('Add Sub-Task')}">
								<i class="fa fa-plus"></i>
							</button>
							${!hasChildren && !isGroup ? `
							<button class="btn btn-xs btn-primary" onclick="add_task_progress_entry('${task.name}')" title="${__('Add Progress')}">
								<i class="fa fa-calendar-plus-o"></i>
							</button>
							` : ''}
							<button class="btn btn-xs btn-default" onclick="view_task_logs('${task.name}')" title="${__('View Progress Logs')}">
								<i class="fa fa-history"></i>
							</button>
							<button class="btn btn-xs btn-default" onclick="window.open('/app/task/${task.name}', '_blank')" title="${__('Open Task')}">
								<i class="fa fa-external-link"></i>
							</button>
						</div>
					</div>
					${hasChildren ? `<div class="task-children">${renderTaskTree(task.children, boqItemData, level + 1)}</div>` : ''}
				</div>
			`;
		}
		return html;
	}

	window._paint_task_dialog = function (boqItemKey, treeData) {
		boqItem = treeData.boq_item || {};
		tasks = treeData.tasks || [];
		hasTasks = treeData.has_tasks || false;
		linkedTask = treeData.linked_task;
		dialog.set_title(__('Task Management - {0}', [boqItem.description?.substring(0, 50) || boqItemKey]));
		renderTaskManagement();
	};

	renderTaskManagement();
	dialog.onhide = function () {
		window._paint_task_dialog = null;
	};
	dialog.show();

	window._current_task_dialog = dialog;
	window._current_boq_item = itemName;
}

function getTaskStatusClass(status) {
	const statusMap = {
		'Open': 'task-status-open',
		'Working': 'task-status-working',
		'Pending Review': 'task-status-pending',
		'Overdue': 'task-status-overdue',
		'Completed': 'task-status-completed',
		'Cancelled': 'task-status-cancelled'
	};
	return statusMap[status] || 'task-status-default';
}

function getTaskManagementStyles() {
	return `<style>
		.task-management-container { padding: 0; }
		.task-header { display: flex; justify-content: space-between; align-items: flex-start; padding: 16px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 8px; margin-bottom: 16px; }
		.task-header h4 { margin: 0 0 8px 0; font-size: 15px; }
		.task-meta { font-size: 12px; opacity: 0.9; }
		.task-meta span { margin-right: 16px; }
		.task-tree { border: 1px solid #e9ecef; border-radius: 8px; overflow: hidden; }
		.task-node { border-bottom: 1px solid #f0f0f0; }
		.task-node:last-child { border-bottom: none; }
		.task-node-content { display: flex; align-items: center; padding: 12px; gap: 12px; transition: background 0.2s; }
		.task-node-content:hover { background: #f8f9fa; }
		.task-toggle { cursor: pointer; width: 20px; text-align: center; color: #6c757d; }
		.task-toggle-placeholder { width: 20px; }
		.task-toggle i { transition: transform 0.2s; }
		.task-node.collapsed .task-toggle i { transform: rotate(-90deg); }
		.task-node.collapsed .task-children { display: none; }
		.task-info { flex: 1; min-width: 0; }
		.task-subject { font-weight: 500; margin-bottom: 2px; }
		.task-subject a { color: #333; text-decoration: none; }
		.task-subject a:hover { color: #5e64ff; }
		.task-subject .badge { font-size: 10px; margin-left: 8px; padding: 2px 6px; }
		.task-details { font-size: 11px; color: #6c757d; }
		.task-details span { margin-right: 8px; }
		.task-tree-header { display: flex; align-items: center; gap: 12px; padding: 8px 12px; background: #f1f5f9; border: 1px solid #e9ecef; border-bottom: none; border-radius: 8px 8px 0 0; font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; }
		.task-tree-header .task-col-name { flex: 1; min-width: 0; padding-left: 32px; }
		.task-tree-header .task-col-area { width: 150px; text-align: center; }
		.task-tree-header .task-col-progress { width: 180px; text-align: center; }
		.task-tree-header .task-col-status { width: 130px; text-align: center; }
		.task-tree-header .task-col-actions { width: 100px; text-align: center; }
		.area-done-wrapper { display: flex; align-items: center; gap: 4px; width: 150px; flex-shrink: 0; }
		.area-done-wrapper .area-label { font-size: 10px; color: #6c757d; margin: 0; min-width: 28px; }
		.area-done-wrapper .qty-input { width: 72px; padding: 2px 4px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px; text-align: center; }
		.area-done-wrapper .qty-input:focus { outline: none; border-color: #5e64ff; }
		.area-done-readonly .qty-input { background: #f8f9fa; }
		.area-done-wrapper .qty-unit { font-size: 10px; color: #6c757d; white-space: nowrap; }
		.task-progress-container { display: flex; align-items: center; gap: 6px; width: 180px; flex-shrink: 0; }
		.progress-bar-wrapper { position: relative; flex: 1; }
		.progress-bar-mini { height: 8px; background: #e9ecef; border-radius: 4px; overflow: hidden; }
		.progress-fill { height: 100%; background: linear-gradient(90deg, #28a745, #20c997); transition: width 0.2s; }
		.progress-slider { position: absolute; top: 0; left: 0; width: 100%; height: 8px; opacity: 0; cursor: pointer; margin: 0; }
		.progress-input { width: 40px; padding: 2px 4px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px; text-align: center; }
		.progress-input:focus { outline: none; border-color: #5e64ff; }
		.progress-percent { font-size: 11px; color: #6c757d; }
		.task-status { width: 130px; }
		.status-select { width: 100%; padding: 4px 8px; border-radius: 4px; border: 1px solid #ddd; font-size: 12px; cursor: pointer; }
		.status-select.task-status-completed { background: #d4edda; border-color: #28a745; }
		.status-select.task-status-working { background: #cce5ff; border-color: #007bff; }
		.status-select.task-status-pending { background: #fff3cd; border-color: #ffc107; }
		.status-select.task-status-overdue { background: #f8d7da; border-color: #dc3545; }
		.status-select.task-status-cancelled { background: #e2e3e5; border-color: #6c757d; }
		.task-actions { display: flex; gap: 4px; }
		.task-children { background: #fafafa; }
		.no-tasks-message { text-align: center; padding: 40px 20px; color: #6c757d; }
	</style>`;
}

// Task management helper functions
window.toggleTaskChildren = function (el) {
	const node = $(el).closest('.task-node');
	node.toggleClass('collapsed');
};

function _resolveTaskExpectedQty($node) {
	if (typeof window.getTaskExpectedQty === 'function') {
		return window.getTaskExpectedQty($node);
	}
	const fromAttr = parseFloat($node.find('.qty-input').attr('data-expected'));
	if (!isNaN(fromAttr) && fromAttr > 0) {
		return fromAttr;
	}
	const fromInput = parseFloat($node.find('.expected-input').val());
	return !isNaN(fromInput) && fromInput > 0 ? fromInput : 0;
}

window.previewTaskProgress = function (task, progress, sliderEl) {
	const $node = $(sliderEl).closest('.task-node');
	const progressValue = Math.min(100, Math.max(0, parseInt(progress) || 0));
	$node.find(`.progress-fill[data-task="${task}"]`).css('width', progressValue + '%');
	$node.find(`.progress-input[data-task="${task}"]`).val(progressValue);
	const expectedQty = _resolveTaskExpectedQty($node);
	if (expectedQty > 0) {
		const qtyValue = (progressValue / 100) * expectedQty;
		$node.find(`.qty-input[data-task="${task}"]`).val(qtyValue.toFixed(2));
	}
};

window.updateTaskQty = function (task, qty, inputEl) {
	const $node = $(inputEl).closest('.task-node');
	const expectedQty = _resolveTaskExpectedQty($node);
	let qtyValue = parseFloat(qty) || 0;
	if (expectedQty > 0) {
		qtyValue = Math.max(0, Math.min(qtyValue, expectedQty));
	}
	if (expectedQty <= 0) {
		frappe.msgprint(__('Please set Expected Area on this sub-task first (e.g. 500 LM out of BOQ total).'));
		return;
	}

	let progressValue = (qtyValue / expectedQty) * 100;
	progressValue = Math.min(100, Math.max(0, parseInt(progressValue) || 0));

	$node.find(`.qty-input[data-task="${task}"]`).val(qtyValue.toFixed(2));
	$node.find(`.progress-fill[data-task="${task}"]`).css('width', progressValue + '%');
	$node.find(`.progress-slider[data-task="${task}"]`).val(progressValue);
	$node.find(`.progress-input[data-task="${task}"]`).val(progressValue);

	let newStatus = null;
	if (progressValue === 100) {
		newStatus = 'Completed';
	} else if (progressValue > 0) {
		const currentStatus = $node.find('.status-select').val();
		if (currentStatus === 'Open') {
			newStatus = 'Working';
		}
	}

	frappe.call({
		method: 'construction_management.api.boq_tasks.update_task_status',
		args: {
			task: task,
			status: newStatus,
			progress: progressValue,
			completed_qty: qtyValue,
			boq_item: window._current_boq_item
		},
		callback: function (r) {
			if (r.message) {
				frappe.show_alert({
					message: __('Area done updated to {0} — log saved', [qtyValue.toFixed(2)]),
					indicator: 'green'
				});
				if (r.message.status) {
					const $select = $node.find('.status-select');
					$select.val(r.message.status);
					$select.removeClass('task-status-open task-status-working task-status-pending task-status-overdue task-status-completed task-status-cancelled');
					$select.addClass(getTaskStatusClass(r.message.status));
				}
				if (window._current_boq_item) {
					refresh_boq_tasks_dialog(window._current_boq_item);
				}
			}
		}
	});
};

if (typeof window.view_task_logs !== 'function') {
	window.view_task_logs = function (task) {
		frappe.call({
			method: 'construction_management.api.boq_tasks.get_task_progress_logs',
			args: { task: task },
			callback: function (r) {
				if (r.message) {
					const d = new frappe.ui.Dialog({
						title: __('Progress Logs - {0}', [task]),
						fields: [{ fieldtype: 'HTML', fieldname: 'logs_html' }]
					});
					let html = `<div class="table-responsive"><table class="table table-bordered">
						<thead><tr>
							<th>${__('Date')}</th>
							<th>${__('Daily Qty')}</th>
							<th>${__('Cumulative Total')}</th>
							<th>${__('Progress %')}</th>
							<th>${__('User')}</th>
							<th>${__('Remarks')}</th>
						</tr></thead><tbody>`;
					if (r.message.length > 0) {
						r.message.forEach(log => {
							html += `<tr>
								<td>${frappe.datetime.str_to_user(log.date)}</td>
								<td>${parseFloat(log.qty_updated || 0).toFixed(2)}</td>
								<td>${parseFloat(log.cumulative_qty || 0).toFixed(2)}</td>
								<td>${parseFloat(log.progress_percent || 0).toFixed(1)}%</td>
								<td>${log.user || ''}</td>
								<td>${log.remarks || ''}</td>
							</tr>`;
						});
					} else {
						html += `<tr><td colspan="6" class="text-center text-muted">${__('No progress logs yet')}</td></tr>`;
					}
					html += '</tbody></table></div>';
					d.fields_dict.logs_html.$wrapper.html(html);
					d.show();
				}
			}
		});
	};
}

window.updateTaskProgress = function (task, progress, inputEl) {
	const progressValue = Math.min(100, Math.max(0, parseInt(progress) || 0));
	const $node = $(inputEl).closest('.task-node');

	$node.find(`.progress-fill[data-task="${task}"]`).css('width', progressValue + '%');
	$node.find(`.progress-slider[data-task="${task}"]`).val(progressValue);
	$node.find(`.progress-input[data-task="${task}"]`).val(progressValue);

	let newStatus = null;
	if (progressValue === 100) {
		newStatus = 'Completed';
	} else if (progressValue > 0) {
		const currentStatus = $node.find('.status-select').val();
		if (currentStatus === 'Open') {
			newStatus = 'Working';
		}
	}

	const expectedQty = _resolveTaskExpectedQty($node);
	let qtyValue = parseFloat($node.find(`.qty-input[data-task="${task}"]`).val()) || 0;
	if (expectedQty > 0) {
		qtyValue = (progressValue / 100) * expectedQty;
		$node.find(`.qty-input[data-task="${task}"]`).val(qtyValue.toFixed(2));
	} else if (progressValue > 0) {
		frappe.msgprint(__('Please set Expected Area on this sub-task first.'));
		return;
	}

	if (progressValue > 0 && qtyValue <= 0) {
		return;
	}

	frappe.call({
		method: 'construction_management.api.boq_tasks.update_task_status',
		args: {
			task: task,
			status: newStatus,
			progress: progressValue,
			completed_qty: qtyValue,
			boq_item: window._current_boq_item
		},
		callback: function (r) {
			if (r.message) {
				frappe.show_alert({ message: __('Progress updated to {0}% — log saved', [progressValue]), indicator: 'green' });
				if (r.message.status) {
					const $select = $node.find('.status-select');
					$select.val(r.message.status);
					$select.removeClass('task-status-open task-status-working task-status-pending task-status-overdue task-status-completed task-status-cancelled');
					$select.addClass(getTaskStatusClass(r.message.status));
				}
				if (window._current_boq_item) {
					refresh_boq_tasks_dialog(window._current_boq_item);
				}
			}
		}
	});
};

window.updateTaskStatusWithProgress = function (task, status, selectEl) {
	const $node = $(selectEl).closest('.task-node');
	let progress = null;

	if (status === 'Completed') {
		progress = 100;
	} else if (status === 'Open') {
		progress = 0;
	} else if (status === 'Cancelled') {
		progress = 0;
	}

	const expectedQty = _resolveTaskExpectedQty($node);
	let qtyValue = parseFloat($node.find(`.qty-input[data-task="${task}"]`).val()) || 0;
	if (progress !== null && expectedQty > 0) {
		qtyValue = (progress / 100) * expectedQty;
		$node.find(`.qty-input[data-task="${task}"]`).val(qtyValue.toFixed(2));
	}

	frappe.call({
		method: 'construction_management.api.boq_tasks.update_task_status',
		args: {
			task: task,
			status: status,
			progress: progress,
			completed_qty: qtyValue,
			boq_item: window._current_boq_item
		},
		callback: function (r) {
			if (r.message) {
				frappe.show_alert({ message: __('Task status updated'), indicator: 'green' });
				const $select = $(selectEl);
				$select.removeClass('task-status-open task-status-working task-status-pending task-status-overdue task-status-completed task-status-cancelled');
				$select.addClass(getTaskStatusClass(status));

				const newProgress = r.message.progress || 0;
				$node.find(`.progress-fill[data-task="${task}"]`).css('width', newProgress + '%');
				$node.find(`.progress-slider[data-task="${task}"]`).val(newProgress);
				$node.find(`.progress-input[data-task="${task}"]`).val(newProgress);
				if (window._current_boq_item) {
					refresh_boq_tasks_dialog(window._current_boq_item);
				}
			}
		}
	});
};

window.createTaskForBOQ = function (boq_item, btnEl) {
	const d = new frappe.ui.Dialog({
		title: __('Create Task for BOQ Item'),
		fields: [
			{ fieldname: 'start_date', label: 'Start Date', fieldtype: 'Date' },
			{ fieldname: 'end_date', label: 'End Date', fieldtype: 'Date' }
		],
		primary_action_label: __('Create'),
		primary_action: function (values) {
			frappe.call({
				method: 'construction_management.api.boq_tasks.create_task_for_existing_boq_item',
				args: {
					boq_item: boq_item,
					start_date: values.start_date,
					end_date: values.end_date
				},
				callback: function (r) {
					if (r.message) {
						d.hide();
						frappe.show_alert({ message: __('Task {0} created', [r.message.task]), indicator: 'green' });
						if (window._current_task_dialog) {
							refresh_boq_tasks_dialog(boq_item);
						}
					}
				}
			});
		}
	});
	d.show();
};

window.addChildTask = function (parent_task, project, btnEl) {
	const boq_item = window._current_boq_item;
	const d = new frappe.ui.Dialog({
		title: __('Add Sub-Task'),
		fields: [
			{ fieldname: 'subject', label: 'Task Name', fieldtype: 'Data', reqd: 1 },
			{ fieldtype: 'Column Break' },
			{ fieldname: 'start_date', label: 'Start Date', fieldtype: 'Date', default: frappe.datetime.get_today() },
			{ fieldname: 'end_date', label: 'End Date', fieldtype: 'Date' },
			{ fieldtype: 'Section Break', label: __('Progress') },
			{
				fieldname: 'expected_area',
				label: __('Expected Area'),
				fieldtype: 'Float',
				reqd: 1,
				default: 0,
				description: __('Portion of BOQ total quantity for this sub-task')
			},
			{ fieldtype: 'Column Break' },
			{ fieldname: 'completed_qty', label: __('Area Done (Total)'), fieldtype: 'Float', default: 0 },
			{ fieldtype: 'Column Break' },
			{ fieldname: 'progress', label: __('Progress (%)'), fieldtype: 'Percent', default: 0 },
			{ fieldtype: 'Section Break', label: __('Assignment') },
			{
				fieldname: 'assignees',
				label: __('Assignees'),
				fieldtype: 'MultiSelectPills',
				get_data: function (txt) {
					return frappe.db.get_link_options('User', txt, {
						user_type: 'System User',
						enabled: 1
					});
				}
			}
		],
		primary_action_label: __('Create'),
		primary_action: function (values) {
			const assignee_list = (values.assignees || []).filter(Boolean);

			frappe.call({
				method: 'construction_management.api.boq_tasks.create_child_task',
				args: {
					parent_task: parent_task,
					subject: values.subject,
					project: project,
					start_date: values.start_date,
					end_date: values.end_date,
					boq_item: boq_item,
					expected_area: values.expected_area || 0,
					progress: values.progress || 0,
					completed_qty: values.completed_qty || 0,
					assignees: assignee_list
				},
				callback: function (r) {
					if (r.message) {
						d.hide();
						frappe.show_alert({ message: __('Sub-task created'), indicator: 'green' });
						if (window._current_task_dialog && window._current_boq_item) {
							refresh_boq_tasks_dialog(window._current_boq_item);
						}
					}
				}
			});
		}
	});
	if (boq_item) {
		frappe.db.get_value('BOQ Item', boq_item, 'total_qty', (r) => {
			const boqTotal = flt(r?.message?.total_qty);
			d.set_df_property('expected_area', 'description', __('BOQ total quantity is {0}. Enter how much this sub-task covers.', [boqTotal]));
			d.show();
		});
	} else {
		d.show();
	}
};

/**
 * Show costs popup for a BOQ item
 * Requirements: 5.3
 */
window.showCostsPopup = function (itemName) {
	frappe.call({
		method: 'construction_management.api.boq_tree.get_boq_item_cost_details',
		args: { boq_item: itemName },
		callback: function (r) {
			const data = r.message || {};
			const cost = data.cost || {};
			const revenue = data.revenue || {};

			// Get estimated costs from BOQ Item
			frappe.call({
				method: 'frappe.client.get',
				args: {
					doctype: 'BOQ Item',
					name: itemName,
					fields: ['estimated_material_cost', 'estimated_labour_cost', 'estimated_asset_cost',
						'estimated_subcontract_cost', 'estimated_other_cost', 'total_estimated_cost']
				},
				callback: function (r2) {
					const estimated = r2.message || {};

					const dialogHtml = `
						<div class="costs-popup-container">
							<!-- Cost Comparison Section -->
							<div class="costs-popup-section">
								<div class="costs-popup-section-title">Cost Comparison (Estimated vs Actual)</div>
								<table class="costs-comparison-table">
									<thead>
										<tr>
											<th>Category</th>
											<th class="text-right">Estimated</th>
											<th class="text-right">Actual</th>
											<th class="text-right">Variance</th>
											<th class="text-right">Progress</th>
										</tr>
									</thead>
									<tbody>
										${renderCostRow('Material', estimated.estimated_material_cost, cost.material)}
										${renderCostRow('Labour', estimated.estimated_labour_cost, cost.labour)}
										${renderCostRow('Asset', estimated.estimated_asset_cost, cost.asset)}
										${renderCostRow('Subcontract', estimated.estimated_subcontract_cost, cost.subcontract)}
										${renderCostRow('Other', estimated.estimated_other_cost, cost.other)}
										<tr class="total-row">
											<td class="font-bold">Total</td>
											<td class="text-right font-bold">${format_currency(estimated.total_estimated_cost || 0)}</td>
											<td class="text-right font-bold">${format_currency(cost.total || 0)}</td>
											<td class="text-right font-bold ${getCostVarianceClass(estimated.total_estimated_cost, cost.total)}">${format_currency((estimated.total_estimated_cost || 0) - (cost.total || 0))}</td>
											<td class="text-right font-bold">${getCostProgress(estimated.total_estimated_cost, cost.total)}%</td>
										</tr>
									</tbody>
								</table>
							</div>
							
							<!-- Revenue Section -->
							<div class="costs-popup-section">
								<div class="costs-popup-section-title">Revenue Summary</div>
								<div class="revenue-grid">
									<div class="revenue-card">
										<span class="revenue-label">Previous</span>
										<span class="revenue-value">${format_currency(revenue.prev || 0)}</span>
									</div>
									<div class="revenue-card">
										<span class="revenue-label">Current</span>
										<span class="revenue-value highlight">${format_currency(revenue.current || 0)}</span>
									</div>
									<div class="revenue-card">
										<span class="revenue-label">To Date</span>
										<span class="revenue-value">${format_currency(revenue.to_date || 0)}</span>
									</div>
									<div class="revenue-card">
										<span class="revenue-label">Total BOQ</span>
										<span class="revenue-value">${format_currency(revenue.total || 0)}</span>
									</div>
								</div>
							</div>
							
							<!-- Profitability Section -->
							<div class="costs-popup-section">
								<div class="costs-popup-section-title">Profitability</div>
								<div class="profit-summary">
									<div class="profit-item">
										<span class="profit-label">Revenue (To Date)</span>
										<span class="profit-value">${format_currency(revenue.to_date || 0)}</span>
									</div>
									<div class="profit-item">
										<span class="profit-label">Cost (To Date)</span>
										<span class="profit-value">${format_currency(cost.total || 0)}</span>
									</div>
									<div class="profit-item profit-gp">
										<span class="profit-label">Gross Profit</span>
										<span class="profit-value ${(revenue.to_date || 0) - (cost.total || 0) >= 0 ? 'text-success' : 'text-danger'}">${format_currency((revenue.to_date || 0) - (cost.total || 0))}</span>
									</div>
								</div>
							</div>
						</div>
						${getCostsPopupStyles()}
					`;

					const dialog = new frappe.ui.Dialog({
						title: __('Cost Details - {0}', [itemName]),
						size: 'large',
						fields: [
							{
								fieldtype: 'HTML',
								fieldname: 'costs_content',
								options: dialogHtml
							}
						]
					});

					dialog.show();
				}
			});
		}
	});
};

function renderCostRow(category, estimated, actual) {
	estimated = estimated || 0;
	actual = actual || 0;
	const variance = estimated - actual;
	const progress = estimated > 0 ? Math.round((actual / estimated) * 100) : 0;
	const varianceClass = variance < 0 ? 'text-danger' : 'text-success';
	const progressClass = progress > 100 ? 'progress-overrun' : '';

	return `
		<tr>
			<td>${category}</td>
			<td class="text-right">${format_currency(estimated)}</td>
			<td class="text-right">${format_currency(actual)}</td>
			<td class="text-right ${varianceClass}">${format_currency(variance)}</td>
			<td class="text-right">
				<div class="cost-progress-bar ${progressClass}">
					<div class="cost-progress-fill" style="width: ${Math.min(progress, 100)}%"></div>
				</div>
				<span class="cost-progress-text ${progressClass}">${progress}%</span>
			</td>
		</tr>
	`;
}

function getCostVarianceClass(estimated, actual) {
	const variance = (estimated || 0) - (actual || 0);
	return variance < 0 ? 'text-danger' : 'text-success';
}

function getCostProgress(estimated, actual) {
	if (!estimated || estimated === 0) return 0;
	return Math.round(((actual || 0) / estimated) * 100);
}

function getCostsPopupStyles() {
	return `<style>
		.costs-popup-container { padding: 0; }
		
		.costs-popup-section { margin-bottom: 20px; }
		.costs-popup-section:last-child { margin-bottom: 0; }
		
		.costs-popup-section-title { font-size: 13px; font-weight: 600; color: #1f272e; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #e8e8e8; }
		
		.costs-comparison-table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e8e8e8; border-radius: 6px; overflow: hidden; }
		.costs-comparison-table th { background: #f7f7f7; padding: 10px 12px; font-size: 10px; font-weight: 500; color: #6c7680; text-transform: uppercase; }
		.costs-comparison-table td { padding: 10px 12px; font-size: 12px; border-top: 1px solid #e8e8e8; }
		.costs-comparison-table .total-row { background: #fafbfc; }
		
		.cost-progress-bar { width: 50px; height: 6px; background: #e8e8e8; border-radius: 3px; display: inline-block; vertical-align: middle; margin-right: 6px; }
		.cost-progress-fill { height: 100%; background: #36b37e; border-radius: 3px; }
		.cost-progress-bar.progress-overrun .cost-progress-fill { background: #ff5630; }
		.cost-progress-text { font-size: 10px; color: #6c7680; }
		.cost-progress-text.progress-overrun { color: #ff5630; font-weight: 600; }
		
		.revenue-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
		.revenue-card { background: #fafbfc; border-radius: 6px; padding: 12px; text-align: center; }
		.revenue-label { display: block; font-size: 10px; color: #6c7680; text-transform: uppercase; margin-bottom: 4px; }
		.revenue-value { display: block; font-size: 14px; font-weight: 600; color: #1f272e; }
		.revenue-value.highlight { color: #1565c0; }
		
		.profit-summary { background: #fafbfc; border-radius: 6px; padding: 16px; }
		.profit-item { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #e8e8e8; }
		.profit-item:last-child { border-bottom: none; }
		.profit-item.profit-gp { background: #f0f0f0; margin: 8px -16px -16px; padding: 12px 16px; border-radius: 0 0 6px 6px; }
		.profit-label { font-size: 12px; color: #6c7680; }
		.profit-value { font-size: 13px; font-weight: 600; color: #1f272e; }
		
		.text-right { text-align: right; }
		.font-bold { font-weight: 600; }
		.text-success { color: #36b37e; }
		.text-danger { color: #ff5630; }
	</style>`;
}

/**
 * Get popup-specific styles
 */
function getPopupStyles() {
	return `<style>
		.txn-popup-container { padding: 0; }
		
		.txn-popup-section { margin-bottom: 20px; }
		.txn-popup-section:last-child { margin-bottom: 0; }
		
		.txn-popup-section-title { 
			font-size: 13px; 
			font-weight: 600; 
			color: #1f272e; 
			margin-bottom: 12px; 
			padding-bottom: 8px; 
			border-bottom: 1px solid #e8e8e8;
			display: flex;
			justify-content: space-between;
			align-items: center;
		}
		
		.txn-popup-count { 
			font-size: 11px; 
			font-weight: 500; 
			color: #6c7680; 
			background: #f0f0f0; 
			padding: 2px 8px; 
			border-radius: 10px; 
		}
		
		.txn-popup-item-details { background: #fafbfc; border-radius: 6px; padding: 12px; }
		
		.txn-popup-detail-row { margin-bottom: 10px; }
		.txn-popup-detail-row .detail-label { font-size: 10px; color: #6c7680; text-transform: uppercase; display: block; margin-bottom: 2px; }
		.txn-popup-detail-row .detail-value { font-size: 13px; color: #1f272e; }
		
		.txn-popup-detail-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
		.detail-cell { }
		.detail-cell .detail-label { font-size: 10px; color: #6c7680; text-transform: uppercase; display: block; margin-bottom: 2px; }
		.detail-cell .detail-value { font-size: 13px; font-weight: 600; color: #1f272e; }
		
		.txn-popup-breakdown-table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e8e8e8; border-radius: 6px; overflow: hidden; }
		.txn-popup-breakdown-table th { background: #f7f7f7; padding: 10px 12px; font-size: 10px; font-weight: 500; color: #6c7680; text-transform: uppercase; }
		.txn-popup-breakdown-table td { padding: 10px 12px; font-size: 12px; border-top: 1px solid #e8e8e8; }
		.txn-popup-breakdown-table .breakdown-label { font-weight: 500; color: #1f272e; }
		.txn-popup-breakdown-table .highlight-current { background: #e3f2fd; color: #1565c0; font-weight: 600; }
		.txn-popup-breakdown-table .font-bold { font-weight: 600; }
		
		.txn-popup-table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e8e8e8; border-radius: 6px; overflow: hidden; }
		.txn-popup-table th { background: #f7f7f7; padding: 10px 12px; font-size: 10px; font-weight: 500; color: #6c7680; text-transform: uppercase; text-align: left; }
		.txn-popup-table td { padding: 10px 12px; font-size: 12px; border-top: 1px solid #e8e8e8; }
		
		.txn-popup-row { cursor: pointer; transition: background 0.15s; }
		.txn-popup-row:hover { background: #f5f7fa; }
		
		.txn-type-badge { padding: 3px 8px; border-radius: 4px; font-size: 10px; font-weight: 600; }
		.txn-type-badge.type-pi { background: #e3f2fd; color: #1565c0; }
		.txn-type-badge.type-pc { background: #fff3e0; color: #e65100; }
		.txn-type-badge.type-tax { background: #e8f5e9; color: #2e7d32; }
		
		.txn-doc-name { font-weight: 500; color: #2490ef; }
		
		.variance-loss { color: #ff5630 !important; font-weight: 600; }
		
		.status-badge-popup { padding: 3px 8px; border-radius: 10px; font-size: 10px; font-weight: 500; }
		.status-badge-popup.status-draft { background: #f7f7f7; color: #6c7680; }
		.status-badge-popup.status-submitted { background: #e3f2fd; color: #1565c0; }
		.status-badge-popup.status-paid { background: #e8f5e9; color: #2e7d32; }
		.status-badge-popup.status-cancelled { background: #ffebee; color: #c62828; }
		.status-badge-popup.status-approved { background: #e8f5e9; color: #2e7d32; }
		.status-badge-popup.status-pending { background: #fff3e0; color: #e65100; }
		.status-badge-popup.status-default { background: #f7f7f7; color: #6c7680; }
		
		.no-txn-popup { text-align: center; padding: 30px; color: #8d99a6; font-size: 13px; background: #fafbfc; border-radius: 6px; }
		
		.text-right { text-align: right; }
	</style>`;
}

function render_transaction_history_row(transactions, parentRow) {
	const colSpan = parentRow.find('td').length;

	if (!transactions || transactions.length === 0) {
		return `<tr class="transaction-history-row"><td colspan="${colSpan}"><div class="txn-container"><div class="no-txn">No transactions found</div></div></td></tr>`;
	}

	let html = `
		<tr class="transaction-history-row">
			<td colspan="${colSpan}">
				<div class="txn-container">
					<div class="txn-header">
						<span class="txn-title">Transaction History</span>
						<span class="txn-count">${transactions.length} transaction(s)</span>
					</div>
					<table class="txn-table">
						<thead>
							<tr>
								<th>TYPE</th>
								<th>DOCUMENT</th>
								<th>DATE</th>
								<th class="text-right">QTY</th>
								<th class="text-right">PI AMOUNT</th>
								<th class="text-right">PC AMOUNT</th>
								<th class="text-right">VARIANCE</th>
								<th>STATUS</th>
							</tr>
						</thead>
						<tbody>
	`;

	transactions.forEach(txn => {
		const typeClass = get_transaction_type_class(txn.doctype);
		const statusClass = get_status_class(txn.status);
		const varianceClass = (txn.variance || 0) > 0 ? 'text-danger' : '';

		html += `
			<tr class="txn-row" onclick="frappe.set_route('Form', '${txn.doctype}', '${txn.name}')">
				<td><span class="txn-type ${typeClass}">${get_short_doctype(txn.doctype)}</span></td>
				<td class="txn-name">${txn.name}</td>
				<td>${txn.date || '-'}</td>
				<td class="text-right">${format_number(txn.qty || 0)}</td>
				<td class="text-right">${format_currency(txn.proforma_amount || txn.amount || 0)}</td>
				<td class="text-right">${format_currency(txn.pc_amount || 0)}</td>
				<td class="text-right ${varianceClass}">${format_currency(txn.variance || 0)}</td>
				<td><span class="status-badge ${statusClass}">${txn.status || '-'}</span></td>
			</tr>
		`;
	});

	html += `</tbody></table></div></td></tr>`;
	return html;
}

function get_short_doctype(doctype) {
	return { 'Sales Order': 'Order', 'Payment Certificate': 'PC', 'Sales Invoice': 'Tax Inv' }[doctype] || doctype;
}

function get_transaction_type_class(doctype) {
	return { 'Sales Order': 'type-pi', 'Payment Certificate': 'type-pc', 'Sales Invoice': 'type-tax' }[doctype] || '';
}

function get_status_class(status) {
	return { 'Draft': 'status-draft', 'Submitted': 'status-submitted', 'Paid': 'status-paid', 'Cancelled': 'status-cancelled', 'Approved': 'status-approved', 'Pending': 'status-pending' }[status] || 'status-default';
}


function get_table_styles() {
	return `<style>
		/* ============================================
		 * BOQ Management Section - Requirements: 4.1
		 * CSS Variables for customization - Requirements: 4.4
		 * ============================================ */
		:root {
			--boq-primary: var(--primary, #2490ef);
			--boq-primary-light: #e3f2fd;
			--boq-danger: var(--danger, #ff5630);
			--boq-danger-light: #ffebee;
			--boq-success: var(--success, #36b37e);
			--boq-success-light: #e8f5e9;
			--boq-warning: #e65100;
			--boq-warning-light: #fff3e0;
			--boq-border: #d1d8dd;
			--boq-border-light: #e8e8e8;
			--boq-text-primary: #1f272e;
			--boq-text-secondary: #6c7680;
			--boq-text-muted: #8d99a6;
			--boq-bg-primary: #fff;
			--boq-bg-secondary: #f7f7f7;
			--boq-bg-tertiary: #fafbfc;
			--boq-shadow: 0 2px 8px rgba(0,0,0,0.08);
			--boq-radius: 8px;
			--boq-radius-sm: 4px;
			--boq-transition: 0.15s ease;
		}
		
		.boq-management-table-container { display: flex; flex-direction: column; gap: 12px; }
		.boq-management-topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
		
		.boq-search-container {
			position: relative;
			display: flex;
			align-items: center;
			width: 300px;
		}
		
		.boq-search-input {
			padding-left: 32px !important;
			height: 32px !important;
			border-radius: 6px !important;
			font-size: 13px !important;
			border: 1px solid var(--boq-border) !important;
		}
		
		.search-icon {
			position: absolute;
			left: 10px;
			color: var(--boq-text-muted);
			pointer-events: none;
		}
		.variance-report-link {
			display: inline-flex;
			align-items: center;
			padding: 6px 10px;
			border-radius: 6px;
			border: 1px solid var(--boq-border);
			background: #fff;
			color: var(--boq-text-primary);
			font-size: 12px;
			font-weight: 600;
			text-decoration: none;
			gap: 6px;
		}
		.variance-report-icon { flex-shrink: 0; }
		.variance-report-link:hover {
			border-color: var(--boq-primary);
			color: var(--boq-primary);
			background: var(--boq-primary-light);
		}
		
		/* Bill Section */
		.bill-section { background: var(--boq-bg-primary); border-radius: var(--boq-radius); border: 1px solid var(--boq-border); overflow: hidden; }
		.bill-section.expanded { box-shadow: var(--boq-shadow); }
		
		.bill-header-row { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; cursor: pointer; background: var(--boq-bg-secondary); transition: background var(--boq-transition); border-bottom: 1px solid var(--boq-border); }
		.bill-header-row:hover { background: #f0f0f0; }
		
		.bill-header-left { display: flex; align-items: center; gap: 10px; }
		.chevron-icon { transition: transform 0.2s; color: var(--boq-text-secondary); }
		.bill-section.expanded .chevron-icon { transform: rotate(180deg); }
		
		.bill-info { display: flex; flex-direction: column; }
		.bill-title { font-size: 14px; font-weight: 600; color: var(--boq-text-primary); }
		.bill-desc { font-size: 11px; color: var(--boq-text-secondary); margin-top: 2px; }
		
		.bill-header-stats { display: flex; gap: 20px; align-items: center; }
		.bill-stat { display: flex; flex-direction: column; align-items: flex-end; }
		.stat-label { font-size: 9px; color: var(--boq-text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
		.stat-value { font-size: 13px; font-weight: 600; color: var(--boq-text-primary); }
		.stat-value.positive { color: var(--boq-success); }
		.stat-value.negative { color: var(--boq-danger); }
		
		/* Financial Summary Button */
		.btn-financial-summary {
			display: inline-flex;
			align-items: center;
			justify-content: center;
			width: 32px;
			height: 32px;
			padding: 0;
			background: rgba(255, 255, 255, 0.9);
			border: 1px solid var(--boq-border);
			border-radius: 6px;
			cursor: pointer;
			transition: all 0.2s;
			margin-left: 8px;
		}
		
		.btn-financial-summary:hover {
			background: #fff;
			border-color: #2490ef;
			transform: scale(1.05);
			box-shadow: 0 2px 8px rgba(36, 144, 239, 0.2);
		}
		
		.btn-financial-summary svg {
			color: #6c7680;
		}
		
		.btn-financial-summary:hover svg {
			color: #2490ef;
		}
		
		.bill-items-container { border-top: none; }
		.bill-toolbar { padding: 10px 16px; background: var(--boq-bg-tertiary); border-bottom: 1px solid var(--boq-border-light); }
		
		/* Frappe-style button - Requirements: 1.2 */
		.btn-frappe { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; font-size: 12px; font-weight: 500; color: var(--boq-text-primary); background: var(--boq-bg-primary); border: 1px solid var(--boq-border); border-radius: var(--boq-radius-sm); cursor: pointer; transition: all var(--boq-transition); }
		.btn-frappe:hover svg { stroke: var(--boq-primary); }
		
		/* Inline Inputs */
		.boq-qty-input, .boq-rate-input {
			width: 100% !important;
			height: 28px !important;
			padding: 2px 6px !important;
			border: 1px solid transparent !important;
			border-radius: 4px !important;
			background: transparent !important;
			text-align: right !important;
			font-size: 12px !important;
			transition: all 0.2s !important;
		}
		
		.boq-qty-input:hover, .boq-rate-input:hover {
			border-color: var(--boq-border) !important;
			background: #fff !important;
		}
		
		.boq-qty-input:focus, .boq-rate-input:focus {
			border-color: var(--boq-primary) !important;
			background: #fff !important;
			outline: none !important;
			box-shadow: 0 0 0 2px rgba(36, 144, 239, 0.1) !important;
		}
		
		/* Remove arrows from number inputs */
		input::-webkit-outer-spin-button,
		input::-webkit-inner-spin-button {
			-webkit-appearance: none;
			margin: 0;
		}
		input[type=number] {
			-moz-appearance: textfield;
		}
		.btn-frappe:hover { background: var(--boq-bg-secondary); border-color: #b8c2cc; }
		
		/* Table - Requirements: 4.1, 4.4 */
		.comprehensive-table-wrapper { 
			max-height: 600px;
			overflow-x: auto; 
			overflow-y: auto;
			-webkit-overflow-scrolling: touch; /* Smooth scrolling on touch devices */
			scroll-behavior: smooth;
		}
		.comprehensive-items-table { 
			width: 100%; 
			min-width: 2200px; /* Minimum width to prevent column truncation */
			border-collapse: collapse; 
			font-size: 11px; 
			border: 1px solid #d1d8dd; 
		}
		.comprehensive-items-table th { background: #f7f7f7; padding: 8px 6px; text-align: center; font-weight: 500; color: #6c7680; font-size: 9px; text-transform: uppercase; letter-spacing: 0.3px; border: 1px solid #d1d8dd; white-space: nowrap; }
		.comprehensive-items-table td { padding: 10px 6px; border: 1px solid #e8e8e8; vertical-align: middle; }
		.comprehensive-items-table td.col-actions { 
			overflow: visible !important; 
			position: relative; 
			z-index: 1;
			padding: 4px 2px !important;
			white-space: normal !important;
		}
		.comprehensive-items-table tr:hover { background: #fafbfc; }
		.comprehensive-items-table tr.fully-billed { opacity: 0.5; }
		
		/* Row status highlighting - Issue #3 */
		.row-status-pc-pending { background-color: #fff3e0 !important; border-left: 3px solid #e65100; }
		.row-status-pc-pending:hover { background-color: #ffe0b2 !important; }
		.row-status-pc-pending .sticky-col { background-color: #fff3e0 !important; }
		.row-status-pc-pending:hover .sticky-col { background-color: #ffe0b2 !important; }
		
		.row-status-invoice-pending { background-color: #e3f2fd !important; border-left: 3px solid #1565c0; }
		.row-status-invoice-pending:hover { background-color: #bbdefb !important; }
		.row-status-invoice-pending .sticky-col { background-color: #e3f2fd !important; }
		.row-status-invoice-pending:hover .sticky-col { background-color: #bbdefb !important; }
		
		.row-status-icon { margin-right: 6px; font-size: 14px; vertical-align: middle; }
		
		/* Column Groups - Subtle colors */
		.col-group { font-weight: 600; font-size: 10px; border-bottom: 2px solid; }
		.col-group-revenue { background: #e3f2fd !important; color: #1565c0; border-color: #1565c0; }
		.col-group-value { background: #fff3e0 !important; color: #e65100; border-color: #e65100; }
		.col-group-qty { background: #e8f5e9 !important; color: #2e7d32; border-color: #2e7d32; }
		.col-group-billing { background: #fce4ec !important; color: #c2185b; border-color: #c2185b; }
		.col-group-estimated { background: #f3e5f5 !important; color: #7b1fa2; border-color: #7b1fa2; }
		.col-group-actual { background: #ffebee !important; color: #c62828; border-color: #c62828; }
		.col-group-profit { background: #e0f2f1 !important; color: #00695c; border-color: #00695c; }
		.col-group-financial { background: #e8f5e9 !important; color: #2e7d32; border-color: #2e7d32; }
		
		/* Column Widths - Requirements: 4.2, 4.3 */
		.col-expand { width: 36px; min-width: 36px; text-align: center; }
		.col-checkbox { width: 32px; min-width: 32px; text-align: center; }
		.col-desc { width: 180px; min-width: 160px; max-width: 200px; text-align: left; word-wrap: break-word; }
		.col-unit { width: 50px; min-width: 50px; text-align: center; }
		.col-rate { width: 80px; min-width: 80px; text-align: right; }
		.col-amount { width: 90px; min-width: 90px; text-align: right; }
		.col-num { width: 80px; min-width: 70px; text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
		.col-actions { width: 160px; min-width: 160px; text-align: center; padding: 4px 2px !important; }
		.col-total-qty { width: 80px; min-width: 70px; text-align: right; }
		
		/* Sticky Columns - Requirements: 2.1, 2.2, 2.3, 2.4 */
		.sticky-col { position: sticky; background: #fff; z-index: 2; }
		.comprehensive-items-table th.sticky-col { background: #f7f7f7; z-index: 3; }
		.comprehensive-items-table tr:hover .sticky-col { background: #fafbfc; }
		
		/* Sticky column left offsets - Recalculated for fixed widths */
		/* Expand (36) + Checkbox (32) + Desc (180) + Unit (50) + Total Qty (80) + Rate (80) */
		.col-expand.sticky-col { left: 0; }
		.col-checkbox.sticky-col { left: 36px; }
		.col-desc.sticky-col { left: 68px; }      /* 36 + 32 */
		.col-unit.sticky-col { left: 247px; }     /* 68 + 180 */
		.col-total-qty.sticky-col { left: 297px; } /* 248 + 50 */
		.col-rate.sticky-col { left: 367px; }     /* 298 + 80 */
		.col-amount.sticky-col { left: 447px; }   /* 378 + 80 */
		
		/* Visual separation for last sticky column - Requirements: 2.1, 2.2, 2.3, 2.4 */
		.sticky-col-last { 
			border-right: 2px solid #ccc !important; /* Requirements: 2.1 - Changed from blue to #ccc */
			box-shadow: 2px 0 4px rgba(0,0,0,0.1); 
			margin-right: 0; /* Remove visual gap after last sticky column */
			transition: border-color 0.2s ease, box-shadow 0.2s ease; /* Requirements: 2.2 */
		}
		
		/* Expand Button */
		.expand-btn { width: 28px; height: 28px; border-radius: 4px; border: 1px solid #d1d8dd; background: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.15s; color: #6c7680; }
		.expand-btn:hover { background: #f7f7f7; border-color: #b8c2cc; }
		.expand-btn.expanded { background: #e3f2fd; color: #1565c0; border-color: #1565c0; }
		.expand-btn.expanded svg { transform: rotate(180deg); }
		.expand-btn.loading { opacity: 0.5; cursor: wait; }
		
		/* Input Fields */
		.current-qty-input, .current-value-input { width: 60px; padding: 4px 6px; border: 1px solid #d1d8dd; border-radius: 4px; font-size: 11px; text-align: right; background: #fff; }
		.current-qty-input:focus, .current-value-input:focus { outline: none; border-color: #2490ef; box-shadow: 0 0 0 2px rgba(36, 144, 239, 0.15); }
		.current-qty-input:disabled, .current-value-input:disabled { background: #f7f7f7; color: #8d99a6; }
		
		/* Text Styling */
		.font-bold { font-weight: 600; }
		.text-success { color: #36b37e; }
		.text-danger { color: #ff5630; }
		.text-right { text-align: right; }
		.balance-value { color: #36b37e; font-weight: 500; }
		
		/* Item Description */
		.item-desc-wrapper { display: flex; flex-direction: column; gap: 2px; }
		.item-code { font-size: 10px; color: #2490ef; background: #e3f2fd; padding: 2px 6px; border-radius: 3px; display: inline-block; font-weight: 500; }
		.item-desc { color: #1f272e; line-height: 1.4; font-size: 11px; }
		
		/* Action Buttons - Requirements: 1.1, 1.2, 1.3, 1.4, 1.5 */
		.comprehensive-items-table .action-icons { 
			display: flex !important;
			gap: 2px !important;
			justify-content: center !important;
			align-items: center !important;
			flex-wrap: nowrap !important;
			visibility: visible !important;
			opacity: 1 !important;
			width: auto !important;
			height: auto !important;
			overflow: visible !important;
			position: relative !important;
		}
		.comprehensive-items-table .action-btn { 
			width: 22px !important;
			height: 22px !important;
			min-width: 22px !important;
			min-height: 22px !important;
			max-width: 22px !important;
			padding: 0 !important;
			border-radius: 4px !important; 
			border: 1px solid #d1d8dd !important; 
			background: #fff !important; 
			cursor: pointer !important; 
			display: inline-flex !important;
			align-items: center !important; 
			justify-content: center !important; 
			transition: all 0.15s ease !important;
			color: #6c7680 !important; 
			flex-shrink: 0 !important;
			visibility: visible !important;
			opacity: 1 !important;
			position: relative !important;
			z-index: 10 !important;
			overflow: visible !important;
		}
		/* Requirements: 1.5 - Hover/focus states with visual feedback */
		.comprehensive-items-table .action-btn:hover:not(:disabled) { 
			background: #f0f0f0 !important; 
			border-color: #b8c2cc !important; 
			color: #1f272e !important; 
		}
		.comprehensive-items-table .action-btn:focus:not(:disabled) {
			outline: none !important;
			border-color: #2490ef !important;
		}
		.comprehensive-items-table .action-btn:disabled { opacity: 0.4 !important; cursor: not-allowed !important; }
		/* Button type colors */
		.comprehensive-items-table .action-btn-tasks:hover:not(:disabled) { background: #e3f2fd !important; border-color: #2490ef !important; color: #2490ef !important; }
		.comprehensive-items-table .action-btn-costs:hover:not(:disabled) { background: #fff3e0 !important; border-color: #e65100 !important; color: #e65100 !important; }
		.comprehensive-items-table .action-btn-edit:hover:not(:disabled) { background: #f3e5f5 !important; border-color: #7b1fa2 !important; color: #7b1fa2 !important; }
		.comprehensive-items-table .action-btn-delete:hover:not(:disabled) { background: #ffebee !important; border-color: #ff5630 !important; color: #ff5630 !important; }
		.comprehensive-items-table .action-btn-invoice:hover:not(:disabled) { background: #e8f5e9 !important; border-color: #36b37e !important; color: #36b37e !important; }
		.comprehensive-items-table .action-btn-pc { background: #e8f5e9 !important; border-color: #2e7d32 !important; }
		.comprehensive-items-table .action-btn-pc:hover:not(:disabled) { background: #c8e6c9 !important; border-color: #1b5e20 !important; color: #1b5e20 !important; }
		
		/* Action button SVG icons */
		.comprehensive-items-table .action-btn svg {
			width: 12px !important;
			height: 12px !important;
			stroke: currentColor !important;
			fill: none !important;
			display: block !important;
			visibility: visible !important;
			opacity: 1 !important;
		}
		
		/* Force visibility of all action buttons */
		.comprehensive-items-table td.col-actions .action-btn {
			display: inline-flex !important;
			visibility: visible !important;
			opacity: 1 !important;
		}
		
		/* Selection Toolbar - Frappe Style - Requirements: 1.1, 1.4 */
		.selection-action-toolbar { 
			display: flex; 
			justify-content: space-between; 
			align-items: center; 
			padding: 10px 16px; 
			background: var(--boq-text-primary, #1f272e); 
			border-radius: 6px; 
			margin-bottom: 12px;
			position: sticky;
			top: 0;
			z-index: 150; /* Requirements: 1.4 - z-index between 100-200 */
		}
		.toolbar-info { display: flex; align-items: center; gap: 12px; }
		.selection-count { color: #fff; font-weight: 500; font-size: 13px; }
		.toolbar-actions { display: flex; gap: 8px; }
		
		.btn-toolbar { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; font-size: 12px; font-weight: 500; border-radius: var(--boq-radius-sm, 4px); cursor: pointer; transition: all var(--boq-transition, 0.15s); border: none; min-height: 36px; }
		.btn-primary-toolbar { background: var(--boq-primary, #2490ef); color: #fff; }
		.btn-primary-toolbar:hover { background: #1a73e8; }
		.btn-secondary-toolbar { background: var(--boq-bg-primary, #fff); color: var(--boq-text-primary, #1f272e); border: 1px solid var(--boq-border, #d1d8dd); }
		.btn-secondary-toolbar:hover { background: var(--boq-bg-secondary, #f7f7f7); }
		.btn-clear-toolbar { background: transparent; color: #fff; border: 1px solid rgba(255,255,255,0.3); }
		.btn-clear-toolbar:hover { background: rgba(255,255,255,0.1); }
		.btn-danger-toolbar { background: #ff5630; color: #fff; }
		.btn-danger-toolbar:hover { background: #de350b; }
		
		.btn-delete-bill { border-color: #ff5630 !important; color: #ff5630 !important; }
		.btn-delete-bill:hover { background: #ffebee !important; }
		
		/* Transaction History */
		.transaction-history-row { background: #fafbfc; }
		.txn-container { padding: 16px; border-top: 2px solid #e8e8e8; margin-left: 36px; }
		.txn-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
		.txn-title { font-weight: 600; color: #1f272e; font-size: 13px; }
		.txn-count { font-size: 11px; color: #6c7680; background: #e8e8e8; padding: 2px 8px; border-radius: 10px; }
		.no-txn { text-align: center; color: #8d99a6; padding: 20px; font-size: 12px; }
		
		.txn-table { width: 100%; border-collapse: collapse; font-size: 11px; background: #fff; border-radius: 6px; overflow: hidden; border: 1px solid #e8e8e8; }
		.txn-table th { background: #f7f7f7; padding: 10px 12px; text-align: left; font-weight: 500; color: #6c7680; font-size: 9px; text-transform: uppercase; letter-spacing: 0.3px; }
		.txn-table td { padding: 10px 12px; border-bottom: 1px solid #e8e8e8; }
		.txn-row { cursor: pointer; transition: background 0.15s; }
		.txn-row:hover { background: #fafbfc; }
		
		.txn-type { padding: 3px 8px; border-radius: 3px; font-size: 10px; font-weight: 600; }
		.type-pi { background: #e3f2fd; color: #1565c0; }
		.type-pc { background: #e8f5e9; color: #2e7d32; }
		.type-tax { background: #fff3e0; color: #e65100; }
		
		.txn-name { font-weight: 500; color: #2490ef; }
		
		.status-badge { padding: 3px 8px; border-radius: 10px; font-size: 10px; font-weight: 500; }
		.status-draft { background: #f7f7f7; color: #6c7680; }
		.status-submitted { background: #e3f2fd; color: #1565c0; }
		.status-paid { background: #e8f5e9; color: #2e7d32; }
		.status-cancelled { background: #ffebee; color: #c62828; }
		.status-approved { background: #e8f5e9; color: #2e7d32; }
		.status-pending { background: #fff3e0; color: #e65100; }
		.status-default { background: #f7f7f7; color: #6c7680; }
		
		/* No items message */
		.no-bills-message, .no-items-message { text-align: center; padding: 40px 20px; color: #8d99a6; font-size: 13px; }
		
		/* Inline Breakdown Section */
		.inline-breakdown-row { background: #fafbfc; }
		.inline-breakdown-row:hover { background: #fafbfc; }
		.inline-breakdown-container { padding: 16px 20px; border-top: 2px solid #2490ef; margin: 0; }
		
		.inline-breakdown-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #e8e8e8; }
		.inline-header-left { display: flex; align-items: center; gap: 12px; }
		.inline-title { font-size: 14px; font-weight: 600; color: #1f272e; }
		.inline-item-code { font-size: 11px; color: #2490ef; background: #e3f2fd; padding: 3px 8px; border-radius: 4px; font-weight: 500; }
		
		.inline-status-indicator { padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 500; }
		.status-none { background: #f7f7f7; color: #6c7680; }
		.status-pi-pending { background: #fff3e0; color: #e65100; }
		.status-pc-draft { background: #e3f2fd; color: #1565c0; }
		.status-pc-submitted { background: #e8f5e9; color: #2e7d32; }
		.status-invoiced { background: #e0f2f1; color: #00695c; }
		
		.inline-breakdown-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 16px; }
		
		.inline-section { background: #fff; border: 1px solid #e8e8e8; border-radius: 6px; padding: 12px; }
		.inline-section-title { font-size: 12px; font-weight: 600; color: #1f272e; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
		
		.inline-breakdown-table { width: 100%; border-collapse: collapse; }
		.inline-breakdown-table th { background: #f7f7f7; padding: 8px 10px; font-size: 10px; font-weight: 500; color: #6c7680; text-transform: uppercase; border: 1px solid #e8e8e8; }
		.inline-breakdown-table td { padding: 8px 10px; font-size: 12px; border: 1px solid #e8e8e8; }
		.inline-breakdown-table .breakdown-label { font-weight: 500; color: #1f272e; background: #fafbfc; }
		.inline-breakdown-table .highlight-current { background: #e3f2fd; color: #1565c0; font-weight: 600; }
		
		.cost-revenue-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
		.cost-card { background: #fafbfc; border-radius: 6px; padding: 10px; text-align: center; }
		.cost-card.positive { background: #e8f5e9; }
		.cost-card.negative { background: #ffebee; }
		.cost-label { display: block; font-size: 10px; color: #6c7680; text-transform: uppercase; margin-bottom: 4px; }
		.cost-value { display: block; font-size: 14px; font-weight: 600; color: #1f272e; }
		.cost-card.positive .cost-value { color: #2e7d32; }
		.cost-card.negative .cost-value { color: #c62828; }
		
		.inline-transactions { background: #fff; border: 1px solid #e8e8e8; border-radius: 6px; padding: 12px; }
		.txn-count-badge { background: #e8e8e8; color: #6c7680; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; }
		
		.inline-txn-table { width: 100%; border-collapse: collapse; font-size: 11px; }
		.inline-txn-table th { background: #f7f7f7; padding: 8px 10px; text-align: left; font-weight: 500; color: #6c7680; font-size: 9px; text-transform: uppercase; border-bottom: 1px solid #e8e8e8; }
		.inline-txn-table td { padding: 8px 10px; border-bottom: 1px solid #e8e8e8; }
		.inline-txn-row { cursor: pointer; transition: background 0.15s; }
		.inline-txn-row:hover { background: #f5f7fa; }
		
		.txn-type-badge { padding: 3px 8px; border-radius: 4px; font-size: 10px; font-weight: 600; }
		.txn-doc-name { font-weight: 500; color: #2490ef; }
		.variance-loss { color: #ff5630 !important; font-weight: 600; }
		
		.no-transactions { text-align: center; padding: 20px; color: #8d99a6; font-size: 12px; background: #fafbfc; border-radius: 4px; }
		
		/* ============================================
		 * Responsive Media Queries - Requirements: 4.3
		 * Breakpoints: 768px, 992px, 1200px
		 * ============================================ */
		
		/* Large screens (1200px+) */
		@media (min-width: 1200px) {
			.comprehensive-items-table { min-width: 2200px; }
			.col-desc { min-width: 180px; max-width: 260px; }
			.action-btn { width: 40px; height: 40px; }
		}
		
		/* Medium screens (992px - 1199px) */
		@media (max-width: 1199px) and (min-width: 992px) {
			.comprehensive-items-table { min-width: 1800px; }
			.col-desc { min-width: 160px; max-width: 220px; }
			.bill-header-stats { gap: 15px; }
			.action-btn { width: 36px; height: 36px; min-width: 36px; min-height: 36px; }
		}
		
		/* Tablet screens (768px - 991px) */
		@media (max-width: 991px) and (min-width: 768px) {
			.comprehensive-items-table { min-width: 1500px; }
			.col-desc { min-width: 140px; max-width: 200px; }
			.bill-header-stats { gap: 12px; }
			.stat-label { font-size: 8px; }
			.stat-value { font-size: 12px; }
			.action-btn { width: 34px; height: 34px; min-width: 34px; min-height: 34px; }
			.inline-breakdown-grid { grid-template-columns: 1fr; }
		}
		
		/* Mobile screens (<768px) */
		@media (max-width: 767px) {
			.comprehensive-items-table { min-width: 1200px; }
			.col-desc { min-width: 120px; max-width: 160px; }
			.bill-header-row { flex-direction: column; align-items: flex-start; gap: 10px; }
			.bill-header-stats { width: 100%; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
			.stat-label { font-size: 8px; }
			.stat-value { font-size: 11px; }
			.action-btn { width: 32px; height: 32px; min-width: 32px; min-height: 32px; }
			.action-icons { gap: 2px; }
			.inline-breakdown-grid { grid-template-columns: 1fr; }
			.cost-revenue-grid { grid-template-columns: 1fr; }
			.selection-action-toolbar { flex-direction: column; gap: 10px; }
			.toolbar-actions { width: 100%; justify-content: center; }
		}
	</style>`;
}
/**
 * Create Payment Certificate from a BOQ Item row
 * This is triggered from the PC button on highlighted rows (Issue #3)
 * @param {string} boqItemName - The BOQ Item name
 */
window.createPCFromRow = function (boqItemName) {
	// Show loading indicator
	frappe.show_alert({ message: __('Looking for pending proforma invoices...'), indicator: 'blue' });

	// Call API to get pending proformas for this BOQ item
	frappe.call({
		method: 'construction_management.api.boq_invoice.get_pending_proformas_for_item',
		args: { boq_item: boqItemName },
		callback: function (r) {
			if (r.message && r.message.length > 0) {
				const proformas = r.message;

				if (proformas.length === 1) {
					// Auto-select if only one proforma
					showPCCreationDialog(proformas[0]);
				} else {
					// Show selection dialog for multiple proformas
					showProformaSelectionForPC(proformas, boqItemName);
				}
			} else {
				frappe.show_alert({
					message: __('No pending proforma invoices found for this item'),
					indicator: 'orange'
				});
			}
		},
		error: function (err) {
			frappe.show_alert({
				message: __('Error fetching proforma invoices: {0}', [err.message || 'Unknown error']),
				indicator: 'red'
			});
		}
	});
};

/**
 * Show PC creation dialog with auto-populated values
 */
function showPCCreationDialog(proforma) {
	const fields = [
		{
			fieldname: 'proforma_info',
			fieldtype: 'HTML',
			options: `<div style="padding: 10px; background: #f5f5f5; border-radius: 4px; margin-bottom: 15px;">
				<strong>Sales Order:</strong> ${proforma.name}<br>
				<strong>Amount:</strong> ${format_currency(proforma.amount || proforma.net_amount)}<br>
				<strong>Date:</strong> ${frappe.datetime.str_to_user(proforma.posting_date)}
			</div>`
		},
		{
			fieldname: 'accepted_amount',
			fieldtype: 'Currency',
			label: __('Accepted Amount'),
			reqd: 1,
			default: flt(proforma.net_amount || proforma.amount),
			description: __('Auto-populated from Proforma. Modify if customer approved different amount.')
		},
		{
			fieldname: 'posting_date',
			fieldtype: 'Date',
			label: __('Posting Date'),
			default: frappe.datetime.get_today(),
			reqd: 1
		},
		{
			fieldname: 'remarks',
			fieldtype: 'Small Text',
			label: __('Remarks')
		}
	];

	const dialog = new frappe.ui.Dialog({
		title: __('Create Payment Certificate'),
		fields: fields,
		primary_action_label: __('Create'),
		primary_action: function (values) {
			frappe.call({
				method: 'construction_management.api.boq_invoice.create_payment_certificate',
				args: {
					proforma_invoice: proforma.name,
					posting_date: values.posting_date,
					accepted_amount: values.accepted_amount
				},
				freeze: true,
				freeze_message: __('Creating Payment Certificate...'),
				callback: function (r) {
					if (r.message) {
						dialog.hide();
						frappe.show_alert({
							message: __('Payment Certificate {0} created successfully', [r.message]),
							indicator: 'green'
						});
						// Navigate to the PC
						frappe.set_route('Form', 'Payment Certificate', r.message);
					}
				}
			});
		}
	});

	dialog.show();
}

/**
 * Show dialog to select from multiple proformas
 */
function showProformaSelectionForPC(proformas, boqItemName) {
	let html = '<table class="table table-bordered"><thead><tr><th>Select</th><th>Proforma</th><th>Date</th><th>Amount</th></tr></thead><tbody>';

	proformas.forEach((p, idx) => {
		html += `<tr>
			<td><input type="radio" name="proforma_select" value="${p.name}" ${idx === 0 ? 'checked' : ''}></td>
			<td>${p.name}</td>
			<td>${frappe.datetime.str_to_user(p.posting_date)}</td>
			<td>${format_currency(p.net_amount || p.amount)}</td>
		</tr>`;
	});

	html += '</tbody></table>';

	const dialog = new frappe.ui.Dialog({
		title: __('Select Sales Order'),
		fields: [
			{
				fieldname: 'info',
				fieldtype: 'HTML',
				options: `<p>Multiple proforma invoices found for this BOQ item. Please select one to create a Payment Certificate.</p>${html}`
			}
		],
		primary_action_label: __('Continue'),
		primary_action: function () {
			const selectedName = dialog.$wrapper.find('input[name="proforma_select"]:checked').val();
			if (selectedName) {
				dialog.hide();
				const selectedProforma = proformas.find(p => p.name === selectedName);
				showPCCreationDialog(selectedProforma);
			} else {
				frappe.msgprint(__('Please select a proforma invoice'));
			}
		}
	});

	dialog.show();
}

// Export for use in project.js
if (typeof module !== 'undefined' && module.exports) {
	module.exports = { render_boq_management_table };
}

/**
 * Format currency value
 */
function format_currency(value) {
	if (typeof frappe !== 'undefined' && frappe.format_currency) {
		return frappe.format_currency(value);
	}
	const num = parseFloat(value) || 0;
	return new Intl.NumberFormat('en-US', {
		style: 'currency',
		currency: 'USD',
		minimumFractionDigits: 2
	}).format(num);
}

/**
 * Format number value
 */
function format_number(value, precision = BOQ_QTY_PRECISION) {
	if (typeof frappe !== 'undefined' && frappe.format) {
		return frappe.format(value, { fieldtype: 'Float', precision: precision });
	}
	const num = parseFloat(value) || 0;
	return num.toLocaleString('en-US', {
		minimumFractionDigits: precision,
		maximumFractionDigits: precision
	});
}


/**
 * Initialize profit/loss indicators for BOQ items
 * Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
 */
function initialize_profit_indicators(container, items) {
	if (!window.ProfitLossIndicator) {
		console.warn('ProfitLossIndicator not loaded');
		return;
	}

	const indicator = new window.ProfitLossIndicator();

	// Add indicators to each item row
	items.forEach(item => {
		const indicatorContainer = container.find(`.profit-indicator-container[data-item-id="${item.name}"]`);
		if (indicatorContainer.length > 0) {
			const itemData = {
				name: item.name,
				total_amount: item.revenue?.total || item.amount?.total || 0,
				total_estimated_cost: item.estimated_costs?.total || 0
			};

			const profitStatus = indicator.calculateProfitStatus(itemData);
			const indicatorHTML = indicator.createIndicatorHTML(profitStatus, item.name);
			indicatorContainer.html(indicatorHTML);
		}
	});

	// Store indicator instance for later updates
	if (!window.boqProfitIndicators) {
		window.boqProfitIndicators = new Map();
	}
	window.boqProfitIndicators.set(container.attr('id') || 'default', indicator);

	return indicator;
}

/**
 * Update profit indicator when item data changes
 * Requirements: 8.5 - Real-time updates
 */
function update_profit_indicator(itemId, updatedData) {
	if (!window.ProfitLossIndicator) return;

	// Get indicator instance
	const indicators = window.boqProfitIndicators;
	if (!indicators) return;

	// Update all indicator instances (in case multiple tables)
	indicators.forEach(indicator => {
		indicator.updateIndicator(itemId, updatedData);
	});
}

/**
 * Refresh all profit indicators
 */
function refresh_profit_indicators(container, items) {
	if (!window.ProfitLossIndicator) return;

	const indicatorKey = container.attr('id') || 'default';
	const indicator = window.boqProfitIndicators?.get(indicatorKey);

	if (indicator) {
		indicator.updateIndicators(items);
	} else {
		initialize_profit_indicators(container, items);
	}
}

// Export functions for global access
window.initialize_profit_indicators = initialize_profit_indicators;
window.update_profit_indicator = update_profit_indicator;
window.refresh_profit_indicators = refresh_profit_indicators;

/**
 * Show adjustments for a billing cycle
 */
window.showAdjustments = function (cycleId) {
	// Find the cycle data from the current display
	const cycleRow = $(`.grouped-transaction-row[data-cycle-id="${cycleId}"]`);
	if (cycleRow.length === 0) return;

	// Toggle the cycle details to show adjustments
	toggleCycleDetails(cycleId);
};

/**
 * Helper function to get transaction type class
 */
function get_transaction_type_class(doctype) {
	const classMap = {
		'Sales Invoice': 'txn-type-invoice',
		'Sales Order': 'txn-type-proforma',
		'Payment Certificate': 'txn-type-pc'
	};
	return classMap[doctype] || 'txn-type-default';
}

/**
 * Helper function to get status class
 */
function get_status_class(status) {
	const classMap = {
		'Draft': 'status-draft',
		'Submitted': 'status-submitted',
		'Paid': 'status-paid',
		'Cancelled': 'status-cancelled'
	};
	return classMap[status] || 'status-default';
}

/**
 * Helper function to get short doctype name
 */
function get_short_doctype(doctype) {
	const shortNames = {
		'Sales Invoice': 'SI',
		'Sales Order': 'Order',
		'Payment Certificate': 'PC'
	};
	return shortNames[doctype] || doctype;
}

/**
 * Test transaction grouping functionality
 */
window.testTransactionGrouping = function (boqItem) {
	if (!boqItem) {
		frappe.prompt([
			{
				fieldname: 'boq_item',
				fieldtype: 'Link',
				options: 'BOQ Item',
				label: 'BOQ Item',
				reqd: 1
			}
		], function (values) {
			testTransactionGrouping(values.boq_item);
		}, 'Test Transaction Grouping');
		return;
	}

	frappe.call({
		method: 'construction_management.api.transaction_grouping_test.test_transaction_grouping',
		args: { boq_item: boqItem },
		callback: function (r) {
			if (r.message) {
				const result = r.message;
				let message = `<h4>Transaction Grouping Test Results</h4>`;
				message += `<p><strong>BOQ Item:</strong> ${result.boq_item}</p>`;
				message += `<p><strong>Status:</strong> ${result.status}</p>`;

				if (result.status === 'success') {
					message += `<h5>Raw Data Summary:</h5>`;
					message += `<ul>`;
					message += `<li>Ledger Entries: ${result.raw_data_summary.ledger_entries}</li>`;
					message += `<li>Payment Certificates: ${result.raw_data_summary.payment_certificates}</li>`;
					message += `<li>Total Amount: ${format_currency(result.raw_data_summary.total_amount)}</li>`;
					message += `</ul>`;

					message += `<h5>Grouped Data Summary:</h5>`;
					message += `<ul>`;
					message += `<li>Billing Cycles: ${result.grouped_data_summary.billing_cycles}</li>`;
					message += `<li>Total Amount: ${format_currency(result.grouped_data_summary.total_amount)}</li>`;
					message += `</ul>`;

					const validation = result.validation_results;
					message += `<h5>Validation Results:</h5>`;
					message += `<ul>`;
					message += `<li>Amount Match: ${validation.total_amount_match ? '✅' : '❌'}</li>`;
					message += `<li>Quantity Match: ${validation.total_qty_match ? '✅' : '❌'}</li>`;
					if (validation.issues.length > 0) {
						message += `<li>Issues: ${validation.issues.join(', ')}</li>`;
					}
					message += `</ul>`;
				} else {
					message += `<p><strong>Error:</strong> ${result.error_message}</p>`;
				}

				frappe.msgprint({
					title: 'Transaction Grouping Test',
					message: message,
					indicator: result.status === 'success' ? 'green' : 'red'
				});
			}
		}
	});
};

/**
 * Run comprehensive transaction grouping tests
 */
window.runComprehensiveGroupingTest = function () {
	frappe.call({
		method: 'construction_management.api.transaction_grouping_test.run_comprehensive_test',
		callback: function (r) {
			if (r.message) {
				const result = r.message;
				let message = `<h4>Comprehensive Transaction Grouping Test Results</h4>`;

				if (result.status === 'completed') {
					const summary = result.summary;
					message += `<h5>Test Summary:</h5>`;
					message += `<ul>`;
					message += `<li>Total Tests: ${summary.total_tests}</li>`;
					message += `<li>Successful Tests: ${summary.successful_tests}</li>`;
					message += `<li>Failed Tests: ${summary.failed_tests}</li>`;
					message += `<li>Integrity Passes: ${summary.integrity_passes}</li>`;
					message += `<li>Integrity Failures: ${summary.integrity_failures}</li>`;
					message += `</ul>`;

					message += `<h5>Items Tested:</h5>`;
					message += `<ul>`;
					result.sample_items_tested.forEach(item => {
						message += `<li>${item}</li>`;
					});
					message += `</ul>`;
				} else {
					message += `<p><strong>Error:</strong> ${result.error_message}</p>`;
				}

				frappe.msgprint({
					title: 'Comprehensive Test Results',
					message: message,
					indicator: result.status === 'completed' ? 'green' : 'red'
				});
			}
		}
	});
};
/**
 * Enhanced variance highlighting functions
 */
function getVarianceClass(varianceAmount) {
	if (!varianceAmount || varianceAmount === 0) return 'variance-zero';
	return varianceAmount > 0 ? 'variance-positive' : 'variance-negative';
}

/**
 * Render workflow progress bar
 */
function renderWorkflowProgressBar(cycle) {
	const steps = [
		{ key: 'proforma_invoice', label: 'Proforma', icon: 'fa-file-text-o' },
		{ key: 'payment_certificate', label: 'Payment Cert', icon: 'fa-certificate' },
		{ key: 'tax_invoice', label: 'Tax Invoice', icon: 'fa-file-text' }
	];

	let progressHtml = '<div class="workflow-progress-bar">';

	steps.forEach((step, index) => {
		let stepClass = 'pending';

		if (cycle[step.key]) {
			stepClass = 'completed';
		} else if (index === 0 || (index === 1 && cycle.proforma_invoice) || (index === 2 && cycle.payment_certificate)) {
			stepClass = 'current';
		}

		progressHtml += `
			<div class="progress-step ${stepClass}">
				<i class="fa ${step.icon}"></i>
				<span>${step.label}</span>
			</div>
		`;

		if (index < steps.length - 1) {
			progressHtml += '<i class="fa fa-arrow-right progress-arrow"></i>';
		}
	});

	progressHtml += '</div>';
	return progressHtml;
}

/**
 * Enhanced expand/collapse functionality with animation
 */
window.toggleCycleDetailsEnhanced = function (cycleId) {
	const detailsRow = $(`#cycle-details-${cycleId}`);
	const expandBtn = $(`.grouped-transaction-row[data-cycle-id="${cycleId}"] .expand-cycle-btn i`);
	const cycleRow = $(`.grouped-transaction-row[data-cycle-id="${cycleId}"]`);

	if (detailsRow.is(':visible')) {
		// Collapse with animation
		detailsRow.find('.cycle-details-container').slideUp(300, function () {
			detailsRow.hide();
			expandBtn.removeClass('fa-chevron-up').addClass('fa-chevron-down');
			cycleRow.removeClass('expanded');
		});
	} else {
		// Expand with animation
		detailsRow.show();
		detailsRow.find('.cycle-details-container').hide().slideDown(300);
		expandBtn.removeClass('fa-chevron-down').addClass('fa-chevron-up');
		cycleRow.addClass('expanded');

		// Scroll to details if needed
		setTimeout(() => {
			const detailsTop = detailsRow.offset().top;
			const windowTop = $(window).scrollTop();
			const windowHeight = $(window).height();

			if (detailsTop > windowTop + windowHeight - 200) {
				$('html, body').animate({
					scrollTop: detailsTop - 100
				}, 300);
			}
		}, 350);
	}
};

/**
 * Show detailed variance breakdown
 */
window.showVarianceBreakdown = function (cycleId, proformaAmount, pcAmount, variance) {
	const variancePercent = proformaAmount > 0 ? ((variance / proformaAmount) * 100).toFixed(2) : 0;
	const varianceType = variance > 0 ? 'Loss' : variance < 0 ? 'Gain' : 'No Variance';
	const varianceClass = variance > 0 ? 'text-danger' : variance < 0 ? 'text-success' : 'text-muted';

	const message = `
		<div class="variance-breakdown">
			<h5>Variance Breakdown - Cycle ${cycleId}</h5>
			<table class="table table-bordered">
				<tr>
					<td><strong>Proforma Amount:</strong></td>
					<td class="text-right">${format_currency(proformaAmount)}</td>
				</tr>
				<tr>
					<td><strong>Payment Certificate Amount:</strong></td>
					<td class="text-right">${format_currency(pcAmount)}</td>
				</tr>
				<tr class="${varianceClass}">
					<td><strong>Variance (${varianceType}):</strong></td>
					<td class="text-right">
						${format_currency(Math.abs(variance))}
						<small>(${variancePercent}%)</small>
					</td>
				</tr>
			</table>
			<div class="variance-explanation">
				<small class="text-muted">
					${variance > 0 ?
			'Positive variance indicates the Payment Certificate amount is less than the Proforma amount (potential loss).' :
			variance < 0 ?
				'Negative variance indicates the Payment Certificate amount is more than the Proforma amount (potential gain).' :
				'No variance - Payment Certificate amount matches Proforma amount exactly.'
		}
				</small>
			</div>
		</div>
	`;

	frappe.msgprint({
		title: 'Variance Details',
		message: message,
		indicator: variance > 0 ? 'red' : variance < 0 ? 'green' : 'blue'
	});
};

/**
 * Toggle between detailed and summary view for adjustments
 */
window.toggleAdjustmentDetails = function (cycleId) {
	const adjustmentSection = $(`#cycle-details-${cycleId} .cycle-adjustments`);
	const toggleBtn = adjustmentSection.find('.adjustment-toggle-btn');

	if (adjustmentSection.hasClass('detailed-view')) {
		// Switch to summary view
		adjustmentSection.removeClass('detailed-view');
		toggleBtn.text('Show Details');
		adjustmentSection.find('.adjustments-table tbody tr:gt(2)').slideUp(200);
	} else {
		// Switch to detailed view
		adjustmentSection.addClass('detailed-view');
		toggleBtn.text('Show Summary');
		adjustmentSection.find('.adjustments-table tbody tr:gt(2)').slideDown(200);
	}
};

/**
 * Enhanced document navigation with context
 */
window.openDocumentWithContext = function (doctype, name, context) {
	if (!name || name === '-') return;

	// Store context for the document view
	if (context) {
		sessionStorage.setItem(`doc_context_${name}`, JSON.stringify(context));
	}

	const route = doctype.toLowerCase().replace(' ', '-');
	window.open(`/app/${route}/${name}`, '_blank');
};

/**
 * Preserve user preferences for view mode
 */
function saveViewModePreference(itemName, viewMode) {
	const preferences = JSON.parse(localStorage.getItem('boq_view_preferences') || '{}');
	preferences[itemName] = viewMode;
	localStorage.setItem('boq_view_preferences', JSON.stringify(preferences));
}

function getViewModePreference(itemName) {
	const preferences = JSON.parse(localStorage.getItem('boq_view_preferences') || '{}');
	return preferences[itemName] || 'grouped'; // Default to grouped view
}

/**
 * Enhanced view mode toggle with preference saving
 */
window.toggleViewModeEnhanced = function (itemName, currentMode) {
	const row = $(`tr.item-row[data-item="${itemName}"]`);
	const inlineRow = row.next('.inline-breakdown-row');

	if (inlineRow.length === 0) return;

	const newMode = currentMode === 'grouped' ? 0 : 1;
	const newModeLabel = newMode ? 'grouped' : 'raw';

	// Save preference
	saveViewModePreference(itemName, newModeLabel);

	// Show loading state with better UX
	const loadingHtml = `
		<div class="loading-state">
			<i class="fa fa-spinner fa-spin"></i>
			<span>Switching to ${newModeLabel} view...</span>
		</div>
	`;
	inlineRow.find('.transaction-history-container').html(loadingHtml);

	frappe.call({
		method: 'construction_management.api.boq_invoice.get_boq_invoice_history',
		args: {
			boq_item: itemName,
			grouped_view: newMode
		},
		callback: function (r) {
			if (r.message) {
				const newHtml = renderTransactionHistorySection(itemName, r.message);
				const newInlineRow = $(newHtml);
				inlineRow.replaceWith(newInlineRow);

				// Show success indicator
				frappe.show_alert({
					message: `Switched to ${newModeLabel} view`,
					indicator: 'green'
				});
			}
		},
		error: function () {
			frappe.show_alert({
				message: __('Failed to switch view mode'),
				indicator: 'red'
			});

			// Restore original content on error
			setTimeout(() => {
				toggleTransactionHistory(itemName);
			}, 1000);
		}
	});
};