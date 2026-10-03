"""Batch loader for the company-wide Collection Manager register."""

from collections import defaultdict

import frappe
from frappe.utils import cint, flt, getdate

from construction_management.api.collection_pc_override import merge_collection_pc_overlays
from construction_management.api.project_collection_data import (
	_apply_batch_pdc_overlay,
	_apply_follow_up_overlay,
	_apply_overdue_rules,
	_batch_pdc_map,
	_collection_filter_date,
	_consolidate_project_collection_rows,
	_customer_name_map,
	_date_matches_filters,
	_employee_name_map,
	_get_invoice_sales_order_allocations,
	_get_unlinked_tax_invoices_without_project,
	_payment_aggregate,
	_shape_collection_row,
)


def build_collection_register(company: str, filters: dict) -> list[dict]:
	projects = _projects(company, filters)
	if not projects:
		return _finish_rows(_get_unlinked_tax_invoices_without_project(company, filters))
	project_names = [project.name for project in projects]
	orders = _orders(company, project_names, filters)
	invoices = _invoices(company, project_names)
	allocations = _get_invoice_sales_order_allocations([invoice.name for invoice in invoices])
	if filters.get("from_date") or filters.get("to_date"):
		visible_orders = {order.name for order in orders}
		invoices = [invoice for invoice in invoices if (
			bool(set(allocations.get(invoice.name) or {}) & visible_orders)
			if allocations.get(invoice.name) else _date_matches_filters(invoice.posting_date, filters)
		)]
	if not orders and not invoices:
		return _finish_rows(_get_unlinked_tax_invoices_without_project(company, filters))
	invoice_names = [invoice.name for invoice in invoices]
	payments = _payment_aggregate("Sales Invoice", invoice_names)
	cheques = _batch_pdc_map(invoice_names)
	proforma_map = _proforma_map(invoices)
	certificate_map = _certificate_map(invoices)
	follow_ups = _follow_ups(project_names)
	project_map = {project.name: project for project in projects}
	customers = _customer_name_map([project.customer for project in projects if project.customer])
	engineers = _employee_name_map([project.custom_project_engineer for project in projects if project.custom_project_engineer])
	rows_by_project = defaultdict(list)
	order_map = {order.name: order for order in orders}
	for order in orders:
		project = project_map[order.project]
		row = _shape_collection_row(
			project=order.project, reference_doctype="Sales Order", reference_name=order.name,
			invoice_no=order.name, stage="Sales Order (Proforma)",
			client_name=customers.get(project.customer) or project.customer or "",
			pm_engg=engineers.get(project.custom_project_engineer) or "",
			workdone=project.project_name or project.name,
			pi_amount=flt(order.grand_total), pi_date=order.transaction_date,
			remarks=order.get("remarks") or "",
		)
		row.update(proforma_net_amount=flt(order.net_total), project_name=project.project_name or project.name,
			document_type="Proforma (Sales Order)")
		rows_by_project[order.project].append(row)
	for invoice in invoices:
		project = project_map[invoice.project]
		row = _invoice_row(invoice, project, customers, engineers, order_map, allocations,
			proforma_map, certificate_map, payments)
		rows_by_project[invoice.project].append(row)

	rows = []
	for project in projects:
		project_rows = rows_by_project[project.name]
		if not project_rows:
			continue
		_apply_batch_pdc_overlay(project_rows, cheques)
		_apply_follow_up_overlay(project_rows, follow_ups.get(project.name, []))
		merge_collection_pc_overlays(project_rows, follow_ups.get(project.name, []))
		project_rows = _consolidate_project_collection_rows(project_rows, filters, allocations)
		_apply_overdue_rules(project_rows, {
			"basis": project.custom_collection_overdue_basis or "Tax Invoice",
			"days": cint(project.custom_collection_overdue_days),
		})
		rows.extend(project_rows)
	rows.extend(_get_unlinked_tax_invoices_without_project(company, filters))
	return _finish_rows(rows)


def _projects(company: str, filters: dict) -> list[dict]:
	conditions = ["p.company = %(company)s", """(
		EXISTS (SELECT 1 FROM `tabSales Invoice` si WHERE si.project = p.name AND si.docstatus = 1)
		OR EXISTS (SELECT 1 FROM `tabSales Order` so WHERE so.project = p.name AND so.docstatus = 1)
	)"""]
	values = {"company": company}
	if filters.get("customer"):
		conditions.append("p.customer = %(customer)s")
		values["customer"] = filters["customer"]
	basis = "p.custom_collection_overdue_basis" if frappe.db.has_column("Project", "custom_collection_overdue_basis") else "'Tax Invoice'"
	days = "p.custom_collection_overdue_days" if frappe.db.has_column("Project", "custom_collection_overdue_days") else "0"
	return frappe.db.sql(f"""SELECT p.name, p.project_name, p.customer, p.custom_project_engineer,
		{basis} AS custom_collection_overdue_basis, {days} AS custom_collection_overdue_days
		FROM `tabProject` p WHERE {' AND '.join(conditions)}
		ORDER BY p.project_name, p.name""", values, as_dict=True)


def _orders(company: str, projects: list[str], filters: dict) -> list[dict]:
	order_filters = {"company": company, "project": ("in", projects), "docstatus": 1}
	if filters.get("from_date") and filters.get("to_date"):
		order_filters["transaction_date"] = ("between", [filters["from_date"], filters["to_date"]])
	elif filters.get("from_date"):
		order_filters["transaction_date"] = (">=", filters["from_date"])
	elif filters.get("to_date"):
		order_filters["transaction_date"] = ("<=", filters["to_date"])
	fields = ["name", "project", "transaction_date", "net_total", "grand_total"]
	if frappe.db.has_column("Sales Order", "remarks"):
		fields.append("remarks")
	return frappe.get_all("Sales Order", filters=order_filters, fields=fields, limit_page_length=0)


