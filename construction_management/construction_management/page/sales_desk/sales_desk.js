// Copyright (c) 2026, Construction Management
// License: MIT

frappe.pages['sales-desk'].on_page_load = function (wrapper) {
	frappe.require('/assets/construction_management/css/sales_desk.css', () => {
		frappe.ui.make_app_page({
			parent: wrapper,
			title: __('Sales Desk'),
			single_column: true,
		});
		new construction_management.SalesDesk(wrapper);
	});
};

frappe.provide('construction_management');

construction_management.SalesDesk = class SalesDesk {
	constructor(wrapper) {
		this.wrapper = $(wrapper);
		this.page_body = this.wrapper.find('.layout-main-section');
		this.company = frappe.defaults.get_user_default('Company') || '';
		this.charts = {};
		this.render_shell();
		this.load();
	}

	render_shell() {
		this.page_body.html(`
			<div class="sales-desk-layout">
				<div class="sd-toolbar">
					<div class="sd-company">
						<label>${__('Company')}</label>
						<select class="form-control input-sm" data-field="company" style="min-width:220px;"></select>
					</div>
					<div class="sd-user-meta text-muted" data-field="user-meta"></div>
					<button class="btn btn-default btn-sm" data-action="refresh">${__('Refresh')}</button>
				</div>
				<div class="sd-loading">${__('Loading...')}</div>
				<div class="sd-content" style="display:none;"></div>
			</div>
		`);
		this.bind();
		this.load_companies();
	}

	bind() {
		this.page_body.on('change', '[data-field="company"]', (e) => {
			this.company = $(e.target).val() || '';
			this.load();
		});
		this.page_body.on('click', '[data-action="refresh"]', () => this.load());
		this.page_body.on('click', '[data-route]', (e) => {
			e.preventDefault();
			const $el = $(e.currentTarget);
			const route = $el.attr('data-route');
			if (!route) return;
			frappe.set_route(...route.split('/'));
		});
	}

	load_companies() {
		frappe.db.get_list('Company', { fields: ['name'], limit: 50 }).then((rows) => {
			const $sel = this.page_body.find('[data-field="company"]');
			$sel.empty().append(`<option value="">${__('All Companies')}</option>`);
			(rows || []).forEach((r) => {
				$sel.append(`<option value="${frappe.utils.escape_html(r.name)}">${frappe.utils.escape_html(r.name)}</option>`);
			});
			if (this.company) $sel.val(this.company);
		});
	}

	load() {
		this.destroy_charts();
		this.page_body.find('.sd-loading').show();
		this.page_body.find('.sd-content').hide();
		frappe.call({
			method: 'construction_management.api.sales_desk.get_sales_desk_data',
			args: { company: this.company || undefined },
			callback: (r) => {
				this.page_body.find('.sd-loading').hide();
				if (!r.message) {
					this.page_body.find('.sd-content').html(`<p class="text-muted">${__('No data')}</p>`).show();
					return;
				}
				this.render(r.message);
			},
			error: () => {
				this.page_body.find('.sd-loading').hide();
			},
		});
	}

	destroy_charts() {
		Object.keys(this.charts || {}).forEach((key) => {
			try {
				if (this.charts[key] && this.charts[key].destroy) {
					this.charts[key].destroy();
				}
			} catch (e) {
				// ignore
			}
		});
		this.charts = {};
	}

	fmt(n) {
		return frappe.format(n || 0, { fieldtype: 'Currency' });
	}

	pie_labels_values(rows) {
		const labels = [];
		const values = [];
		(rows || []).forEach((r) => {
			if (flt(r.value) > 0) {
				labels.push(r.label);
				values.push(flt(r.value));
			}
		});
		return { labels, values };
	}

	render_pie(container_selector, title, rows, colors) {
		const $el = this.page_body.find(container_selector);
		if (!$el.length) return;
		$el.empty();
		const { labels, values } = this.pie_labels_values(rows);
		if (!labels.length) {
			$el.html(`<div class="sd-chart-empty text-muted">${__('No data')}</div>`);
			return;
		}
		try {
			this.charts[container_selector] = new frappe.Chart($el[0], {
				title: title,
				data: { labels, datasets: [{ values }] },
				type: 'pie',
				height: 260,
				colors: colors || ['#4299e1', '#48bb78', '#ed8936', '#9f7aea', '#f56565', '#38b2ac', '#ecc94b'],
				truncateLegends: true,
			});
		} catch (e) {
			console.error('Sales Desk chart error', e);
			$el.html(`<div class="sd-chart-empty text-muted">${__('Chart unavailable')}</div>`);
		}
	}

	render_bar(container_selector, title, labels, datasets, colors) {
		const $el = this.page_body.find(container_selector);
		if (!$el.length) return;
		$el.empty();
		if (!labels.length) {
			$el.html(`<div class="sd-chart-empty text-muted">${__('No data')}</div>`);
			return;
		}
		try {
			this.charts[container_selector] = new frappe.Chart($el[0], {
				title: title,
				data: { labels, datasets },
				type: 'bar',
				height: 280,
				colors: colors || ['#4299e1', '#48bb78', '#805ad5'],
				barOptions: { stacked: 0, spaceRatio: 0.4 },
				axisOptions: { xIsSeries: 0 },
			});
		} catch (e) {
			console.error('Sales Desk chart error', e);
			$el.html(`<div class="sd-chart-empty text-muted">${__('Chart unavailable')}</div>`);
		}
	}

	render_percentage_bar(container_selector, title, labels, values, colors) {
		const $el = this.page_body.find(container_selector);
		if (!$el.length) return;
		$el.empty();
		if (!labels.length) {
			$el.html(`<div class="sd-chart-empty text-muted">${__('No data')}</div>`);
			return;
		}
		try {
			this.charts[container_selector] = new frappe.Chart($el[0], {
				title: title,
				data: { labels, datasets: [{ values }] },
				type: 'percentage',
				height: 80,
				colors: colors || ['#4299e1', '#48bb78', '#ed8936', '#f56565'],
			});
		} catch (e) {
			$el.html(`<div class="sd-chart-empty text-muted">${__('Chart unavailable')}</div>`);
		}
	}

	render(data) {
		const emp = data.employee_name || data.employee || __('Not linked');
		const sp = data.sales_person || __('No Sales Person');
		this.page_body.find('[data-field="user-meta"]').html(
			`${__('Employee')}: <b>${frappe.utils.escape_html(emp)}</b> &nbsp;|&nbsp; ${__('Sales Person')}: <b>${frappe.utils.escape_html(sp)}</b>`
		);

		const L = data.leads || {};
		const Q = data.quotations || {};
		const C = data.commission || {};
		const F = data.funnel || {};
		const pipeline = data.sales_person_pipeline || [];

		const team_pipeline_section = data.is_sales_manager ? `
			<div class="sd-section">
				<h4>${__('Sales Team Pipeline')}</h4>
				<p class="text-muted small">${__('Leads and quotations by Sales Person')}</p>
				<div class="sd-chart" data-chart="team-bar"></div>
			</div>` : '';

		let projects_html = '';
		(data.projects || []).forEach((p) => {
			projects_html += `
				<tr>
					<td><a href="/app/project/${encodeURIComponent(p.name)}">${frappe.utils.escape_html(p.name)}</a></td>
					<td>${frappe.utils.escape_html(p.project_name || '')}</td>
					<td>${frappe.utils.escape_html(p.customer || '')}</td>
					<td>${frappe.utils.escape_html(p.status || '')}</td>
					<td class="text-right">
						<a class="btn btn-xs btn-default" href="/app/project-commission/${encodeURIComponent(p.name)}">${__('Commission')}</a>
						<a class="btn btn-xs btn-default" href="/app/project-soa/${encodeURIComponent(p.name)}">${__('SOA')}</a>
					</td>
				</tr>`;
		});
		if (!projects_html) {
			projects_html = `<tr><td colspan="5" class="text-muted text-center">${__('No linked projects')}</td></tr>`;
		}

		let commission_html = '';
		(C.by_project || []).forEach((row) => {
			commission_html += `
				<tr>
					<td>${row.project ? `<a href="/app/project/${encodeURIComponent(row.project)}">${frappe.utils.escape_html(row.project)}</a>` : '—'}</td>
					<td>${frappe.utils.escape_html(row.project_name || '')}</td>
					<td class="text-right">${row.invoice_count || 0}</td>
					<td class="text-right">${this.fmt(row.commission_amount)}</td>
					<td class="text-right">
						${row.project ? `<a class="btn btn-xs btn-default" href="/app/project-commission/${encodeURIComponent(row.project)}">${__('Open')}</a>` : ''}
					</td>
				</tr>`;
		});
		if (!commission_html) {
			commission_html = `<tr><td colspan="5" class="text-muted text-center">${__('No commission accrued in this period')}</td></tr>`;
		}

		this.page_body.find('.sd-content').html(`
			<div class="sd-section">
				<h4>${__('Pipeline Snapshot')} <span class="text-muted" style="font-size:12px;">(${__('Lead')} → ${__('Quotation')} → ${__('Agreed')})</span></h4>
				<div class="sd-kpi-grid">
					<div class="sd-kpi" data-route="List/Lead/List">
						<div class="sd-kpi-label">${__('Leads (Open)')}</div>
						<div class="sd-kpi-value">${L.open || 0}</div>
						<div class="sd-kpi-sub">${__('Total')}: ${L.total || 0} · ${__('Agreed')}: ${L.agreed || 0} · ${__('Converted')}: ${L.converted || 0}</div>
					</div>
					<div class="sd-kpi" data-route="List/Quotation/List">
						<div class="sd-kpi-label">${__('Quotations Open')}</div>
						<div class="sd-kpi-value">${Q.open || 0}</div>
						<div class="sd-kpi-sub">${this.fmt(Q.open_amount)} · ${__('Draft')}: ${Q.draft || 0}</div>
					</div>
					<div class="sd-kpi sd-kpi-success" data-route="List/Quotation/List">
						<div class="sd-kpi-label">${__('Agreed / Ordered')}</div>
						<div class="sd-kpi-value">${Q.agreed || 0}</div>
						<div class="sd-kpi-sub">${this.fmt(Q.agreed_amount)}</div>
					</div>
					<div class="sd-kpi sd-kpi-warn" data-route="List/Quotation/List">
						<div class="sd-kpi-label">${__('Lost / Not Agreed')}</div>
						<div class="sd-kpi-value">${(Q.lost || 0) + (Q.expired || 0)}</div>
						<div class="sd-kpi-sub">${__('Lost')}: ${Q.lost || 0} · ${__('Expired')}: ${Q.expired || 0}</div>
					</div>
				</div>
				<div class="sd-chart" data-chart="funnel-pct"></div>
				<div class="sd-actions">
					<button class="btn btn-primary btn-sm" data-route="Form/Lead/new">${__('New Lead')}</button>
					<button class="btn btn-default btn-sm" data-route="Form/Quotation/new">${__('New Quotation')}</button>
					<button class="btn btn-default btn-sm" data-route="List/Lead/List">${__('All Leads')}</button>
					<button class="btn btn-default btn-sm" data-route="List/Quotation/List">${__('All Quotations')}</button>
				</div>
			</div>

			<div class="sd-section">
				<h4>${__('Status Breakdown')}</h4>
				<div class="sd-chart-grid">
					<div class="sd-chart-card">
						<div class="sd-chart-title">${__('Leads by Status')}</div>
						<div class="sd-chart" data-chart="leads-pie"></div>
					</div>
					<div class="sd-chart-card">
						<div class="sd-chart-title">${__('Quotations by Status')}</div>
						<div class="sd-chart" data-chart="quotations-pie"></div>
					</div>
					<div class="sd-chart-card">
						<div class="sd-chart-title">${__('Commission by Project')} <span class="text-muted">(${__('This month')})</span></div>
						<div class="sd-chart" data-chart="commission-pie"></div>
					</div>
				</div>
			</div>

			${team_pipeline_section}

			<div class="sd-section">
				<h4>${__('My Commission')} <span class="text-muted" style="font-size:12px;">(${__('This month')} · ${frappe.utils.escape_html(C.from_date || '')} → ${frappe.utils.escape_html(C.to_date || '')})</span></h4>
				<div class="sd-kpi-grid">
					<div class="sd-kpi sd-kpi-info">
						<div class="sd-kpi-label">${__('Accrued Commission')}</div>
						<div class="sd-kpi-value">${this.fmt(C.accrued_total)}</div>
						<div class="sd-kpi-sub">${__('Invoices')}: ${C.invoice_count || 0}</div>
					</div>
					<div class="sd-kpi" data-route="query-report/Sales Person Commission Payment Summary">
						<div class="sd-kpi-label">${__('Commission Report')}</div>
						<div class="sd-kpi-value" style="font-size:16px;">${__('Open Report')}</div>
						<div class="sd-kpi-sub">${frappe.utils.escape_html(C.sales_person || __('Link Employee → Sales Person'))}</div>
					</div>
				</div>
				<table class="table table-bordered sd-table">
					<thead>
						<tr>
							<th>${__('Project')}</th>
							<th>${__('Name')}</th>
							<th class="text-right">${__('Invoices')}</th>
							<th class="text-right">${__('Commission')}</th>
							<th></th>
						</tr>
					</thead>
					<tbody>${commission_html}</tbody>
				</table>
			</div>

			<div class="sd-section">
				<h4>${__('My Projects')}</h4>
				<table class="table table-bordered sd-table">
					<thead>
						<tr>
							<th>${__('Project')}</th>
							<th>${__('Name')}</th>
							<th>${__('Customer')}</th>
							<th>${__('Status')}</th>
							<th class="text-right">${__('Actions')}</th>
						</tr>
					</thead>
					<tbody>${projects_html}</tbody>
				</table>
			</div>
		`).show();

		// Charts after DOM mount
		setTimeout(() => {
			this.render_percentage_bar(
				'[data-chart="funnel-pct"]',
				__('Pipeline mix'),
				[__('Open Leads'), __('Lead Quotation'), __('Lead Agreed'), __('Converted'), __('Q Open'), __('Q Agreed'), __('Q Lost')],
				[
					F.leads_open || 0,
					F.leads_quotation || 0,
					F.leads_agreed || 0,
					F.leads_converted || 0,
					F.quotations_open || 0,
					F.quotations_agreed || 0,
					F.quotations_lost || 0,
				],
				['#63b3ed', '#4299e1', '#48bb78', '#38a169', '#ed8936', '#9f7aea', '#f56565']
			);

			this.render_pie(
				'[data-chart="leads-pie"]',
				'',
				L.by_status || [],
				['#63b3ed', '#4299e1', '#805ad5', '#48bb78', '#38a169', '#f56565', '#a0aec0', '#ed8936']
			);

			this.render_pie(
				'[data-chart="quotations-pie"]',
				'',
				Q.by_status || [],
				['#a0aec0', '#4299e1', '#ed8936', '#9f7aea', '#48bb78', '#38a169', '#f56565', '#e53e3e', '#ecc94b']
			);

			const commission_rows = (C.by_project || []).map((r) => ({
				label: r.project_name || r.project || __('No Project'),
				value: flt(r.commission_amount),
			}));
			this.render_pie(
				'[data-chart="commission-pie"]',
				'',
				commission_rows,
				['#38b2ac', '#4299e1', '#9f7aea', '#ed8936', '#48bb78', '#f56565']
			);

			if (data.is_sales_manager && pipeline.length) {
				const labels = pipeline.slice(0, 12).map((r) => r.sales_person || __('Unassigned'));
				this.render_bar(
					'[data-chart="team-bar"]',
					__('Team comparison'),
					labels,
					[
						{ name: __('Leads'), values: pipeline.slice(0, 12).map((r) => r.leads || 0) },
						{ name: __('Qualified'), values: pipeline.slice(0, 12).map((r) => r.qualified || 0) },
						{ name: __('Quotations'), values: pipeline.slice(0, 12).map((r) => r.quotations || 0) },
					],
					['#4299e1', '#48bb78', '#805ad5']
				);
			}
		}, 50);
	}
};
