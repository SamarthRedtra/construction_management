// Copyright (c) 2026, Construction Management
// License: MIT

frappe.pages['project-soa'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Project SOA'),
		single_column: true
	});

	// Initialize the page body structure
	page.body.html(`
		<div id="project-soa-wrapper" class="project-soa-layout">
			<div class="project-soa-header-row">
				<div class="project-soa-title-container">
					<h1 class="soa-title-main">${__('SOA - PROJECT WISE')}</h1>
				</div>
				<div class="project-soa-filter-container">
					<div id="project-field-wrapper"></div>
				</div>
			</div>
			<div id="project-soa-container">
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
			</div>
		</div>
	`);

	// Add Project selector control
	var project_control = frappe.ui.form.make_control({
		parent: wrapper.querySelector('#project-field-wrapper'),
		df: {
			label: __('Project'),
			fieldname: 'project',
			fieldtype: 'Link',
			options: 'Project',
			placeholder: __('Select Project'),
			change: function() {
				var project = this.get_value();
				if (project) {
					render_soa_dashboard(project, page);
				} else {
					reset_soa_dashboard();
				}
			}
		},
		render_input: true
	});

	// Handle standard routing if project is passed in route
	var project_val = null;
	var route = frappe.get_route();
	if (route && route[2]) {
		project_val = route[2];
	} else if (frappe.route_options && frappe.route_options.project) {
		project_val = frappe.route_options.project;
	}
	if (project_val) {
		project_control.set_value(project_val);
	}
};

