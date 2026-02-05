// Copyright (c) 2024, Construction Management
// License: MIT
// Bill Financial Summary Widget - Phase 3: UI/UX Improvements
// Requirements: 7.5 - Bill-level financial visibility

/**
 * Show bill financial summary dialog
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
 */
window.showBillFinancialSummary = function (billNo) {
	frappe.call({
		method: 'construction_management.api.bill_financial_aggregator.get_bill_financial_breakdown',
		args: { bill_no: billNo },
		freeze: true,
		freeze_message: __('Loading financial summary...'),
		callback: function (r) {
			if (r.message) {
				renderBillFinancialSummaryDialog(r.message);
			}
		},
		error: function (err) {
			frappe.show_alert({
				message: __('Failed to load financial summary'),
				indicator: 'red'
			});
		}
	});
};

/**
 * Render bill financial summary dialog
 */
function renderBillFinancialSummaryDialog(data) {
	const dialog = new frappe.ui.Dialog({
		title: __('Financial Summary - {0}', [data.bill_no]),
		size: 'extra-large',
		fields: [
			{
				fieldtype: 'HTML',
				fieldname: 'financial_summary_content'
			}
		]
	});

	const content = renderFinancialSummaryContent(data);
	dialog.fields_dict.financial_summary_content.$wrapper.html(content);
	dialog.show();
}

/**
 * Render financial summary content
 */
function renderFinancialSummaryContent(data) {
	return `
		<div class="bill-financial-summary-container">
			<!-- Header Section -->
			<div class="financial-summary-header">
				<div class="header-info">
					<h3>${data.bill_no}</h3>
					<p class="bill-description">${data.description || 'No description'}</p>
					<p class="project-name"><strong>Project:</strong> ${data.project}</p>
				</div>
				<div class="header-stats">
					<div class="stat-card stat-card-primary">
						<span class="stat-label">Total BOQ Value</span>
						<span class="stat-value">${format_currency(data.total_boq_value || 0)}</span>
					</div>
					<div class="stat-card stat-card-success">
						<span class="stat-label">Billed To Date</span>
						<span class="stat-value">${format_currency(data.total_billed_to_date || 0)}</span>
						<span class="stat-percent">${((data.total_billed_to_date / data.total_boq_value * 100) || 0).toFixed(1)}%</span>
					</div>
					<div class="stat-card stat-card-info">
						<span class="stat-label">Balance to Bill</span>
						<span class="stat-value">${format_currency(data.balance_to_bill || 0)}</span>
					</div>
				</div>
			</div>

			<!-- Financial Breakdown Section -->
			<div class="financial-breakdown-section">
				<div class="section-title">Financial Breakdown</div>
				<div class="breakdown-grid">
					<!-- Gross Billed -->
					<div class="breakdown-card">
						<div class="breakdown-header">
							<span class="breakdown-label">Gross Billed</span>
							<span class="breakdown-icon">💰</span>
						</div>
						<div class="breakdown-value">${format_currency(data.gross_billed || 0)}</div>
					</div>

					<!-- Retention -->
					<div class="breakdown-card breakdown-card-warning">
						<div class="breakdown-header">
							<span class="breakdown-label">Retention</span>
							<span class="breakdown-icon">🔒</span>
						</div>
						<div class="breakdown-value">${format_currency(data.total_retention || 0)}</div>
						<div class="breakdown-details">
							<div class="detail-row">
								<span>Released:</span>
								<span>${format_currency(data.retention_released || 0)}</span>
							</div>
							<div class="detail-row">
								<span>Balance:</span>
								<span class="text-bold">${format_currency(data.retention_balance || 0)}</span>
							</div>
						</div>
					</div>

					<!-- Advances -->
					<div class="breakdown-card breakdown-card-info">
						<div class="breakdown-header">
							<span class="breakdown-label">Advances</span>
							<span class="breakdown-icon">💳</span>
						</div>
						<div class="breakdown-value">${format_currency(data.total_advances_deducted || 0)}</div>
						<div class="breakdown-details">
							<div class="detail-row">
								<span>Available:</span>
								<span>${format_currency(data.total_advances_available || 0)}</span>
							</div>
							<div class="detail-row">
								<span>Remaining:</span>
								<span class="text-bold">${format_currency(data.advance_balance || 0)}</span>
							</div>
						</div>
					</div>

					<!-- Net Amount -->
					<div class="breakdown-card breakdown-card-success">
						<div class="breakdown-header">
							<span class="breakdown-label">Net Amount</span>
							<span class="breakdown-icon">✅</span>
						</div>
						<div class="breakdown-value text-success">${format_currency(data.net_amount || 0)}</div>
						<div class="breakdown-formula">
							= Gross - Retention - Advances
						</div>
					</div>
				</div>
			</div>

			<!-- Invoices Section -->
			${renderInvoicesSection(data.invoices || [])}

			<!-- Retention Transactions Section -->
			${data.retention_transactions && data.retention_transactions.length > 0 ?
			renderRetentionTransactionsSection(data.retention_transactions) : ''}

			<!-- Advance Transactions Section -->
			${data.advance_transactions && data.advance_transactions.length > 0 ?
			renderAdvanceTransactionsSection(data.advance_transactions) : ''}
		</div>
		${getBillFinancialSummaryStyles()}
	`;
}