def _invoices(company: str, projects: list[str]) -> list[dict]:
	fields = ["name", "project", "posting_date", "grand_total", "due_date", "remarks",
		"custom_sales_order", "custom_proforma_invoice", "custom_payment_certificate"]
	if frappe.db.has_column("Sales Invoice", "custom_is_advanced"):
		fields.append("custom_is_advanced")
	if frappe.db.has_column("Sales Invoice", "custom_is_proforma"):
		fields.append("custom_is_proforma")
	filters = {"company": company, "project": ("in", projects), "docstatus": 1}
	return [row for row in frappe.get_all("Sales Invoice", filters=filters, fields=fields,
		limit_page_length=0) if not cint(row.get("custom_is_proforma"))]


def _proforma_map(invoices: list[dict]) -> dict:
	names = {row.custom_proforma_invoice for row in invoices if row.custom_proforma_invoice}
	if not names:
		return {}
	result = {row.name: row for row in frappe.get_all("Sales Invoice", filters={"name": ("in", names)},
		fields=["name", "posting_date", "grand_total"], limit_page_length=0)}
	for row in frappe.get_all("Proforma Invoice", filters={"name": ("in", names)},
		fields=["name", "posting_date", "amount"], limit_page_length=0):
		result.setdefault(row.name, row)
	return result


def _certificate_map(invoices: list[dict]) -> dict:
	names = {row.custom_payment_certificate for row in invoices if row.custom_payment_certificate}
	if not names:
		return {}
	fields = ["name", "posting_date", "accepted_amount", "grand_total", "proforma_amount", "remarks"]
	if frappe.db.has_column("Payment Certificate", "custom_certificate_date"):
		fields.append("custom_certificate_date")
	return {row.name: row for row in frappe.get_all("Payment Certificate", filters={"name": ("in", names)},
		fields=fields, limit_page_length=0)}


def _follow_ups(projects: list[str]) -> dict[str, list[dict]]:
	if not frappe.db.table_exists("Project SOA Follow Up"):
		return {}
	fields = ["name", "project", "reference_doctype", "reference_name", "payment_certificate",
		"follow_up_date", "status", "remarks", "attachment", "modified"]
	for optional in ("pc_amount", "collection_due_date"):
		if frappe.db.has_column("Project SOA Follow Up", optional):
			fields.append(optional)
	result = defaultdict(list)
	for row in frappe.get_all("Project SOA Follow Up", filters={"project": ("in", projects)},
		fields=fields, order_by="follow_up_date desc, modified desc", limit_page_length=0):
		result[row.project].append(row)
	return result


def _invoice_row(invoice, project, customers, engineers, orders, allocations, proformas, certificates, payments):
	linked_orders = allocations.get(invoice.name) or {}
	order_name = invoice.custom_sales_order or next(iter(linked_orders), "")
	order = orders.get(order_name)
	proforma = proformas.get(invoice.custom_proforma_invoice)
	certificate = certificates.get(invoice.custom_payment_certificate)
	payment = payments.get(("Sales Invoice", invoice.name)) or {}
	row = _shape_collection_row(
		project=invoice.project, reference_doctype="Sales Invoice", reference_name=invoice.name,
		invoice_no=invoice.name, stage="Tax Invoice",
		client_name=customers.get(project.customer) or project.customer or "",
		pm_engg=engineers.get(project.custom_project_engineer) or "",
		workdone=project.project_name or project.name,
		pi_amount=flt(proforma.get("grand_total") or proforma.get("amount")) if proforma else flt(order.grand_total) if order else None,
		pi_date=proforma.posting_date if proforma else order.transaction_date if order else None,
		pc_date=certificate.get("custom_certificate_date") or certificate.posting_date if certificate else None,
		pc_amt=(flt(certificate.accepted_amount) or flt(certificate.grand_total) or flt(certificate.proforma_amount)) if certificate else None,
		ti_date=invoice.posting_date, ti_amt=flt(invoice.grand_total), due_date=invoice.due_date,
		payment_mode=payment.get("mode_of_payment") or "", payment_date=payment.get("payment_date"),
		cheque_no=payment.get("reference_no") or "",
		remarks=" · ".join(filter(None, [invoice.remarks, certificate.remarks if certificate else ""])),
		payment_certificate=invoice.custom_payment_certificate or "",
	)
	row.update(project_name=project.project_name or project.name, document_type="Tax Invoice",
		is_advance=cint(invoice.get("custom_is_advanced")))
	return row


def _finish_rows(rows: list[dict]) -> list[dict]:
	invoice_names = {invoice["name"] for row in rows for invoice in row.get("tax_invoices") or []}
	invoice_names.update(row["reference_name"] for row in rows if row.get("reference_doctype") == "Sales Invoice")
	retention_names = set()
	if invoice_names:
		retention_names = set(frappe.get_all("Sales Invoice Item", filters={"parent": ("in", invoice_names),
			"item_code": "RETENTION-RELEASE", "docstatus": 1}, pluck="parent", limit_page_length=0))
	for row in rows:
		linked = {invoice["name"] for invoice in row.get("tax_invoices") or []}
		if row.get("reference_doctype") == "Sales Invoice":
			linked.add(row["reference_name"])
		row["is_retention_release"] = bool(linked & retention_names)
	rows.sort(key=lambda row: (getdate(_collection_filter_date(row) or "1900-01-01"),
		row.get("invoice_no") or ""), reverse=True)
	rows.sort(key=lambda row: (row.get("project_name") or "", row.get("project") or ""))
	for index, row in enumerate(rows, 1):
		row["sr_no"] = index
	return rows
