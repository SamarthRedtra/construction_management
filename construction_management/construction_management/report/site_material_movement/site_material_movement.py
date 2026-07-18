# Copyright (c) 2026, Construction Management
# License: MIT

"""Site Material Movement — PR / Transfer / Issue with site balance + consumption flag."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate

TX_PURCHASE_RECEIPT = "Purchase Receipt"
TX_MATERIAL_TRANSFER = "Material Transfer"
TX_MATERIAL_ISSUE = "Material Issue (Consumption)"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is required"))
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are required"))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date"))


def get_columns():
	return [
		{
			"fieldname": "item_code",
			"label": _("Item Code"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 160,
		},
		{
			"fieldname": "item_name",
			"label": _("Item Name"),
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"fieldname": "posting_date",
			"label": _("Date"),
			"fieldtype": "Date",
			"width": 100,
		},
		{
			"fieldname": "voucher_no",
			"label": _("Voucher No."),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 150,
		},
		{
			"fieldname": "voucher_type",
			"label": _("Voucher Type"),
			"fieldtype": "Data",
			"width": 120,
			"hidden": 1,
		},
		{
			"fieldname": "transaction_type",
			"label": _("Transaction Type"),
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"fieldname": "received_warehouse",
			"label": _("Received Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 170,
		},
		{
			"fieldname": "transfer_to_site",
			"label": _("Transfer To (Site)"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 170,
		},
		{
			"fieldname": "qty_in",
			"label": _("Qty In"),
			"fieldtype": "Float",
			"width": 90,
			"precision": 3,
		},
		{
			"fieldname": "qty_out",
			"label": _("Qty Out"),
			"fieldtype": "Float",
			"width": 90,
			"precision": 3,
		},
		{
			"fieldname": "qty_consumed",
			"label": _("Qty Consumed"),
			"fieldtype": "Float",
			"width": 110,
			"precision": 3,
		},
		{
			"fieldname": "balance_at_site",
			"label": _("Balance at Site"),
			"fieldtype": "Float",
			"width": 120,
			"precision": 3,
		},
		{
			"fieldname": "consumption_posted",
			"label": _("Consumption Entry Posted?"),
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 120,
		},
	]


def get_data(filters):
	rows = []
	tx_filter = (filters.get("transaction_type") or "").strip()

	if not tx_filter or tx_filter == TX_PURCHASE_RECEIPT:
		rows.extend(_get_purchase_receipt_rows(filters))
	if not tx_filter or tx_filter == TX_MATERIAL_TRANSFER:
		rows.extend(_get_material_transfer_rows(filters))
	if not tx_filter or tx_filter == TX_MATERIAL_ISSUE:
		rows.extend(_get_material_issue_rows(filters))

	rows.sort(
		key=lambda r: (
			getdate(r["posting_date"]),
			r.get("voucher_no") or "",
			r.get("item_code") or "",
			r.get("idx") or 0,
		)
	)

	_apply_site_balances(rows, filters)

	consumption_filter = (filters.get("consumption_status") or "").strip()
	if consumption_filter:
		rows = [r for r in rows if r.get("consumption_posted") == consumption_filter]

	return rows


def _get_purchase_receipt_rows(filters):
	conditions = ["pr.docstatus = 1", "pr.company = %(company)s"]
	values = {
		"company": filters.company,
		"from_date": filters.from_date,
		"to_date": filters.to_date,
	}
	conditions.append("pr.posting_date BETWEEN %(from_date)s AND %(to_date)s")

	if filters.get("project"):
		conditions.append("(pr.project = %(project)s OR pri.project = %(project)s)")
		values["project"] = filters.project
	if filters.get("item_code"):
		conditions.append("pri.item_code = %(item_code)s")
		values["item_code"] = filters.item_code
	if filters.get("site_warehouse"):
		conditions.append("pri.warehouse = %(site_warehouse)s")
		values["site_warehouse"] = filters.site_warehouse

	sql = f"""
		SELECT
			pri.item_code,
			pri.item_name,
			pr.posting_date,
			pr.name AS voucher_no,
			pri.warehouse AS received_warehouse,
			NULL AS transfer_to_site,
			pri.qty AS qty_in,
			0 AS qty_out,
			0 AS qty_consumed,
			IFNULL(pri.project, pr.project) AS project,
			pri.warehouse AS site_warehouse,
			pri.idx,
			'Purchase Receipt' AS voucher_type
		FROM `tabPurchase Receipt` pr
		INNER JOIN `tabPurchase Receipt Item` pri ON pri.parent = pr.name
		WHERE {" AND ".join(conditions)}
		ORDER BY pr.posting_date, pr.name, pri.idx
	"""
	result = []
	for row in frappe.db.sql(sql, values, as_dict=True):
		result.append(
			{
				**row,
				"transaction_type": TX_PURCHASE_RECEIPT,
				"qty_in": flt(row.qty_in),
				"qty_out": None,
				"qty_consumed": None,
				"consumption_posted": "N/A",
				"affects_site_balance": 1 if row.site_warehouse else 0,
				"balance_delta": flt(row.qty_in),
			}
		)
	return result


def _has_issued_qty_column():
	return frappe.db.has_column("Stock Entry Detail", "custom_material_issued_qty")


def _get_material_transfer_rows(filters):
	conditions = [
		"se.docstatus = 1",
		"se.company = %(company)s",
		"se.stock_entry_type = 'Material Transfer'",
		"se.posting_date BETWEEN %(from_date)s AND %(to_date)s",
		"sed.t_warehouse IS NOT NULL",
	]
	values = {
		"company": filters.company,
		"from_date": filters.from_date,
		"to_date": filters.to_date,
	}

	if filters.get("project"):
		conditions.append("(se.project = %(project)s OR sed.project = %(project)s)")
		values["project"] = filters.project
	if filters.get("item_code"):
		conditions.append("sed.item_code = %(item_code)s")
		values["item_code"] = filters.item_code
	if filters.get("site_warehouse"):
		conditions.append("sed.t_warehouse = %(site_warehouse)s")
		values["site_warehouse"] = filters.site_warehouse

	issued_expr = (
		"IFNULL(sed.custom_material_issued_qty, 0)"
		if _has_issued_qty_column()
		else "0"
	)

	sql = f"""
		SELECT
			sed.item_code,
			sed.item_name,
			se.posting_date,
			se.name AS voucher_no,
			sed.s_warehouse AS received_warehouse,
			sed.t_warehouse AS transfer_to_site,
			sed.qty AS qty_in,
			sed.qty AS qty_out,
			0 AS qty_consumed,
			IFNULL(sed.project, se.project) AS project,
			sed.t_warehouse AS site_warehouse,
			sed.idx,
			{issued_expr} AS issued_qty,
			sed.qty AS transfer_qty,
			'Stock Entry' AS voucher_type
		FROM `tabStock Entry` se
		INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
		WHERE {" AND ".join(conditions)}
		ORDER BY se.posting_date, se.name, sed.idx
	"""
	result = []
	for row in frappe.db.sql(sql, values, as_dict=True):
		issued = flt(row.issued_qty)
		transfer_qty = flt(row.transfer_qty)
		posted = "Yes" if transfer_qty and issued >= transfer_qty - 0.0001 else "No"
		result.append(
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"posting_date": row.posting_date,
				"voucher_no": row.voucher_no,
				"voucher_type": "Stock Entry",
				"transaction_type": TX_MATERIAL_TRANSFER,
				"received_warehouse": row.received_warehouse,
				"transfer_to_site": row.transfer_to_site,
				"qty_in": flt(row.qty_in),
				"qty_out": flt(row.qty_out),
				"qty_consumed": None,
				"project": row.project,
				"site_warehouse": row.site_warehouse,
				"idx": row.idx,
				"consumption_posted": posted,
				"affects_site_balance": 1,
				"balance_delta": flt(row.qty_in),
			}
		)
	return result


def _get_material_issue_rows(filters):
	conditions = [
		"se.docstatus = 1",
		"se.company = %(company)s",
		"se.stock_entry_type = 'Material Issue'",
		"se.posting_date BETWEEN %(from_date)s AND %(to_date)s",
		"sed.s_warehouse IS NOT NULL",
	]
	values = {
		"company": filters.company,
		"from_date": filters.from_date,
		"to_date": filters.to_date,
	}

	if filters.get("project"):
		conditions.append("(se.project = %(project)s OR sed.project = %(project)s)")
		values["project"] = filters.project
	if filters.get("item_code"):
		conditions.append("sed.item_code = %(item_code)s")
		values["item_code"] = filters.item_code
	if filters.get("site_warehouse"):
		conditions.append("sed.s_warehouse = %(site_warehouse)s")
		values["site_warehouse"] = filters.site_warehouse

	sql = f"""
		SELECT
			sed.item_code,
			sed.item_name,
			se.posting_date,
			se.name AS voucher_no,
			sed.s_warehouse AS received_warehouse,
			NULL AS transfer_to_site,
			0 AS qty_in,
			sed.qty AS qty_out,
			sed.qty AS qty_consumed,
			IFNULL(sed.project, se.project) AS project,
			sed.s_warehouse AS site_warehouse,
			sed.idx,
			'Stock Entry' AS voucher_type
		FROM `tabStock Entry` se
		INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
		WHERE {" AND ".join(conditions)}
		ORDER BY se.posting_date, se.name, sed.idx
	"""
	result = []
	for row in frappe.db.sql(sql, values, as_dict=True):
		result.append(
			{
				**row,
				"transaction_type": TX_MATERIAL_ISSUE,
				"qty_in": None,
				"qty_out": flt(row.qty_out),
				"qty_consumed": flt(row.qty_consumed),
				"consumption_posted": "Yes",
				"affects_site_balance": 1,
				"balance_delta": -flt(row.qty_out),
			}
		)
	return result


def _apply_site_balances(rows, filters):
	"""Running balance per item + site warehouse, starting from opening before from_date."""
	keys = {
		(r["item_code"], r["site_warehouse"])
		for r in rows
		if r.get("item_code") and r.get("site_warehouse") and r.get("affects_site_balance")
	}
	opening = {}
	for item_code, warehouse in keys:
		opening[(item_code, warehouse)] = _get_opening_qty(
			item_code, warehouse, filters.from_date
		)

	running = dict(opening)
	for row in rows:
		key = (row.get("item_code"), row.get("site_warehouse"))
		if row.get("affects_site_balance") and key[0] and key[1]:
			running[key] = flt(running.get(key, 0)) + flt(row.get("balance_delta"))
			row["balance_at_site"] = flt(running[key], 3)
		else:
			row["balance_at_site"] = None

		# Clean helper fields from report output
		row.pop("affects_site_balance", None)
		row.pop("balance_delta", None)
		row.pop("site_warehouse", None)
		row.pop("idx", None)


def _get_opening_qty(item_code, warehouse, from_date) -> float:
	"""Stock as of day before from_date (last SLE qty_after_transaction)."""
	as_on = add_days(getdate(from_date), -1)
	qty = frappe.db.sql(
		"""
		SELECT qty_after_transaction
		FROM `tabStock Ledger Entry`
		WHERE item_code = %s
		  AND warehouse = %s
		  AND posting_date <= %s
		  AND is_cancelled = 0
		ORDER BY posting_date DESC, posting_time DESC, creation DESC
		LIMIT 1
		""",
		(item_code, warehouse, as_on),
	)
	if qty:
		return flt(qty[0][0])
	return 0.0
