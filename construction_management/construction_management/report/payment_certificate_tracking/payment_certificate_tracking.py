# Copyright (c) 2024, Construction Management
# License: MIT

"""
Payment Certificate Tracking Report

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
Property 8: Report Type Filter
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
	"""Execute the report"""
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart_data(data, filters)
	return columns, data, None, chart


def get_columns():
	"""
	Get report columns.
	Requirements: 8.2
	"""
	return [
		{
			"fieldname": "name",
			"label": _("PC No"),
			"fieldtype": "Link",
			"options": "Payment Certificate",
			"width": 140
		},
		{
			"fieldname": "type",
			"label": _("Type"),
			"fieldtype": "Data",
			"width": 80
		},
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 150
		},
		{
			"fieldname": "bill_no",
			"label": _("Bill No"),
			"fieldtype": "Link",
			"options": "BOQ Bill",
			"width": 120
		},
		{
			"fieldname": "boq_item",
			"label": _("BOQ Item"),
			"fieldtype": "Link",
			"options": "BOQ Item",
			"width": 120
		},
		{
			"fieldname": "posting_date",
			"label": _("Date"),
			"fieldtype": "Date",
			"width": 100
		},
		{
			"fieldname": "original_amount",
			"label": _("Original Amount"),
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"fieldname": "accepted_amount",
			"label": _("Accepted Amount"),
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"fieldname": "variance",
			"label": _("Variance"),
			"fieldtype": "Currency",
			"width": 100
		},
		{
			"fieldname": "variance_percent",
			"label": _("Variance %"),
			"fieldtype": "Percent",
			"width": 90
		},
		{
			"fieldname": "status",
			"label": _("Status"),
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "invoice",
			"label": _("Invoice"),
			"fieldtype": "Dynamic Link",
			"options": "invoice_doctype",
			"width": 140
		}
	]


def get_data(filters):
	"""
	Get report data.
	Property 8: For any type filter applied, results SHALL only include certificates matching the selected type.
	"""
	conditions = get_conditions(filters)
	
	data = frappe.db.sql("""
		SELECT 
			pc.name,
			pc.type,
			pc.project,
			pc.bill_no,
			pc.boq_item,
			pc.posting_date,
			CASE 
				WHEN pc.type = 'Sales' THEN pc.proforma_amount
				ELSE pc.pr_amount
			END as original_amount,
			pc.accepted_amount,
			pc.variance,
			pc.variance_percent,
			pc.status,
			CASE 
				WHEN pc.type = 'Sales' THEN pc.tax_invoice
				ELSE pc.purchase_invoice
			END as invoice,
			CASE 
				WHEN pc.type = 'Sales' THEN 'Sales Invoice'
				ELSE 'Purchase Invoice'
			END as invoice_doctype,
			pc.customer,
			pc.supplier
		FROM `tabPayment Certificate` pc
		WHERE pc.docstatus != 2
		{conditions}
		ORDER BY pc.posting_date DESC
	""".format(conditions=conditions), filters, as_dict=True)
	
	return data


def get_conditions(filters):
	"""Build SQL conditions from filters"""
	conditions = []
	
	if filters.get("from_date"):
		conditions.append("AND pc.posting_date >= %(from_date)s")
	
	if filters.get("to_date"):
		conditions.append("AND pc.posting_date <= %(to_date)s")
	
	if filters.get("project"):
		conditions.append("AND pc.project = %(project)s")
	
	if filters.get("type"):
		conditions.append("AND pc.type = %(type)s")
	
	if filters.get("bill_no"):
		conditions.append("AND pc.bill_no = %(bill_no)s")
	
	if filters.get("boq_item"):
		conditions.append("AND pc.boq_item = %(boq_item)s")
	
	if filters.get("status"):
		conditions.append("AND pc.status = %(status)s")
	
	return " ".join(conditions)


def get_chart_data(data, filters):
	"""
	Get chart data for the report.
	Requirements: 8.3 - Status Distribution, Monthly Trend, Variance Analysis
	"""
	if not data:
		return None
	
	# Status Distribution
	status_counts = {}
	for row in data:
		status = row.get("status", "Unknown")
		status_counts[status] = status_counts.get(status, 0) + 1
	
	return {
		"data": {
			"labels": list(status_counts.keys()),
			"datasets": [
				{
					"name": _("Count"),
					"values": list(status_counts.values())
				}
			]
		},
		"type": "pie",
		"colors": ["#5e64ff", "#36b37e", "#ff5630", "#ffab00", "#6c7680"]
	}
