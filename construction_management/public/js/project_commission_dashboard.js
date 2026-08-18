// Copyright (c) 2026, Construction Management
// License: MIT

frappe.provide('construction_management.project_commission');

construction_management.project_commission.BADGE_SLUGS = {
	'Tax Invoice': 'tax-invoice',
	'Proforma Invoice': 'proforma-invoice',
	'Journal Entry': 'journal-entry',
	'Payment Entry': 'payment-entry',
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
				construction_management.project_commission.bind_pay_actions($container);
			} else {
				$container.html(`<div class="commission-error-state"><p>${__('Could not load commission data.')}</p></div>`);
			}
		},
		error() {
			$container.html(`<div class="commission-error-state"><p>${__('Failed to fetch commission data.')}</p></div>`);
		},
	});
};

construction_management.project_commission.get_pay_cell_html = function (row, can_create_pe) {
	if (row.row_type !== 'Sales Invoice') {
		return '';
	}
	if (!(flt(row.commission_amount) > 0)) {
		return '';
	}
	if (row.commission_paid) {
		const extra = flt(row.extra_paid_amount);
		if (extra > 0) {
			return `<span class="text-muted">${__('Paid')}</span><br><small class="commission-extra-label">${__('Extra')}: ${frappe.format(extra, { fieldtype: 'Currency' })}</small>`;
		}
		return `<span class="text-muted">${__('Paid')}</span>`;
	}
	if (!row.employee) {
		return `<span class="text-muted">${__('No Employee')}</span>`;
	}
	if (!row.show_pay) {
		return '';
	}
	if (!can_create_pe) {
		return `<span class="text-muted">${__('No Permission')}</span>`;
	}

	const outstanding_amount = flt(row.outstanding_amount);
	const paid_amount = flt(row.paid_amount);
	const partial_label = paid_amount > 0 && outstanding_amount > 0
		? `<small class="text-muted">${__('Partial')}</small><br>`
		: '';

	const attrs = [
		`data-project="${frappe.utils.escape_html(row.project || '')}"`,
		`data-employee="${frappe.utils.escape_html(row.employee || '')}"`,
		`data-company="${frappe.utils.escape_html(row.company || '')}"`,
		`data-invoice="${frappe.utils.escape_html(row.invoice_no || '')}"`,
	].join(' ');

	return `${partial_label}<button type="button" class="commission-pay-btn" ${attrs}>${__('Pay')}</button>`;
};

construction_management.project_commission.bind_pay_actions = function ($container) {
	$container.find('.commission-pay-btn').off('click.commissionPay').on('click.commissionPay', function (e) {
		e.preventDefault();
		e.stopPropagation();

		const $btn = $(this);
		if ($btn.prop('disabled')) {
			return;
		}
		$btn.prop('disabled', true);

		frappe.call({
			method: 'construction_management.construction_management.page.project_commission.project_commission.get_commission_pay_defaults',
			args: {
				project: $btn.attr('data-project'),
				employee: $btn.attr('data-employee'),
				company: $btn.attr('data-company'),
				invoice_no: $btn.attr('data-invoice'),
			},
			freeze: true,
			freeze_message: __('Preparing Payment Entry...'),
			callback(r) {
				$btn.prop('disabled', false);
				if (!r.message) {
					return;
				}
				const defaults = r.message || {};
				const invoice_no = defaults.custom_commission_sales_invoice || $btn.attr('data-invoice');
				defaults.custom_is_commission_payout = 1;
				if (invoice_no) {
					defaults.custom_commission_sales_invoice = invoice_no;
					defaults.remarks = `Commission payout for Sales Invoice ${invoice_no}`;
					defaults.custom_remarks = 1;
					frappe.commission_payout_invoice = invoice_no;
				}

				frappe.new_doc('Payment Entry', defaults).then(() => {
					if (cur_frm && invoice_no) {
						cur_frm.set_value('custom_commission_sales_invoice', invoice_no);
						cur_frm.set_value('custom_is_commission_payout', 1);
						cur_frm.set_value('remarks', `Commission payout for Sales Invoice ${invoice_no}`);
						cur_frm.set_value('custom_remarks', 1);
						cur_frm.set_df_property('custom_commission_sales_invoice', 'hidden', 0);
						cur_frm.set_df_property('custom_commission_sales_invoice', 'read_only', 1);
					}
					frappe.commission_payout_invoice = null;
				});
			},
			error() {
				$btn.prop('disabled', false);
			},
		});
	});
};

construction_management.project_commission.get_invoice_link = function (row) {
	if (!row.invoice_no || row.row_type !== 'Sales Invoice') {
		return '';
	}
	return `<a href="/app/sales-invoice/${encodeURIComponent(row.invoice_no)}" target="_blank" class="document-link">${frappe.utils.escape_html(row.invoice_no)}</a>`;
};

