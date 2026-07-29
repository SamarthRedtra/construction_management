// Copyright (c) 2026, Construction Management
// License: MIT

frappe.pages['project-collection'].on_page_load = function (wrapper) {
	frappe.require('/assets/construction_management/css/project_collection.css', () => {
		initialize_collection_manager(wrapper);
	});
};

function initialize_collection_manager(wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Collection Manager'),
		single_column: true,
	});

	const page_body = $(wrapper).find('.layout-main-section');
	page_body.html(`
		<div id="project-collection-wrapper" class="project-collection-layout">
			<div class="project-collection-header-row">
				<h1 class="collection-title-main">${__('COLLECTION MANAGER')}</h1>
			</div>
			<div class="collection-view-switch" role="group" aria-label="${__('Collection view')}">
				<button type="button" class="collection-view-toggle active" data-view="register">${__('Collection Register')}</button>
				<button type="button" class="collection-view-toggle" data-view="expected">${__('Expected Payments')}</button>
			</div>
			<div class="collection-period-bar" role="group" aria-label="${__('Date period')}">
				<span class="collection-period-label">${__('Period')}</span>
				<button type="button" class="collection-period-chip" data-range="this_week">${__('This Week')}</button>
				<button type="button" class="collection-period-chip active" data-range="this_month">${__('This Month')}</button>
				<button type="button" class="collection-period-chip" data-range="last_month">${__('Last Month')}</button>
				<button type="button" class="collection-period-chip" data-range="this_quarter">${__('This Quarter')}</button>
				<button type="button" class="collection-period-chip" data-range="this_year">${__('This Year')}</button>
				<button type="button" class="collection-period-chip" data-range="all_time">${__('All Time')}</button>
			</div>
			<div class="project-collection-filters-row">
				<div id="project-collection-company-wrapper"></div>
				<div id="project-collection-customer-wrapper"></div>
				<div id="project-collection-from-date-wrapper"></div>
				<div id="project-collection-to-date-wrapper"></div>
			</div>
			<div id="project-collection-container"></div>
		</div>
	`);

	const container_el = wrapper.querySelector('#project-collection-container');
	let selected_company = frappe.defaults.get_user_default('Company') || '';
	let active_range = 'this_month';
	let applying_date_range = false;
	let active_view = 'register';

	function to_date_string(value) {
		return [value.getFullYear(), String(value.getMonth() + 1).padStart(2, '0'), String(value.getDate()).padStart(2, '0')].join('-');
	}

	function get_date_range(range) {
		const now = new Date();
		const year = now.getFullYear();
		const month = now.getMonth();
		if (range === 'all_time') return { from_date: '', to_date: '' };
		if (range === 'this_week') {
			const start = new Date(year, month, now.getDate() - ((now.getDay() + 6) % 7));
			return { from_date: to_date_string(start), to_date: to_date_string(now) };
		}
		if (range === 'last_month') {
			return { from_date: to_date_string(new Date(year, month - 1, 1)), to_date: to_date_string(new Date(year, month, 0)) };
		}
		if (range === 'this_quarter') {
			const quarter_start = Math.floor(month / 3) * 3;
			return { from_date: to_date_string(new Date(year, quarter_start, 1)), to_date: to_date_string(now) };
		}
		if (range === 'this_year') {
			return { from_date: `${year}-01-01`, to_date: to_date_string(now) };
		}
		return { from_date: to_date_string(new Date(year, month, 1)), to_date: to_date_string(now) };
	}

	function update_active_range(range) {
		active_range = range;
		page_body.find('.collection-period-chip').toggleClass('active', function () {
			return $(this).data('range') === range;
		});
	}

	function render_front() {
		construction_management.project_collection.render_invoice_portfolio(container_el, {
			company: selected_company,
			customer: customer_control.get_value() || '',
			from_date: from_date_control.get_value() || '',
			to_date: to_date_control.get_value() || '',
			view: active_view,
		});
	}

	const company_control = frappe.ui.form.make_control({
		parent: wrapper.querySelector('#project-collection-company-wrapper'),
		df: {
			label: __('Company'),
			fieldname: 'company',
			fieldtype: 'Link',
			options: 'Company',
			placeholder: __('Select Company'),
			change() {
				selected_company = this.get_value() || '';
				render_front();
			},
		},
		render_input: true,
	});

	const customer_control = frappe.ui.form.make_control({
		parent: wrapper.querySelector('#project-collection-customer-wrapper'),
		df: {
			label: __('Customer'),
			fieldname: 'customer',
			fieldtype: 'Link',
			options: 'Customer',
			placeholder: __('All Customers'),
			change() {
				render_front();
			},
		},
		render_input: true,
	});
	const make_date_control = (selector, fieldname, label) => frappe.ui.form.make_control({
		parent: wrapper.querySelector(selector),
		df: { label, fieldname, fieldtype: 'Date', change() { if (!applying_date_range) { update_active_range('custom'); render_front(); } } },
		render_input: true,
	});
	const from_date_control = make_date_control('#project-collection-from-date-wrapper', 'from_date', __('From Date'));
	const to_date_control = make_date_control('#project-collection-to-date-wrapper', 'to_date', __('To Date'));

	function apply_date_range(range) {
		const dates = get_date_range(range);
		applying_date_range = true;
		from_date_control.set_value(dates.from_date);
		to_date_control.set_value(dates.to_date);
		applying_date_range = false;
		update_active_range(range);
		render_front();
	}

	page_body.on('click', '.collection-period-chip', function () {
		apply_date_range($(this).data('range'));
	});
	page_body.on('click', '.collection-view-toggle', function () {
		active_view = $(this).data('view');
		page_body.find('.collection-view-toggle').toggleClass('active', function () {
			return $(this).data('view') === active_view;
		});
		render_front();
	});

	let company_val = frappe.defaults.get_user_default('Company') || '';
	if (frappe.route_options) {
		company_val = frappe.route_options.company || company_val;
	}

	if (company_val) {
		selected_company = company_val;
		company_control.set_value(company_val);
	}

	apply_date_range(active_range);
}
