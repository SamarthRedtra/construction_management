// Copyright (c) 2026, Construction Management
// License: MIT

frappe.provide('construction_management.project_collection');

construction_management.project_collection.STAGE_BADGE_SLUGS = {
	'Tax Invoice': 'tax-invoice',
	'Proforma Invoice': 'proforma-invoice',
	'Sales Order (Proforma)': 'sales-order-proforma',
	'Payment Certificate': 'payment-certificate',
};

construction_management.project_collection.format_num = function (value, fieldtype, options) {
	options = options || {};
	const company_currency = frappe.defaults.get_default('currency') || 'AED';
	const formatted = frappe.format(value, {
		fieldtype: fieldtype,
		currency: options.currency || company_currency,
		precision: options.precision,
	});
	return `<span class="collection-num">${formatted}</span>`;
};

construction_management.project_collection.format_date = function (value) {
	return value ? frappe.datetime.str_to_user(value) : '';
};

construction_management.project_collection.get_doc_link = function (doctype, name) {
	if (!name) {
		return '';
	}
	const route = (construction_management.project_soa && construction_management.project_soa._route_for_doctype)
		? construction_management.project_soa._route_for_doctype(doctype)
		: 'Form';
	return `<a href="/app/${route}/${encodeURIComponent(name)}" target="_blank" class="document-link">${frappe.utils.escape_html(name)}</a>`;
};

construction_management.project_collection.BILLING_CATEGORIES = [
	{ key: 'proforma', label: __('Proforma'), slug: 'proforma' },
	{ key: 'pc-pending', label: __('PC Pending'), slug: 'pc-pending' },
	{ key: 'overdue', label: __('Overdue'), slug: 'overdue' },
	{ key: 'unpaid', label: __('Unpaid'), slug: 'unpaid' },
	{ key: 'paid', label: __('Paid'), slug: 'paid' },
];

construction_management.project_collection.get_payment_category = function (row) {
	if (row.payment_date) {
		return 'paid';
	}
	if (row.is_overdue) {
		return 'overdue';
	}
	if (row.ti_amt && row.ti_amt > 0) {
		return 'unpaid';
	}
	if (row.pc_amt && row.pc_amt > 0) {
		return 'pc-pending';
	}
	return 'proforma';
};

construction_management.project_collection.get_row_status = function (row) {
	if (row.payment_date) {
		return { label: __('Paid'), slug: 'paid' };
	}
	if (row.is_overdue) {
		return { label: __('Overdue'), slug: 'overdue' };
	}
	if (row.ti_amt && row.ti_amt > 0) {
		return { label: __('Unpaid'), slug: 'unpaid' };
	}
	if (row.pc_amt && row.pc_amt > 0) {
		return { label: __('PC Pending'), slug: 'pc-pending' };
	}
	if (row.pi_amount && row.pi_amount > 0) {
		return { label: __('Proforma'), slug: 'proforma' };
	}
	return { label: row.stage || '', slug: 'default' };
};

construction_management.project_collection.to_input_date = function (value) {
	if (!value) {
		return '';
	}
	if (typeof value === 'string') {
		return value.slice(0, 10);
	}
	try {
		return frappe.datetime.obj_to_str(value).slice(0, 10);
	} catch (e) {
		return '';
	}
};

