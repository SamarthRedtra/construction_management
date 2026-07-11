// Copyright (c) 2026, Construction Management
// License: MIT

frappe.provide('construction_management.project_soa');

construction_management.project_soa.INVOICE_BADGE_SLUGS = {
	'Tax Invoice': 'tax-invoice',
	'Proforma Invoice': 'proforma-invoice',
	'Sales Order (Proforma)': 'sales-order-proforma',
	'Payment Certificate': 'payment-certificate',
};

construction_management.project_soa.format_num = function (value, fieldtype, options) {
	options = options || {};
	const company_currency = frappe.defaults.get_default('currency') || 'AED';
	const formatted = frappe.format(value, {
		fieldtype: fieldtype,
		currency: options.currency || company_currency,
		precision: options.precision,
	});
	return `<span class="soa-num">${formatted}</span>`;
};

construction_management.project_soa.reset_dashboard = function (container) {
	const $container = $(container);
	$container.html(`
		<div class="soa-empty-state">
			<div class="soa-empty-icon">
				<svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
					<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
					<polyline points="14 2 14 8 20 8"></polyline>
					<circle cx="11.5" cy="13.5" r="2.5"></circle>
					<path d="M16 18c0-2-1.5-3.5-3.5-3.5h-2C8.5 14.5 7 16 7 18"></path>
				</svg>
			</div>
			<h3>${__('Select a Project')}</h3>
			<p>${__('Please select a project to generate the Statement of Account.')}</p>
		</div>
	`);
};

construction_management.project_soa.render_dashboard = function (container, project, options) {
	options = options || {};
	const $container = $(container);

	if (!project) {
		construction_management.project_soa.reset_dashboard(container);
		return;
	}

	$container.html(`
		<div class="soa-loading-state">
			<div class="soa-spinner"></div>
			<p>${__('Generating Statement of Account...')}</p>
		</div>
	`);

	frappe.call({
		method: 'construction_management.construction_management.page.project_soa.project_soa.get_project_soa_data',
		args: { project },
		callback(r) {
			if (r.message) {
				$container.html(construction_management.project_soa.build_dashboard_html(r.message, options, project));
				construction_management.project_soa.bind_follow_up_events($container, project);
				construction_management.project_soa.bind_expense_expand_events($container, project);
			} else {
				$container.html(`
					<div class="soa-error-state">
						<p>${__('Error: Could not retrieve Statement of Account data.')}</p>
					</div>
				`);
			}
		},
		error() {
			$container.html(`
				<div class="soa-error-state">
					<p>${__('Failed to fetch data. Please check project configuration and try again.')}</p>
				</div>
			`);
		},
	});
};

construction_management.project_soa.get_invoice_link = function (row) {
	const route_map = {
		'Tax Invoice': 'sales-invoice',
		'Proforma Invoice': 'proforma-invoice',
		'Sales Order (Proforma)': 'sales-order',
		'Payment Certificate': 'payment-certificate',
	};
	const route = route_map[row.invoice_type] || 'Form';
	if (route === 'Form') {
		return `<span class="document-link">${frappe.utils.escape_html(row.invoice_no)}</span>`;
	}
	return `<a href="/app/${route}/${encodeURIComponent(row.invoice_no)}" target="_blank" class="document-link">${frappe.utils.escape_html(row.invoice_no)}</a>`;
};

