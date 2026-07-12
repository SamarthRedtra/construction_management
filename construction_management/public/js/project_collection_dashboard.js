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

construction_management.project_collection._build_billing_row_html = function (row, project, fmt, fmt_date) {
	const status = construction_management.project_collection.get_row_status(row);
	const category = construction_management.project_collection.get_payment_category(row);
	const ref_doctype = row.reference_doctype || '';
	const ref_name = row.reference_name || row.invoice_no;
	const invoice_link = construction_management.project_collection.get_doc_link(ref_doctype, row.invoice_no);
	const payment_mode_disp = [row.payment_mode, row.cheque_no].filter(Boolean).join(' · ');

	return `
		<tr class="collection-billing-row" data-category="${category}"
			data-ref-doctype="${frappe.utils.escape_html(ref_doctype)}" data-ref-name="${frappe.utils.escape_html(ref_name)}">
			<td class="text-center">${row.sr_no}</td>
			<td class="collection-invoice-cell">
				<div class="collection-invoice-link">${invoice_link}</div>
				<span class="badge-status ${status.slug}">${status.label}</span>
			</td>
			<td>${frappe.utils.escape_html(row.client_name || '')}</td>
			<td>${frappe.utils.escape_html(row.pm_engg || '')}</td>
			<td>${frappe.utils.escape_html(row.workdone || '')}</td>
			<td class="text-right">${row.pi_amount && row.pi_amount > 0 ? fmt(row.pi_amount, 'Currency') : ''}</td>
			<td class="text-center">${fmt_date(row.pi_date)}</td>
			<td class="text-center">${fmt_date(row.pc_date)}</td>
			<td class="text-right">${row.pc_amt && row.pc_amt > 0 ? fmt(row.pc_amt, 'Currency') : ''}</td>
			<td class="text-center">${fmt_date(row.ti_date)}</td>
			<td class="text-right">${row.ti_amt && row.ti_amt > 0 ? fmt(row.ti_amt, 'Currency') : ''}</td>
			<td class="text-center">${fmt_date(row.due_date)}</td>
			<td>${frappe.utils.escape_html(payment_mode_disp)}</td>
			<td class="text-center">${fmt_date(row.payment_date)}</td>
			<td>
				${frappe.utils.escape_html(row.remarks || '')}
				<div class="collection-row-actions">
					<span class="collection-action-link collection-add-follow-up"
						data-project="${frappe.utils.escape_html(project)}"
						data-ref-doctype="${frappe.utils.escape_html(ref_doctype)}"
						data-ref-name="${frappe.utils.escape_html(ref_name)}">${__('Add Follow Up')}</span>
					${row.stage === 'Payment Certificate' || row.payment_certificate ? `
						<span class="collection-action-link collection-attach-pc"
							data-project="${frappe.utils.escape_html(project)}"
							data-ref-doctype="${frappe.utils.escape_html(ref_doctype)}"
							data-ref-name="${frappe.utils.escape_html(ref_name)}"
							data-pc="${frappe.utils.escape_html(row.payment_certificate || row.invoice_no)}">${__('Attach PC')}</span>
					` : ''}
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
				<td colspan="15">
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
					<td class="text-center">${row.overdue_count || 0}</td>
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
		grid_rows = `<tr><td colspan="15" class="text-center text-muted">${__('No billing cycles for this project')}</td></tr>`;
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
								<th>${__('Client Name')}</th>
								<th>${__('PM / Engg')}</th>
								<th>${__('Workdone')}</th>
								<th class="text-right">${__('PI Amount')}</th>
								<th>${__('PI Date')}</th>
								<th>${__('PC Date')}</th>
								<th class="text-right">${__('PC Amt')}</th>
								<th>${__('TI Date')}</th>
								<th class="text-right">${__('TI Amt')}</th>
								<th>${__('Due Date')}</th>
								<th>${__('Payment Mode')}</th>
								<th>${__('Payment Date')}</th>
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
