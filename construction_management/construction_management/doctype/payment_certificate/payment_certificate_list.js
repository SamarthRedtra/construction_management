// Copyright (c) 2024, Construction Management
// License: MIT

frappe.listview_settings['Payment Certificate'] = {
	add_fields: ['type', 'status', 'accepted_amount', 'variance'],
	
	get_indicator: function(doc) {
		// Status indicators
		const status_colors = {
			'Draft': 'grey',
			'Submitted': 'blue',
			'Invoiced': 'green',
			'Paid': 'green',
			'Cancelled': 'red'
		};
		
		return [__(doc.status), status_colors[doc.status] || 'grey', 'status,=,' + doc.status];
	},
	
	formatters: {
		type: function(value) {
			if (value === 'Sales') {
				return `<span class="indicator-pill blue">${value}</span>`;
			} else if (value === 'Purchase') {
				return `<span class="indicator-pill orange">${value}</span>`;
			}
			return value;
		},
		
		variance: function(value) {
			if (flt(value) > 0) {
				return `<span style="color: red;">${format_currency(value)}</span>`;
			} else if (flt(value) < 0) {
				return `<span style="color: green;">${format_currency(value)}</span>`;
			}
			return format_currency(value);
		}
	}
};