construction_management.project_soa.build_dashboard_html = function (data, options, project) {
	options = options || {};
	const fmt = construction_management.project_soa.format_num;
	const badge_slugs = construction_management.project_soa.INVOICE_BADGE_SLUGS;

	let services_html = '';
	if (data.services && data.services.length > 0) {
		data.services.forEach(function (row) {
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

	let invoice_html = '';
	if (data.invoices && data.invoices.length > 0) {
		data.invoices.forEach(function (row) {
			const invoice_link = construction_management.project_soa.get_invoice_link(row);
			const badge_slug = badge_slugs[row.invoice_type] || row.invoice_type.toLowerCase().replace(/\s+/g, '-');
			const proforma_date_disp = row.proforma_date ? frappe.datetime.str_to_user(row.proforma_date) : '';
			const tax_invoice_date_disp = row.tax_invoice_date ? frappe.datetime.str_to_user(row.tax_invoice_date) : '';
			const cheque_no_disp = row.cheque_no ? row.cheque_no : '';
			const cheque_date_disp = row.cheque_date ? frappe.datetime.str_to_user(row.cheque_date) : '';
			const cheque_amt_disp = row.cheque_amount > 0 ? fmt(row.cheque_amount, 'Currency') : '';
			const ref_doctype = row.reference_doctype || '';
			const ref_name = row.reference_name || row.invoice_no;

			invoice_html += `
				<tr data-ref-doctype="${frappe.utils.escape_html(ref_doctype)}" data-ref-name="${frappe.utils.escape_html(ref_name)}">
					<td class="text-center">${row.serial_no}</td>
					<td class="text-center">${proforma_date_disp}</td>
					<td class="text-center">${tax_invoice_date_disp}</td>
					<td class="text-center font-medium">${row.serial_no}</td>
					<td>${invoice_link}</td>
					<td><span class="badge-type ${badge_slug}">${row.invoice_type}</span></td>
					<td class="text-right font-medium">${fmt(row.amount, 'Currency')}</td>
					<td>
						${row.cheque_no || row.cheque_amount > 0 ? `
							<div class="cheque-box">
								<span class="cheque-no">${cheque_no_disp}</span>
								<span class="cheque-divider">|</span>
								<span class="cheque-date">${cheque_date_disp}</span>
								<span class="cheque-divider">|</span>
								<span class="cheque-amt">${cheque_amt_disp}</span>
							</div>
						` : ''}
						<div class="soa-row-actions">
							<span class="soa-action-link soa-add-follow-up"
								data-project="${frappe.utils.escape_html(project)}"
								data-ref-doctype="${frappe.utils.escape_html(ref_doctype)}"
								data-ref-name="${frappe.utils.escape_html(ref_name)}">${__('Add Follow Up')}</span>
							${row.invoice_type === 'Payment Certificate' || row.payment_certificate ? `
								<span class="soa-action-link soa-attach-pc"
									data-project="${frappe.utils.escape_html(project)}"
									data-ref-doctype="${frappe.utils.escape_html(ref_doctype)}"
									data-ref-name="${frappe.utils.escape_html(ref_name)}"
									data-pc="${frappe.utils.escape_html(row.payment_certificate || row.invoice_no)}">${__('Attach PC')}</span>
							` : ''}
						</div>
					</td>
				</tr>
			`;
		});
	} else {
		invoice_html = `<tr><td colspan="8" class="text-center text-muted">${__('No invoices generated for this project')}</td></tr>`;
	}

	let follow_up_html = '';
	const follow_ups = data.follow_ups || [];
	if (follow_ups.length) {
		follow_ups.forEach(function (row) {
			const attach_link = row.attachment
				? `<a href="${row.attachment}" target="_blank">${__('View')}</a>`
				: '';
			follow_up_html += `
				<tr>
					<td>${frappe.utils.escape_html(row.reference_doctype || '')}</td>
					<td><a href="/app/${construction_management.project_soa._route_for_doctype(row.reference_doctype)}/${encodeURIComponent(row.reference_name)}" target="_blank">${frappe.utils.escape_html(row.reference_name || '')}</a></td>
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

	let expenses_html = '';
	data.expenses.forEach(function (row) {
		const row_class = row.is_total ? 'expenses-total-row font-bold' : '';
		const expandable = row.expandable && row.category_key;
		const chevron = expandable
			? `<span class="expense-chevron" data-category="${frappe.utils.escape_html(row.category_key)}">▸</span>`
			: '<span class="expense-chevron-spacer"></span>';
		expenses_html += `
			<tr class="expense-category-row ${row_class}${expandable ? ' expense-expandable' : ''}"
				data-category="${expandable ? frappe.utils.escape_html(row.category_key) : ''}"
				data-expandable="${expandable ? '1' : '0'}">
				<td class="text-center">${row.idx}</td>
				<td class="expense-category-cell">${chevron}${frappe.utils.escape_html(row.category)}</td>
				<td class="text-right font-semibold">${fmt(row.cost, 'Currency')}</td>
			</tr>
		`;
		if (expandable) {
			expenses_html += `
				<tr class="expense-detail-row" data-category="${frappe.utils.escape_html(row.category_key)}" style="display:none;">
					<td colspan="3" class="expense-detail-cell">
						<div class="expense-detail-placeholder text-muted">${__('Click to load breakdown')}</div>
					</td>
				</tr>
			`;
		}
	});

	const profit_loss_class = data.profit_loss >= 0 ? 'profit-positive' : 'profit-negative';
	const profit_loss_sign = data.profit_loss >= 0 ? '+' : '';
	const embedded_class = options.embedded ? ' project-soa-embedded' : '';

	return `
		<div class="project-soa-dashboard${embedded_class}">
			<div class="soa-section-row">
				<div class="soa-ongoing-project-left">
					<h2 class="ongoing-project-title">${__('On Going Project')}</h2>
				</div>
				<div class="soa-services-right">
					<table class="soa-table soa-services-table border-table">
						<thead>
							<tr>
								<th style="width: 50px;">#</th>
								<th>${__('Service')}</th>
								<th style="width: 120px;" class="text-right">${__('Area')}</th>
								<th style="width: 150px;" class="text-right">${__('Unit Price')}</th>
								<th style="width: 180px;" class="text-right">${__('Total Amount')}</th>
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

			<div class="soa-section-block">
				<table class="soa-table text-medium border-table invoice-transactions-table">
					<thead>
						<tr>
							<th style="width: 50px;">#</th>
							<th style="width: 120px;">${__('Proforma Date')}</th>
							<th style="width: 120px;">${__('TAX Invoice Date')}</th>
							<th style="width: 120px;">${__('Invoice Serial No')}</th>
							<th style="width: 150px;">${__('Invoice No')}</th>
							<th style="width: 150px;">${__('Invoice Type')}</th>
							<th style="width: 160px;" class="text-right">${__('Amount')}</th>
							<th>
								<div class="cheque-header">
									<span>${__('Cheque No')}</span>
									<span class="cheque-divider">|</span>
									<span>${__('Cheque Date')}</span>
									<span class="cheque-divider">|</span>
									<span>${__('Cheque Amount')}</span>
								</div>
							</th>
						</tr>
					</thead>
					<tbody>${invoice_html}</tbody>
				</table>

				<div class="soa-summary-bar">
					<div class="soa-summary-item">
						<span class="summary-label">${__('Total Invoice Amount')}</span>
						<span class="summary-value red-text">${fmt(data.summary.total_invoice_amount, 'Currency')}</span>
					</div>
					<div class="soa-summary-item">
						<span class="summary-label">${__('Total Received Amount')}</span>
						<span class="summary-value blue-text">${fmt(data.summary.total_received_amount, 'Currency')}</span>
					</div>
					<div class="soa-summary-item">
						<span class="summary-label">${__('Balance')}</span>
						<span class="summary-value red-text">${fmt(data.summary.balance, 'Currency')}</span>
					</div>
					<div class="soa-summary-item">
						<span class="summary-label">${__('Retention Amount(w/o VAT)')}</span>
						<span class="summary-value red-text">${fmt(data.summary.retention_amount, 'Currency')}</span>
					</div>
					<div class="soa-summary-item">
						<span class="summary-label">${__('Any Deduction')}</span>
						<span class="summary-value red-text">${fmt(data.summary.any_deduction, 'Currency')}</span>
					</div>
				</div>
			</div>

			<div class="soa-follow-up-section">
				<h3 class="bottom-section-title">${__('Payment Certificate Follow Ups')}</h3>
				<table class="soa-table border-table soa-follow-up-table">
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

			<div class="soa-bottom-row">
				<div class="soa-expenses-block">
					<h3 class="bottom-section-title">${__('Total Expenses')}</h3>
					<table class="soa-table border-table expenses-table">
						<thead>
							<tr>
								<th style="width: 50px;">#</th>
								<th>${__('Expenses')}</th>
								<th style="width: 200px;" class="text-right">${__('Cost')}</th>
							</tr>
						</thead>
						<tbody>${expenses_html}</tbody>
					</table>
				</div>

				<div class="soa-profit-loss-block">
					<div class="profit-loss-card">
						<h3 class="profit-loss-title">${__('Total Profit/Loss')}</h3>
						<div class="profit-loss-value ${profit_loss_class}">
							${profit_loss_sign}${fmt(data.profit_loss, 'Currency')}
						</div>
					</div>
				</div>
			</div>

			${options.embedded ? '' : `
				<div class="soa-footer">
					<p>${__('Copyright © {0} {1}. All Rights Reserved.', [new Date().getFullYear(), frappe.defaults.get_default('company') || 'MRG Insulation'])}</p>
				</div>
			`}
		</div>
	`;
};

construction_management.project_soa._route_for_doctype = function (doctype) {
	const routes = {
		'Sales Order': 'sales-order',
		'Payment Certificate': 'payment-certificate',
		'Sales Invoice': 'sales-invoice',
		'Proforma Invoice': 'proforma-invoice',
	};
	return routes[doctype] || 'Form';
};

construction_management.project_soa._expense_breakdown_cache = {};

construction_management.project_soa.bind_expense_expand_events = function ($container, project) {
	const me = this;
	me._expense_breakdown_cache = {};

	$container.off('click.soa-expense').on('click.soa-expense', '.expense-expandable .expense-category-cell, .expense-expandable .expense-chevron', function (e) {
		e.preventDefault();
		const $row = $(this).closest('.expense-category-row');
		const category = $row.data('category');
		if (!category) {
			return;
		}
		const $detail = $container.find(`.expense-detail-row[data-category="${category}"]`);
		const is_open = $row.hasClass('expanded');

		if (is_open) {
			$row.removeClass('expanded');
			$row.find('.expense-chevron').text('▸');
			$detail.hide();
			return;
		}

		$row.addClass('expanded');
		$row.find('.expense-chevron').text('▾');
		$detail.show();

		if (me._expense_breakdown_cache[category]) {
			$detail.find('.expense-detail-cell').html(me._expense_breakdown_cache[category]);
			me.bind_expense_tree_events($detail);
			return;
		}

		$detail.find('.expense-detail-cell').html(`
			<div class="expense-detail-loading">
				<div class="soa-spinner" style="width:24px;height:24px;margin:10px auto;"></div>
				<p class="text-muted text-center">${__('Loading breakdown...')}</p>
			</div>
		`);

		frappe.call({
			method: 'construction_management.construction_management.page.project_soa.project_soa.get_soa_expense_breakdown',
			args: { project, category },
			callback(r) {
				const html = me.build_expense_breakdown_html(r.message || {});
				me._expense_breakdown_cache[category] = html;
				$detail.find('.expense-detail-cell').html(html);
				me.bind_expense_tree_events($detail);
			},
			error() {
				$detail.find('.expense-detail-cell').html(
					`<div class="text-muted">${__('Failed to load expense breakdown.')}</div>`
				);
			},
		});
	});
};

construction_management.project_soa.build_qty_rate_meta = function (qty, uom, rate) {
	const fmt = construction_management.project_soa.format_num;
	const parts = [];
	if (qty != null && flt(qty) !== 0) {
		parts.push(`${frappe.format(qty, { fieldtype: 'Float', precision: 2 })} ${uom || ''}`.trim());
	}
	if (rate != null && flt(rate) !== 0) {
		parts.push(fmt(rate, 'Currency'));
	}
	return parts.join(' · ');
};

construction_management.project_soa.build_expense_breakdown_html = function (data) {
	const fmt = construction_management.project_soa.format_num;
	const qtyRateMeta = construction_management.project_soa.build_qty_rate_meta;
	const groups = data.groups || [];

	if (!groups.length) {
		return `<div class="expense-detail-empty text-muted">${__('No breakdown available for this category.')}</div>`;
	}

	let html = '<div class="expense-breakdown-tree">';
	groups.forEach(function (group) {
		html += `
			<div class="expense-group-block">
				<div class="expense-group-row" data-level="group">
					<span class="expense-tree-chevron">▸</span>
					<span class="expense-tree-label">${frappe.utils.escape_html(group.label)}</span>
					<span class="expense-tree-meta"></span>
					<span class="expense-tree-amount">${fmt(group.amount, 'Currency')}</span>
				</div>
				<div class="expense-group-children" style="display:none;">
		`;
		(group.lines || []).forEach(function (line) {
			const line_meta = qtyRateMeta(line.qty, line.uom, line.rate);
			const line_meta_html = line_meta
				? `<span class="expense-line-meta">${line_meta}</span>`
				: '';

			html += `
				<div class="expense-line-block">
					<div class="expense-line-row" data-level="line">
						<span class="expense-tree-chevron">▸</span>
						<span class="expense-tree-label">${frappe.utils.escape_html(line.label)}</span>
						<span class="expense-tree-meta">${line_meta_html}</span>
						<span class="expense-tree-amount">${fmt(line.amount, 'Currency')}</span>
					</div>
					<div class="expense-line-children" style="display:none;">
			`;
			(line.sources || []).forEach(function (source) {
				const date_disp = source.date ? frappe.datetime.str_to_user(source.date) : '';
				const source_qty_rate = qtyRateMeta(source.qty, source.uom, source.rate);
				const source_meta_parts = [];
				if (source_qty_rate) {
					source_meta_parts.push(source_qty_rate);
				}
				if (date_disp) {
					source_meta_parts.push(date_disp);
				}
				const source_meta_html = source_meta_parts.join(' · ');
				const unalloc = source.unallocated ? ` <span class="expense-unallocated-badge">${__('Unallocated')}</span>` : '';
				html += `
					<div class="expense-source-row" data-level="source">
						<span class="expense-tree-chevron-spacer"></span>
						<span class="expense-tree-label">
							<a href="${source.link}" target="_blank">${frappe.utils.escape_html(source.document || '')}</a>
							<span class="expense-source-type">${frappe.utils.escape_html(source.doctype || '')}</span>
							${unalloc}
						</span>
						<span class="expense-tree-meta">${frappe.utils.escape_html(source_meta_html)}</span>
						<span class="expense-tree-amount">${fmt(source.amount, 'Currency')}</span>
					</div>
				`;
				if (source.remarks) {
					html += `<div class="expense-source-remarks">${frappe.utils.escape_html(source.remarks)}</div>`;
				}
			});
			html += '</div></div>';
		});
		html += '</div></div>';
	});
	html += '</div>';
	return html;
};

construction_management.project_soa.bind_expense_tree_events = function ($container) {
	$container.off('click.soa-expense-tree').on('click.soa-expense-tree', '.expense-group-row, .expense-line-row', function (e) {
		e.stopPropagation();
		const $row = $(this);
		const is_group = $row.hasClass('expense-group-row');
		const $children = is_group ? $row.next('.expense-group-children') : $row.next('.expense-line-children');
		const is_open = $row.hasClass('expanded');

		if (is_open) {
			$row.removeClass('expanded');
			$row.find('.expense-tree-chevron').first().text('▸');
			$children.slideUp(150);
		} else {
			$row.addClass('expanded');
			$row.find('.expense-tree-chevron').first().text('▾');
			$children.slideDown(150);
		}
	});
};

construction_management.project_soa.bind_follow_up_events = function ($container, project) {
	const me = this;

	$container.off('click.soa-follow-up').on('click.soa-follow-up', '.soa-add-follow-up, .soa-attach-pc', function (e) {
		e.preventDefault();
		const $el = $(this);
		const is_attach = $el.hasClass('soa-attach-pc');
		me.show_follow_up_dialog({
			project: $el.data('project') || project,
			reference_doctype: $el.data('ref-doctype'),
			reference_name: $el.data('ref-name'),
			payment_certificate: $el.data('pc') || '',
			focus_attachment: is_attach,
		}, $container, project);
	});
};

construction_management.project_soa.show_follow_up_dialog = function (context, $container, project) {
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
					construction_management.project_soa.render_dashboard($container, project, { embedded: $container.closest('.project-soa-embedded').length > 0 });
				},
			});
		},
	});
	dialog.show();
	if (context.focus_attachment) {
		dialog.fields_dict.attachment.$wrapper.find('button').trigger('click');
	}
};

window.render_project_soa_dashboard = function (container, project, options) {
	frappe.require(
		'/assets/construction_management/css/project_soa.css',
		() => construction_management.project_soa.render_dashboard(container, project, options)
	);
};

window.reset_project_soa_dashboard = function (container) {
	construction_management.project_soa.reset_dashboard(container);
};
