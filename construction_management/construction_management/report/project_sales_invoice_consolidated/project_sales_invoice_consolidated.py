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

	if not from_date or not to_date:
		frappe.throw(_("From and To Dates are required."))
	elif date_diff(to_date, from_date) < 0:
		frappe.throw(_("To Date cannot be before From Date."))


def get_conditions(filters):
	conditions = []
	values = {}

	if filters.get("from_date") and filters.get("to_date"):
		conditions.append("si.posting_date between %(from_date)s and %(to_date)s")
		values["from_date"] = filters.get("from_date")
		values["to_date"] = filters.get("to_date")

	if filters.get("company"):
		conditions.append("si.company = %(company)s")
		values["company"] = filters.get("company")

	if filters.get("project"):
		conditions.append("si.project = %(project)s")
		values["project"] = filters.get("project")

	if filters.get("sales_invoice"):
		conditions.append("si.name in %(sales_invoice)s")
		values["sales_invoice"] = filters.get("sales_invoice")

	if filters.get("customer"):
		conditions.append("si.customer = %(customer)s")
		values["customer"] = filters.get("customer")

	if filters.get("status"):
		conditions.append("si.status in %(status)s")
		values["status"] = filters.get("status")

	where_clause = " and ".join(conditions)
	if where_clause:
		where_clause = " and " + where_clause

	return where_clause, values


def get_data(filters):
	where_clause, values = get_conditions(filters)
	has_proforma = frappe.db.has_column("Sales Invoice", "custom_is_proforma")
	proforma_sql = "AND IFNULL(si.custom_is_proforma, 0) = 0" if has_proforma else ""

	has_so_link = frappe.db.has_column("Sales Invoice", "custom_sales_order")
	so_select = (
		"IFNULL(NULLIF(si.custom_sales_order, ''), ("
		"SELECT sii.sales_order FROM `tabSales Invoice Item` sii "
		"WHERE sii.parent = si.name AND IFNULL(sii.sales_order, '') != '' "
		"ORDER BY sii.idx LIMIT 1"
		")) AS sales_order"
		if has_so_link
		else (
			"(SELECT sii.sales_order FROM `tabSales Invoice Item` sii "
			"WHERE sii.parent = si.name AND IFNULL(sii.sales_order, '') != '' "
			"ORDER BY sii.idx LIMIT 1) AS sales_order"
		)
	)

	rows = frappe.db.sql(
		f"""
		SELECT
			si.posting_date AS date,
			si.name AS sales_invoice,
			si.project,
			si.status,
			si.customer,
			si.company,
			si.base_grand_total AS invoice_amount,
			(
				si.base_grand_total - (
					IFNULL(si.outstanding_amount, 0) / IFNULL(NULLIF(si.conversion_rate, 0), 1)
				)
			) AS received_amount,
			(
				IFNULL(si.outstanding_amount, 0) / IFNULL(NULLIF(si.conversion_rate, 0), 1)
			) AS outstanding_amount,
			{so_select}
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
			AND IFNULL(si.is_return, 0) = 0
			AND IFNULL(si.is_opening, 'No') = 'No'
			{proforma_sql}
			{where_clause}
		ORDER BY si.posting_date ASC, si.name ASC
		""",
		values,
		as_dict=True,
	)

	for row in rows:
		row["received_amount"] = flt(row.get("received_amount"), 2)
		row["outstanding_amount"] = flt(max(0, flt(row.get("outstanding_amount"))), 2)
		row["invoice_amount"] = flt(row.get("invoice_amount"), 2)

	return rows


def prepare_chart_data(data):
	outstanding = sum(flt(row.outstanding_amount) for row in data)
	received = sum(flt(row.received_amount) for row in data)

	return {
		"data": {
			"labels": [_("Outstanding"), _("Received")],
			"datasets": [{"values": [outstanding, received]}],
		},
		"type": "donut",
		"height": 300,
	}


def get_columns():
	return [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 90},
		{
			"label": _("Sales Invoice"),
			"fieldname": "sales_invoice",
			"fieldtype": "Link",
			"options": "Sales Invoice",
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
			"label": _("Sales Order"),
			"fieldname": "sales_order",
			"fieldtype": "Link",
			"options": "Sales Order",
			"width": 150,
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
			"label": _("Invoice Amount"),
			"fieldname": "invoice_amount",
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
			"label": _("Outstanding Amount"),
			"fieldname": "outstanding_amount",
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
