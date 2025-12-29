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
						${bill.description ? `<span class="bill-desc">${bill.description}</span>` : ''}
					</div>
				</div>
				<div class="bill-header-stats">
					<div class="bill-stat"><span class="stat-label">ITEMS</span><span class="stat-value">${(bill.items || []).length}</span></div>
					<div class="bill-stat"><span class="stat-label">REVENUE</span><span class="stat-value">${format_currency(revenue.total || 0)}</span></div>
					<div class="bill-stat"><span class="stat-label">COST</span><span class="stat-value">${format_currency(actual.total || 0)}</span></div>
					<div class="bill-stat"><span class="stat-label">GP</span><span class="stat-value ${profitability.gp >= 0 ? 'positive' : 'negative'}">${format_currency(profitability.gp || 0)}</span></div>
					<div class="bill-stat"><span class="stat-label">GP%</span><span class="stat-value">${(profitability.gp_percent || 0).toFixed(1)}%</span></div>
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
						<th rowspan="2" class="col-rate sticky-col sticky-col-last">Rate</th>
						<th colspan="3" class="col-group col-group-qty">Qty Breakdown</th>
						<th colspan="3" class="col-group col-group-value">Value Breakdown</th>
						<th colspan="2" class="col-group col-group-billing">Current Billing</th>
						<th colspan="6" class="col-group col-group-revenue">Revenue</th>
						<th colspan="6" class="col-group col-group-estimated">Estimated Cost</th>
						<th colspan="6" class="col-group col-group-actual">Actual Cost</th>
						<th colspan="2" class="col-group col-group-profit">Profitability</th>
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
						<!-- Current Billing -->
						<th class="col-num">Qty</th>
						<th class="col-num">Value</th>
						<!-- Revenue -->
						<th class="col-num">PI</th>
						<th class="col-num">PC</th>
						<th class="col-num">Tax Inv</th>
						<th class="col-num">Variance</th>
						<th class="col-num">BOQ Balance</th>
						<th class="col-num">Total</th>
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
						<th class="col-num">Total</th>
						<!-- Profitability -->
						<th class="col-num">GP</th>
						<th class="col-num">GP%</th>
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
	const qty = item.qty || {};
	const amount = item.amount || {};
	const estimated = item.estimated_costs || {};
	const actual = item.actual_costs || {};
	const profitability = item.profitability || {};
	const isFullyBilled = item.billing_status === 'Fully Billed';

	const varianceClass = revenue.variance > 0 ? 'text-danger' : '';

	// Determine row status for highlighting (Issue #3)
	const hasProforma = flt(revenue.proforma || 0) > 0;
	const hasPC = flt(revenue.pc || 0) > 0;
	const hasTaxInvoice = flt(revenue.tax_invoice || 0) > 0;

	let rowStatusClass = '';
	let rowStatusIcon = '';
	let rowStatusTooltip = '';

	if (hasProforma && !hasPC && !isFullyBilled) {
		// PI exists, PC pending
		rowStatusClass = 'row-status-pc-pending';
		rowStatusIcon = '⏳';
		rowStatusTooltip = 'Proforma created - Payment Certificate pending';
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
			<td class="col-checkbox sticky-col"><input type="checkbox" class="item-checkbox" data-item="${item.name}" ${isFullyBilled ? 'disabled' : ''} aria-label="Select item ${item.description || item.name}" tabindex="0"></td>
			<td class="col-desc sticky-col">
				<div class="item-desc-wrapper">
					${rowStatusIcon ? `<span class="row-status-icon" title="${rowStatusTooltip}">${rowStatusIcon}</span>` : ''}
					${item.item_code ? `<span class="item-code">${item.item_code}</span>` : ''}
					<span class="item-desc">${item.description || 'No description'}</span>
				</div>
			</td>
			<td class="col-unit sticky-col">${item.unit || '-'}</td>
			<td class="col-rate sticky-col sticky-col-last">${format_currency(amount.rate || 0)}</td>
			
			<!-- Qty Breakdown (moved before Value) -->
			<td class="col-num">${format_number(qty.prev || 0)}</td>
			<td class="col-num curr-qty-cell" data-item="${item.name}">${format_number(qty.current || 0)}</td>
			<td class="col-num font-bold">${format_number(qty.to_date || 0)}</td>
			
			<!-- Value Breakdown -->
			<td class="col-num">${format_currency(amount.prev || 0)}</td>
			<td class="col-num curr-value-cell" data-item="${item.name}">${format_currency(amount.current || 0)}</td>
			<td class="col-num font-bold accum-value-cell" data-item="${item.name}">${format_currency(amount.to_date || 0)}</td>
			
			<!-- Current Billing Inputs -->
			<td class="col-num">
				<input type="number" class="current-qty-input" value="${qty.current || 0}" 
					data-item="${item.name}" data-max="${qty.balance + (qty.current || 0)}" data-rate="${amount.rate || 0}"
					data-prev-amount="${amount.prev || 0}" data-total-amount="${amount.total || 0}"
					step="0.001" min="0" ${isFullyBilled ? 'disabled' : ''} aria-label="Current billing quantity" tabindex="0">
			</td>
			<td class="col-num">
				<input type="number" class="current-value-input" value="${amount.current || 0}" 
					data-item="${item.name}" data-max="${amount.balance + (amount.current || 0)}" data-rate="${amount.rate || 0}"
					data-prev-amount="${amount.prev || 0}" data-total-amount="${amount.total || 0}"
					step="0.01" min="0" ${isFullyBilled ? 'disabled' : ''} aria-label="Current billing value" tabindex="0">
			</td>
			
			<!-- Revenue columns -->
			<td class="col-num">${format_currency(revenue.proforma || 0)}</td>
			<td class="col-num">${format_currency(revenue.pc || 0)}</td>
			<td class="col-num">${format_currency(revenue.tax_invoice || 0)}</td>
			<td class="col-num ${varianceClass}">${format_currency(revenue.variance || 0)}</td>
			<td class="col-num balance-value">${format_currency(revenue.balance || 0)}</td>
			<td class="col-num font-bold">${format_currency(revenue.total || 0)}</td>
			
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
			<td class="col-num font-bold">${format_currency(actual.total || 0)}</td>
			
			<!-- Profitability -->
			<td class="col-num ${profitability.gp >= 0 ? 'text-success' : 'text-danger'} font-bold">${format_currency(profitability.gp || 0)}</td>
			<td class="col-num ${profitability.gp_percent >= 0 ? 'text-success' : 'text-danger'}">${(profitability.gp_percent || 0).toFixed(1)}%</td>
			
			<!-- Actions - Requirements: 3.2, 3.3 -->
			<td class="col-actions" role="cell">
				<div class="action-icons" role="group" aria-label="Item actions">
					${(hasProforma && !hasPC && !isFullyBilled) ? `
					<button class="action-btn action-btn-pc" onclick="createPCFromRow('${item.name}'); event.stopPropagation();" title="Create Payment Certificate" aria-label="Create PC for this item" tabindex="0">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
							<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
							<polyline points="22 4 12 14.01 9 11.01"></polyline>
						</svg>
					</button>
					` : ''}
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
 * Attach event handlers for the table
 */
function attach_table_events(container, frm) {
	// Handle Qty input change
	container.find('.current-qty-input').on('change input', function () {
		const input = $(this);
		const itemName = input.data('item');
		const maxQty = parseFloat(input.data('max')) || 0;
		const rate = parseFloat(input.data('rate')) || 0;
		const prevAmount = parseFloat(input.data('prev-amount')) || 0;
		const totalAmount = parseFloat(input.data('total-amount')) || 0;
		let newQty = parseFloat(input.val()) || 0;

		if (newQty < 0) { newQty = 0; input.val(0); }
		if (newQty > maxQty) {
			frappe.show_alert({ message: __('Quantity cannot exceed balance ({0})', [maxQty]), indicator: 'orange' });
			newQty = maxQty;
			input.val(maxQty);
		}

		const row = input.closest('tr');
		const valueInput = row.find('.current-value-input');
		const newValue = newQty * rate;
		valueInput.val(newValue.toFixed(2));

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
		const prevAmount = parseFloat(input.data('prev-amount')) || 0;
		let newValue = parseFloat(input.val()) || 0;

		if (newValue < 0) { newValue = 0; input.val(0); }
		if (newValue > maxValue) {
			frappe.show_alert({ message: __('Value cannot exceed balance'), indicator: 'orange' });
			newValue = maxValue;
			input.val(maxValue.toFixed(2));
		}

		const row = input.closest('tr');
		const qtyInput = row.find('.current-qty-input');
		const newQty = rate > 0 ? newValue / rate : 0;
		qtyInput.val(newQty.toFixed(3));

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
		container.find('.item-checkbox:not(:disabled)').prop('checked', isChecked);
		updateSelectionToolbar(container);
	});

	// Handle individual item checkbox
	container.find('.item-checkbox').on('change', function () {
		updateSelectionToolbar(container);
	});
}


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
						<button class="btn-toolbar btn-primary-toolbar" onclick="generateBulkProforma()">
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
								<polyline points="14 2 14 8 20 8"></polyline>
							</svg>
							Generate Proforma
						</button>
						<button class="btn-toolbar btn-secondary-toolbar" onclick="createPaymentCertificate()">
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
								<polyline points="22 4 12 14.01 9 11.01"></polyline>
							</svg>
							Create PC
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

window.generateBulkProforma = function () {
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
		const qty = parseFloat(qtyInput.val()) || 0;
		if (qty > 0) {
			items.push({ boq_item: itemName, qty: qty });
		}
	});

	if (items.length === 0) {
		frappe.show_alert({ message: __('Please enter billing quantities for selected items'), indicator: 'orange' });
		return;
	}

	const project = cur_frm.doc.name;
	frappe.call({
		method: 'construction_management.construction_management.doctype.proforma_invoice.proforma_invoice.create_proforma_from_selected_items',
		args: { project: project, items: JSON.stringify(items), apply_retention: 1, auto_submit: 1 },
		freeze: true,
		freeze_message: __('Creating and Submitting Proforma Invoice...'),
		callback: function (r) {
			if (r.message) {
				if (r.message.status === 'success' && r.message.name) {
					const statusMsg = r.message.doc_status === 'Submitted'
						? __('Proforma Invoice {0} created and submitted', [r.message.name])
						: __('Proforma Invoice {0} created', [r.message.name]);
					frappe.show_alert({ message: statusMsg, indicator: 'green' });
					// Clear selection and refresh the table
					clearSelection();
					if (cur_frm) {
						cur_frm.reload_doc();
					}
					frappe.set_route('Form', 'Proforma Invoice', r.message.name);
				} else if (r.message.status === 'error') {
					frappe.show_alert({ message: r.message.error_message || __('Failed to create proforma invoice'), indicator: 'red' });
				} else if (r.message.name) {
					// Backward compatibility
					frappe.show_alert({ message: __('Proforma Invoice {0} created', [r.message.name]), indicator: 'green' });
					frappe.set_route('Form', 'Proforma Invoice', r.message.name);
				}
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

	frappe.prompt([
		{
			fieldname: 'proforma_invoice', fieldtype: 'Link', label: 'Proforma Invoice', options: 'Proforma Invoice', reqd: 1,
			get_query: function () { return { filters: { docstatus: 1, status: ['in', ['Submitted', 'Partially Certified']] } }; }
		},
		{ fieldname: 'posting_date', fieldtype: 'Date', label: 'Posting Date', default: frappe.datetime.get_today(), reqd: 1 }
	], function (values) {
		frappe.call({
			method: 'construction_management.api.boq_invoice.create_payment_certificate',
			args: { proforma_invoice: values.proforma_invoice, posting_date: values.posting_date },
			freeze: true,
			freeze_message: __('Creating Payment Certificate...'),
			callback: function (r) {
				if (r.message) {
					frappe.show_alert({ message: __('Payment Certificate {0} created', [r.message]), indicator: 'green' });
					frappe.set_route('Form', 'Payment Certificate', r.message);
				}
			}
		});
	}, __('Create Payment Certificate'), __('Create'));
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
 * Toggle transaction history for an item - Shows inline expandable section
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7
 */
window.toggleTransactionHistory = function (itemName) {
	const row = $(`tr.item-row[data-item="${itemName}"]`);
	const expandBtn = row.find('.expand-btn');
	const existingInline = row.next('.inline-breakdown-row');

	// If inline section exists, toggle it
	if (existingInline.length > 0) {
		if (existingInline.is(':visible')) {
			existingInline.slideUp(200, function () {
				expandBtn.removeClass('expanded');
			});
		} else {
			existingInline.slideDown(200, function () {
				expandBtn.addClass('expanded');
			});
		}
		return;
	}

	// Fetch and create inline section
	expandBtn.addClass('loading');

	frappe.call({
		method: 'construction_management.api.boq_tree.get_boq_item_with_transactions',
		args: { boq_item: itemName },
		callback: function (r) {
			expandBtn.removeClass('loading');
			if (r.message) {
				const inlineHtml = renderInlineBreakdownSection(itemName, r.message);
				const inlineRow = $(inlineHtml);
				inlineRow.hide();
				row.after(inlineRow);
				inlineRow.slideDown(200, function () {
					expandBtn.addClass('expanded');
				});
			} else {
				frappe.show_alert({ message: __('No data found'), indicator: 'blue' });
			}
		},
		error: function () {
			expandBtn.removeClass('loading');
			frappe.show_alert({ message: __('Failed to load data'), indicator: 'red' });
		}
	});
};

/**
 * Render inline breakdown section for a BOQ Item
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
 */
function renderInlineBreakdownSection(itemName, data) {
	const item = data.item || {};
	const transactions = data.transactions || [];
	const qty = item.qty || {};
	const amount = item.amount || {};
	const estimated = item.estimated_costs || {};
	const actual = item.actual_costs || {};

	// Determine proforma/PC status
	const proformaStatus = getProformaStatus(transactions);
	const statusIndicator = getStatusIndicatorHtml(proformaStatus);

	// Get column count from parent table
	const colSpan = $(`tr.item-row[data-item="${itemName}"]`).find('td').length;

	return `
		<tr class="inline-breakdown-row" data-item="${itemName}">
			<td colspan="${colSpan}">
				<div class="inline-breakdown-container">
					<!-- Header with Status -->
					<div class="inline-breakdown-header">
						<div class="inline-header-left">
							<span class="inline-title">Item Breakdown</span>
							<span class="inline-item-code">${item.item_code || itemName}</span>
						</div>
						<div class="inline-header-right">
							${statusIndicator}
						</div>
					</div>
					
					<!-- Main Content Grid -->
					<div class="inline-breakdown-grid">
						<!-- Qty & Value Breakdown -->
						<div class="inline-section">
							<div class="inline-section-title">Qty & Value Breakdown</div>
							<table class="inline-breakdown-table">
								<thead>
									<tr>
										<th></th>
										<th class="text-right">Previous</th>
										<th class="text-right">Current</th>
										<th class="text-right">Accumulated</th>
										<th class="text-right">Balance</th>
									</tr>
								</thead>
								<tbody>
									<tr>
										<td class="breakdown-label">Quantity</td>
										<td class="text-right">${format_number(qty.prev || 0)}</td>
										<td class="text-right highlight-current">${format_number(qty.current || 0)}</td>
										<td class="text-right font-bold">${format_number(qty.to_date || 0)}</td>
										<td class="text-right balance-value">${format_number(qty.balance || 0)}</td>
									</tr>
									<tr>
										<td class="breakdown-label">Amount</td>
										<td class="text-right">${format_currency(amount.prev || 0)}</td>
										<td class="text-right highlight-current">${format_currency(amount.current || 0)}</td>
										<td class="text-right font-bold">${format_currency(amount.to_date || 0)}</td>
										<td class="text-right balance-value">${format_currency(amount.balance || 0)}</td>
									</tr>
								</tbody>
							</table>
						</div>
						
						<!-- Cost & Revenue Estimation -->
						<div class="inline-section">
							<div class="inline-section-title">Cost & Revenue</div>
							<div class="cost-revenue-grid">
								<div class="cost-card">
									<span class="cost-label">Estimated Cost</span>
									<span class="cost-value">${format_currency(estimated.total || 0)}</span>
								</div>
								<div class="cost-card">
									<span class="cost-label">Actual Cost</span>
									<span class="cost-value">${format_currency(actual.total || 0)}</span>
								</div>
								<div class="cost-card">
									<span class="cost-label">Revenue (To Date)</span>
									<span class="cost-value">${format_currency(amount.to_date || 0)}</span>
								</div>
								<div class="cost-card ${(amount.to_date || 0) - (actual.total || 0) >= 0 ? 'positive' : 'negative'}">
									<span class="cost-label">Gross Profit</span>
									<span class="cost-value">${format_currency((amount.to_date || 0) - (actual.total || 0))}</span>
								</div>
							</div>
						</div>
					</div>
					
					<!-- Transactions Section -->
					<div class="inline-section inline-transactions">
						<div class="inline-section-title">
							Transaction History
							<span class="txn-count-badge">${transactions.length}</span>
						</div>
						${transactions.length > 0 ? renderInlineTransactionsTable(transactions) : '<div class="no-transactions">No transactions found</div>'}
					</div>
				</div>
			</td>
		</tr>
	`;
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
		if (txn.doctype === 'Proforma Invoice' || txn.doctype === 'Sales Invoice') {
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
 * Show tasks popup for a BOQ item
 * Requirements: 5.2
 */
window.showTasksPopup = function (itemName) {
	frappe.call({
		method: 'construction_management.api.boq_tasks.get_boq_item_tasks',
		args: { boq_item: itemName },
		callback: function (r) {
			const tasks = r.message || [];
			const item = frappe.db.get_value ? null : null; // Will fetch from API

			let tasksHtml = '';
			if (tasks.length === 0) {
				tasksHtml = '<div class="no-tasks-message">No tasks linked to this BOQ item.</div>';
			} else {
				tasksHtml = `
					<table class="tasks-popup-table">
						<thead>
							<tr>
								<th>Task</th>
								<th>Status</th>
								<th>Start Date</th>
								<th>End Date</th>
								<th>Progress</th>
							</tr>
						</thead>
						<tbody>
				`;

				tasks.forEach(task => {
					const statusClass = getTaskStatusClass(task.status);
					tasksHtml += `
						<tr class="task-row" onclick="frappe.set_route('Form', 'Task', '${task.name}')">
							<td class="task-name">${task.subject || task.name}</td>
							<td><span class="task-status ${statusClass}">${task.status || '-'}</span></td>
							<td>${task.exp_start_date || '-'}</td>
							<td>${task.exp_end_date || '-'}</td>
							<td>
								<div class="task-progress-bar">
									<div class="task-progress-fill" style="width: ${task.progress || 0}%"></div>
								</div>
								<span class="task-progress-text">${task.progress || 0}%</span>
							</td>
						</tr>
					`;
				});

				tasksHtml += '</tbody></table>';
			}

			const dialogHtml = `
				<div class="tasks-popup-container">
					<div class="tasks-popup-header">
						<span class="tasks-count">${tasks.length} task(s)</span>
					</div>
					${tasksHtml}
				</div>
				${getTasksPopupStyles()}
			`;

			const dialog = new frappe.ui.Dialog({
				title: __('Tasks - {0}', [itemName]),
				size: 'large',
				fields: [
					{
						fieldtype: 'HTML',
						fieldname: 'tasks_content',
						options: dialogHtml
					}
				]
			});

			dialog.show();
		}
	});
};

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

function getTasksPopupStyles() {
	return `<style>
		.tasks-popup-container { padding: 0; }
		.tasks-popup-header { display: flex; justify-content: flex-end; margin-bottom: 12px; }
		.tasks-count { font-size: 11px; color: #6c7680; background: #f0f0f0; padding: 2px 8px; border-radius: 10px; }
		
		.tasks-popup-table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e8e8e8; border-radius: 6px; overflow: hidden; }
		.tasks-popup-table th { background: #f7f7f7; padding: 10px 12px; font-size: 10px; font-weight: 500; color: #6c7680; text-transform: uppercase; text-align: left; }
		.tasks-popup-table td { padding: 10px 12px; font-size: 12px; border-top: 1px solid #e8e8e8; }
		
		.task-row { cursor: pointer; transition: background 0.15s; }
		.task-row:hover { background: #f5f7fa; }
		
		.task-name { font-weight: 500; color: #2490ef; }
		
		.task-status { padding: 3px 8px; border-radius: 10px; font-size: 10px; font-weight: 500; }
		.task-status-open { background: #e3f2fd; color: #1565c0; }
		.task-status-working { background: #fff3e0; color: #e65100; }
		.task-status-pending { background: #fce4ec; color: #c2185b; }
		.task-status-overdue { background: #ffebee; color: #c62828; }
		.task-status-completed { background: #e8f5e9; color: #2e7d32; }
		.task-status-cancelled { background: #f7f7f7; color: #6c7680; }
		.task-status-default { background: #f7f7f7; color: #6c7680; }
		
		.task-progress-bar { width: 60px; height: 6px; background: #e8e8e8; border-radius: 3px; display: inline-block; vertical-align: middle; margin-right: 6px; }
		.task-progress-fill { height: 100%; background: #36b37e; border-radius: 3px; }
		.task-progress-text { font-size: 10px; color: #6c7680; }
		
		.no-tasks-message { text-align: center; padding: 30px; color: #8d99a6; font-size: 13px; background: #fafbfc; border-radius: 6px; }
	</style>`;
}

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
	return { 'Proforma Invoice': 'PI', 'Payment Certificate': 'PC', 'Sales Invoice': 'Tax Inv' }[doctype] || doctype;
}

function get_transaction_type_class(doctype) {
	return { 'Proforma Invoice': 'type-pi', 'Payment Certificate': 'type-pc', 'Sales Invoice': 'type-tax' }[doctype] || '';
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
		
		.bill-header-stats { display: flex; gap: 20px; }
		.bill-stat { display: flex; flex-direction: column; align-items: flex-end; }
		.stat-label { font-size: 9px; color: var(--boq-text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
		.stat-value { font-size: 13px; font-weight: 600; color: var(--boq-text-primary); }
		.stat-value.positive { color: var(--boq-success); }
		.stat-value.negative { color: var(--boq-danger); }
		
		.bill-items-container { border-top: none; }
		.bill-toolbar { padding: 10px 16px; background: var(--boq-bg-tertiary); border-bottom: 1px solid var(--boq-border-light); }
		
		/* Frappe-style button - Requirements: 1.2 */
		.btn-frappe { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; font-size: 12px; font-weight: 500; color: var(--boq-text-primary); background: var(--boq-bg-primary); border: 1px solid var(--boq-border); border-radius: var(--boq-radius-sm); cursor: pointer; transition: all var(--boq-transition); }
		.btn-frappe:hover { background: var(--boq-bg-secondary); border-color: #b8c2cc; }
		
		/* Table - Requirements: 4.1, 4.4 */
		.comprehensive-table-wrapper { 
			overflow-x: auto; 
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
		
		/* Column Widths - Requirements: 4.2, 4.3 */
		.col-expand { width: 36px; min-width: 36px; text-align: center; }
		.col-checkbox { width: 32px; min-width: 32px; text-align: center; }
		.col-desc { min-width: 180px; max-width: 280px; text-align: left; word-wrap: break-word; }
		.col-unit { width: 50px; min-width: 50px; text-align: center; }
		.col-rate { width: 80px; min-width: 80px; text-align: right; }
		.col-num { width: 80px; min-width: 70px; text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
		.col-actions { width: 180px; min-width: 180px; text-align: left; padding: 4px 2px !important; }
		
		/* Sticky Columns - Requirements: 2.1, 2.2, 2.3, 2.4 */
		.sticky-col { position: sticky; background: #fff; z-index: 2; }
		.comprehensive-items-table th.sticky-col { background: #f7f7f7; z-index: 3; }
		.comprehensive-items-table tr:hover .sticky-col { background: #fafbfc; }
		
		/* Sticky column left offsets */
		.col-expand.sticky-col { left: 0; }
		.col-checkbox.sticky-col { left: 36px; }
		.col-desc.sticky-col { left: 68px; }
		.col-unit.sticky-col { left: 248px; }
		.col-rate.sticky-col { left: 298px; }
		
		/* Visual separation for last sticky column - Requirements: 2.1, 2.2, 2.3, 2.4 */
		.sticky-col-last { 
			border-right: 2px solid #ccc !important; /* Requirements: 2.1 - Changed from blue to #ccc */
			box-shadow: 2px 0 4px rgba(0,0,0,0.1); 
			margin-right: 8px; /* Requirements: 2.4 */
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
			justify-content: flex-start !important;
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
			width: 26px !important;
			height: 26px !important;
			min-width: 26px !important;
			min-height: 26px !important;
			max-width: 26px !important;
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
			width: 14px !important;
			height: 14px !important;
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
			.col-desc { min-width: 200px; max-width: 300px; }
			.action-btn { width: 40px; height: 40px; }
		}
		
		/* Medium screens (992px - 1199px) */
		@media (max-width: 1199px) and (min-width: 992px) {
			.comprehensive-items-table { min-width: 1800px; }
			.col-desc { min-width: 160px; max-width: 240px; }
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
				<strong>Proforma Invoice:</strong> ${proforma.name}<br>
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
		title: __('Select Proforma Invoice'),
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