construction_management.project_collection._build_billing_row_html = function (row, project, fmt, fmt_date) {
	const status = construction_management.project_collection.get_row_status(row);
	const category = construction_management.project_collection.get_payment_category(row);
	const ref_doctype = row.reference_doctype || '';
	const ref_name = row.reference_name || row.invoice_no;
	const invoice_link = construction_management.project_collection.get_doc_link(ref_doctype, row.invoice_no);
	const project_link = row.project ? `<a href="/app/project/${encodeURIComponent(row.project)}" target="_blank" class="document-link">${frappe.utils.escape_html(row.project)}</a>` : '';
	const document_type = row.document_type || (ref_doctype === 'Sales Order' ? __('Proforma (Sales Order)') : row.stage || '');
	const document_type_slug = ref_doctype === 'Sales Order' ? 'proforma' : 'tax-invoice';
	const payment_mode_disp = [row.payment_mode, row.cheque_no].filter(Boolean).join(' · ');
	const pc_name = row.payment_certificate || (row.stage === 'Payment Certificate' ? row.invoice_no : '');
	const pc_attachment = row.pc_attachment || '';
	const pc_date_value = construction_management.project_collection.to_input_date(row.pc_date);
	const pc_amt_value = row.pc_amt != null && row.pc_amt !== '' ? flt(row.pc_amt) : '';
	// Always show an editable PC Date control so users can find/set it in the grid.
	const pc_date_html = `
		<input type="date" class="form-control input-xs collection-pc-date-input"
			value="${pc_date_value}"
			data-pc="${frappe.utils.escape_html(pc_name || '')}"
			data-project="${frappe.utils.escape_html(project)}"
			data-ref-doctype="${frappe.utils.escape_html(ref_doctype)}"
			data-ref-name="${frappe.utils.escape_html(ref_name)}"
			title="${__('Certificate / PC Date')}" />
		${!pc_name ? `<div class="text-muted text-xs">${__('Saves as PC Date')}</div>` : ''}
	`;
	const pc_amt_html = `
		<input type="number" step="0.01" class="form-control input-xs text-right collection-pc-amt-input"
			value="${pc_amt_value}"
			data-pc="${frappe.utils.escape_html(pc_name || '')}"
			data-project="${frappe.utils.escape_html(project)}"
			data-ref-doctype="${frappe.utils.escape_html(ref_doctype)}"
			data-ref-name="${frappe.utils.escape_html(ref_name)}"
			title="${__('PC Amount')}"
			placeholder="0.00" />
		${!pc_name ? `<div class="text-muted text-xs">${__('Saves as PC Amt')}</div>` : ''}
	`;

	return `
		<tr class="collection-billing-row" data-category="${category}"
			data-ref-doctype="${frappe.utils.escape_html(ref_doctype)}" data-ref-name="${frappe.utils.escape_html(ref_name)}">
			<td class="text-center">${row.sr_no}</td>
			<td class="collection-invoice-cell">
				<div class="collection-invoice-link">${invoice_link}</div>
				<span class="badge-status ${status.slug}">${status.label}</span>
				${row.is_advance ? `<span class="badge-status advance">${__('Advance')}</span>` : ''}
			</td>
			<td><span class="collection-document-type ${document_type_slug}">${frappe.utils.escape_html(document_type)}</span></td>
			<td>${frappe.utils.escape_html(row.client_name || '')}</td>
			<td>${frappe.utils.escape_html(row.pm_engg || '')}</td>
			<td>${frappe.utils.escape_html(row.workdone || '')}</td>
			<td class="text-right">${row.pi_amount && row.pi_amount > 0 ? fmt(row.pi_amount, 'Currency') : ''}</td>
			<td class="text-center">${fmt_date(row.pi_date)}</td>
			<td class="text-center collection-pc-date-cell">${pc_date_html}</td>
			<td class="text-right collection-pc-amt-cell">${pc_amt_html}</td>
			<td class="text-center">${fmt_date(row.ti_date)}</td>
			<td class="text-right">${row.ti_amt && row.ti_amt > 0 ? fmt(row.ti_amt, 'Currency') : ''}</td>
			<td class="text-center">${fmt_date(row.overdue_date || row.due_date)}${row.days_overdue ? ` <span class="text-danger">(+${row.days_overdue}d)</span>` : ''}</td>
			<td>${frappe.utils.escape_html(payment_mode_disp)}</td>
			<td class="text-center">${fmt_date(row.payment_date)}</td>
			<td>${project_link}</td>
			<td>
				${frappe.utils.escape_html(row.remarks || '')}
				<div class="collection-row-actions">
					<span class="collection-action-link collection-add-follow-up"
						data-project="${frappe.utils.escape_html(project)}"
						data-ref-doctype="${frappe.utils.escape_html(ref_doctype)}"
						data-ref-name="${frappe.utils.escape_html(ref_name)}">${__('Add Follow Up')}</span>
					<span class="collection-action-link collection-upload-pc"
							data-project="${frappe.utils.escape_html(project)}"
							data-ref-doctype="${frappe.utils.escape_html(ref_doctype)}"
							data-ref-name="${frappe.utils.escape_html(ref_name)}"
							data-pc="${frappe.utils.escape_html(row.payment_certificate || '')}">${__('Add / Upload PC')}</span>
					${pc_attachment ? `<a class="collection-action-link" href="${frappe.utils.escape_html(pc_attachment)}" target="_blank" rel="noopener">${__('View PC')}</a>` : ''}
				</div>
			</td>
		</tr>
	`;
};

construction_management.project_collection._build_billing_category_summary = function (rows, fmt) {
	const categories = construction_management.project_collection.BILLING_CATEGORIES;
	const counts = {};
	const totals = {};

	categories.forEach((cat) => {
		counts[cat.key] = 0;
		totals[cat.key] = 0;
	});

	rows.forEach((row) => {
		const key = construction_management.project_collection.get_payment_category(row);
		counts[key] = (counts[key] || 0) + 1;
		const amount = row.ti_amt || row.pc_amt || row.pi_amount || 0;
		totals[key] = (totals[key] || 0) + flt(amount);
	});

	let html = `
		<div class="collection-category-filters">
			<button type="button" class="collection-filter-chip active" data-filter="all">
				${__('All')} <span class="chip-count">${rows.length}</span>
			</button>
	`;

	categories.forEach((cat) => {
		if (!counts[cat.key]) {
			return;
		}
		html += `
			<button type="button" class="collection-filter-chip" data-filter="${cat.key}">
				<span class="badge-status ${cat.slug}">${cat.label}</span>
				<span class="chip-count">${counts[cat.key]}</span>
				<span class="chip-amount">${fmt(totals[cat.key], 'Currency')}</span>
			</button>
		`;
	});

	html += '</div>';
	return html;
};