construction_management.project_commission.get_voucher_link = function (row) {
	if (!row.source_name) {
		return '';
	}
	if (row.row_type === 'Journal Entry') {
		return `<a href="/app/journal-entry/${encodeURIComponent(row.source_name)}" target="_blank" class="document-link">${frappe.utils.escape_html(row.source_name)}</a>`;
	}
	if (row.row_type === 'Payment Entry') {
		return `<a href="/app/payment-entry/${encodeURIComponent(row.source_name)}" target="_blank" class="document-link">${frappe.utils.escape_html(row.source_name)}</a>`;
	}
	return '';
};

construction_management.project_commission.get_commission_payout_details = function (row) {
	if (row.row_type !== 'Sales Invoice' || !(row.commission_payouts || []).length) {
		return '';
	}

	const payouts = row.commission_payouts.map((payout) => {
		const name = frappe.utils.escape_html(payout.name || '');
		const link = payout.name
			? `<a href="/app/payment-entry/${encodeURIComponent(payout.name)}" target="_blank" class="document-link">${name}</a>`
			: '';
		const timestamp = payout.creation || payout.posting_date;
		const paid_at = timestamp ? frappe.datetime.str_to_user(timestamp) : '';
		const paid_amt = flt(payout.paid_amount);
		const extra_amt = flt(payout.extra_paid_amount);
		const amount_bits = [];
		if (paid_amt > 0) {
			amount_bits.push(`${__('Paid')}: ${frappe.format(paid_amt, { fieldtype: 'Currency' })}`);
		}
		if (extra_amt > 0) {
			amount_bits.push(`${__('Extra')}: ${frappe.format(extra_amt, { fieldtype: 'Currency' })}`);
		}
		const amount_line = amount_bits.length
			? `<br><small class="text-muted">${amount_bits.join(' · ')}</small>`
			: '';
		return `<div>${link}${paid_at ? `<br><small class="text-muted">${paid_at}</small>` : ''}${amount_line}</div>`;
	});

	return payouts.join('');
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
	const can_create_pe = frappe.model.can_create('Payment Entry');
	if (ledger.length) {
		ledger.forEach((row) => {
			const invoice_date = row.invoice_date ? frappe.datetime.str_to_user(row.invoice_date) : '';
			const cheque_date = row.cheque_date ? frappe.datetime.str_to_user(row.cheque_date) : '';
			const invoice_link = construction_management.project_commission.get_invoice_link(row);
			const badge_slug = row.invoice_type ? (badge_slugs[row.invoice_type] || '') : '';
			const type_badge = row.invoice_type
				? `<span class="badge-type ${badge_slug}">${row.invoice_type}</span>`
				: (row.row_type === 'Journal Entry'
					? `<span class="badge-type journal-entry">${__('Journal Entry')}</span>`
					: (row.row_type === 'Payment Entry'
						? `<span class="badge-type payment-entry">${__('Payment Entry')}</span>`
						: ''));
			const pct_disp = row.commission_pct > 0
				? `${frappe.format(row.commission_pct, { fieldtype: 'Float', precision: 2 })}%`
				: '';
			const cheque_amt_disp = row.cheque_amount > 0 ? fmt(row.cheque_amount, 'Currency') : '';
			const comm_recv_disp = row.paid_amount > 0 ? fmt(row.paid_amount, 'Currency') : '';
			const extra_paid_disp = row.extra_paid_amount > 0 ? fmt(row.extra_paid_amount, 'Currency') : '';
			const outstanding_disp = row.outstanding_amount > 0 ? fmt(row.outstanding_amount, 'Currency') : '';
			const voucher_link = construction_management.project_commission.get_voucher_link(row);
			const payout_details = construction_management.project_commission.get_commission_payout_details(row);
			const remarks_cell = payout_details || (row.remarks
				? frappe.utils.escape_html(row.remarks)
				: voucher_link);
			const pay_cell = construction_management.project_commission.get_pay_cell_html(row, can_create_pe);

			ledger_html += `
				<tr>
					<td class="text-center">${row.serial_no}</td>
					<td class="text-center">${invoice_date}</td>
					<td class="text-center">${row.invoice_serial_no || ''}</td>
					<td>${invoice_link || voucher_link}</td>
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
					<td class="text-right">${extra_paid_disp ? `<span class="commission-extra-label">${extra_paid_disp}</span>` : ''}</td>
					<td class="text-right">${outstanding_disp}</td>
					<td>${frappe.utils.escape_html(row.commission_cheque_no || '')}</td>
					<td>${remarks_cell}</td>
					<td class="text-center commission-pay-cell">${pay_cell}</td>
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
		ledger_html = `<tr><td colspan="15" class="text-center text-muted">${empty_msg}</td></tr>`;
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
							<th style="width:130px;" class="text-right">${__('Paid Amount')}</th>
							<th style="width:130px;" class="text-right">${__('Extra Paid')}</th>
							<th style="width:130px;" class="text-right">${__('Outstanding Amount')}</th>
							<th style="width:100px;">${__('Cheque No.')}</th>
							<th style="width:180px;">${__('Remarks')}</th>
							<th style="width:90px;" class="text-center">${__('Action')}</th>
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
						<span class="summary-label">${__('Extra Paid')}</span>
						<span class="summary-value commission-extra-label">${fmt(summary.commission_extra_paid_total, 'Currency')}</span>
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
