// Copyright (c) 2024, Construction Management
// License: MIT

frappe.views.calendar["Resource Planner"] = {
	field_map: {
		"start": "start_date",
		"end": "end_date",
		"id": "name",
		"title": "calendar_title",
		"allDay": 1
	},
	gantt: true,
	filters: [
		{
			"fieldtype": "Link",
			"fieldname": "project",
			"options": "Project",
			"label": __("Project")
		},
		{
			"fieldtype": "Link",
			"fieldname": "employee",
			"options": "Employee",
			"label": __("Employee")
		}
	]
};