construction_management.project_collection._build_grouped_billing_rows = function (rows, project, fmt, fmt_date) {
	const categories = construction_management.project_collection.BILLING_CATEGORIES;
	const grouped = {};

	categories.forEach((cat) => {
		grouped[cat.key] = [];
	});

	rows.forEach((row) => {
		const key = construction_management.project_collection.get_payment_category(row);
		if (grouped[key]) {
			grouped[key].push(row);
		}
	});

	let html = '';
	let serial = 0;

	categories.forEach((cat) => {
		const cat_rows = grouped[cat.key];
		if (!cat_rows.length) {
			return;
		}

		const cat_total = cat_rows.reduce((sum, row) => sum + flt(row.ti_amt || row.pc_amt || row.pi_amount || 0), 0);
		html += `
			<tr class="collection-category-header" data-category="${cat.key}">
				<td colspan="17">
					<span class="badge-status ${cat.slug}">${cat.label}</span>
					<span class="category-meta">${cat_rows.length} ${__('rows')} · ${fmt(cat_total, 'Currency')}</span>
				</td>
			</tr>
		`;

		cat_rows.forEach((row) => {
			serial += 1;
			html += construction_management.project_collection._build_billing_row_html(
				Object.assign({}, row, { sr_no: serial }),
				project,
				fmt,
				fmt_date
			);
		});
	});

	return html;
};

function flt(value) {
	return parseFloat(value) || 0;
}

construction_management.project_collection.reset_dashboard = function (container, options) {
	options = options || {};
	const $container = $(container);
	const company = options.company || '';

	if (!company) {
		$container.html(`
			<div class="collection-empty-state">
				<h3>${__('Select a Company')}</h3>
				<p>${__('Choose a company to view the collection portfolio across all projects.')}</p>
			</div>
		`);
		return;
	}

	$container.html(`
		<div class="collection-loading-state">
			<div class="collection-spinner"></div>
			<p>${__('Loading portfolio...')}</p>
		</div>
	`);

	frappe.call({
		method: 'construction_management.construction_management.page.project_collection.project_collection.get_collection_portfolio',
		args: { company },
		callback(r) {
			if (r.message) {
				$container.html(
					construction_management.project_collection.build_portfolio_html(r.message, options)
				);
				construction_management.project_collection.bind_portfolio_events($container);
			} else {
				$container.html(`<div class="collection-error-state"><p>${__('Could not load portfolio.')}</p></div>`);
			}
		},
		error() {
			$container.html(`<div class="collection-error-state"><p>${__('Failed to fetch portfolio.')}</p></div>`);
		},
	});
};

construction_management.project_collection.render_dashboard = function (container, project, options) {
	options = options || {};
	const $container = $(container);

	if (!project) {
		construction_management.project_collection.reset_dashboard(container, options);
		return;
	}

	$container.html(`
		<div class="collection-loading-state">
			<div class="collection-spinner"></div>
			<p>${__('Loading collection data...')}</p>
		</div>
	`);

	frappe.call({
		method: 'construction_management.construction_management.page.project_collection.project_collection.get_collection_project_detail',
		args: { project },
		callback(r) {
			try {
				if (r.message) {
					$container.html(
						construction_management.project_collection.build_detail_html(r.message, project, options)
					);
					construction_management.project_collection.bind_detail_events($container, project, options);
				} else {
					$container.html(`<div class="collection-error-state"><p>${__('Could not load collection data.')}</p></div>`);
				}
			} catch (err) {
				console.error('Collection Manager render error:', err);
				$container.html(`<div class="collection-error-state"><p>${__('Failed to render collection data.')}</p></div>`);
			}
		},
		error() {
			$container.html(`<div class="collection-error-state"><p>${__('Failed to fetch collection data.')}</p></div>`);
		},
	});
};

construction_management.project_collection.render_invoice_portfolio = function (container, filters) {
	const $container = $(container);
	if (!filters.company) {
			$container.html(`<div class="collection-empty-state"><h3>${__('Select a Company')}</h3></div>`);
		return;
	}
	if (filters.view === 'expected') {
		$container.html(`<div class="collection-loading-state"><div class="collection-spinner"></div><p>${__('Loading expected payments...')}</p></div>`);
		construction_management.project_collection.render_expected_payments($container, filters, true);
		return;
	}
	$container.html(`<div class="collection-loading-state"><div class="collection-spinner"></div><p>${__('Loading invoiced projects...')}</p></div>`);
	frappe.call({
		method: 'construction_management.construction_management.page.project_collection.project_collection.get_collection_invoice_portfolio',
		args: { company: filters.company, filters },
		callback: (r) => {
			const rows = r.message || [];
			$container.html(construction_management.project_collection.build_invoice_portfolio_html(rows));
			construction_management.project_collection.bind_invoice_portfolio_events($container, filters);
		},
		error: () => $container.html(`<div class="collection-error-state"><p>${__('Failed to load invoiced projects.')}</p></div>`),
	});
};

