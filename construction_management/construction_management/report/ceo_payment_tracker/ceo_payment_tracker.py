# Copyright (c) 2026, Construction Management
# License: MIT

"""
CEO Payment Tracker Report

Rows are driven by accounting documents (not Payment Certificate):
  Sales:    Proforma / Sales Order → (optional PC omitted) → Tax Sales Invoice → Payment Entry
  Purchase: Purchase Receipt / PO context → Purchase Invoice → Payment Entry

Column layout matches `Format for redra.xlsx` (Sr No. through Remarks).
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart_data(data)
	summary = get_report_summary(data)
	return columns, data, None, chart, summary


def get_columns():
	return [
		{"fieldname": "sr_no", "label": _("Sr No."), "fieldtype": "Int", "width": 60},
		{"fieldname": "invoice_no", "label": _("Invoice No."), "fieldtype": "Data", "width": 150},
		{"fieldname": "client_name", "label": _("Client Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "pm_engg", "label": _("PM / Engg"), "fieldtype": "Data", "width": 150},
		{"fieldname": "workdone", "label": _("Workdone"), "fieldtype": "Data", "width": 200},
		{"fieldname": "pi_amount", "label": _("PI Amount"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "pi_date", "label": _("PI Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "pc_date", "label": _("PC Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "pc_amt", "label": _("PC Amt"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "ti_date", "label": _("TI Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "ti_amt", "label": _("TI Amt"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "due_date", "label": _("Due Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "payment_mode", "label": _("Payment Mode"), "fieldtype": "Data", "width": 140},
		{"fieldname": "payment_date", "label": _("Payment Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "cheque_no", "label": _("Cheque/Reference No"), "fieldtype": "Data", "width": 140},
		{"fieldname": "remarks", "label": _("Remarks"), "fieldtype": "Data", "width": 200},
	]


def get_data(filters):
	cheque_sets = _invoices_matching_cheque_filter(filters)
	if cheque_sets is not None and not cheque_sets["Sales Invoice"] and not cheque_sets["Purchase Invoice"]:
		return []

	rows = []
	type_filter = (filters.get("type") or "").strip()

	if not type_filter or type_filter == "Sales":
		allowed = None if cheque_sets is None else cheque_sets["Sales Invoice"]
		rows.extend(_get_sales_invoice_rows(filters, allowed_names=allowed))
	if not type_filter or type_filter == "Purchase":
		allowed = None if cheque_sets is None else cheque_sets["Purchase Invoice"]
		rows.extend(_get_purchase_invoice_rows(filters, allowed_names=allowed))

	rows.sort(key=lambda r: (r.get("ti_date") or r.get("pi_date") or ""), reverse=True)

	pay_map = _build_payment_map(rows)
	for row in rows:
		key = (row["_ref_dt"], row["_ref_dn"])
		info = pay_map.get(key) or {}
		row["payment_mode"] = info.get("mode_of_payment") or ""
		row["payment_date"] = info.get("payment_date")
		row["cheque_no"] = info.get("reference_no") or ""
		row.pop("_ref_dt", None)
		row.pop("_ref_dn", None)

	for idx, row in enumerate(rows, start=1):
		row["sr_no"] = idx

	return rows


def _invoices_matching_cheque_filter(filters):
	"""If cheque_no filter is set, return sets of invoice names per doctype; else None."""
	cheque = (filters.get("cheque_no") or "").strip()
	if not cheque:
		return None

	values = {"pattern": f"%{cheque}%"}
	company_clause = ""
	if filters.get("company"):
		company_clause = "AND pe.company = %(company)s"
		values["company"] = filters["company"]

	rows = frappe.db.sql(
		"""
		SELECT DISTINCT per.reference_doctype, per.reference_name
		FROM `tabPayment Entry Reference` per
		INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
		WHERE pe.docstatus = 1
		  {company_clause}
		  AND IFNULL(pe.reference_no, '') != ''
		  AND pe.reference_no LIKE %(pattern)s
		  AND per.reference_doctype IN ('Sales Invoice', 'Purchase Invoice')
		""".format(company_clause=company_clause),
		values,
		as_dict=True,
	)
	si, pi = set(), set()
	for r in rows:
		if r.reference_doctype == "Sales Invoice":
			si.add(r.reference_name)
		elif r.reference_doctype == "Purchase Invoice":
			pi.add(r.reference_name)
	return {"Sales Invoice": si, "Purchase Invoice": pi}


def _get_sales_invoice_rows(filters, allowed_names=None):
	has_proforma_flag = frappe.db.has_column("Sales Invoice", "custom_is_proforma")
	has_pf_link = frappe.db.has_column("Sales Invoice", "custom_proforma_invoice")
	has_so_link = frappe.db.has_column("Sales Invoice", "custom_sales_order")

	proforma_sql = "AND IFNULL(si.custom_is_proforma, 0) = 0" if has_proforma_flag else ""
	extra_fields = ""
	if has_pf_link:
		extra_fields += ", IFNULL(si.custom_proforma_invoice, '') AS custom_proforma_invoice"
	else:
		extra_fields += ", '' AS custom_proforma_invoice"
	if has_so_link:
		extra_fields += ", IFNULL(si.custom_sales_order, '') AS custom_sales_order"
	else:
		extra_fields += ", '' AS custom_sales_order"

	conditions, values = _build_si_conditions(filters)
	name_clause = ""
	if allowed_names is not None:
		if not allowed_names:
			return []
		esc = ", ".join(frappe.db.escape(n) for n in allowed_names)
		name_clause = f"AND si.name IN ({esc})"

	si_list = frappe.db.sql(
		"""
		SELECT
			si.name,
			si.posting_date AS ti_date,
			si.grand_total AS ti_amt,
			si.due_date,
			si.customer,
			si.project,
			si.company,
			si.remarks
			{extra_fields}
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		  {proforma_sql}
		  AND IFNULL(si.project, '') != ''
		  {name_clause}
		{conditions}
		ORDER BY si.posting_date DESC, si.name DESC
		""".format(
			extra_fields=extra_fields,
			proforma_sql=proforma_sql,
			name_clause=name_clause,
			conditions=conditions,
		),
		values,
		as_dict=True,
	)
	if not si_list:
		return []

	project_names = {r.project for r in si_list if r.project}
	project_map = _project_engineer_map(project_names)

	proforma_names = {r.custom_proforma_invoice for r in si_list if r.custom_proforma_invoice}
	so_names = {r.custom_sales_order for r in si_list if r.custom_sales_order}

	pfi_map = {}
	if proforma_names:
		for d in frappe.get_all(
			"Sales Invoice",
			filters={"name": ("in", list(proforma_names))},
			fields=["name", "posting_date", "grand_total"],
		):
			pfi_map[d.name] = d

	so_map = {}
	if so_names:
		for d in frappe.get_all(
			"Sales Order",
			filters={"name": ("in", list(so_names))},
			fields=["name", "transaction_date", "grand_total"],
		):
			so_map[d.name] = d

	customer_ids = list({r.customer for r in si_list if r.customer})
	cust_map = {}
	if customer_ids:
		for c in frappe.get_all(
			"Customer", filters={"name": ("in", customer_ids)}, fields=["name", "customer_name"]
		):
			cust_map[c.name] = c.customer_name

	out = []
	for si in si_list:
		pi_amount = None
		pi_date = None
		if si.custom_proforma_invoice and si.custom_proforma_invoice in pfi_map:
			pf = pfi_map[si.custom_proforma_invoice]
			pi_amount = flt(pf.grand_total)
			pi_date = pf.posting_date
		elif si.custom_sales_order and si.custom_sales_order in so_map:
			so = so_map[si.custom_sales_order]
			pi_amount = flt(so.grand_total)
			pi_date = so.transaction_date

		proj = project_map.get(si.project) or {}
		out.append(
			{
				"_ref_dt": "Sales Invoice",
				"_ref_dn": si.name,
				"invoice_no": si.name,
				"client_name": cust_map.get(si.customer) or si.customer or "",
				"pm_engg": proj.get("engineer") or "",
				"workdone": proj.get("project_name") or si.project or "",
				"pi_amount": pi_amount if pi_amount is not None else None,
				"pi_date": pi_date,
				"pc_date": None,
				"pc_amt": None,
				"ti_date": si.ti_date,
				"ti_amt": flt(si.ti_amt),
				"due_date": si.due_date,
				"payment_mode": "",
				"payment_date": None,
				"cheque_no": "",
				"remarks": si.remarks or "",
			}
		)
	return out


def _get_purchase_invoice_rows(filters, allowed_names=None):
	conditions, values = _build_pi_conditions(filters)
	name_clause = ""
	if allowed_names is not None:
		if not allowed_names:
			return []
		esc = ", ".join(frappe.db.escape(n) for n in allowed_names)
		name_clause = f"AND pi.name IN ({esc})"

	pi_list = frappe.db.sql(
		"""
		SELECT
			pi.name,
			pi.posting_date AS ti_date,
			pi.grand_total AS ti_amt,
			pi.due_date,
			pi.supplier,
			pi.project,
			pi.company,
			pi.remarks
		FROM `tabPurchase Invoice` pi
		WHERE pi.docstatus = 1
		  AND IFNULL(pi.project, '') != ''
		  {name_clause}
		{conditions}
		ORDER BY pi.posting_date DESC, pi.name DESC
		""".format(name_clause=name_clause, conditions=conditions),
		values,
		as_dict=True,
	)
	if not pi_list:
		return []

	project_names = {r.project for r in pi_list if r.project}
	project_map = _project_engineer_map(project_names)

	supplier_ids = list({r.supplier for r in pi_list if r.supplier})
	supp_map = {}
	if supplier_ids:
		for s in frappe.get_all(
			"Supplier", filters={"name": ("in", supplier_ids)}, fields=["name", "supplier_name"]
		):
			supp_map[s.name] = s.supplier_name

	parents = [r.name for r in pi_list]
	pr_dates_amounts = _purchase_receipt_pi_from_items(parents)

	out = []
	for pi in pi_list:
		pr_info = pr_dates_amounts.get(pi.name) or {}
		proj = project_map.get(pi.project) or {}
		out.append(
			{
				"_ref_dt": "Purchase Invoice",
				"_ref_dn": pi.name,
				"invoice_no": pi.name,
				"client_name": supp_map.get(pi.supplier) or pi.supplier or "",
				"pm_engg": proj.get("engineer") or "",
				"workdone": proj.get("project_name") or pi.project or "",
				"pi_amount": pr_info.get("amount"),
				"pi_date": pr_info.get("date"),
				"pc_date": None,
				"pc_amt": None,
				"ti_date": pi.ti_date,
				"ti_amt": flt(pi.ti_amt),
				"due_date": pi.due_date,
				"payment_mode": "",
				"payment_date": None,
				"cheque_no": "",
				"remarks": pi.remarks or "",
			}
		)
	return out


def _purchase_receipt_pi_from_items(pi_names):
	"""Earliest Purchase Receipt date and summed item amounts linked to PR lines."""
	if not pi_names:
		return {}
	placeholders = ", ".join(["%s"] * len(pi_names))
	rows = frappe.db.sql(
		"""
		SELECT
			pii.parent AS pi_name,
			pii.purchase_receipt,
			pr.posting_date AS pr_date,
			pii.amount AS line_amt
		FROM `tabPurchase Invoice Item` pii
		LEFT JOIN `tabPurchase Receipt` pr ON pr.name = pii.purchase_receipt
		WHERE pii.parent IN ({ph})
		  AND IFNULL(pii.purchase_receipt, '') != ''
		""".format(ph=placeholders),
		pi_names,
		as_dict=True,
	)
	result = {}
	for row in rows:
		pn = row.pi_name
		if pn not in result:
			result[pn] = {"dates": [], "amount": 0.0}
		if row.pr_date:
			result[pn]["dates"].append(row.pr_date)
		result[pn]["amount"] += flt(row.line_amt)

	out = {}
	for pn, agg in result.items():
		dates = [d for d in agg["dates"] if d]
		out[pn] = {
			"date": min(dates) if dates else None,
			"amount": agg["amount"] if agg["amount"] else None,
		}
	return out


def _project_engineer_map(project_names):
	if not project_names:
		return {}
	projects = frappe.get_all(
		"Project",
		filters={"name": ("in", list(project_names))},
		fields=["name", "project_name", "custom_project_engineer"],
	)
	engineer_ids = [p.custom_project_engineer for p in projects if p.custom_project_engineer]
	emp_name_map = {}
	if engineer_ids:
		for emp in frappe.get_all(
			"Employee", filters={"name": ("in", engineer_ids)}, fields=["name", "employee_name"]
		):
			emp_name_map[emp.name] = emp.employee_name

	m = {}
	for p in projects:
		m[p.name] = {
			"project_name": p.project_name or p.name,
			"engineer": emp_name_map.get(p.custom_project_engineer, p.custom_project_engineer or ""),
		}
	return m


def _build_payment_map(rows):
	keys_si = []
	keys_pi = []
	for r in rows:
		dt, dn = r["_ref_dt"], r["_ref_dn"]
		if dt == "Sales Invoice":
			keys_si.append(dn)
		elif dt == "Purchase Invoice":
			keys_pi.append(dn)

	out = {}
	if keys_si:
		out.update(_payment_aggregate("Sales Invoice", keys_si))
	if keys_pi:
		out.update(_payment_aggregate("Purchase Invoice", keys_pi))
	return out


def _payment_aggregate(reference_doctype, docnames):
	if not docnames:
		return {}
	placeholders = ", ".join(["%s"] * len(docnames))
	rows = frappe.db.sql(
		"""
		SELECT
			per.reference_name,
			per.allocated_amount,
			pe.posting_date,
			pe.mode_of_payment,
			IFNULL(pe.reference_no, '') AS reference_no
		FROM `tabPayment Entry Reference` per
		INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
		WHERE pe.docstatus = 1
		  AND per.reference_doctype = %s
		  AND per.reference_name IN ({ph})
		ORDER BY per.reference_name, pe.posting_date ASC, pe.name ASC
		""".format(ph=placeholders),
		tuple([reference_doctype] + docnames),
		as_dict=True,
	)

	by_inv = {}
	for row in rows:
		rn = row.reference_name
		if rn not in by_inv:
			by_inv[rn] = {"paid": 0.0, "last": None, "mode": "", "refs": []}
		by_inv[rn]["paid"] += flt(row.allocated_amount)
		by_inv[rn]["last"] = row.posting_date
		by_inv[rn]["mode"] = row.mode_of_payment or by_inv[rn]["mode"]
		ref = (row.reference_no or "").strip()
		if ref:
			by_inv[rn]["refs"].append(ref)

	result = {}
	for rn, agg in by_inv.items():
		if agg["paid"] > 0:
			seen = set()
			uniq = []
			for r in agg["refs"]:
				if r not in seen:
					seen.add(r)
					uniq.append(r)
			result[(reference_doctype, rn)] = {
				"payment_date": agg["last"],
				"mode_of_payment": agg["mode"],
				"reference_no": ", ".join(uniq),
			}
	return result


def _build_si_conditions(filters):
	conditions = []
	values = {}
	if filters.get("company"):
		conditions.append("AND si.company = %(company)s")
		values["company"] = filters["company"]
	if filters.get("project"):
		conditions.append("AND si.project = %(project)s")
		values["project"] = filters["project"]
	if filters.get("from_date"):
		conditions.append("AND si.posting_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("AND si.posting_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]
	return "\n".join(conditions), values


def _build_pi_conditions(filters):
	conditions = []
	values = {}
	if filters.get("company"):
		conditions.append("AND pi.company = %(company)s")
		values["company"] = filters["company"]
	if filters.get("project"):
		conditions.append("AND pi.project = %(project)s")
		values["project"] = filters["project"]
	if filters.get("from_date"):
		conditions.append("AND pi.posting_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("AND pi.posting_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]
	return "\n".join(conditions), values


def get_chart_data(data):
	if not data:
		return None

	client_totals = {}
	for row in data:
		client = row.get("client_name") or "Unknown"
		if client not in client_totals:
			client_totals[client] = {"pi": 0.0, "ti": 0.0}
		client_totals[client]["pi"] += flt(row.get("pi_amount"))
		client_totals[client]["ti"] += flt(row.get("ti_amt"))

	sorted_clients = sorted(client_totals.items(), key=lambda x: x[1]["ti"], reverse=True)[:10]
	labels = [c[0] for c in sorted_clients]

	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("PI Amount"), "values": [c[1]["pi"] for c in sorted_clients]},
				{"name": _("TI Amount"), "values": [c[1]["ti"] for c in sorted_clients]},
			],
		},
		"type": "bar",
		"colors": ["#7cd6fd", "#36b37e"],
		"barOptions": {"stacked": 0},
	}


def get_report_summary(data):
	if not data:
		return []

	total_pi = sum(flt(r.get("pi_amount")) for r in data if r.get("pi_amount") is not None)
	total_ti = sum(flt(r.get("ti_amt")) for r in data)
	paid_count = sum(1 for r in data if r.get("payment_date"))
	unpaid_count = len(data) - paid_count

	return [
		{"value": total_pi, "label": _("Total PI Amount"), "datatype": "Currency", "indicator": "blue"},
		{"value": total_ti, "label": _("Total TI Amount"), "datatype": "Currency", "indicator": "green"},
		{"value": paid_count, "label": _("Paid"), "datatype": "Int", "indicator": "green"},
		{"value": unpaid_count, "label": _("Unpaid"), "datatype": "Int", "indicator": "orange"},
	]
