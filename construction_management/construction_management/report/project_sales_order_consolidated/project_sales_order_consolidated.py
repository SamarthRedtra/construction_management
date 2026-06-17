# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import date_diff, flt


def execute(filters=None):
	if not filters:
		return [], [], None, []

	validate_filters(filters)

	columns = get_columns()
	data = get_data(filters)

	if not data:
		return columns, [], None, []

	chart_data = prepare_chart_data(data)
	return columns, data, None, chart_data


def validate_filters(filters):
	from_date, to_date = filters.get("from_date"), filters.get("to_date")

	if not from_date and to_date:
		frappe.throw(_("From and To Dates are required."))
	elif date_diff(to_date, from_date) < 0:
		frappe.throw(_("To Date cannot be before From Date."))


def get_conditions(filters):
	conditions = []
	values = {}

	if filters.get("from_date") and filters.get("to_date"):
		conditions.append("so.transaction_date between %(from_date)s and %(to_date)s")
		values["from_date"] = filters.get("from_date")
		values["to_date"] = filters.get("to_date")

	if filters.get("company"):
		conditions.append("so.company = %(company)s")
		values["company"] = filters.get("company")

	if filters.get("project"):
		conditions.append("so.project = %(project)s")
		values["project"] = filters.get("project")

	if filters.get("sales_order"):
		conditions.append("so.name in %(sales_order)s")
		values["sales_order"] = filters.get("sales_order")

	if filters.get("status"):
		conditions.append("so.status in %(status)s")
		values["status"] = filters.get("status")

	where_clause = " and ".join(conditions)
	if where_clause:
		where_clause = " and " + where_clause

	return where_clause, values


def get_data(filters):
	where_clause, values = get_conditions(filters)

	rows = frappe.db.sql(
		f"""
		SELECT
			so.transaction_date AS date,
			so.name AS sales_order,
			so.project,
			so.bill_no,
			so.status,
			so.customer,
			so.company,
			so.base_grand_total AS so_amount
		FROM `tabSales Order` so
		WHERE so.docstatus = 1
			AND so.status NOT IN ('Stopped', 'On Hold')
			{where_clause}
		ORDER BY so.transaction_date ASC, so.name ASC
		""",
		values,
		as_dict=True,
	)

	if not rows:
		return []

	invoice_metrics = get_invoice_metrics([row.sales_order for row in rows])

	for row in rows:
		metrics = invoice_metrics.get(row.sales_order) or {}
		row["tax_invoiced_amount"] = flt(metrics.get("tax_invoiced_amount"))
		row["received_amount"] = flt(metrics.get("received_amount"))
		row["pending_tax_amount"] = flt(
			max(0, flt(row.so_amount) - flt(row.tax_invoiced_amount)), 2
		)

	return rows


def get_invoice_metrics(so_names):
	if not so_names:
		return {}

	has_proforma = frappe.db.has_column("Sales Invoice", "custom_is_proforma")
	has_so_link = frappe.db.has_column("Sales Invoice", "custom_sales_order")

	proforma_sql = "AND IFNULL(si.custom_is_proforma, 0) = 0" if has_proforma else ""
	so_field_sql = "IFNULL(si.custom_sales_order, '')" if has_so_link else "''"

	rows = frappe.db.sql(
		f"""
		SELECT
			sales_order,
			SUM(base_grand_total) AS tax_invoiced_amount,
			SUM(
				base_grand_total - (
					IFNULL(outstanding_amount, 0) / IFNULL(NULLIF(conversion_rate, 0), 1)
				)
			) AS received_amount
		FROM (
			SELECT DISTINCT
				si.name,
				CASE
					WHEN {so_field_sql} != '' THEN {so_field_sql}
					ELSE sii.sales_order
				END AS sales_order,
				si.base_grand_total,
				si.outstanding_amount,
				si.conversion_rate
			FROM `tabSales Invoice` si
			LEFT JOIN `tabSales Invoice Item` sii
				ON sii.parent = si.name
				AND IFNULL(sii.sales_order, '') != ''
			WHERE si.docstatus = 1
				AND IFNULL(si.is_return, 0) = 0
				{proforma_sql}
				AND (
					{so_field_sql} IN %(so_names)s
					OR sii.sales_order IN %(so_names)s
				)
		) invoices
		WHERE sales_order IN %(so_names)s
		GROUP BY sales_order
		""",
		{"so_names": so_names},
		as_dict=True,
	)

	return {row.sales_order: row for row in rows}


def prepare_chart_data(data):
	pending = sum(flt(row.pending_tax_amount) for row in data)
	invoiced = sum(flt(row.tax_invoiced_amount) for row in data)

	return {
		"data": {
			"labels": [_("Pending to Create Tax"), _("Tax Invoiced")],
			"datasets": [{"values": [pending, invoiced]}],
		},
		"type": "donut",
		"height": 300,
	}


def get_columns():
	return [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 90},
		{
			"label": _("Sales Order"),
			"fieldname": "sales_order",
			"fieldtype": "Link",
			"options": "Sales Order",
			"width": 160,
		},
		{
			"label": _("Project"),
			"fieldname": "project",
			"fieldtype": "Link",
			"options": "Project",
			"width": 140,
		},
		{
			"label": _("Bill No"),
			"fieldname": "bill_no",
			"fieldtype": "Link",
			"options": "BOQ Bill",
			"width": 100,
		},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
		{
			"label": _("Customer"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 130,
		},
		{
			"label": _("Sales Order Amount"),
			"fieldname": "so_amount",
			"fieldtype": "Currency",
			"width": 140,
			"options": "Company:company:default_currency",
		},
		{
			"label": _("Tax Invoiced Amount"),
			"fieldname": "tax_invoiced_amount",
			"fieldtype": "Currency",
			"width": 140,
			"options": "Company:company:default_currency",
		},
		{
			"label": _("Received Amount"),
			"fieldname": "received_amount",
			"fieldtype": "Currency",
			"width": 130,
			"options": "Company:company:default_currency",
		},
		{
			"label": _("Pending to Create Tax"),
			"fieldname": "pending_tax_amount",
			"fieldtype": "Currency",
			"width": 150,
			"options": "Company:company:default_currency",
		},
		{
			"label": _("Company"),
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 100,
		},
	]