construction_management.project_collection.build_invoice_portfolio_html = function (rows) {
	const fmt = construction_management.project_collection.format_num;
	const fmtDate = construction_management.project_collection.format_date;
	const tax_invoices = rows.filter((row) => row.reference_doctype === 'Sales Invoice');
	const total_invoiced = tax_invoices.reduce((total, row) => total + flt(row.ti_amt || 0), 0);
	const paid_count = tax_invoices.filter((row) => row.payment_date).length;
	const awaiting_pc_count = tax_invoices.filter((row) => !row.pc_date).length;
	const overdue_count = tax_invoices.filter((row) => row.is_overdue).length;
	let body = '';
	if (rows.length) {
		let active_project = '';
		let serial = 0;
		body = rows.map((row) => {
			let group_header = '';
			if (row.project !== active_project) {
				active_project = row.project;
				group_header = `<tr class="collection-project-group-header"><td colspan="17"><span>${frappe.utils.escape_html(row.project_name || row.project)}</span><small>${frappe.utils.escape_html(row.client_name || '')}${row.pm_engg ? ` · ${frappe.utils.escape_html(row.pm_engg)}` : ''}</small></td></tr>`;
			}
			serial += 1;
			return group_header + construction_management.project_collection._build_billing_row_html(
				Object.assign({}, row, { sr_no: serial }), row.project, fmt, fmtDate
			);
		}).join('');
	} else {
		body = `<tr><td colspan="17" class="text-center text-muted">${__('No invoiced projects match the selected filters')}</td></tr>`;
	}
	return `<div class="project-collection-dashboard collection-register-dashboard">
		<div class="collection-register-heading">
			<div><p class="collection-eyebrow">${__('Collection control centre')}</p><h2 class="collection-section-title">${__('Invoice Register')}</h2><p class="collection-section-sub">${__('Submitted invoices only · newest invoices first')}</p></div>
			<div class="collection-register-note">${__('Add a PC date, certified amount, or upload the certificate directly from the invoice row.')}</div>
		</div>
		<div class="collection-register-kpis">
			<div class="collection-register-kpi"><span>${__('Documents')}</span><strong>${rows.length}</strong></div>
			<div class="collection-register-kpi collection-register-kpi-primary"><span>${__('Tax invoice value')}</span><strong>${fmt(total_invoiced, 'Currency')}</strong></div>
			<div class="collection-register-kpi collection-register-kpi-success"><span>${__('Paid')}</span><strong>${paid_count}</strong></div>
			<div class="collection-register-kpi collection-register-kpi-warning"><span>${__('Awaiting PC')}</span><strong>${awaiting_pc_count}</strong></div>
			<div class="collection-register-kpi collection-register-kpi-danger"><span>${__('Overdue')}</span><strong>${overdue_count}</strong></div>
		</div>
		<div class="collection-table-toolbar"><span>${__('Invoice details and collection progress')}</span><span>${__('Scroll horizontally to view all fields')} →</span></div>
		<div class="collection-grid-scroll"><table class="collection-table border-table collection-billing-grid"><thead><tr>
			<th>${__('Sr No')}</th><th>${__('Document No')}</th><th>${__('Document Type')}</th><th>${__('Client Name')}</th><th>${__('PM / Engg')}</th><th>${__('Workdone')}</th>
			<th class="text-right">${__('PI Amount')}</th><th>${__('PI Date')}</th><th>${__('PC Date')}</th><th class="text-right">${__('PC Amt')}</th>
			<th>${__('TI Date')}</th><th class="text-right">${__('TI Amt')}</th><th>${__('Due Date')}</th><th>${__('Payment Mode')}</th><th>${__('Payment Date')}</th><th>${__('Project No')}</th><th>${__('Remarks / Action')}</th>
		</tr></thead><tbody>${body}</tbody></table></div></div>`;
};

