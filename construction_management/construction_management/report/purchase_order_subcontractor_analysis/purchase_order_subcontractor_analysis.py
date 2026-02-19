# Copyright (c) 2026, Construction Management
# License: MIT
# Purchase Order Subcontractor Analysis Report
# Based on ERPNext's Purchase Order Analysis with additional advance/retention columns

import copy

import frappe
from frappe import _
from frappe.query_builder.functions import IfNull, Sum
from frappe.utils import date_diff, flt, getdate


def execute(filters=None):
	if not filters:
		return [], []

	validate_filters(filters)

	columns = get_columns(filters)
	data = get_data(filters)

	if not data:
		return columns, [], None, []

	update_received_amount(data)
	update_advance_and_retention(data)

	data, chart_data = prepare_data(data, filters)

	return columns, data, None, chart_data


def validate_filters(filters):
	from_date, to_date = filters.get("from_date"), filters.get("to_date")

	if not from_date and to_date:
		frappe.throw(_("From and To Dates are required."))
	elif date_diff(to_date, from_date) < 0:
		frappe.throw(_("To Date cannot be before From Date."))


def get_data(filters):
	po = frappe.qb.DocType("Purchase Order")
	po_item = frappe.qb.DocType("Purchase Order Item")
	pi_item = frappe.qb.DocType("Purchase Invoice Item")

	query = (
		frappe.qb.from_(po)
		.inner_join(po_item)
		.on(po_item.parent == po.name)
		.left_join(pi_item)
		.on((pi_item.po_detail == po_item.name) & (pi_item.docstatus == 1))
		.select(
			po.transaction_date.as_("date"),
			po_item.schedule_date.as_("required_date"),
			po_item.project,
			po.name.as_("purchase_order"),
			po.status,
			po.supplier,
			po_item.item_code,
			po_item.qty,
			po_item.received_qty,
			(po_item.qty - po_item.received_qty).as_("pending_qty"),
			Sum(IfNull(pi_item.qty, 0)).as_("billed_qty"),
			po_item.base_amount.as_("amount"),
			(po_item.billed_amt * IfNull(po.conversion_rate, 1)).as_("billed_amount"),
			(po_item.base_amount - (po_item.billed_amt * IfNull(po.conversion_rate, 1))).as_(
				"pending_amount"
			),
			po.set_warehouse.as_("warehouse"),
			po.company,
			po.grand_total.as_("po_grand_total"),
			po.custom_retention_.as_("retention_pct"),
			po.custom_advance_.as_("advance_pct"),
			po_item.name,
		)
		.where(
			(po_item.parent == po.name)
			& (po.status.notin(("Stopped", "On Hold")))
			& (po.docstatus == 1)
			& (po.custom_suppliersubcontractor == "Subcontractor")
		)
		.groupby(po_item.name)
		.orderby(po.transaction_date)
	)

	if filters.get("company"):
		query = query.where(po.company == filters.get("company"))

	if filters.get("name"):
		query = query.where(po.name.isin(filters.get("name")))

	if filters.get("from_date") and filters.get("to_date"):
		query = query.where(po.transaction_date.between(filters.get("from_date"), filters.get("to_date")))

	if filters.get("status"):
		query = query.where(po.status.isin(filters.get("status")))

	if filters.get("project"):
		query = query.where(po_item.project == filters.get("project"))

	if filters.get("supplier"):
		query = query.where(po.supplier == filters.get("supplier"))

	data = query.run(as_dict=True)

	return data


def update_received_amount(data):
	pr = frappe.qb.DocType("Purchase Receipt")
	pr_item = frappe.qb.DocType("Purchase Receipt Item")

	po_items = [row.name for row in data]

	if not po_items:
		return

	query = (
		frappe.qb.from_(pr)
		.inner_join(pr_item)
		.on(pr_item.parent == pr.name)
		.select(
			pr_item.purchase_order_item,
			Sum(pr_item.base_amount).as_("received_qty_amount"),
		)
		.where((pr.docstatus == 1) & (pr_item.purchase_order_item.isin(po_items)))
		.groupby(pr_item.purchase_order_item)
	)

	pr_data = query.run()

	if not pr_data:
		pr_data_dict = frappe._dict()
	else:
		pr_data_dict = frappe._dict(pr_data)

	for row in data:
		row.received_qty_amount = flt(pr_data_dict.get(row.name))


def update_advance_and_retention(data):
	"""Add advance and retention data per Purchase Order"""
	# Get unique PO names
	po_names = list(set(row.purchase_order for row in data))

	if not po_names:
		return

	# Get advance payments per PO
	advance_data = {}
	for po_name in po_names:
		advances = frappe.db.sql("""
			SELECT COALESCE(SUM(amount), 0) as total_advance,
			       COALESCE(SUM(allocated_amount), 0) as advance_allocated
			FROM `tabPurchase Advance Payment`
			WHERE purchase_order = %s AND docstatus = 1
		""", po_name, as_dict=True)

		if advances:
			advance_data[po_name] = advances[0]

	# Get retention deducted per PO (from invoices)
	retention_data = {}
	for po_name in po_names:
		ret = frappe.db.sql("""
			SELECT COALESCE(SUM(ABS(pii.amount)), 0) as retention_deducted
			FROM `tabPurchase Invoice Item` pii
			INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
			WHERE pii.purchase_order = %s
			AND pii.item_code = 'RETENTION-DEDUCTION'
			AND pi.docstatus = 1
		""", po_name, as_dict=True)

		if ret:
			retention_data[po_name] = ret[0]

	# Get advance deducted per PO (from invoices)
	advance_deducted_data = {}
	for po_name in po_names:
		adv = frappe.db.sql("""
			SELECT COALESCE(SUM(ABS(pii.amount)), 0) as advance_deducted
			FROM `tabPurchase Invoice Item` pii
			INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
			WHERE pii.purchase_order = %s
			AND pii.item_code = 'ADVANCE-DEDUCTION'
			AND pi.docstatus = 1
		""", po_name, as_dict=True)

		if adv:
			advance_deducted_data[po_name] = adv[0]

	# Apply to data rows
	for row in data:
		po_name = row.purchase_order
		po_total = flt(row.po_grand_total)
		ret_pct = flt(row.retention_pct)
		adv_pct = flt(row.advance_pct)

		# Advance
		adv_info = advance_data.get(po_name, {})
		row["advance_paid"] = flt(adv_info.get("total_advance", 0))
		adv_ded = advance_deducted_data.get(po_name, {})
		row["advance_deducted"] = flt(adv_ded.get("advance_deducted", 0))
		row["advance_balance"] = row["advance_paid"] - row["advance_deducted"]

		# Retention
		row["expected_retention"] = flt(po_total * ret_pct / 100, 2) if ret_pct else 0
		ret_info = retention_data.get(po_name, {})
		row["retention_deducted"] = flt(ret_info.get("retention_deducted", 0))
		row["retention_balance"] = row["expected_retention"] - row["retention_deducted"]