/**
 * Render invoices section
 */
function renderInvoicesSection(invoices) {
	if (!invoices || invoices.length === 0) {
		return `
			<div class="financial-section">
				<div class="section-title">Invoices</div>
				<div class="no-data-message">No invoices found for this bill</div>
			</div>
		`;
	}

	return `
		<div class="financial-section">
			<div class="section-title">
				Invoices
				<span class="count-badge">${invoices.length}</span>
			</div>
			<table class="financial-table">
				<thead>
					<tr>
						<th>Invoice No</th>
						<th>Date</th>
						<th>Customer</th>
						<th>Type</th>
						<th class="text-right">Grand Total</th>
						<th class="text-right">Outstanding</th>
						<th>Status</th>
					</tr>
				</thead>
				<tbody>
					${invoices.map(inv => `
						<tr class="clickable-row" onclick="frappe.set_route('Form', 'Sales Invoice', '${inv.invoice_no}')">
							<td class="invoice-link">${inv.invoice_no}</td>
							<td>${inv.posting_date || '-'}</td>
							<td>${inv.customer || '-'}</td>
							<td><span class="type-badge ${inv.is_proforma ? 'type-proforma' : 'type-tax'}">${inv.is_proforma ? 'Sales Order' : 'Tax Invoice'}</span></td>
							<td class="text-right">${format_currency(inv.grand_total || 0)}</td>
							<td class="text-right">${format_currency(inv.outstanding_amount || 0)}</td>
							<td><span class="status-badge status-${(inv.status || '').toLowerCase().replace(' ', '-')}">${inv.status || 'Draft'}</span></td>
						</tr>
					`).join('')}
				</tbody>
			</table>
		</div>
	`;
}

/**
 * Render retention transactions section
 */
function renderRetentionTransactionsSection(transactions) {
	return `
		<div class="financial-section">
			<div class="section-title">
				Retention Transactions
				<span class="count-badge">${transactions.length}</span>
			</div>
			<table class="financial-table">
				<thead>
					<tr>
						<th>Invoice No</th>
						<th>Date</th>
						<th>Type</th>
						<th class="text-right">Amount</th>
					</tr>
				</thead>
				<tbody>
					${transactions.map(txn => `
						<tr class="clickable-row" onclick="frappe.set_route('Form', 'Sales Invoice', '${txn.invoice_no}')">
							<td class="invoice-link">${txn.invoice_no}</td>
							<td>${txn.posting_date || '-'}</td>
							<td><span class="txn-type-badge ${txn.transaction_type === 'Deduction' ? 'txn-deduction' : 'txn-release'}">${txn.transaction_type}</span></td>
							<td class="text-right ${txn.transaction_type === 'Deduction' ? 'text-danger' : 'text-success'}">${format_currency(txn.amount || 0)}</td>
						</tr>
					`).join('')}
				</tbody>
			</table>
		</div>
	`;
}

