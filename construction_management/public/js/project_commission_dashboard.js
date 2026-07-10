// Copyright (c) 2026, Construction Management
// License: MIT

frappe.provide('construction_management.project_commission');

construction_management.project_commission.BADGE_SLUGS = {
	'Tax Invoice': 'tax-invoice',
	'Proforma Invoice': 'proforma-invoice',
	'Journal Entry': 'journal-entry',
};

construction_management.project_commission.format_num = function (value, fieldtype, options) {
	options = options || {};
	const company_currency = frappe.defaults.get_default('currency') || 'AED';
	const formatted = frappe.format(value, {
		fieldtype: fieldtype,
		currency: options.currency || company_currency,
		precision: options.precision,
	});
	return `<span class="commission-num">${formatted}</span>`;
};

construction_management.project_commission.reset_dashboard = function (container, options) {
	options = options || {};
	const $container = $(container);
	const company = options.company || '';

	let title;
	let message;
	if (!company) {
		title = __('Select a Company and Project');
		message = __('Please select a company, then choose a project to view the commission statement.');
	} else {
		title = __('Select a Project');
		message = __('Choose a project for {0} to view the commission statement.', [company]);
	}

	$container.html(`
		<div class="commission-empty-state">
			<h3>${title}</h3>
			<p>${message}</p>
		</div>
	`);
};

construction_management.project_commission.render_dashboard = function (container, project, options) {
	options = options || {};
	const $container = $(container);

	if (!project) {
		construction_management.project_commission.reset_dashboard(container);
		return;
	}

	$container.html(`
		<div class="commission-loading-state">
			<div class="commission-spinner"></div>
			<p>${__('Loading commission data...')}</p>
		</div>
	`);

	frappe.call({
		method: 'construction_management.construction_management.page.project_commission.project_commission.get_project_commission_data',
		args: { project },
		callback(r) {
			if (r.message) {
				$container.html(
					construction_management.project_commission.build_dashboard_html(r.message, options)
				);
			} else {
				$container.html(`<div class="commission-error-state"><p>${__('Could not load commission data.')}</p></div>`);
			}
		},
		error() {
			$container.html(`<div class="commission-error-state"><p>${__('Failed to fetch commission data.')}</p></div>`);
		},
	});
};

construction_management.project_commission.get_invoice_link = function (row) {
	if (!row.invoice_no || row.row_type !== 'Sales Invoice') {
		return '';
	}
	return `<a href="/app/sales-invoice/${encodeURIComponent(row.invoice_no)}" target="_blank" class="document-link">${frappe.utils.escape_html(row.invoice_no)}</a>`;
};

construction_management.project_commission.get_jv_link = function (row) {
	if (!row.source_name || row.row_type !== 'Journal Entry') {
		return '';
	}
	return `<a href="/app/journal-entry/${encodeURIComponent(row.source_name)}" target="_blank" class="document-link">${frappe.utils.escape_html(row.source_name)}</a>`;
};

