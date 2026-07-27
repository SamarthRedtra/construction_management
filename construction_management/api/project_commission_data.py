# Copyright (c) 2026, Construction Management
# License: MIT

"""Project-wise commission ledger — combines Sales Invoice accrual + JV payouts."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from construction_management.api.project_boq_scope import fetch_scope_boq_items, resolve_boq_source_project


ROW_TYPE_SI = "Sales Invoice"
ROW_TYPE_JV = "Journal Entry"
ROW_TYPE_PE = "Payment Entry"

COMMISSION_PAYOUT_REMARK_PREFIX = "Commission payout for Sales Invoice "


def build_services(project: str) -> tuple[list[dict], float, str]:
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


def build_commission_ledger(project: str) -> tuple[list[dict], dict]:
	company = frappe.db.get_value("Project", project, "company")
	if not company:
		return [], {"redtra_missing": False, "commission_account_missing": True}

	si_rows = _build_sales_invoice_commission_rows(project, company)
	jv_rows = _build_journal_commission_rows(project, company)
	pe_rows = _build_commission_payout_payment_rows(project, company)
	rows = si_rows + jv_rows + pe_rows

	rows.sort(key=lambda row: (
		getdate(row.get("sort_date") or "1900-01-01"),
		row.get("row_type") or "",
		row.get("invoice_no") or row.get("source_name") or "",
	))

	invoice_serial = 0
	seen_invoices = set()
	for row in rows:
		if row["row_type"] == ROW_TYPE_SI and row.get("invoice_no"):
			if row["invoice_no"] not in seen_invoices:
				invoice_serial += 1
				seen_invoices.add(row["invoice_no"])
			row["invoice_serial_no"] = invoice_serial
		else:
			row["invoice_serial_no"] = ""

	for idx, row in enumerate(rows, start=1):
		row["serial_no"] = idx
		row.pop("sort_date", None)

	meta = {
		"redtra_missing": not _redtra_available(),
		"commission_account_missing": not _get_commission_account(company),
	}
	return rows, meta


def build_summary(project: str, ledger_rows: list[dict]) -> dict:
	seen_invoice_commission = set()
	commission_total = 0.0
	seen_invoices = set()
	total_invoice_amount = 0.0

	for row in ledger_rows:
		if row["row_type"] == ROW_TYPE_SI:
			invoice_no = row.get("invoice_no")
			if invoice_no and invoice_no not in seen_invoices:
				total_invoice_amount += flt(row.get("amount"))
				seen_invoices.add(invoice_no)

			key = (invoice_no, row.get("sales_person"), row.get("commission_amount"))
			if key not in seen_invoice_commission:
				commission_total += flt(row.get("commission_amount"))
				seen_invoice_commission.add(key)

	total_received_amount = sum(
		flt(row.get("cheque_amount"))
		for row in ledger_rows
		if row["row_type"] == ROW_TYPE_SI
	)
	balance = total_invoice_amount - total_received_amount

	commission_received_total = sum(
		flt(row.get("commission_received"))
		for row in ledger_rows
		if row["row_type"] in (ROW_TYPE_JV, ROW_TYPE_PE)
	)
	commission_balance = commission_total - commission_received_total

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
		"commission_total": commission_total,
		"commission_received_total": commission_received_total,
		"commission_balance": commission_balance,
		"retention_amount": retention_amount,
		"any_deduction": any_deduction,
	}


def _redtra_available() -> bool:
	try:
		import redtra_customisation  # noqa: F401
		return True
	except ImportError:
		return False


def _get_commission_account(company: str) -> str | None:
	if not frappe.db.exists("DocType", "BOQ Settings"):
		return None
	return frappe.db.get_value("BOQ Settings", company, "sales_person_commission_account")


def _build_sales_invoice_commission_rows(project: str, company: str) -> list[dict]:
	if not _redtra_available():
		return []

	try:
		from redtra_customisation.redtra_customisation.report.sales_person_commission_payment_summary.sales_person_commission_payment_summary import (
			get_entries,
		)
	except ImportError:
		return []

	entries = get_entries({
		"company": company,
		"project": project,
		"doc_type": "Sales Invoice",
	}) or []

	rows = []
	pay_shown_for = set()
	paid_out_invoices = _get_paid_out_commission_invoices(project)
	for entry in entries:
		invoice_name = entry.get("source_name")
		payments = _get_si_payments(invoice_name)
		payment_lines = payments or [{"reference_no": "", "posting_date": "", "allocated_amount": 0.0}]
		commission_amount = flt(entry.get("commission_amount"))
		employee = entry.get("employee") or ""
		pay_key = (invoice_name, entry.get("sales_person") or "")
		already_paid = invoice_name in paid_out_invoices

		for idx, payment in enumerate(payment_lines):
			# One Pay action per invoice + sales person (not per customer cheque line).
			show_pay = (
				idx == 0
				and pay_key not in pay_shown_for
				and commission_amount > 0
				and bool(employee)
				and not already_paid
			)
			if show_pay:
				pay_shown_for.add(pay_key)

			rows.append({
				"row_type": ROW_TYPE_SI,
				"sort_date": entry.get("posting_date"),
				"invoice_date": entry.get("posting_date"),
				"invoice_serial_no": "",
				"invoice_no": invoice_name,
				"invoice_type": "Tax Invoice",
				"amount": flt(entry.get("amount")),
				"cheque_no": payment.get("reference_no") or "",
				"cheque_date": payment.get("posting_date") or "",
				"cheque_amount": flt(payment.get("allocated_amount")),
				"commission_pct": flt(entry.get("commission_rate")),
				"commission_amount": commission_amount,
				"commission_received": 0.0,
				"commission_cheque_no": "",
				"remarks": "",
				"sales_person": entry.get("sales_person") or "",
				"employee": employee,
				"employee_name": entry.get("employee_name") or "",
				"company": entry.get("company") or company,
				"project": project,
				"show_pay": show_pay,
				"commission_paid": already_paid,
				"source_name": invoice_name,
			})

	return rows


def _commission_payout_remark(invoice_no: str) -> str:
	return f"{COMMISSION_PAYOUT_REMARK_PREFIX}{invoice_no}"


def _pe_has_commission_payout_flag() -> bool:
	return frappe.db.has_column("Payment Entry", "custom_is_commission_payout")


def _extract_invoice_from_commission_pe(row) -> str | None:
	"""Resolve Sales Invoice name from a commission payout Payment Entry row."""
	ref = (row.get("reference_no") or "").strip()
	if ref and frappe.db.exists("Sales Invoice", ref):
		return ref

	remarks = row.get("remarks") or ""
	prefix = COMMISSION_PAYOUT_REMARK_PREFIX
	if prefix in remarks:
		rest = remarks.split(prefix, 1)[1].strip()
		invoice = rest.split()[0] if rest else ""
		if invoice and frappe.db.exists("Sales Invoice", invoice):
			return invoice
	return None


def _get_paid_out_commission_invoices(project: str) -> set[str]:
	"""Invoices that already have a commission Payment Entry (draft or submitted)."""
	if not project:
		return set()

	has_flag = _pe_has_commission_payout_flag()
	if has_flag:
		where_extra = """
		  AND (
				IFNULL(custom_is_commission_payout, 0) = 1
				OR remarks LIKE %s
		  )
		"""
		params = (project, f"{COMMISSION_PAYOUT_REMARK_PREFIX}%")
		select_cols = "reference_no, remarks, custom_is_commission_payout"
	else:
		where_extra = " AND remarks LIKE %s "
		params = (project, f"{COMMISSION_PAYOUT_REMARK_PREFIX}%")
		select_cols = "reference_no, remarks"

	rows = frappe.db.sql(
		f"""
		SELECT {select_cols}
		FROM `tabPayment Entry`
		WHERE project = %s
		  AND docstatus < 2
		  AND payment_type = 'Pay'
		  AND party_type = 'Employee'
		  {where_extra}
		""",
		params,
		as_dict=True,
	)

	paid = set()
	for row in rows:
		invoice = _extract_invoice_from_commission_pe(row)
		if invoice:
			paid.add(invoice)
	return paid


def _build_commission_payout_payment_rows(project: str, company: str) -> list[dict]:
	"""Commission payout Payment Entries — shown as Commission Received."""
	has_flag = _pe_has_commission_payout_flag()
	if has_flag:
		where_extra = """
		  AND (
				IFNULL(custom_is_commission_payout, 0) = 1
				OR remarks LIKE %s
		  )
		"""
		params = (project, company, f"{COMMISSION_PAYOUT_REMARK_PREFIX}%")
	else:
		where_extra = " AND remarks LIKE %s "
		params = (project, company, f"{COMMISSION_PAYOUT_REMARK_PREFIX}%")

	rows = frappe.db.sql(
		f"""
		SELECT
			name,
			posting_date,
			party AS employee,
			paid_amount,
			reference_no,
			remarks,
			company
		FROM `tabPayment Entry`
		WHERE project = %s
		  AND company = %s
		  AND docstatus = 1
		  AND payment_type = 'Pay'
		  AND party_type = 'Employee'
		  {where_extra}
		ORDER BY posting_date ASC, name ASC
		""",
		params,
		as_dict=True,
	)

	result = []
	for pe in rows:
		employee = pe.employee or ""
		employee_name = (
			frappe.db.get_value("Employee", employee, "employee_name") if employee else ""
		)
		result.append({
			"row_type": ROW_TYPE_PE,
			"sort_date": pe.posting_date,
			"invoice_date": "",
			"invoice_serial_no": "",
			"invoice_no": "",
			"invoice_type": "",
			"amount": 0.0,
			"cheque_no": "",
			"cheque_date": "",
			"cheque_amount": 0.0,
			"commission_pct": 0.0,
			"commission_amount": flt(pe.paid_amount),
			"commission_received": flt(pe.paid_amount),
			"commission_cheque_no": pe.reference_no or "",
			"remarks": pe.remarks or "",
			"sales_person": "",
			"employee": employee,
			"employee_name": employee_name or "",
			"company": pe.company or company,
			"project": project,
			"show_pay": False,
			"source_name": pe.name,
		})
	return result


def get_commission_payment_entry_defaults(
	project: str,
	employee: str,
	commission_amount: float,
	invoice_no: str,
	company: str | None = None,
) -> dict:
	"""Prefill values for a commission payout Payment Entry."""
	from erpnext.accounts.doctype.journal_entry.journal_entry import get_default_bank_cash_account

	from construction_management.api.sales_commission_gl import require_commission_posting_accounts

	if not project:
		frappe.throw(_("Project is required"))
	if not employee:
		frappe.throw(_("Employee is required"))

	amount = flt(commission_amount)
	if amount <= 0:
		frappe.throw(_("Commission amount must be greater than zero"))

	company = company or frappe.db.get_value("Project", project, "company")
	if not company:
		frappe.throw(_("Company not found for project {0}").format(project))

	cost_center = frappe.db.get_value("Project", project, "cost_center")
	if not cost_center:
		cost_center = frappe.get_cached_value("Company", company, "cost_center")

	bank = get_default_bank_cash_account(company, "Bank") or {}
	if not bank.get("account"):
		bank = get_default_bank_cash_account(company, "Cash") or {}

	payable_account = require_commission_posting_accounts(company)["payable_account"]
	payable_currency = frappe.db.get_value("Account", payable_account, "account_currency")

	defaults = {
		"payment_type": "Pay",
		"party_type": "Employee",
		"party": employee,
		"company": company,
		"project": project,
		"paid_amount": amount,
		"received_amount": amount,
		"source_exchange_rate": 1,
		"target_exchange_rate": 1,
		"remarks": _commission_payout_remark(invoice_no),
		"custom_remarks": 1,
		"reference_no": invoice_no,
		"custom_is_commission_payout": 1,
		"paid_to": payable_account,
	}
	if payable_currency:
		defaults["paid_to_account_currency"] = payable_currency

	if cost_center:
		defaults["cost_center"] = cost_center

	if bank.get("account"):
		defaults["paid_from"] = bank["account"]
		if bank.get("account_currency"):
			defaults["paid_from_account_currency"] = bank["account_currency"]

	mode_of_payment = (
		frappe.db.get_value(
			"Mode of Payment Account",
			{"default_account": bank.get("account")},
			"parent",
		)
		if bank.get("account")
		else None
	)
	if mode_of_payment:
		defaults["mode_of_payment"] = mode_of_payment

	return defaults


def _build_journal_commission_rows(project: str, company: str) -> list[dict]:
	if not _redtra_available():
		return []

	try:
		from redtra_customisation.redtra_customisation.report.sales_person_commission_payment_summary.sales_person_commission_payment_summary import (
			get_journal_entries,
		)
	except ImportError:
		return []

	entries = get_journal_entries({
		"company": company,
		"project": project,
	}) or []

	from construction_management.api.sales_commission_gl import is_commission_accrual_journal

	rows = []
	for entry in entries:
		jv_name = entry.get("source_name")
		if is_commission_accrual_journal(jv_name):
			continue
		jv_amount = flt(entry.get("commission_amount"))
		rows.append({
			"row_type": ROW_TYPE_JV,
			"sort_date": entry.get("posting_date"),
			"invoice_date": "",
			"invoice_serial_no": "",
			"invoice_no": "",
			"invoice_type": "",
			"amount": 0.0,
			"cheque_no": "",
			"cheque_date": "",
			"cheque_amount": 0.0,
			"commission_pct": 0.0,
			"commission_amount": jv_amount,
			"commission_received": jv_amount,
			"commission_cheque_no": _get_je_reference_no(jv_name),
			"remarks": entry.get("user_remark") or "",
			"sales_person": "",
			"employee": entry.get("employee") or "",
			"employee_name": entry.get("employee_name") or "",
			"company": company,
			"project": project,
			"show_pay": False,
			"source_name": jv_name,
		})

	return rows


def _get_si_payments(invoice_name: str) -> list[dict]:
	if not invoice_name:
		return []
	return frappe.db.sql(
		"""
		SELECT pe.reference_no, pe.posting_date, per.allocated_amount
		FROM `tabPayment Entry Reference` per
		INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
		WHERE pe.docstatus = 1
		  AND per.reference_doctype = 'Sales Invoice'
		  AND per.reference_name = %s
		ORDER BY pe.posting_date ASC, pe.name ASC
		""",
		invoice_name,
		as_dict=True,
	)


def _get_je_reference_no(journal_entry: str) -> str:
	if not journal_entry:
		return ""
	cheque_no = frappe.db.get_value("Journal Entry", journal_entry, "cheque_no")
	if cheque_no:
		return cheque_no
	if frappe.get_meta("Journal Entry").has_field("reference_no"):
		return frappe.db.get_value("Journal Entry", journal_entry, "reference_no") or ""
	return ""