/**
 * Render advance transactions section
 */
function renderAdvanceTransactionsSection(transactions) {
	return `
		<div class="financial-section">
			<div class="section-title">
				Advance Transactions
				<span class="count-badge">${transactions.length}</span>
			</div>
			<table class="financial-table">
				<thead>
					<tr>
						<th>Invoice No</th>
						<th>Date</th>
						<th>Type</th>
						<th class="text-right">Amount</th>
					</tr>
				</thead>
				<tbody>
					${transactions.map(txn => `
						<tr class="clickable-row" onclick="frappe.set_route('Form', 'Sales Invoice', '${txn.invoice_no}')">
							<td class="invoice-link">${txn.invoice_no}</td>
							<td>${txn.posting_date || '-'}</td>
							<td><span class="txn-type-badge txn-deduction">${txn.transaction_type}</span></td>
							<td class="text-right text-danger">${format_currency(txn.amount || 0)}</td>
						</tr>
					`).join('')}
				</tbody>
			</table>
		</div>
	`;
}

/**
 * Get bill financial summary styles
 */
function getBillFinancialSummaryStyles() {
	return `<style>
		.bill-financial-summary-container {
			padding: 0;
		}

		/* Header Section */
		.financial-summary-header {
			background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
			color: white;
			padding: 24px;
			border-radius: 8px;
			margin-bottom: 24px;
			display: flex;
			justify-content: space-between;
			align-items: flex-start;
		}

		.header-info h3 {
			margin: 0 0 8px 0;
			font-size: 20px;
			font-weight: 600;
		}

		.bill-description {
			margin: 4px 0;
			font-size: 13px;
			opacity: 0.9;
		}

		.project-name {
			margin: 4px 0 0 0;
			font-size: 12px;
			opacity: 0.85;
		}

		.header-stats {
			display: flex;
			gap: 16px;
		}

		.stat-card {
			background: rgba(255, 255, 255, 0.15);
			backdrop-filter: blur(10px);
			padding: 12px 16px;
			border-radius: 8px;
			min-width: 140px;
			text-align: center;
		}

		.stat-label {
			display: block;
			font-size: 10px;
			text-transform: uppercase;
			opacity: 0.8;
			margin-bottom: 4px;
		}

		.stat-value {
			display: block;
			font-size: 18px;
			font-weight: 700;
			margin-bottom: 2px;
		}

		.stat-percent {
			display: block;
			font-size: 11px;
			opacity: 0.9;
		}

		/* Financial Breakdown Section */
		.financial-breakdown-section {
			margin-bottom: 24px;
		}

		.section-title {
			font-size: 15px;
			font-weight: 600;
			color: #1f272e;
			margin-bottom: 16px;
			padding-bottom: 8px;
			border-bottom: 2px solid #e8e8e8;
			display: flex;
			align-items: center;
			gap: 8px;
		}

		.count-badge {
			background: #e3f2fd;
			color: #1565c0;
			padding: 2px 8px;
			border-radius: 10px;
			font-size: 11px;
			font-weight: 500;
		}

		.breakdown-grid {
			display: grid;
			grid-template-columns: repeat(4, 1fr);
			gap: 16px;
		}

		.breakdown-card {
			background: #fff;
			border: 1px solid #e8e8e8;
			border-radius: 8px;
			padding: 16px;
			transition: all 0.2s;
		}

		.breakdown-card:hover {
			box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
			transform: translateY(-2px);
		}

		.breakdown-card-warning {
			border-left: 4px solid #ff8f00;
		}

		.breakdown-card-info {
			border-left: 4px solid #1565c0;
		}

		.breakdown-card-success {
			border-left: 4px solid #2e7d32;
		}

		.breakdown-header {
			display: flex;
			justify-content: space-between;
			align-items: center;
			margin-bottom: 12px;
		}

		.breakdown-label {
			font-size: 11px;
			color: #6c7680;
			text-transform: uppercase;
			font-weight: 500;
		}

		.breakdown-icon {
			font-size: 20px;
		}

		.breakdown-value {
			font-size: 22px;
			font-weight: 700;
			color: #1f272e;
			margin-bottom: 8px;
		}

		.breakdown-details {
			border-top: 1px solid #f0f0f0;
			padding-top: 8px;
			margin-top: 8px;
		}

		.detail-row {
			display: flex;
			justify-content: space-between;
			font-size: 11px;
			color: #6c7680;
			margin-bottom: 4px;
		}

		.detail-row:last-child {
			margin-bottom: 0;
		}

		.breakdown-formula {
			font-size: 10px;
			color: #8d99a6;
			font-style: italic;
			margin-top: 4px;
		}

		/* Financial Section */
		.financial-section {
			margin-bottom: 24px;
		}

		.financial-table {
			width: 100%;
			border-collapse: collapse;
			background: #fff;
			border: 1px solid #e8e8e8;
			border-radius: 8px;
			overflow: hidden;
		}

		.financial-table th {
			background: #f7f7f7;
			padding: 12px;
			font-size: 10px;
			font-weight: 500;
			color: #6c7680;
			text-transform: uppercase;
			text-align: left;
			border-bottom: 1px solid #e8e8e8;
		}

		.financial-table td {
			padding: 12px;
			font-size: 12px;
			border-bottom: 1px solid #f0f0f0;
		}

		.financial-table tbody tr:last-child td {
			border-bottom: none;
		}

		.clickable-row {
			cursor: pointer;
			transition: background 0.15s;
		}

		.clickable-row:hover {
			background: #fafbfc;
		}

		.invoice-link {
			color: #2490ef;
			font-weight: 500;
		}

		.type-badge {
			padding: 3px 8px;
			border-radius: 4px;
			font-size: 10px;
			font-weight: 600;
		}

		.type-proforma {
			background: #e3f2fd;
			color: #1565c0;
		}

		.type-tax {
			background: #e8f5e9;
			color: #2e7d32;
		}

		.status-badge {
			padding: 3px 8px;
			border-radius: 10px;
			font-size: 10px;
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

		.status-unpaid {
			background: #fff3e0;
			color: #e65100;
		}

		.status-overdue {
			background: #ffebee;
			color: #c62828;
		}

		.txn-type-badge {
			padding: 3px 8px;
			border-radius: 4px;
			font-size: 10px;
			font-weight: 600;
		}

		.txn-deduction {
			background: #ffebee;
			color: #c62828;
		}

		.txn-release {
			background: #e8f5e9;
			color: #2e7d32;
		}

		.no-data-message {
			text-align: center;
			padding: 40px;
			color: #8d99a6;
			font-size: 13px;
			background: #fafbfc;
			border-radius: 8px;
		}

		.text-right {
			text-align: right;
		}

		.text-bold {
			font-weight: 600;
		}

		.text-success {
			color: #2e7d32;
		}

		.text-danger {
			color: #c62828;
		}

		/* Responsive */
		@media (max-width: 1200px) {
			.breakdown-grid {
				grid-template-columns: repeat(2, 1fr);
			}
		}

		@media (max-width: 768px) {
			.financial-summary-header {
				flex-direction: column;
				gap: 16px;
			}

			.header-stats {
				flex-direction: column;
				width: 100%;
			}

			.stat-card {
				width: 100%;
			}

			.breakdown-grid {
				grid-template-columns: 1fr;
			}
		}
	</style>`;
}