def prepare_data(data, filters):
	completed, pending = 0, 0
	pending_field = "pending_amount"
	completed_field = "billed_amount"

	if filters.get("group_by_po"):
		purchase_order_map = {}

	for row in data:
		# sum data for chart
		completed += flt(row.get(completed_field, 0))
		pending += flt(row.get(pending_field, 0))

		# prepare data for report view
		row["qty_to_bill"] = flt(row["qty"]) - flt(row["billed_qty"])

		if filters.get("group_by_po"):
			po_name = row["purchase_order"]

			if po_name not in purchase_order_map:
				row_copy = copy.deepcopy(row)
				purchase_order_map[po_name] = row_copy
			else:
				po_row = purchase_order_map[po_name]
				po_row["required_date"] = min(getdate(po_row["required_date"]), getdate(row["required_date"]))

				# sum numeric columns
				sum_fields = [
					"qty", "received_qty", "pending_qty", "billed_qty", "qty_to_bill",
					"amount", "received_qty_amount", "billed_amount", "pending_amount",
				]
				for field in sum_fields:
					po_row[field] = flt(row.get(field, 0)) + flt(po_row.get(field, 0))

				# advance/retention are PO-level, don't sum - keep the first values

	chart_data = prepare_chart_data(pending, completed)

	if filters.get("group_by_po"):
		data = list(purchase_order_map.values())
		return data, chart_data

	return data, chart_data


def prepare_chart_data(pending, completed):
	labels = [_("Amount to Bill"), _("Billed Amount")]

	return {
		"data": {"labels": labels, "datasets": [{"values": [pending, completed]}]},
		"type": "donut",
		"height": 300,
	}


def get_columns(filters):
	columns = [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 90},
		{"label": _("Required By"), "fieldname": "required_date", "fieldtype": "Date", "width": 90},
		{
			"label": _("Purchase Order"),
			"fieldname": "purchase_order",
			"fieldtype": "Link",
			"options": "Purchase Order",
			"width": 160,
		},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
		{
			"label": _("Supplier"),
			"fieldname": "supplier",
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 130,
		},
		{
			"label": _("Project"),
			"fieldname": "project",
			"fieldtype": "Link",
			"options": "Project",
			"width": 130,
		},
	]

	if not filters.get("group_by_po"):
		columns.append(
			{
				"label": _("Item Code"),
				"fieldname": "item_code",
				"fieldtype": "Link",
				"options": "Item",
				"width": 100,
			}
		)

	columns.extend([
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 110,
			"options": "Company:company:default_currency"},
		{"label": _("Billed Amount"), "fieldname": "billed_amount", "fieldtype": "Currency", "width": 110,
			"options": "Company:company:default_currency"},
		{"label": _("Pending Amount"), "fieldname": "pending_amount", "fieldtype": "Currency", "width": 110,
			"options": "Company:company:default_currency"},
		# Retention columns
		{"label": _("Retention %"), "fieldname": "retention_pct", "fieldtype": "Percent", "width": 80},
		{"label": _("Expected Retention"), "fieldname": "expected_retention", "fieldtype": "Currency", "width": 120,
			"options": "Company:company:default_currency"},
		{"label": _("Retention Deducted"), "fieldname": "retention_deducted", "fieldtype": "Currency", "width": 120,
			"options": "Company:company:default_currency"},
		{"label": _("Retention Balance"), "fieldname": "retention_balance", "fieldtype": "Currency", "width": 120,
			"options": "Company:company:default_currency"},
		# Advance columns
		{"label": _("Advance %"), "fieldname": "advance_pct", "fieldtype": "Percent", "width": 80},
		{"label": _("Advance Paid"), "fieldname": "advance_paid", "fieldtype": "Currency", "width": 110,
			"options": "Company:company:default_currency"},
		{"label": _("Advance Deducted"), "fieldname": "advance_deducted", "fieldtype": "Currency", "width": 120,
			"options": "Company:company:default_currency"},
		{"label": _("Advance Balance"), "fieldname": "advance_balance", "fieldtype": "Currency", "width": 110,
			"options": "Company:company:default_currency"},
		# Standard columns
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 80},
		{"label": _("Received Qty"), "fieldname": "received_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Received Amount"), "fieldname": "received_qty_amount", "fieldtype": "Currency", "width": 120,
			"options": "Company:company:default_currency"},
		{
			"label": _("Company"),
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 100,
		},
	])

	return columns