construction_management.project_commission.build_dashboard_html = function (data, options) {
	const fmt = construction_management.project_commission.format_num;
	const badge_slugs = construction_management.project_commission.BADGE_SLUGS;
	const embedded_class = options.embedded ? ' project-commission-embedded' : '';

	let services_html = '';
	if (data.services && data.services.length) {
		data.services.forEach((row) => {
			services_html += `
				<tr>
					<td class="text-center">${row.idx}</td>
					<td>${frappe.utils.escape_html(row.service || '')}</td>
					<td class="text-right">${fmt(row.area, 'Float', { precision: 2 })}</td>
					<td class="text-right">${fmt(row.unit_price, 'Currency')}</td>
					<td class="text-right font-semibold">${fmt(row.total_amount, 'Currency')}</td>
				</tr>
			`;
		});
	} else {
		services_html = `<tr><td colspan="5" class="text-center text-muted">${__('No services recorded in BOQ')}</td></tr>`;
	}

	let ledger_html = '';
	const ledger = data.ledger || [];
	if (ledger.length) {
		ledger.forEach((row) => {
			const invoice_date = row.invoice_date ? frappe.datetime.str_to_user(row.invoice_date) : '';
			const cheque_date = row.cheque_date ? frappe.datetime.str_to_user(row.cheque_date) : '';
			const invoice_link = construction_management.project_commission.get_invoice_link(row);
			const badge_slug = row.invoice_type ? (badge_slugs[row.invoice_type] || '') : '';
			const type_badge = row.invoice_type
				? `<span class="badge-type ${badge_slug}">${row.invoice_type}</span>`
				: (row.row_type === 'Journal Entry' ? `<span class="badge-type journal-entry">${__('Journal Entry')}</span>` : '');
			const pct_disp = row.commission_pct > 0
				? `${frappe.format(row.commission_pct, { fieldtype: 'Float', precision: 2 })}%`
				: '';
			const cheque_amt_disp = row.cheque_amount > 0 ? fmt(row.cheque_amount, 'Currency') : '';
			const comm_recv_disp = row.commission_received > 0 ? fmt(row.commission_received, 'Currency') : '';
			const remarks_cell = row.remarks
				? frappe.utils.escape_html(row.remarks)
				: (row.row_type === 'Journal Entry' ? construction_management.project_commission.get_jv_link(row) : '');

			ledger_html += `
				<tr>
					<td class="text-center">${row.serial_no}</td>
					<td class="text-center">${invoice_date}</td>
					<td class="text-center">${row.invoice_serial_no || ''}</td>
					<td>${invoice_link || (row.row_type === 'Journal Entry' ? construction_management.project_commission.get_jv_link(row) : '')}</td>
					<td>${type_badge}</td>
					<td class="text-right">${row.amount > 0 ? fmt(row.amount, 'Currency') : ''}</td>
					<td>
						${row.cheque_no || row.cheque_amount > 0 ? `
							<div class="cheque-box">
								<span class="cheque-no">${row.cheque_no || ''}</span>
								<span class="cheque-divider">|</span>
								<span class="cheque-date">${cheque_date}</span>
								<span class="cheque-divider">|</span>
								<span class="cheque-amt">${cheque_amt_disp}</span>
							</div>
						` : ''}
					</td>
					<td class="text-center">${pct_disp}</td>
					<td class="text-right">${row.commission_amount > 0 ? fmt(row.commission_amount, 'Currency') : ''}</td>
					<td class="text-right">${comm_recv_disp}</td>
					<td>${frappe.utils.escape_html(row.commission_cheque_no || '')}</td>
					<td>${remarks_cell}</td>
				</tr>
			`;
		});
	} else {
		let empty_msg = __('No commission transactions for this project');
		if (data.meta && data.meta.redtra_missing) {
			empty_msg = __('Commission module (redtra_customisation) is not installed.');
		} else if (data.meta && data.meta.commission_account_missing) {
			empty_msg = __('Configure Sales Person Commission Account in BOQ Settings.');
		}
		ledger_html = `<tr><td colspan="12" class="text-center text-muted">${empty_msg}</td></tr>`;
	}

	const summary = data.summary || {};

	return `
		<div class="project-commission-dashboard${embedded_class}">
			<div class="commission-section-row">
				<div class="commission-ongoing-left">
					<h2 class="ongoing-project-title">${__('On Going Project')}</h2>
				</div>
				<div class="commission-services-right">
					<table class="commission-table border-table commission-services-table">
						<thead>
							<tr>
								<th style="width:50px;">#</th>
								<th>${__('Service')}</th>
								<th style="width:120px;" class="text-right">${__('Area')}</th>
								<th style="width:150px;" class="text-right">${__('Unit Price')}</th>
								<th style="width:180px;" class="text-right">${__('Total Amount')}</th>
							</tr>
						</thead>
						<tbody>${services_html}</tbody>
						<tfoot>
							<tr class="services-total-row">
								<td colspan="4" class="text-right font-bold">${__('Total Project Value')}</td>
								<td class="text-right font-bold total-val">${fmt(data.total_project_value, 'Currency')}</td>
							</tr>
						</tfoot>
					</table>
				</div>
			</div>

			<div class="commission-section-block">
				<table class="commission-table text-medium border-table commission-ledger-table">
					<thead>
						<tr>
							<th style="width:40px;">#</th>
							<th style="width:100px;">${__('Invoice Date')}</th>
							<th style="width:80px;">${__('Invoice Serial No')}</th>
							<th style="width:140px;">${__('Invoice No')}</th>
							<th style="width:120px;">${__('Invoice Type')}</th>
							<th style="width:120px;" class="text-right">${__('Amount')}</th>
							<th>
								<div class="cheque-header">
									<span>${__('Cheque No')}</span>
									<span class="cheque-divider">|</span>
									<span>${__('Cheque Date')}</span>
									<span class="cheque-divider">|</span>
									<span>${__('Cheque Amount')}</span>
								</div>
							</th>
							<th style="width:90px;" class="text-center">${__('Commission %')}</th>
							<th style="width:130px;" class="text-right">${__('Commission Amount')}</th>
							<th style="width:130px;" class="text-right">${__('Commission Received')}</th>
							<th style="width:100px;">${__('Cheque No.')}</th>
							<th style="width:180px;">${__('Remarks')}</th>
						</tr>
					</thead>
					<tbody>${ledger_html}</tbody>
				</table>

				<div class="commission-summary-bar">
					<div class="commission-summary-item">
						<span class="summary-label">${__('Total Invoice Amount')}</span>
						<span class="summary-value red-text">${fmt(summary.total_invoice_amount, 'Currency')}</span>
					</div>
					<div class="commission-summary-item">
						<span class="summary-label">${__('Total Received Amount')}</span>
						<span class="summary-value blue-text">${fmt(summary.total_received_amount, 'Currency')}</span>
					</div>
					<div class="commission-summary-item">
						<span class="summary-label">${__('Balance')}</span>
						<span class="summary-value red-text">${fmt(summary.balance, 'Currency')}</span>
					</div>
					<div class="commission-summary-item">
						<span class="summary-label">${__('Commission Total')}</span>
						<span class="summary-value blue-text">${fmt(summary.commission_total, 'Currency')}</span>
					</div>
					<div class="commission-summary-item">
						<span class="summary-label">${__('Commission Received')}</span>
						<span class="summary-value blue-text">${fmt(summary.commission_received_total, 'Currency')}</span>
					</div>
					<div class="commission-summary-item">
						<span class="summary-label">${__('Commission Balance')}</span>
						<span class="summary-value red-text">${fmt(summary.commission_balance, 'Currency')}</span>
					</div>
					<div class="commission-summary-item">
						<span class="summary-label">${__('Retention Amount(w/o VAT)')}</span>
						<span class="summary-value red-text">${fmt(summary.retention_amount, 'Currency')}</span>
					</div>
					<div class="commission-summary-item">
						<span class="summary-label">${__('Any Deduction')}</span>
						<span class="summary-value red-text">${fmt(summary.any_deduction, 'Currency')}</span>
					</div>
				</div>
			</div>

			${options.embedded ? '' : `
				<div class="commission-footer">
					<p>${__('Copyright © {0} {1}. All Rights Reserved.', [new Date().getFullYear(), frappe.defaults.get_default('company') || 'MRG Insulation'])}</p>
				</div>
			`}
		</div>
	`;
};

window.render_project_commission_dashboard = function (container, project, options) {
	frappe.require(
		'/assets/construction_management/css/project_commission.css',
		() => construction_management.project_commission.render_dashboard(container, project, options)
	);
};

window.reset_project_commission_dashboard = function (container, options) {
	construction_management.project_commission.reset_dashboard(container, options);
};