construction_management.project_collection.render_expected_payments = function ($container, filters, replace) {
	frappe.call({
		method: 'construction_management.construction_management.page.project_collection.project_collection.get_collection_expected_payments',
		args: { company: filters.company, filters },
		callback: (r) => {
			const data = r.message || { months: [], rows: [] };
			const fmt = construction_management.project_collection.format_num;
			const headers = (data.months || []).map((month) => `<th class="text-right">${frappe.utils.escape_html(month.label)}</th>`).join('');
			const rows = (data.rows || []).map((row, index) => `<tr><td class="text-center">${index + 1}</td><td>${frappe.utils.escape_html(row.customer_name || row.customer)}</td>${data.months.map((month) => `<td class="text-right">${row.amounts[month.key] ? fmt(row.amounts[month.key], 'Currency') : ''}</td>`).join('')}</tr>`).join('') || `<tr><td colspan="${(data.months || []).length + 2}" class="text-center text-muted">${__('No outstanding payments due in these months')}</td></tr>`;
			const totals = (data.months || []).map((month) => `<td class="text-right">${fmt((data.rows || []).reduce((sum, row) => sum + flt(row.amounts[month.key] || 0), 0), 'Currency')}</td>`).join('');
			const html = `<div class="collection-expected-payments"><div class="collection-register-heading"><div><p class="collection-eyebrow">${__('Cash forecast')}</p><h2 class="collection-section-title">${__('Expected Payments by Customer')}</h2><p class="collection-section-sub">${__('Outstanding Tax Invoices grouped by due month')}</p></div></div><div class="collection-grid-scroll"><table class="collection-table border-table collection-expected-table"><thead><tr><th>${__('Sr No')}</th><th>${__('Customer')}</th>${headers}</tr></thead><tbody>${rows}</tbody><tfoot><tr><td colspan="2">${__('Total')}</td>${totals}</tr></tfoot></table></div></div>`;
			if (replace) $container.html(html); else $container.append(html);
		},
	});
};

construction_management.project_collection.build_portfolio_html = function (rows, options) {
	const fmt = construction_management.project_collection.format_num;
	const embedded_class = options.embedded ? ' project-collection-embedded' : '';

	let table_rows = '';
	if (rows && rows.length) {
		rows.forEach((row) => {
			table_rows += `
				<tr class="collection-portfolio-row" data-project="${frappe.utils.escape_html(row.project)}">
					<td class="font-medium">${frappe.utils.escape_html(row.project_name || row.project)}</td>
					<td>${frappe.utils.escape_html(row.client_name || '')}</td>
					<td>${frappe.utils.escape_html(row.pm_engg || '')}</td>
					<td class="text-right">${row.pi_count || 0} · ${fmt(row.pi_total, 'Currency')}</td>
					<td class="text-right">${row.pc_count || 0} · ${fmt(row.pc_certified, 'Currency')}</td>
					<td class="text-right">${fmt(row.ti_billed, 'Currency')}</td>
					<td class="text-right">${fmt(row.collected, 'Currency')}</td>
					<td class="text-right">${fmt(row.pending, 'Currency')}</td>
					<td class="text-center">${row.overdue_count || 0}${row.overdue_amount ? `<div class="text-muted text-xs">${fmt(row.overdue_amount, 'Currency')}</div>` : ''}</td>
					<td>${frappe.utils.escape_html(row.last_follow_up_status || '')}</td>
				</tr>
			`;
		});
	} else {
		table_rows = `<tr><td colspan="10" class="text-center text-muted">${__('No active projects found')}</td></tr>`;
	}

	return `
		<div class="project-collection-dashboard${embedded_class}">
			<div class="collection-section-block">
				<h2 class="collection-section-title">${__('Portfolio Overview')}</h2>
				<p class="collection-section-sub">${__('Click a project row to view the billing grid.')}</p>
				<div class="collection-grid-scroll">
					<table class="collection-table border-table collection-portfolio-table">
						<thead>
							<tr>
								<th>${__('Project')}</th>
								<th>${__('Client')}</th>
								<th>${__('PM / Engg')}</th>
								<th class="text-right">${__('PI Raised')}</th>
								<th class="text-right">${__('PC Certified')}</th>
								<th class="text-right">${__('TI Billed')}</th>
								<th class="text-right">${__('Collected')}</th>
								<th class="text-right">${__('Pending')}</th>
								<th class="text-center">${__('Overdue')}</th>
								<th>${__('Last Follow Up')}</th>
							</tr>
						</thead>
						<tbody>${table_rows}</tbody>
					</table>
				</div>
			</div>
		</div>
	`;
};

