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

	fmt(n) {
		return frappe.format(n || 0, { fieldtype: 'Currency' });
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
				<h4>${__('Pipeline')} <span class="text-muted" style="font-size:12px;">(${__('Lead')} → ${__('Quotation')})</span></h4>
				<div class="sd-kpi-grid">
					<div class="sd-kpi" data-route="List/Lead/List">
						<div class="sd-kpi-label">${__('Leads (Open)')}</div>
						<div class="sd-kpi-value">${L.open || 0}</div>
						<div class="sd-kpi-sub">${__('Total')}: ${L.total || 0} · ${__('Converted')}: ${L.converted || 0}</div>
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
						<div class="sd-kpi-label">${__('Lost / Expired')}</div>
						<div class="sd-kpi-value">${(Q.lost || 0) + (Q.expired || 0)}</div>
						<div class="sd-kpi-sub">${__('Lost')}: ${Q.lost || 0} · ${__('Expired')}: ${Q.expired || 0}</div>
					</div>
				</div>
				<div class="sd-actions">
					<button class="btn btn-primary btn-sm" data-route="Form/Lead/new">${__('New Lead')}</button>
					<button class="btn btn-default btn-sm" data-route="Form/Quotation/new">${__('New Quotation')}</button>
					<button class="btn btn-default btn-sm" data-route="List/Lead/List">${__('All Leads')}</button>
					<button class="btn btn-default btn-sm" data-route="List/Quotation/List">${__('All Quotations')}</button>
				</div>
			</div>

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
	}
};