function reset_soa_dashboard() {
	$('#project-soa-container').html(`
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
}

function render_soa_dashboard(project, page) {
	// Show loading indicator
	$('#project-soa-container').html(`
		<div class="soa-loading-state">
			<div class="soa-spinner"></div>
			<p>${__('Generating Statement of Account...')}</p>
		</div>
	`);

	frappe.call({
		method: 'construction_management.construction_management.page.project_soa.project_soa.get_project_soa_data',
		args: { project: project },
		callback: function(r) {
			if (r.message) {
				var data = r.message;
				var company_currency = frappe.defaults.get_default("currency") || "AED";
				
				// Build services rows
				var services_html = '';
				if (data.services && data.services.length > 0) {
					data.services.forEach(function(row) {
						services_html += `
							<tr>
								<td class="text-center">${row.idx}</td>
								<td>${row.service}</td>
								<td class="text-right">${frappe.format(row.area, { fieldtype: 'Float', precision: 2 })}</td>
								<td class="text-right">${frappe.format(row.unit_price, { fieldtype: 'Currency', currency: company_currency })}</td>
								<td class="text-right font-semibold">${frappe.format(row.total_amount, { fieldtype: 'Currency', currency: company_currency })}</td>
							</tr>
						`;
					});
				} else {
					services_html = `<tr><td colspan="5" class="text-center text-muted">${__('No services recorded in BOQ')}</td></tr>`;
				}

				// Build invoice rows
				var invoice_html = '';
				if (data.invoices && data.invoices.length > 0) {
					data.invoices.forEach(function(row) {
						var invoice_link = '';
						if (row.invoice_type === 'Tax Invoice') {
							invoice_link = `<a href="/app/sales-invoice/${row.invoice_no}" target="_blank" class="document-link">${row.invoice_no}</a>`;
						} else {
							invoice_link = `<a href="/app/proforma-invoice/${row.invoice_no}" target="_blank" class="document-link">${row.invoice_no}</a>`;
						}

						var cheque_no_disp = row.cheque_no ? row.cheque_no : '';
						var cheque_date_disp = row.cheque_date ? frappe.datetime.str_to_user(row.cheque_date) : '';
						var cheque_amt_disp = row.cheque_amount > 0 ? frappe.format(row.cheque_amount, { fieldtype: 'Currency', currency: company_currency }) : '';

						invoice_html += `
							<tr>
								<td class="text-center">${row.serial_no}</td>
								<td class="text-center">${frappe.datetime.str_to_user(row.proforma_date)}</td>
								<td class="text-center">${frappe.datetime.str_to_user(row.tax_invoice_date)}</td>
								<td class="text-center font-medium">${row.serial_no}</td>
								<td>${invoice_link}</td>
								<td><span class="badge-type ${row.invoice_type.toLowerCase().replace(' ', '-')}">${row.invoice_type}</span></td>
								<td class="text-right font-medium">${frappe.format(row.amount, { fieldtype: 'Currency', currency: company_currency })}</td>
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
								</td>
							</tr>
						`;
					});
				} else {
					invoice_html = `<tr><td colspan="8" class="text-center text-muted">${__('No invoices generated for this project')}</td></tr>`;
				}

				// Build expenses rows
				var expenses_html = '';
				data.expenses.forEach(function(row) {
					var row_class = row.is_total ? 'expenses-total-row font-bold' : '';
					expenses_html += `
						<tr class="${row_class}">
							<td class="text-center">${row.idx}</td>
							<td>${row.category}</td>
							<td class="text-right font-semibold">${frappe.format(row.cost, { fieldtype: 'Currency', currency: company_currency })}</td>
						</tr>
					`;
				});

				// Profit loss display variables
				var profit_loss_class = data.profit_loss >= 0 ? 'profit-positive' : 'profit-negative';
				var profit_loss_sign = data.profit_loss >= 0 ? '+' : '';

				var dashboard_html = `
					<!-- Services Top Section -->
					<div class="soa-section-row">
						<div class="soa-ongoing-project-left">
							<h2 class="ongoing-project-title">${__('On Going Project')}</h2>
						</div>
						<div class="soa-services-right">
							<table class="soa-table border-table">
								<thead>
									<tr>
										<th style="width: 50px;">#</th>
										<th>${__('Service')}</th>
										<th style="width: 120px;" class="text-right">${__('Area')}</th>
										<th style="width: 150px;" class="text-right">${__('Unit Price')}</th>
										<th style="width: 180px;" class="text-right">${__('Total Amount')}</th>
									</tr>
								</thead>
								<tbody>
									${services_html}
								</tbody>
								<tfoot>
									<tr class="services-total-row">
										<td colspan="4" class="text-right font-bold">${__('Total Project Value')}</td>
										<td class="text-right font-bold total-val">${frappe.format(data.total_project_value, { fieldtype: 'Currency', currency: company_currency })}</td>
									</tr>
								</tfoot>
							</table>
						</div>
					</div>

					<!-- Invoices Middle Section -->
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
							<tbody>
								${invoice_html}
							</tbody>
						</table>

						<!-- Middle Section Summary Row -->
						<div class="soa-summary-bar">
							<div class="soa-summary-item">
								<span class="summary-label">${__('Total Invoice Amount')}</span>
								<span class="summary-value red-text">${frappe.format(data.summary.total_invoice_amount, { fieldtype: 'Currency', currency: company_currency })}</span>
							</div>
							<div class="soa-summary-item">
								<span class="summary-label">${__('Total Received Amount')}</span>
								<span class="summary-value blue-text">${frappe.format(data.summary.total_received_amount, { fieldtype: 'Currency', currency: company_currency })}</span>
							</div>
							<div class="soa-summary-item">
								<span class="summary-label">${__('Balance')}</span>
								<span class="summary-value red-text">${frappe.format(data.summary.balance, { fieldtype: 'Currency', currency: company_currency })}</span>
							</div>
							<div class="soa-summary-item">
								<span class="summary-label">${__('Retention Amount(w/o VAT)')}</span>
								<span class="summary-value red-text">${frappe.format(data.summary.retention_amount, { fieldtype: 'Currency', currency: company_currency })}</span>
							</div>
							<div class="soa-summary-item">
								<span class="summary-label">${__('Any Deduction')}</span>
								<span class="summary-value red-text">${frappe.format(data.summary.any_deduction, { fieldtype: 'Currency', currency: company_currency })}</span>
							</div>
						</div>
					</div>

					<!-- Bottom Section: Expenses & Profit/Loss -->
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
								<tbody>
									${expenses_html}
								</tbody>
							</table>
						</div>

						<div class="soa-profit-loss-block">
							<div class="profit-loss-card">
								<h3 class="profit-loss-title">${__('Total Profit/Loss')}</h3>
								<div class="profit-loss-value ${profit_loss_class}">
									${profit_loss_sign}${frappe.format(data.profit_loss, { fieldtype: 'Currency', currency: company_currency })}
								</div>
							</div>
						</div>
					</div>
					
					<!-- Footer Branding -->
					<div class="soa-footer">
						<p>${__('Copyright © {0} {1}. All Rights Reserved.', [new Date().getFullYear(), frappe.defaults.get_default("company") || "MRG Insulation"])}</p>
					</div>
				`;

				$('#project-soa-container').html(dashboard_html);
			} else {
				$('#project-soa-container').html(`
					<div class="soa-error-state">
						<p>${__('Error: Could not retrieve Statement of Account data.')}</p>
					</div>
				`);
			}
		},
		error: function() {
			$('#project-soa-container').html(`
				<div class="soa-error-state">
					<p>${__('Failed to fetch data. Please check project configuration and try again.')}</p>
				</div>
			`);
		}
	});
}