construction_management.project_collection.build_detail_html = function (data, project, options) {
	const fmt = construction_management.project_collection.format_num;
	const fmt_date = construction_management.project_collection.format_date;
	const embedded_class = options.embedded ? ' project-collection-embedded' : '';
	const summary = data.summary || {};
	const project_info = data.project || {};

	let grid_rows = '';
	const rows = data.rows || [];
	let category_summary_html = '';
	if (rows.length) {
		category_summary_html = construction_management.project_collection._build_billing_category_summary(rows, fmt);
		grid_rows = construction_management.project_collection._build_grouped_billing_rows(rows, project, fmt, fmt_date);
	} else {
		grid_rows = `<tr><td colspan="17" class="text-center text-muted">${__('No billing cycles for this project')}</td></tr>`;
	}

	let follow_up_html = '';
	const follow_ups = data.follow_ups || [];
	if (follow_ups.length) {
		follow_ups.forEach((row) => {
			const attach_link = row.attachment
				? `<a href="${row.attachment}" target="_blank">${__('View')}</a>`
				: '';
			const route = construction_management.project_soa
				? construction_management.project_soa._route_for_doctype(row.reference_doctype)
				: 'Form';
			follow_up_html += `
				<tr>
					<td>${frappe.utils.escape_html(row.reference_doctype || '')}</td>
					<td><a href="/app/${route}/${encodeURIComponent(row.reference_name)}" target="_blank">${frappe.utils.escape_html(row.reference_name || '')}</a></td>
					<td>${row.follow_up_date ? frappe.datetime.str_to_user(row.follow_up_date) : ''}</td>
					<td>${frappe.utils.escape_html(row.status || '')}</td>
					<td>${frappe.utils.escape_html(row.remarks || '')}</td>
					<td>${attach_link}</td>
				</tr>
			`;
		});
	} else {
		follow_up_html = `<tr><td colspan="6" class="text-center text-muted">${__('No follow-ups recorded')}</td></tr>`;
	}

	return `
		<div class="project-collection-dashboard${embedded_class}">
			<div class="collection-project-header">
				<h2 class="collection-project-title">${frappe.utils.escape_html(project_info.project_name || project)}</h2>
				<p class="collection-project-meta">
					${frappe.utils.escape_html(project_info.client_name || '')}
					${project_info.pm_engg ? ' · ' + frappe.utils.escape_html(project_info.pm_engg) : ''}
				</p>
			</div>

			<div class="collection-kpi-row">
				<div class="collection-kpi-card">
					<span class="kpi-label">${__('PI Raised')}</span>
					<span class="kpi-value">${fmt(summary.pi_raised, 'Currency')}</span>
					<span class="kpi-sub">${summary.pi_count || 0} ${__('invoices')}</span>
				</div>
				<div class="collection-kpi-card">
					<span class="kpi-label">${__('PC Certified')}</span>
					<span class="kpi-value">${fmt(summary.pc_certified, 'Currency')}</span>
					<span class="kpi-sub">${summary.pc_count || 0} ${__('certificates')}</span>
				</div>
				<div class="collection-kpi-card">
					<span class="kpi-label">${__('TI Billed')}</span>
					<span class="kpi-value">${fmt(summary.ti_billed, 'Currency')}</span>
				</div>
				<div class="collection-kpi-card kpi-success">
					<span class="kpi-label">${__('Collected')}</span>
					<span class="kpi-value">${fmt(summary.collected, 'Currency')}</span>
				</div>
				<div class="collection-kpi-card kpi-warning">
					<span class="kpi-label">${__('Pending')}</span>
					<span class="kpi-value">${fmt(summary.pending, 'Currency')}</span>
				</div>
				<div class="collection-kpi-card kpi-danger">
					<span class="kpi-label">${__('Overdue')}</span>
					<span class="kpi-value">${summary.overdue_count || 0}</span>
					<span class="kpi-sub">${fmt(summary.overdue_amount || 0, 'Currency')}</span>
				</div>
			</div>

			<div class="collection-section-block">
				<h3 class="collection-section-title">${__('Billing Grid')}</h3>
				${category_summary_html}
				<div class="collection-grid-scroll">
					<table class="collection-table border-table collection-billing-grid">
						<thead>
							<tr>
								<th>${__('Sr No')}</th>
								<th>${__('Invoice No')}</th>
								<th>${__('Document Type')}</th>
								<th>${__('Client Name')}</th>
								<th>${__('PM / Engg')}</th>
								<th>${__('Workdone')}</th>
								<th class="text-right">${__('PI Amount')}</th>
								<th>${__('PI Date')}</th>
								<th>${__('PC Date')}</th>
								<th class="text-right">${__('PC Amt')}</th>
								<th>${__('TI Date')}</th>
								<th class="text-right">${__('TI Amt')}</th>
								<th>${__('Overdue Date')}</th>
								<th>${__('Payment Mode')}</th>
								<th>${__('Payment Date')}</th>
								<th>${__('Project No')}</th>
								<th>${__('Remarks')}</th>
							</tr>
						</thead>
						<tbody>${grid_rows}</tbody>
					</table>
				</div>
			</div>

			<div class="collection-follow-up-section">
				<h3 class="collection-section-title">${__('Payment Certificate Follow Ups')}</h3>
				<table class="collection-table border-table collection-follow-up-table">
					<thead>
						<tr>
							<th>${__('Reference Type')}</th>
							<th>${__('Reference')}</th>
							<th>${__('Follow Up Date')}</th>
							<th>${__('Status')}</th>
							<th>${__('Remarks')}</th>
							<th>${__('Attachment')}</th>
						</tr>
					</thead>
					<tbody>${follow_up_html}</tbody>
				</table>
			</div>
		</div>
	`;
};

