// Copyright (c) 2026, Construction Management
// License: MIT

frappe.pages['bulk-raven-channel-members'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Bulk Raven Channel Members'),
		single_column: true,
	});

	const state = {
		company: frappe.defaults.get_user_default('Company') || '',
		channels: [],
	};

	const $body = $(wrapper).find('.layout-main-section');
	$body.html(`
		<div class="bulk-raven-members" style="max-width: 960px; margin: 0 auto; padding: 12px 8px 40px;">
			<p class="text-muted" style="margin-bottom: 18px;">
				${__('Add one or many Users to one or many Project Raven Channels. Manual memberships are kept even when Project team sync runs.')}
			</p>
			<div id="bulk-raven-company" style="margin-bottom: 14px;"></div>
			<div id="bulk-raven-users" style="margin-bottom: 14px;"></div>
			<div id="bulk-raven-notification-preference" style="margin-bottom: 14px;"></div>
			<div style="margin: 8px 0 6px; font-weight: 600;">${__('Project Raven Channels')}</div>
			<div id="bulk-raven-channel-list" class="frappe-card" style="padding: 12px; max-height: 360px; overflow: auto;"></div>
			<div id="bulk-raven-result" class="text-muted" style="margin-top: 16px;"></div>
		</div>
	`);

	const company_control = frappe.ui.form.make_control({
		parent: wrapper.querySelector('#bulk-raven-company'),
		df: {
			label: __('Company'),
			fieldname: 'company',
			fieldtype: 'Link',
			options: 'Company',
			default: state.company,
			change() {
				state.company = this.get_value() || '';
				load_channels();
			},
		},
		render_input: true,
	});
	if (state.company) {
		company_control.set_value(state.company);
	}

	const users_control = frappe.ui.form.make_control({
		parent: wrapper.querySelector('#bulk-raven-users'),
		df: {
			label: __('Users'),
			fieldname: 'users',
			fieldtype: 'MultiSelectList',
			options: 'User',
			reqd: 1,
			get_data(txt) {
				return frappe.db.get_link_options('User', txt, {
					enabled: 1,
					user_type: 'System User',
				});
			},
		},
		render_input: true,
	});

	const notification_preference_control = frappe.ui.form.make_control({
		parent: wrapper.querySelector('#bulk-raven-notification-preference'),
		df: {
			label: __('Notification Preference'),
			fieldname: 'notification_preference',
			fieldtype: 'Select',
			options: 'All Messages\nMentions Only',
			default: 'All Messages',
			description: __('Mentions Only sends push notifications only when the member is tagged.'),
		},
		render_input: true,
	});
	notification_preference_control.set_value('All Messages');

	function render_channel_checks(rows) {
		const $list = $body.find('#bulk-raven-channel-list');
		if (!rows.length) {
			$list.html(`<div class="text-muted">${__('No project Raven channels found for this company.')}</div>`);
			return;
		}
		const html = rows
			.map((row) => {
				const label = frappe.utils.escape_html(
					row.channel_name || row.channel_id || ''
				);
				const meta = frappe.utils.escape_html(
					[row.custom_project_no, row.project_name || row.project, row.company]
						.filter(Boolean)
						.join(' · ')
				);
				return `
					<label style="display:flex; gap:10px; align-items:flex-start; margin: 0 0 10px; font-weight: 400;">
						<input type="checkbox" class="bulk-raven-channel-check" value="${frappe.utils.escape_html(row.channel_id)}" style="margin-top:3px;">
						<span>
							<strong>${label}</strong>
							<div class="text-muted small">${meta}</div>
						</span>
					</label>
				`;
			})
			.join('');
		$list.html(
			`<div style="margin-bottom:10px;">
				<a href="#" class="bulk-raven-select-all">${__('Select all')}</a>
				<span class="text-muted"> · </span>
				<a href="#" class="bulk-raven-clear-all">${__('Clear')}</a>
			</div>${html}`
		);
		$list.find('.bulk-raven-select-all').on('click', (e) => {
			e.preventDefault();
			$list.find('.bulk-raven-channel-check').prop('checked', true);
		});
		$list.find('.bulk-raven-clear-all').on('click', (e) => {
			e.preventDefault();
			$list.find('.bulk-raven-channel-check').prop('checked', false);
		});
	}

	function load_channels() {
		frappe.call({
			method:
				'construction_management.construction_management.page.bulk_raven_channel_members.bulk_raven_channel_members.get_project_raven_channels',
			args: { company: state.company || null },
			callback(r) {
				state.channels = r.message || [];
				render_channel_checks(state.channels);
			},
		});
	}

	function get_selected_users() {
		const value = users_control.get_value();
		if (Array.isArray(value)) {
			return value.map((v) => (typeof v === 'string' ? v : v.value || v.name)).filter(Boolean);
		}
		if (!value) {
			return [];
		}
		return String(value)
			.split(',')
			.map((v) => v.trim())
			.filter(Boolean);
	}

	function get_selected_channels() {
		return $body
			.find('.bulk-raven-channel-check:checked')
			.map((_, el) => el.value)
			.get();
	}

	function submit_add() {
		const users = get_selected_users();
		const channel_ids = get_selected_channels();
		if (!users.length) {
			frappe.msgprint(__('Select at least one User'));
			return;
		}
		if (!channel_ids.length) {
			frappe.msgprint(__('Select at least one Raven Channel'));
			return;
		}

		frappe.call({
			method: 'construction_management.raven_integrations.project_channel.add_users_to_raven_channels',
			args: {
				users,
				channel_ids,
				notification_preference: notification_preference_control.get_value() || 'All Messages',
			},
			freeze: true,
			freeze_message: __('Adding members…'),
			callback(r) {
				const res = r.message || {};
				$body.find('#bulk-raven-result').html(
					__(
						'Added {0} membership(s). Updated notification preference for {1} existing membership(s).',
						[res.added || 0, res.updated || 0]
					)
				);
				frappe.show_alert({ message: __('Channel members updated'), indicator: 'green' });
			},
		});
	}

	page.set_primary_action(__('Add to Channels'), submit_add);
	load_channels();
};
