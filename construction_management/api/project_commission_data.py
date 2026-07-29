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
	# Commission Payment Entry details are embedded in their Sales Invoice row.
	# Keeping a separate row made a paid commission appear twice in the ledger.
	rows = si_rows + jv_rows

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

	commission_received_total = 0.0
	seen_payouts = set()
	for row in ledger_rows:
		if row["row_type"] == ROW_TYPE_JV:
			commission_received_total += flt(row.get("commission_received"))
		elif row["row_type"] == ROW_TYPE_SI:
			for payout in row.get("commission_payouts") or []:
				payout_name = payout.get("name")
				if payout_name and payout_name not in seen_payouts:
					commission_received_total += flt(payout.get("paid_amount"))
					seen_payouts.add(payout_name)
		elif row["row_type"] == ROW_TYPE_PE:
			commission_received_total += flt(row.get("commission_received"))
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
	"""Build invoice commission rows, including invoices without a Sales Team row.

	The Redtra report is based on ``Sales Team``.  Some historical invoices have
	the commission fields populated directly on the Sales Invoice but no Sales
	Team child row; excluding those invoices made their commission invisible.
	"""
	entries = []
	if _redtra_available():
		try:
			from redtra_customisation.redtra_customisation.report.sales_person_commission_payment_summary.sales_person_commission_payment_summary import (
				get_entries,
			)
			entries = get_entries({
				"company": company,
				"project": project,
				"doc_type": "Sales Invoice",
			}) or []
		except ImportError:
			pass

	# Preserve the Sales Team rows from Redtra, then supplement invoices whose
	# commission was stored directly on the invoice (for example ACC-SINV-2026-00214).
	reported_invoices = {entry.get("source_name") for entry in entries if entry.get("source_name")}
	entries.extend(_get_unreported_invoice_commission_entries(project, company, reported_invoices))

	rows = []
	pay_shown_for = set()
	payout_resolution = _get_commission_payout_resolution(project, company, entries)
	paid_out_invoices = set(payout_resolution["invoice_by_payment"].values())
	payouts_by_invoice = _get_submitted_commission_payouts_by_invoice(payout_resolution)
	for entry in entries:
		invoice_name = entry.get("source_name")
		payment = _get_si_payment_summary(invoice_name)
		commission_amount = flt(entry.get("commission_amount"))
		employee = entry.get("employee") or ""
		pay_key = (invoice_name, entry.get("sales_person") or "")
		already_paid = invoice_name in paid_out_invoices
		payouts = payouts_by_invoice.get(invoice_name, [])
		payout_amount = sum(flt(payout.get("paid_amount")) for payout in payouts)
		payout_cheques = ", ".join(
			str(payout.get("reference_no") or "") for payout in payouts if payout.get("reference_no")
		)

		# One row per invoice + sales person, even when its receipt has multiple
		# Payment Entry references (including small round-off adjustments).
		show_pay = (
			pay_key not in pay_shown_for
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
			"commission_received": payout_amount,
			"commission_cheque_no": payout_cheques,
			"commission_payouts": payouts,
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


def _get_unreported_invoice_commission_entries(
	project: str, company: str, reported_invoices: set[str]
) -> list[dict]:
	"""Return submitted commission invoices absent from the Sales Team report."""
	if not frappe.get_meta("Sales Invoice").has_field("total_commission"):
		return []

	fields = [
		"name",
		"posting_date",
		"company",
		"project",
		"base_total",
		"total_commission",
	]
	meta = frappe.get_meta("Sales Invoice")
	if meta.has_field("commission_rate"):
		fields.append("commission_rate")
	if meta.has_field("custom_sales_order"):
		fields.append("custom_sales_order")

	invoices = frappe.get_all(
		"Sales Invoice",
		filters={"project": project, "company": company, "docstatus": 1},
		fields=fields,
		order_by="posting_date asc, name asc",
	)

	entries = []
	for invoice in invoices:
		if invoice.name in reported_invoices or flt(invoice.total_commission) <= 0:
			continue
		sales_person, employee, employee_name = _get_invoice_commission_recipient(invoice)
		entries.append({
			"source_name": invoice.name,
			"posting_date": invoice.posting_date,
			"company": invoice.company,
			"project": invoice.project,
			"amount": flt(invoice.base_total),
			"sales_person": sales_person,
			"employee": employee,
			"employee_name": employee_name,
			"commission_rate": flt(invoice.get("commission_rate")),
			"commission_amount": flt(invoice.total_commission),
		})
	return entries


def _get_invoice_commission_recipient(invoice) -> tuple[str, str, str]:
	"""Find the sales person/employee on an invoice, then on its linked order."""
	parent_names = [invoice.name]
	parent_types = ["Sales Invoice"]
	if invoice.get("custom_sales_order"):
		parent_names.append(invoice.custom_sales_order)
		parent_types.append("Sales Order")

	for parent, parenttype in zip(parent_names, parent_types):
		row = frappe.db.sql(
			"""
			SELECT st.sales_person, sp.employee, emp.employee_name
			FROM `tabSales Team` st
			LEFT JOIN `tabSales Person` sp ON sp.name = st.sales_person
			LEFT JOIN `tabEmployee` emp ON emp.name = sp.employee
			WHERE st.parent = %s AND st.parenttype = %s
			ORDER BY st.idx ASC
			LIMIT 1
			""",
			(parent, parenttype),
			as_dict=True,
		)
		if row:
			return row[0].sales_person or "", row[0].employee or "", row[0].employee_name or ""

	return "", "", ""


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


def _get_paid_out_commission_invoices(
	project: str, company: str | None = None, commission_entries: list[dict] | None = None
) -> set[str]:
	"""Invoices with a commission payout, including safely inferred legacy payouts."""
	return set(_get_commission_payout_resolution(project, company, commission_entries)["invoice_by_payment"].values())


def _get_submitted_commission_payouts_by_invoice(resolution: dict) -> dict[str, list[dict]]:
	"""Group submitted commission payout Payment Entries by their invoice."""
	payouts_by_invoice = {}
	for payout in resolution.get("rows") or []:
		invoice = resolution.get("invoice_by_payment", {}).get(payout.name)
		if not invoice or payout.docstatus != 1:
			continue
		payouts_by_invoice.setdefault(invoice, []).append({
			"name": payout.name,
			"posting_date": payout.posting_date,
			"creation": payout.get("creation"),
			"reference_no": payout.reference_no or "",
			"paid_amount": flt(payout.paid_amount),
		})
	return payouts_by_invoice


def _get_commission_payout_resolution(
	project: str, company: str | None = None, commission_entries: list[dict] | None = None
) -> dict:
	"""Map commission Payment Entries to invoices.

	New Payment Entries carry a dedicated flag and invoice remark.  Older entries
	were sometimes created without either.  Such a legacy entry is accepted only
	when its project, employee and amount identify exactly one unpaid invoice;
	this avoids treating ordinary employee payments as commission.
	"""
	if not project:
		return {"rows": [], "invoice_by_payment": {}}

	has_flag = _pe_has_commission_payout_flag()
	flag_column = ", IFNULL(custom_is_commission_payout, 0) AS is_commission_payout" if has_flag else ", 0 AS is_commission_payout"
	company_clause = " AND company = %s" if company else ""
	params = [project]
	if company:
		params.append(company)
	rows = frappe.db.sql(
		f"""
		SELECT name, docstatus, posting_date, creation, party AS employee, paid_amount,
			reference_no, remarks, company{flag_column}
		FROM `tabPayment Entry`
		WHERE project = %s{company_clause}
		  AND docstatus < 2
		  AND payment_type = 'Pay'
		  AND party_type = 'Employee'
		ORDER BY posting_date ASC, name ASC
		""",
		params,
		as_dict=True,
	)

	invoice_by_payment = {}
	used_invoices = set()
	for row in rows:
		is_marked = flt(row.get("is_commission_payout")) == 1 or (
			COMMISSION_PAYOUT_REMARK_PREFIX in (row.get("remarks") or "")
		)
		if not is_marked:
			continue
		invoice = _extract_invoice_from_commission_pe(row)
		if invoice:
			invoice_by_payment[row.name] = invoice
			used_invoices.add(invoice)

	# Match only unmarked legacy entries where there is one exact invoice match.
	# This supports historical entries such as MRG-PE-00450 without broadening
	# the definition of a commission payout to every employee payment.
	candidates_by_key = {}
	for entry in commission_entries or []:
		invoice = entry.get("source_name") or entry.get("invoice_no")
		employee = entry.get("employee") or ""
		amount = flt(entry.get("commission_amount"))
		if not invoice or not employee or amount <= 0 or invoice in used_invoices:
			continue
		key = (employee, round(amount, 2))
		candidates_by_key.setdefault(key, []).append(invoice)

	for row in rows:
		if row.name in invoice_by_payment:
			continue
		if flt(row.get("is_commission_payout")) or COMMISSION_PAYOUT_REMARK_PREFIX in (row.get("remarks") or ""):
			continue
		key = (row.get("employee") or "", round(flt(row.get("paid_amount")), 2))
		matches = list(dict.fromkeys(candidates_by_key.get(key, [])))
		if len(matches) == 1 and matches[0] not in used_invoices:
			invoice_by_payment[row.name] = matches[0]
			used_invoices.add(matches[0])

	return {"rows": rows, "invoice_by_payment": invoice_by_payment}


def _build_commission_payout_payment_rows(
	project: str, company: str, si_rows: list[dict] | None = None
) -> list[dict]:
	"""Commission payout Payment Entries — shown as Commission Received."""
	resolution = _get_commission_payout_resolution(project, company, si_rows)
	rows = [
		row for row in resolution["rows"]
		if row.docstatus == 1 and row.name in resolution["invoice_by_payment"]
	]

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
			"invoice_no": resolution["invoice_by_payment"].get(pe.name, ""),
			"invoice_type": "",
			"amount": 0.0,
			"cheque_no": "",
			"cheque_date": "",
			"cheque_amount": 0.0,
			"commission_pct": 0.0,
			"commission_amount": flt(pe.paid_amount),
			"commission_received": flt(pe.paid_amount),
			"commission_cheque_no": pe.reference_no or "",
			"remarks": pe.remarks or _commission_payout_remark(
				resolution["invoice_by_payment"].get(pe.name, "")
			),
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


def _get_si_payment_summary(invoice_name: str) -> dict:
	"""Collapse all receipt references into one display value for an invoice."""
	payments = _get_si_payments(invoice_name)
	if not payments:
		return {"reference_no": "", "posting_date": "", "allocated_amount": 0.0}

	primary = max(payments, key=lambda row: flt(row.get("allocated_amount")))
	return {
		"reference_no": primary.get("reference_no") or "",
		"posting_date": primary.get("posting_date") or "",
		"allocated_amount": sum(flt(row.get("allocated_amount")) for row in payments),
	}


def _get_je_reference_no(journal_entry: str) -> str:
	if not journal_entry:
		return ""
	cheque_no = frappe.db.get_value("Journal Entry", journal_entry, "cheque_no")
	if cheque_no:
		return cheque_no
	if frappe.get_meta("Journal Entry").has_field("reference_no"):
		return frappe.db.get_value("Journal Entry", journal_entry, "reference_no") or ""
	return ""