construction_management.project_collection.bind_portfolio_events = function ($container) {
	$container.off('click.collection-portfolio').on('click.collection-portfolio', '.collection-portfolio-row', function () {
		const project = $(this).data('project');
		if (project && window.__collection_on_project_select) {
			window.__collection_on_project_select(project);
		}
	});
};

construction_management.project_collection.show_follow_up_dialog = function (context, $container, project, options) {
	const me = this;
	const dialog = new frappe.ui.Dialog({
		title: context.focus_attachment ? __('Attach Payment Certificate') : __('Add Follow Up'),
		fields: [
			{
				fieldname: 'follow_up_date',
				label: __('Follow Up Date'),
				fieldtype: 'Date',
				default: frappe.datetime.get_today(),
			},
			{
				fieldname: 'status',
				label: __('Status'),
				fieldtype: 'Select',
				options: ['Open', 'Followed Up', 'Waiting Payment', 'Closed'].join('\n'),
				default: 'Open',
			},
			{ fieldname: 'remarks', label: __('Remarks'), fieldtype: 'Small Text' },
			{ fieldname: 'attachment', label: __('Attachment'), fieldtype: 'Attach' },
		],
		primary_action_label: __('Save'),
		primary_action(values) {
			frappe.call({
				method: 'construction_management.construction_management.page.project_soa.project_soa.create_project_soa_follow_up',
				args: {
					project: context.project,
					reference_doctype: context.reference_doctype,
					reference_name: context.reference_name,
					payment_certificate: context.payment_certificate || '',
					follow_up_date: values.follow_up_date,
					status: values.status,
					remarks: values.remarks,
					attachment: values.attachment,
				},
				callback() {
					dialog.hide();
					frappe.show_alert({ message: __('Follow up saved'), indicator: 'green' });
					me.render_dashboard($container[0], project, options);
				},
			});
		},
	});
	dialog.show();
	if (context.focus_attachment) {
		dialog.fields_dict.attachment.$wrapper.find('button').trigger('click');
	}
};

construction_management.project_collection.show_payment_certificate_dialog = function (context, on_saved) {
	const dialog = new frappe.ui.Dialog({
		title: __('Add / Upload Payment Certificate'),
		fields: [
			{ fieldname: 'certificate_date', label: __('PC Date'), fieldtype: 'Date', default: frappe.datetime.get_today(), reqd: 1 },
			{ fieldname: 'pc_amount', label: __('PC Amount'), fieldtype: 'Currency', reqd: 1 },
			{ fieldname: 'attachment', label: __('Payment Certificate'), fieldtype: 'Attach', reqd: 1 },
		],
		primary_action_label: __('Save Certificate'),
		primary_action(values) {
			frappe.call({
				method: 'construction_management.construction_management.page.project_collection.project_collection.save_collection_payment_certificate',
				args: Object.assign({}, context, values),
				freeze: true,
				freeze_message: __('Saving payment certificate...'),
				callback(r) {
					if (!r.exc) {
						dialog.hide();
						frappe.show_alert({ message: __('Payment certificate saved'), indicator: 'green' });
						on_saved(r.message || {}, values);
					}
				},
			});
		},
	});
	dialog.show();
};

