# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt, getdate

from construction_management.api.boq_tree import get_project_cost_breakdown
from construction_management.api.project_boq_scope import fetch_scope_boq_items, resolve_boq_source_project


INVOICE_TYPE_TAX = "Tax Invoice"
INVOICE_TYPE_PROFORMA = "Proforma Invoice"
INVOICE_TYPE_SO = "Sales Order (Proforma)"
INVOICE_TYPE_PC = "Payment Certificate"


@frappe.whitelist()
def get_project_soa_data(project: str) -> dict:
	if not project:
		frappe.throw(_("Project is required"))

	services, total_project_value, boq_source_project = _build_services(project)
	invoice_rows = _build_invoice_rows(project)
	summary = _build_summary(project, invoice_rows)
	expenses = _build_expenses(project)
	profit_loss = summary["total_received_amount"] - expenses[-1]["cost"]
	follow_ups = get_project_soa_follow_ups(project)

	return {
		"services": services,
		"total_project_value": total_project_value,
		"boq_source_project": boq_source_project,
		"invoices": invoice_rows,
		"summary": summary,
		"expenses": expenses,
		"profit_loss": profit_loss,
		"follow_ups": follow_ups,
	}


def _build_services(project: str) -> tuple[list[dict], float, str]:
	source_project = resolve_boq_source_project(project)
	boq_items = fetch_scope_boq_items(source_project)

	services = []
	total_project_value = 0.0
	for idx, item in enumerate(boq_items, start=1):
		amount = flt(item.total_amount)
		total_project_value += amount
		services.append({
			"idx": idx,
			"service": item.description or item.label or item.item_code,
			"area": flt(item.total_qty),
			"unit_price": flt(item.rate),
			"total_amount": amount,
		})

	return services, total_project_value, source_project


