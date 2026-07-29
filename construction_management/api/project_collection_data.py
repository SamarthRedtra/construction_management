# Copyright (c) 2026, Construction Management
# License: MIT

"""Collection Manager data — unified PI → PC → TI → payment rows (shared with Project SOA backend)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, flt, getdate, today

COLLECTION_ROW_KEYS = (
	"sr_no",
	"invoice_no",
	"client_name",
	"pm_engg",
	"workdone",
	"pi_amount",
	"pi_date",
	"pc_date",
	"pc_amt",
	"ti_date",
	"ti_amt",
	"due_date",
	"payment_mode",
	"payment_date",
	"cheque_no",
	"remarks",
)


def get_collection_portfolio(company: str, filters: dict | None = None) -> list[dict]:
	"""Summary row per active project in a company."""
	if not company:
		frappe.throw(_("Company is required"))

	filters = filters or {}
	conditions = ["p.company = %(company)s", "IFNULL(p.status, '') != 'Completed'"]
	values = {"company": company}

	if filters.get("customer"):
		conditions.append("p.customer = %(customer)s")
		values["customer"] = filters["customer"]

	projects = frappe.db.sql(
		f"""
		SELECT p.name, p.project_name, p.customer, p.custom_project_engineer
		FROM `tabProject` p
		WHERE {" AND ".join(conditions)}
		ORDER BY p.project_name ASC, p.name ASC
		""",
		values,
		as_dict=True,
	)
	if not projects:
		return []

	customer_map = _customer_name_map([p.customer for p in projects if p.customer])
	engineer_map = _employee_name_map([p.custom_project_engineer for p in projects if p.custom_project_engineer])

	portfolio = []
	for project in projects:
		detail = get_collection_project_rows(project.name, include_follow_ups=False)
		summary = detail.get("summary") or {}
		portfolio.append({
			"project": project.name,
			"project_name": project.project_name or project.name,
			"client_name": customer_map.get(project.customer) or project.customer or "",
			"pm_engg": engineer_map.get(project.custom_project_engineer) or "",
			"pi_count": summary.get("pi_count", 0),
			"pi_total": flt(summary.get("pi_raised")),
			"pc_count": summary.get("pc_count", 0),
			"pc_certified": flt(summary.get("pc_certified")),
			"ti_billed": flt(summary.get("ti_billed")),
			"collected": flt(summary.get("collected")),
			"pending": flt(summary.get("pending")),
			"overdue_count": summary.get("overdue_count", 0),
			"overdue_amount": flt(summary.get("overdue_amount")),
			"last_follow_up_status": summary.get("last_follow_up_status") or "",
		})

	return portfolio


def get_collection_invoice_portfolio(company: str, filters: dict | None = None) -> list[dict]:
	"""Collection rows grouped by invoiced project, including its Sales Order proformas."""
	if not company:
		frappe.throw(_("Company is required"))
	filters = filters or {}
	conditions = [
		"p.company = %(company)s",
		"EXISTS (SELECT 1 FROM `tabSales Invoice` si WHERE si.project = p.name AND si.docstatus = 1)",
	]
	values = {"company": company}
	if filters.get("customer"):
		conditions.append("p.customer = %(customer)s")
		values["customer"] = filters["customer"]

	projects = frappe.db.sql(
		f"""
		SELECT p.name, p.project_name
		FROM `tabProject` p
		WHERE {' AND '.join(conditions)}
		ORDER BY p.project_name ASC, p.name ASC
		""",
		values,
		as_dict=True,
	)
	rows = []
	for project in projects:
		detail = get_collection_project_rows(project.name, include_follow_ups=True)
		project_rows = []
		for row in detail.get("rows") or []:
			if row.get("reference_doctype") not in ("Sales Invoice", "Sales Order"):
				continue
			document_date = row.get("ti_date") or row.get("pi_date")
			if filters.get("from_date") and (not document_date or getdate(document_date) < getdate(filters["from_date"])):
				continue
			if filters.get("to_date") and (not document_date or getdate(document_date) > getdate(filters["to_date"])):
				continue
			row["project_name"] = project.project_name or project.name
			row["document_type"] = "Tax Invoice" if row.get("reference_doctype") == "Sales Invoice" else "Proforma (Sales Order)"
			project_rows.append(row)

		# A Sales Order linked to a submitted Tax Invoice is intentionally omitted by
		# get_collection_project_rows. Add it here so the register visibly shows the
		# Proforma (Sales Order) and Tax Invoice stages together. These supplemental
		# rows must receive the same PC/follow-up overlay as the original rows;
		# otherwise a PC saved against the Sales Order cannot be found by the
		# Collection Manager filter.
		existing_sales_orders = {row.get("reference_name") for row in project_rows if row.get("reference_doctype") == "Sales Order"}
		supplemental_sales_order_rows = []
		sales_order_fields = ["name", "transaction_date", "grand_total"]
		if frappe.db.has_column("Sales Order", "remarks"):
			sales_order_fields.append("remarks")
		for sales_order in frappe.get_all(
			"Sales Order",
			filters={"project": project.name, "docstatus": 1},
			fields=sales_order_fields,
			order_by="transaction_date desc, name desc",
		):
			if sales_order.name in existing_sales_orders:
				continue
			document_date = sales_order.transaction_date
			if filters.get("from_date") and (not document_date or getdate(document_date) < getdate(filters["from_date"])):
				continue
			if filters.get("to_date") and (not document_date or getdate(document_date) > getdate(filters["to_date"])):
				continue
			supplemental_sales_order_rows.append(
				_shape_collection_row(
					project=project.name,
					reference_doctype="Sales Order",
					reference_name=sales_order.name,
					invoice_no=sales_order.name,
					stage="Sales Order (Proforma)",
					client_name=detail["project"].get("client_name") or "",
					pm_engg=detail["project"].get("pm_engg") or "",
					workdone=project.project_name or project.name,
					pi_amount=flt(sales_order.grand_total),
					pi_date=document_date,
					remarks=sales_order.remarks or "",
				)
			)
			supplemental_sales_order_rows[-1]["project_name"] = project.project_name or project.name
			supplemental_sales_order_rows[-1]["document_type"] = "Proforma (Sales Order)"

		if supplemental_sales_order_rows:
			follow_ups = detail.get("follow_ups") or []
			_apply_follow_up_overlay(supplemental_sales_order_rows, follow_ups)
			from construction_management.api.collection_pc_override import merge_collection_pc_overlays

			merge_collection_pc_overlays(supplemental_sales_order_rows, follow_ups)
			project_rows.extend(supplemental_sales_order_rows)

		rows.extend(project_rows)

	# Keep each project together while showing its newest documents first.
	rows.sort(key=lambda row: (getdate(row.get("ti_date") or row.get("pi_date") or "1900-01-01"), row.get("invoice_no") or ""), reverse=True)
	rows.sort(key=lambda row: (row.get("project_name") or "", row.get("project") or ""))
	for idx, row in enumerate(rows, start=1):
		row["sr_no"] = idx
	return rows


def get_collection_expected_payments(company: str, filters: dict | None = None) -> dict:
	"""Outstanding Tax Invoices grouped by customer for the next three due-date months."""
	if not company:
		frappe.throw(_("Company is required"))
	filters = filters or {}
	anchor = getdate(filters.get("from_date") or today()).replace(day=1)
	months = [getdate(add_months(anchor, offset)).replace(day=1) for offset in range(3)]
	end_date = add_days(getdate(add_months(months[-1], 1)).replace(day=1), -1)
	conditions = ["si.company = %(company)s", "si.docstatus = 1", "si.outstanding_amount > 0", "si.due_date BETWEEN %(start)s AND %(end)s"]
	values = {"company": company, "start": months[0], "end": end_date}
	if filters.get("customer"):
		conditions.append("si.customer = %(customer)s")
		values["customer"] = filters["customer"]
	entries = frappe.db.sql(
		f"""
		SELECT si.customer, COALESCE(c.customer_name, si.customer) AS customer_name,
			si.due_date, si.outstanding_amount
		FROM `tabSales Invoice` si
		LEFT JOIN `tabCustomer` c ON c.name = si.customer
		WHERE {' AND '.join(conditions)}
		""",
		values,
		as_dict=True,
	)
	by_customer = {}
	for entry in entries:
		row = by_customer.setdefault(entry.customer, {"customer": entry.customer, "customer_name": entry.customer_name, "amounts": {}})
		month_key = getdate(entry.due_date).replace(day=1).isoformat()
		row["amounts"][month_key] = flt(row["amounts"].get(month_key)) + flt(entry.outstanding_amount)
	rows = sorted(by_customer.values(), key=lambda row: row["customer_name"] or row["customer"])
	return {"months": [{"key": month.isoformat(), "label": month.strftime("%b %Y")} for month in months], "rows": rows}


def get_collection_project_rows(project: str, include_follow_ups: bool = True) -> dict:
	"""Full collection detail for one project."""
	if not project:
		frappe.throw(_("Project is required"))

	fields = ["name", "project_name", "customer", "company", "custom_project_engineer"]
	if frappe.db.has_column("Project", "custom_collection_overdue_basis"):
		fields.append("custom_collection_overdue_basis")
	if frappe.db.has_column("Project", "custom_collection_overdue_days"):
		fields.append("custom_collection_overdue_days")

	project_doc = frappe.db.get_value(
		"Project",
		project,
		fields,
		as_dict=True,
	)
	if not project_doc:
		frappe.throw(_("Project {0} not found").format(project))

	client_name = ""
	if project_doc.customer:
		client_name = frappe.db.get_value("Customer", project_doc.customer, "customer_name") or project_doc.customer

	pm_engg = ""
	if project_doc.custom_project_engineer:
		pm_engg = frappe.db.get_value("Employee", project_doc.custom_project_engineer, "employee_name") or project_doc.custom_project_engineer

	workdone = project_doc.project_name or project.name
	overdue_settings = {
		"basis": project_doc.get("custom_collection_overdue_basis") or "Tax Invoice",
		"days": cint(project_doc.get("custom_collection_overdue_days")),
	}
	raw_rows = _build_collection_cycles(project, client_name, pm_engg, workdone)
	follow_ups = []
	if include_follow_ups:
		from construction_management.construction_management.page.project_soa.project_soa import (
			get_project_soa_follow_ups,
		)

		follow_ups = get_project_soa_follow_ups(project)

	_apply_follow_up_overlay(raw_rows, follow_ups)
	from construction_management.api.collection_pc_override import merge_collection_pc_overlays

	merge_collection_pc_overlays(raw_rows, follow_ups)
	_apply_pdc_overlay(raw_rows)
	_apply_overdue_rules(raw_rows, overdue_settings)

	for idx, row in enumerate(raw_rows, start=1):
		row["sr_no"] = idx

	summary = _build_collection_summary(project, raw_rows, follow_ups)

	return {
		"project": {
			"name": project,
			"project_name": project_doc.project_name or project,
			"client_name": client_name,
			"pm_engg": pm_engg,
			"company": project_doc.company,
		},
		"summary": summary,
		"rows": raw_rows,
		"follow_ups": follow_ups,
	}


def _build_collection_cycles(project: str, client_name: str, pm_engg: str, workdone: str) -> list[dict]:
	rows: list[dict] = []

	has_proforma_flag = frappe.db.has_column("Sales Invoice", "custom_is_proforma")
	has_pf_link = frappe.db.has_column("Sales Invoice", "custom_proforma_invoice")
	has_so_link = frappe.db.has_column("Sales Invoice", "custom_sales_order")
	has_pc_link = frappe.db.has_column("Sales Invoice", "custom_payment_certificate")
	has_advance_flag = frappe.db.has_column("Sales Invoice", "custom_is_advanced")

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
	if has_pc_link:
		extra_fields += ", IFNULL(si.custom_payment_certificate, '') AS custom_payment_certificate"
	else:
		extra_fields += ", '' AS custom_payment_certificate"
	if has_advance_flag:
		extra_fields += ", IFNULL(si.custom_is_advanced, 0) AS custom_is_advanced"
	else:
		extra_fields += ", 0 AS custom_is_advanced"

	si_list = frappe.db.sql(
		f"""
		SELECT
			si.name,
			si.posting_date AS ti_date,
			si.grand_total AS ti_amt,
			si.due_date,
			si.remarks
			{extra_fields}
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		  AND si.project = %(project)s
		  {proforma_sql}
		ORDER BY si.posting_date ASC, si.name ASC
		""",
		{"project": project},
		as_dict=True,
	)

	proforma_names = {r.custom_proforma_invoice for r in si_list if r.custom_proforma_invoice}
	so_names = {r.custom_sales_order for r in si_list if r.custom_sales_order}
	pc_names = {r.custom_payment_certificate for r in si_list if r.custom_payment_certificate}

	pfi_map = {}
	if proforma_names:
		for d in frappe.get_all(
			"Sales Invoice",
			filters={"name": ("in", list(proforma_names))},
			fields=["name", "posting_date", "grand_total"],
		):
			pfi_map[d.name] = d
		for d in frappe.get_all(
			"Proforma Invoice",
			filters={"name": ("in", list(proforma_names))},
			fields=["name", "posting_date", "amount"],
		):
			pfi_map.setdefault(
				d.name,
				frappe._dict({"posting_date": d.posting_date, "grand_total": d.amount, "amount": d.amount}),
			)

	so_map = {}
	if so_names:
		for d in frappe.get_all(
			"Sales Order",
			filters={"name": ("in", list(so_names))},
			fields=["name", "transaction_date", "grand_total"],
		):
			so_map[d.name] = d

	pc_map = {}
	if pc_names:
		pc_fields = ["name", "posting_date", "accepted_amount", "grand_total", "proforma_amount", "remarks"]
		if frappe.db.has_column("Payment Certificate", "custom_certificate_date"):
			pc_fields.append("custom_certificate_date")
		for d in frappe.get_all(
			"Payment Certificate",
			filters={"name": ("in", list(pc_names))},
			fields=pc_fields,
		):
			pc_map[d.name] = d

	pay_map = _payment_aggregate("Sales Invoice", [r.name for r in si_list])

	for si in si_list:
		pi_amount = None
		pi_date = None
		if si.custom_proforma_invoice and si.custom_proforma_invoice in pfi_map:
			pf = pfi_map[si.custom_proforma_invoice]
			pi_amount = flt(pf.grand_total or pf.get("amount"))
			pi_date = pf.posting_date
		elif si.custom_sales_order and si.custom_sales_order in so_map:
			so = so_map[si.custom_sales_order]
			pi_amount = flt(so.grand_total)
			pi_date = so.transaction_date

		pc_date = None
		pc_amt = None
		pc_remarks = ""
		if si.custom_payment_certificate and si.custom_payment_certificate in pc_map:
			pc = pc_map[si.custom_payment_certificate]
			pc_date = _pc_display_date(pc)
			pc_amt = flt(pc.accepted_amount) or flt(pc.grand_total) or flt(pc.proforma_amount)
			pc_remarks = pc.remarks or ""

		pay = pay_map.get(("Sales Invoice", si.name)) or {}
		collection_row = _shape_collection_row(
			project=project,
			reference_doctype="Sales Invoice",
			reference_name=si.name,
			invoice_no=si.name,
			stage="Tax Invoice",
			client_name=client_name,
			pm_engg=pm_engg,
			workdone=workdone,
			pi_amount=pi_amount,
			pi_date=pi_date,
			pc_date=pc_date,
			pc_amt=pc_amt,
			ti_date=si.ti_date,
			ti_amt=flt(si.ti_amt),
			due_date=si.due_date,
			payment_mode=pay.get("mode_of_payment") or "",
			payment_date=pay.get("payment_date"),
			cheque_no=pay.get("reference_no") or "",
			remarks=" · ".join(filter(None, [si.remarks, pc_remarks])),
			payment_certificate=si.custom_payment_certificate or "",
		)
		collection_row["is_advance"] = cint(si.custom_is_advanced)
		rows.append(collection_row)

	for pi in frappe.db.get_all(
		"Proforma Invoice",
		filters={"project": project, "docstatus": 1, "status": ["!=", "Converted"]},
		fields=["name", "posting_date", "amount", "remarks"],
		order_by="posting_date asc, name asc",
	):
		rows.append(_shape_collection_row(
			project=project,
			reference_doctype="Proforma Invoice",
			reference_name=pi.name,
			invoice_no=pi.name,
			stage="Proforma Invoice",
			client_name=client_name,
			pm_engg=pm_engg,
			workdone=workdone,
			pi_amount=flt(pi.amount),
			pi_date=pi.posting_date,
			remarks=pi.remarks or "",
		))

	pcs_without_si = frappe.db.sql(
		f"""
		SELECT name, posting_date, sales_order, grand_total, proforma_amount, accepted_amount, remarks
			{', custom_certificate_date' if frappe.db.has_column('Payment Certificate', 'custom_certificate_date') else ", NULL AS custom_certificate_date"}
		FROM `tabPayment Certificate`
		WHERE project = %s
		  AND docstatus IN (0, 1)
		  AND type = 'Sales'
		  AND (tax_invoice IS NULL OR tax_invoice = '')
		ORDER BY posting_date ASC, name ASC
		""",
		project,
		as_dict=True,
	)
	pc_so_names = {pc.sales_order for pc in pcs_without_si if pc.sales_order}

	for pc in pcs_without_si:
		pi_amount = None
		pi_date = None
		if pc.sales_order and pc.sales_order in so_map:
			so = so_map[pc.sales_order]
			pi_amount = flt(so.grand_total)
			pi_date = so.transaction_date
		elif pc.sales_order:
			so_row = frappe.db.get_value(
				"Sales Order", pc.sales_order, ["transaction_date", "grand_total"], as_dict=True
			)
			if so_row:
				pi_amount = flt(so_row.grand_total)
				pi_date = so_row.transaction_date

		pc_amt = flt(pc.accepted_amount) or flt(pc.grand_total) or flt(pc.proforma_amount)
		rows.append(_shape_collection_row(
			project=project,
			reference_doctype="Payment Certificate",
			reference_name=pc.name,
			invoice_no=pc.name,
			stage="Payment Certificate",
			client_name=client_name,
			pm_engg=pm_engg,
			workdone=workdone,
			pi_amount=pi_amount,
			pi_date=pi_date,
			pc_date=_pc_display_date(pc),
			pc_amt=pc_amt,
			remarks=pc.remarks or "",
			payment_certificate=pc.name,
		))

	so_remarks_field = ", remarks" if frappe.db.has_column("Sales Order", "remarks") else ", '' AS remarks"
	for so in frappe.db.sql(
		f"""
		SELECT name, transaction_date, grand_total{so_remarks_field}
		FROM `tabSales Order`
		WHERE project = %s AND docstatus = 1
		ORDER BY transaction_date ASC, name ASC
		""",
		project,
		as_dict=True,
	):
		if so.name in pc_so_names:
			continue
		if _sales_order_has_tax_invoice(so.name, project):
			continue
		if _sales_order_has_open_pc(so.name, project):
			continue

		rows.append(_shape_collection_row(
			project=project,
			reference_doctype="Sales Order",
			reference_name=so.name,
			invoice_no=so.name,
			stage="Sales Order (Proforma)",
			client_name=client_name,
			pm_engg=pm_engg,
			workdone=workdone,
			pi_amount=flt(so.grand_total),
			pi_date=so.transaction_date,
			remarks=so.remarks or "",
		))

	rows.sort(key=lambda r: (
		getdate(r.get("pi_date") or r.get("pc_date") or r.get("ti_date") or "1900-01-01"),
		r.get("invoice_no") or "",
	))
	return rows


def _shape_collection_row(
	project: str,
	reference_doctype: str,
	reference_name: str,
	invoice_no: str,
	stage: str,
	client_name: str,
	pm_engg: str,
	workdone: str,
	pi_amount=None,
	pi_date=None,
	pc_date=None,
	pc_amt=None,
	ti_date=None,
	ti_amt=None,
	due_date=None,
	payment_mode: str = "",
	payment_date=None,
	cheque_no: str = "",
	remarks: str = "",
	payment_certificate: str = "",
) -> dict:
	return {
		"project": project,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"payment_certificate": payment_certificate,
		"stage": stage,
		"invoice_no": invoice_no,
		"client_name": client_name,
		"pm_engg": pm_engg,
		"workdone": workdone,
		"pi_amount": pi_amount,
		"pi_date": pi_date,
		"pc_date": pc_date,
		"pc_amt": pc_amt,
		"ti_date": ti_date,
		"ti_amt": ti_amt,
		"due_date": due_date,
		"payment_mode": payment_mode,
		"payment_date": payment_date,
		"cheque_no": cheque_no,
		"remarks": remarks,
		"follow_up_status": "",
		"follow_up_attachment": "",
		"is_overdue": False,
		"overdue_date": None,
		"days_overdue": 0,
	}


def _pc_display_date(pc) -> str | None:
	if not pc:
		return None
	return pc.get("custom_certificate_date") or pc.get("posting_date")


def _apply_overdue_rules(rows: list[dict], overdue_settings: dict | None = None) -> None:
	"""Apply Project overdue basis/days, else legacy Tax Invoice due_date."""
	overdue_settings = overdue_settings or {}
	basis = overdue_settings.get("basis") or "Tax Invoice"
	days = cint(overdue_settings.get("days"))

	for row in rows:
		payment_date = row.get("payment_date")
		unpaid_amt = flt(row.get("ti_amt") or row.get("pc_amt") or row.get("pi_amount"))
		if payment_date or unpaid_amt <= 0:
			row["is_overdue"] = False
			row["overdue_date"] = row.get("due_date")
			row["days_overdue"] = 0
			continue

		if days > 0:
			if basis == "Proforma Invoice":
				base_date = row.get("pi_date")
			else:
				base_date = row.get("due_date") or row.get("ti_date")

			if not base_date:
				row["is_overdue"] = False
				row["overdue_date"] = None
				row["days_overdue"] = 0
				continue

			overdue_date = add_days(getdate(base_date), days)
			row["overdue_date"] = overdue_date
			if not row.get("due_date"):
				row["due_date"] = overdue_date
			is_overdue = getdate(today()) > getdate(overdue_date)
			row["is_overdue"] = is_overdue
			row["days_overdue"] = (getdate(today()) - getdate(overdue_date)).days if is_overdue else 0
			continue

		# Legacy: Tax Invoice due_date only
		row["overdue_date"] = row.get("due_date")
		row["is_overdue"] = _is_overdue(row.get("due_date"), row.get("ti_amt"), payment_date)
		if row["is_overdue"] and row.get("due_date"):
			row["days_overdue"] = (getdate(today()) - getdate(row["due_date"])).days
		else:
			row["days_overdue"] = 0


def _build_collection_summary(project: str, rows: list[dict], follow_ups: list[dict]) -> dict:
	pi_count = sum(1 for r in rows if flt(r.get("pi_amount")))
	pi_raised = sum(flt(r.get("pi_amount")) for r in rows if flt(r.get("pi_amount")))
	pc_count = sum(1 for r in rows if flt(r.get("pc_amt")))
	pc_certified = sum(flt(r.get("pc_amt")) for r in rows if flt(r.get("pc_amt")))
	ti_billed = sum(flt(r.get("ti_amt")) for r in rows if flt(r.get("ti_amt")))

	kpi = {}
	try:
		from construction_management.api.boq_tree import get_boq_kpi

		kpi = get_boq_kpi(project) or {}
	except Exception:
		pass

	collected = flt(kpi.get("invoice_collected")) or sum(
		flt(r.get("ti_amt")) for r in rows if r.get("payment_date")
	)
	pending = flt(kpi.get("pending")) or max(0, ti_billed - collected)
	overdue_count = sum(1 for r in rows if r.get("is_overdue"))
	overdue_amount = sum(
		flt(r.get("ti_amt") or r.get("pc_amt") or r.get("pi_amount"))
		for r in rows
		if r.get("is_overdue")
	)

	last_follow_up_status = ""
	if follow_ups:
		last_follow_up_status = follow_ups[0].get("status") or ""

	return {
		"pi_count": pi_count,
		"pi_raised": pi_raised,
		"pc_count": pc_count,
		"pc_certified": pc_certified,
		"ti_billed": ti_billed,
		"collected": collected,
		"pending": pending,
		"overdue_count": overdue_count,
		"overdue_amount": overdue_amount,
		"last_follow_up_status": last_follow_up_status,
	}


def _apply_follow_up_overlay(rows: list[dict], follow_ups: list[dict]) -> None:
	latest: dict[tuple[str, str], dict] = {}
	for fu in follow_ups:
		key = (fu.get("reference_doctype"), fu.get("reference_name"))
		if key not in latest:
			latest[key] = fu

	for row in rows:
		key = (row.get("reference_doctype"), row.get("reference_name"))
		fu = latest.get(key)
		if not fu:
			continue
		# Expose the source record so Collection Manager can link users directly to
		# the follow-up where PC details and attachments were saved.
		row["follow_up_name"] = fu.get("name") or ""
		row["follow_up_status"] = fu.get("status") or ""
		row["follow_up_attachment"] = fu.get("attachment") or ""
		if fu.get("remarks"):
			base = row.get("remarks") or ""
			row["remarks"] = f"{base} · {fu.remarks}" if base else fu.remarks
		# Follow-up date/amount for Collection PC are applied in merge_collection_pc_overlays.
		if fu.get("follow_up_date") and (fu.get("status") or "") not in (
			"Collection PC",
			"PC Date",
			"PC Amount",
		):
			if not row.get("pc_date") and fu.get("payment_certificate"):
				row["pc_date"] = fu.follow_up_date
		if fu.get("payment_certificate") and not row.get("payment_certificate"):
			row["payment_certificate"] = fu.payment_certificate


def _apply_pdc_overlay(rows: list[dict]) -> None:
	try:
		from redtra_customisation.redtra_customisation.doctype.post_dated_cheques.post_dated_cheques import (
			get_invoice_pdc_connections,
		)
	except ImportError:
		return

	for row in rows:
		if row.get("reference_doctype") != "Sales Invoice" or row.get("payment_date"):
			continue
		pdcs = get_invoice_pdc_connections("Sales Invoice", row["reference_name"]) or []
		if not pdcs:
			continue
		pdc = pdcs[0]
		row["payment_mode"] = row.get("payment_mode") or _("Cheque")
		row["payment_date"] = row.get("payment_date") or pdc.get("reference_date")
		row["cheque_no"] = row.get("cheque_no") or pdc.get("reference_no") or ""


def _payment_aggregate(reference_doctype: str, docnames: list[str]) -> dict:
	if not docnames:
		return {}

	placeholders = ", ".join(["%s"] * len(docnames))
	rows = frappe.db.sql(
		f"""
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
		  AND per.reference_name IN ({placeholders})
		ORDER BY per.reference_name, pe.posting_date ASC, pe.name ASC
		""",
		tuple([reference_doctype] + docnames),
		as_dict=True,
	)

	by_inv: dict[str, dict] = {}
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
		if agg["paid"] <= 0:
			continue
		seen = set()
		uniq = []
		for ref in agg["refs"]:
			if ref not in seen:
				seen.add(ref)
				uniq.append(ref)
		result[(reference_doctype, rn)] = {
			"payment_date": agg["last"],
			"mode_of_payment": agg["mode"],
			"reference_no": ", ".join(uniq),
		}
	return result


def _sales_order_has_tax_invoice(so_name: str, project: str) -> bool:
	return bool(
		frappe.db.sql(
			"""
			SELECT 1
			FROM `tabSales Invoice` si
			WHERE si.docstatus = 1
			  AND si.project = %s
			  AND (
				si.custom_sales_order = %s
				OR EXISTS (
					SELECT 1 FROM `tabSales Invoice Item` sii
					WHERE sii.parent = si.name AND sii.sales_order = %s
				)
			  )
			LIMIT 1
			""",
			(project, so_name, so_name),
		)
	)


def _sales_order_has_open_pc(so_name: str, project: str) -> bool:
	return bool(
		frappe.db.sql(
			"""
			SELECT 1
			FROM `tabPayment Certificate` pc
			WHERE pc.project = %s
			  AND pc.docstatus IN (0, 1)
			  AND pc.type = 'Sales'
			  AND pc.sales_order = %s
			  AND (pc.tax_invoice IS NULL OR pc.tax_invoice = '')
			LIMIT 1
			""",
			(project, so_name),
		)
	)


def _is_overdue(due_date, ti_amt, payment_date) -> bool:
	if not due_date or not flt(ti_amt) or payment_date:
		return False
	return getdate(due_date) < getdate(today())


def _customer_name_map(customer_ids: list[str]) -> dict[str, str]:
	if not customer_ids:
		return {}
	return {
		row.name: row.customer_name
		for row in frappe.get_all(
			"Customer",
			filters={"name": ("in", list(set(customer_ids)))},
			fields=["name", "customer_name"],
		)
	}


def _employee_name_map(employee_ids: list[str]) -> dict[str, str]:
	if not employee_ids:
		return {}
	return {
		row.name: row.employee_name
		for row in frappe.get_all(
			"Employee",
			filters={"name": ("in", list(set(employee_ids)))},
			fields=["name", "employee_name"],
		)
	}