construction_management.project_collection.bind_invoice_portfolio_events = function ($container, filters) {
	const me = this;
	const mark_row_saved = ($row, message) => {
		$row.addClass('collection-row-saved');
		const $actions = $row.find('.collection-row-actions');
		$actions.find('.collection-save-note').remove();
		$actions.append(`<span class="collection-save-note">${frappe.utils.escape_html(message || __('Saved'))}</span>`);
		setTimeout(() => {
			$row.removeClass('collection-row-saved');
			$actions.find('.collection-save-note').fadeOut(180, function () { $(this).remove(); });
		}, 2200);
	};
	$container.off('click.collection-upload-pc').on('click.collection-upload-pc', '.collection-upload-pc', function (e) {
		e.preventDefault();
		const $el = $(this);
		me.show_payment_certificate_dialog({
			project: $el.data('project'),
			reference_doctype: $el.data('ref-doctype'),
			reference_name: $el.data('ref-name'),
		}, (result, values) => {
			const $row = $el.closest('.collection-billing-row');
			$row.find('.collection-pc-date-input').val(values.certificate_date);
			$row.find('.collection-pc-amt-input').val(values.pc_amount);
			$el.text(__('Update PC'));
			if (result.attachment && !$row.find('.collection-view-pc').length) {
				$el.after(`<a class="collection-action-link collection-view-pc" href="${frappe.utils.escape_html(result.attachment)}" target="_blank" rel="noopener">${__('View PC')}</a>`);
			}
			mark_row_saved($row, __('PC saved'));
		});
	});
	$container.off('change.collection-portfolio-pc').on('change.collection-portfolio-pc', '.collection-pc-date-input, .collection-pc-amt-input', function () {
		const $input = $(this);
		const isDate = $input.hasClass('collection-pc-date-input');
		$input.prop('disabled', true).addClass('collection-input-saving');
		frappe.call({
			method: isDate
				? 'construction_management.construction_management.page.project_collection.project_collection.update_collection_pc_date'
				: 'construction_management.construction_management.page.project_collection.project_collection.update_collection_pc_amount',
			args: isDate ? {
				project: $input.attr('data-project'), payment_certificate: $input.attr('data-pc'),
				certificate_date: $input.val(), reference_doctype: $input.attr('data-ref-doctype'), reference_name: $input.attr('data-ref-name'),
			} : {
				project: $input.attr('data-project'), payment_certificate: $input.attr('data-pc'),
				pc_amount: $input.val(), reference_doctype: $input.attr('data-ref-doctype'), reference_name: $input.attr('data-ref-name'),
			},
			callback(r) {
				$input.prop('disabled', false).removeClass('collection-input-saving');
				if (!r.exc) mark_row_saved($input.closest('.collection-billing-row'));
			},
			error() {
				$input.prop('disabled', false).removeClass('collection-input-saving');
			},
		});
	});
};

construction_management.project_collection.bind_detail_events = function ($container, project, options) {
	const me = this;

	$container.off('click.collection-filter').on('click.collection-filter', '.collection-filter-chip', function () {
		const filter = $(this).data('filter');
		$container.find('.collection-filter-chip').removeClass('active');
		$(this).addClass('active');

		$container.find('.collection-category-header, .collection-billing-row').each(function () {
			const $el = $(this);
			const category = $el.data('category');
			const show = filter === 'all' || category === filter;
			$el.toggle(show);
		});
	});

	$container.off('click.collection-follow-up').on('click.collection-follow-up', '.collection-add-follow-up, .collection-attach-pc', function (e) {
		e.preventDefault();
		const $el = $(this);
		const is_attach = $el.hasClass('collection-attach-pc');
		me.show_follow_up_dialog({
			project: $el.data('project') || project,
			reference_doctype: $el.data('ref-doctype'),
			reference_name: $el.data('ref-name'),
			payment_certificate: $el.data('pc') || '',
			focus_attachment: is_attach,
		}, $container, project, options);
	});

	$container.off('change.collection-pc-date').on('change.collection-pc-date', '.collection-pc-date-input', function () {
		const $input = $(this);
		const pc = ($input.attr('data-pc') || '').trim();
		const certificate_date = $input.val() || null;
		const args = {
			project: $input.attr('data-project') || project,
			payment_certificate: pc,
			certificate_date: certificate_date,
			reference_doctype: $input.attr('data-ref-doctype') || '',
			reference_name: $input.attr('data-ref-name') || '',
		};
		frappe.call({
			method: 'construction_management.construction_management.page.project_collection.project_collection.update_collection_pc_date',
			args: args,
			freeze: true,
			freeze_message: __('Updating PC date...'),
			callback: function (r) {
				if (!r.exc) {
					frappe.show_alert({ message: __('PC date updated'), indicator: 'green' });
					me.render_dashboard($container.get(0), project, options);
				}
			},
		});
	});

	$container.off('change.collection-pc-amt').on('change.collection-pc-amt', '.collection-pc-amt-input', function () {
		const $input = $(this);
		const pc = ($input.attr('data-pc') || '').trim();
		const args = {
			project: $input.attr('data-project') || project,
			payment_certificate: pc,
			pc_amount: $input.val(),
			reference_doctype: $input.attr('data-ref-doctype') || '',
			reference_name: $input.attr('data-ref-name') || '',
		};
		frappe.call({
			method: 'construction_management.construction_management.page.project_collection.project_collection.update_collection_pc_amount',
			args: args,
			freeze: true,
			freeze_message: __('Updating PC amount...'),
			callback: function (r) {
				if (!r.exc) {
					frappe.show_alert({ message: __('PC amount updated'), indicator: 'green' });
					me.render_dashboard($container.get(0), project, options);
				}
			},
		});
	});
};

window.render_project_collection_dashboard = function (container, project, options) {
	frappe.require(
		'/assets/construction_management/css/project_collection.css',
		() => construction_management.project_collection.render_dashboard(container, project, options)
	);
};

window.reset_project_collection_dashboard = function (container, options) {
	frappe.require(
		'/assets/construction_management/css/project_collection.css',
		() => construction_management.project_collection.reset_dashboard(container, options)
	);
};