def _build_invoice_rows(project: str) -> list[dict]:
	rows: list[dict] = []

	# Tax Invoices (submitted Sales Invoices)
	sales_invoices = frappe.db.get_all(
		"Sales Invoice",
		filters={"project": project, "docstatus": 1},
		fields=["name", "posting_date", "grand_total", "custom_proforma_invoice", "custom_sales_order", "custom_retention_amount"],
		order_by="posting_date asc, name asc",
	)

	so_names = [si.custom_sales_order for si in sales_invoices if si.custom_sales_order]
	pfi_names = [si.custom_proforma_invoice for si in sales_invoices if si.custom_proforma_invoice]

	so_dates = {}
	if so_names:
		for row in frappe.db.get_all("Sales Order", filters={"name": ["in", so_names]}, fields=["name", "transaction_date"]):
			so_dates[row.name] = row.transaction_date

	pfi_dates = {}
	if pfi_names:
		for row in frappe.db.get_all("Proforma Invoice", filters={"name": ["in", pfi_names]}, fields=["name", "posting_date"]):
			pfi_dates[row.name] = row.posting_date

	for si in sales_invoices:
		proforma_date = _proforma_date_for_sales_invoice(si, so_dates, pfi_dates)
		rows.extend(_payment_rows_for_reference(
			project=project,
			reference_doctype="Sales Invoice",
			reference_name=si.name,
			proforma_date=proforma_date,
			tax_invoice_date=si.posting_date,
			invoice_no=si.name,
			invoice_type=INVOICE_TYPE_TAX,
			amount=flt(si.grand_total),
		))

	# Unconverted Proforma Invoices
	proforma_invoices = frappe.db.get_all(
		"Proforma Invoice",
		filters={"project": project, "docstatus": 1, "status": ["!=", "Converted"]},
		fields=["name", "posting_date", "amount"],
		order_by="posting_date asc, name asc",
	)
	for pi in proforma_invoices:
		rows.extend(_payment_rows_for_reference(
			project=project,
			reference_doctype="Proforma Invoice",
			reference_name=pi.name,
			proforma_date=pi.posting_date,
			tax_invoice_date=pi.posting_date,
			invoice_no=pi.name,
			invoice_type=INVOICE_TYPE_PROFORMA,
			amount=flt(pi.amount),
		))

	# Payment Certificates without tax invoice
	pcs_without_si = frappe.db.sql(
		"""
		SELECT name, posting_date, sales_order, grand_total, proforma_amount
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
		amount = flt(pc.grand_total) or flt(pc.proforma_amount)
		rows.extend(_payment_rows_for_reference(
			project=project,
			reference_doctype="Payment Certificate",
			reference_name=pc.name,
			payment_certificate=pc.name,
			proforma_date=pc.posting_date,
			tax_invoice_date=None,
			invoice_no=pc.name,
			invoice_type=INVOICE_TYPE_PC,
			amount=amount,
		))

	# Submitted Sales Orders without SI or open PC
	submitted_sos = frappe.db.get_all(
		"Sales Order",
		filters={"project": project, "docstatus": 1},
		fields=["name", "transaction_date", "grand_total"],
		order_by="transaction_date asc, name asc",
	)
	for so in submitted_sos:
		if so.name in pc_so_names:
			continue
		if _sales_order_has_tax_invoice(so.name, project):
			continue
		if _sales_order_has_open_pc(so.name, project):
			continue

		rows.extend(_payment_rows_for_reference(
			project=project,
			reference_doctype="Sales Order",
			reference_name=so.name,
			proforma_date=so.transaction_date,
			tax_invoice_date=None,
			invoice_no=so.name,
			invoice_type=INVOICE_TYPE_SO,
			amount=flt(so.grand_total),
		))

	rows.sort(key=lambda row: (getdate(row["proforma_date"]) if row.get("proforma_date") else getdate("1900-01-01"), row["invoice_no"]))
	for idx, row in enumerate(rows, start=1):
		row["serial_no"] = idx

	return rows


def _proforma_date_for_sales_invoice(si, so_dates: dict, pfi_dates: dict):
	if si.custom_proforma_invoice and si.custom_proforma_invoice in pfi_dates:
		return pfi_dates[si.custom_proforma_invoice]
	if si.custom_sales_order and si.custom_sales_order in so_dates:
		return so_dates[si.custom_sales_order]

	standard_so = frappe.db.get_value(
		"Sales Invoice Item",
		{"parent": si.name, "sales_order": ["is", "set"]},
		"sales_order",
	)
	if standard_so:
		return frappe.db.get_value("Sales Order", standard_so, "transaction_date")
	return si.posting_date


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


def _payment_rows_for_reference(
	project: str,
	reference_doctype: str,
	reference_name: str,
	proforma_date,
	tax_invoice_date,
	invoice_no: str,
	invoice_type: str,
	amount: float,
	payment_certificate: str = "",
) -> list[dict]:
	payment_ref_doctype = reference_doctype
	if reference_doctype == "Payment Certificate":
		payment_ref_doctype = "Payment Certificate"
	elif reference_doctype == "Sales Order":
		payment_ref_doctype = "Sales Order"

	payments = []
	if payment_ref_doctype in ("Sales Invoice", "Proforma Invoice"):
		payments = frappe.db.sql(
			"""
			SELECT pe.reference_no, pe.posting_date, per.allocated_amount
			FROM `tabPayment Entry Reference` per
			INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
			WHERE pe.docstatus = 1
			  AND per.reference_doctype = %s
			  AND per.reference_name = %s
			ORDER BY pe.posting_date ASC, pe.name ASC
			""",
			(payment_ref_doctype, reference_name),
			as_dict=True,
		)

	base = {
		"project": project,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"payment_certificate": payment_certificate,
		"proforma_date": proforma_date,
		"tax_invoice_date": tax_invoice_date,
		"invoice_no": invoice_no,
		"invoice_type": invoice_type,
		"amount": amount,
	}

	if not payments:
		return [{**base, "cheque_no": "", "cheque_date": "", "cheque_amount": 0.0}]

	return [
		{
			**base,
			"cheque_no": pe.reference_no or "",
			"cheque_date": pe.posting_date,
			"cheque_amount": flt(pe.allocated_amount),
		}
		for pe in payments
	]


def _build_summary(project: str, invoice_rows: list[dict]) -> dict:
	seen_invoices = set()
	total_invoice_amount = 0.0
	for row in invoice_rows:
		if row["invoice_no"] not in seen_invoices:
			total_invoice_amount += row["amount"]
			seen_invoices.add(row["invoice_no"])

	total_received_amount = sum(row["cheque_amount"] for row in invoice_rows)
	balance = total_invoice_amount - total_received_amount

	retention_amount = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(ABS(sii.amount)), 0) AS total
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.project = %s
		  AND si.docstatus = 1
		  AND sii.item_code = 'RETENTION-DEDUCTION'
		""",
		project,
	)[0][0] or 0.0

	if retention_amount == 0.0:
		sales_invoices = frappe.db.get_all(
			"Sales Invoice",
			filters={"project": project, "docstatus": 1},
			fields=["custom_retention_amount"],
		)
		retention_amount = sum(flt(si.custom_retention_amount) for si in sales_invoices)

	any_deduction = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(ABS(sii.amount)), 0) AS total
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.project = %s
		  AND si.docstatus = 1
		  AND sii.item_code = 'ADVANCE-DEDUCTION'
		""",
		project,
	)[0][0] or 0.0

	return {
		"total_invoice_amount": total_invoice_amount,
		"total_received_amount": total_received_amount,
		"balance": balance,
		"retention_amount": retention_amount,
		"any_deduction": any_deduction,
	}


def _build_expenses(project: str) -> list[dict]:
	gl_breakdown = get_project_cost_breakdown(project) or {}

	material_cost = flt(gl_breakdown.get("material", 0.0))
	labor_cost = flt(gl_breakdown.get("labor", 0.0))
	subcontractor_cost = flt(gl_breakdown.get("subcontractor", 0.0))
	commission = flt(gl_breakdown.get("commission", 0.0))
	other_cost = flt(gl_breakdown.get("other", 0.0)) + flt(gl_breakdown.get("unallocated", 0.0))
	# Use summary total — unallocated is already included in category rows (e.g. subcontractor)
	total_project_cost = flt(gl_breakdown.get("total", 0.0))

	def _expense_row(idx, label, cost, category_key):
		return {
			"idx": idx,
			"category": label,
			"cost": cost,
			"category_key": category_key,
			"expandable": cost > 0,
		}

	return [
		_expense_row(1, _("Material Cost"), material_cost, "material"),
		_expense_row(2, _("Labour Cost"), labor_cost, "labor"),
		_expense_row(3, _("Subcontractor Cost"), subcontractor_cost, "subcontractor"),
		_expense_row(4, _("Commission"), commission, "commission"),
		_expense_row(5, _("Other/Unallocated Cost"), other_cost, "other"),
		{"idx": 6, "category": _("Total Project Cost"), "cost": total_project_cost, "is_total": True, "expandable": False},
	]


@frappe.whitelist()
def get_soa_expense_breakdown(project: str, category: str) -> dict:
	from construction_management.api.project_soa_cost_detail import get_soa_expense_breakdown as _get_breakdown

	return _get_breakdown(project, category)


@frappe.whitelist()
def get_project_soa_follow_ups(project: str) -> list[dict]:
	if not project:
		frappe.throw(_("Project is required"))

	fields = [
		"name",
		"project",
		"reference_doctype",
		"reference_name",
		"payment_certificate",
		"follow_up_date",
		"status",
		"remarks",
		"attachment",
		"modified",
	]
	if frappe.db.has_column("Project SOA Follow Up", "pc_amount"):
		fields.append("pc_amount")

	return frappe.get_all(
		"Project SOA Follow Up",
		filters={"project": project},
		fields=fields,
		order_by="follow_up_date desc, modified desc",
	)


@frappe.whitelist()
def create_project_soa_follow_up(
	project: str,
	reference_doctype: str,
	reference_name: str,
	follow_up_date: str = None,
	status: str = "Open",
	remarks: str = "",
	attachment: str = "",
	payment_certificate: str = "",
	pc_amount=None,
) -> dict:
	if not project or not reference_doctype or not reference_name:
		frappe.throw(_("Project, reference doctype, and reference name are required"))

	doc = frappe.new_doc("Project SOA Follow Up")
	doc.project = project
	doc.reference_doctype = reference_doctype
	doc.reference_name = reference_name
	doc.payment_certificate = payment_certificate or ""
	doc.follow_up_date = follow_up_date or frappe.utils.today()
	doc.status = status or "Open"
	doc.remarks = remarks or ""
	doc.attachment = attachment or ""
	if pc_amount is not None and frappe.get_meta("Project SOA Follow Up").has_field("pc_amount"):
		doc.pc_amount = flt(pc_amount)
	doc.insert(ignore_permissions=True)

	return {"name": doc.name}
