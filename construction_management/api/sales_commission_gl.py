# Copyright (c) 2026, Construction Management
# License: MIT

"""Sales commission accrual / settlement GL helpers."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

COMMISSION_ACCRUAL_REMARK_PREFIX = "Sales Commission Accrual for Sales Invoice "


def commission_accrual_remark(si_name: str) -> str:
	return f"{COMMISSION_ACCRUAL_REMARK_PREFIX}{si_name}"


def get_commission_posting_accounts(company: str) -> dict:
	"""Return expense + payable accounts from BOQ Settings for the company."""
	if not company or not frappe.db.exists("DocType", "BOQ Settings"):
		return {"expense_account": None, "payable_account": None}

	row = frappe.db.get_value(
		"BOQ Settings",
		company,
		["sales_person_commission_account", "sales_commission_payable_account"],
		as_dict=True,
	) or {}
	return {
		"expense_account": row.get("sales_person_commission_account"),
		"payable_account": row.get("sales_commission_payable_account"),
	}


def require_commission_posting_accounts(company: str) -> dict:
	accounts = get_commission_posting_accounts(company)
	missing = []
	if not accounts.get("expense_account"):
		missing.append(_("Sales Commission Account"))
	if not accounts.get("payable_account"):
		missing.append(_("Sales Commission Payable Account"))
	if missing:
		frappe.throw(
			_("Set {0} in BOQ Settings for company {1} before booking sales commission.").format(
				frappe.bold(", ".join(missing)), frappe.bold(company)
			),
			title=_("Commission Accounts Missing"),
		)
	return accounts


def create_or_update_commission_accrual_jv(
	si_name: str,
	amount: float,
	project: str | None = None,
	company: str | None = None,
	posting_date=None,
) -> str | None:
	"""
	Book Dr Sales Commission / Cr Sales Commission Payable when commission is recorded.
	Stores JV name on Sales Invoice.custom_commission_accrual_jv.
	Returns JV name or None when amount is zero.
	"""
	amount = flt(amount)
	if amount <= 0:
		cancel_commission_accrual_jv(si_name)
		return None

	si = frappe.db.get_value(
		"Sales Invoice",
		si_name,
		["name", "company", "project", "posting_date", "cost_center", "custom_commission_accrual_jv"],
		as_dict=True,
	)
	if not si:
		frappe.throw(_("Sales Invoice {0} not found").format(si_name))

	company = company or si.company
	project = project or si.project
	accounts = require_commission_posting_accounts(company)

	existing = si.get("custom_commission_accrual_jv")
	if existing and frappe.db.exists("Journal Entry", existing):
		docstatus = frappe.db.get_value("Journal Entry", existing, "docstatus")
		if docstatus == 1:
			# Already booked — keep unless force recreate after cancel path.
			return existing
		if docstatus == 0:
			frappe.delete_doc("Journal Entry", existing, force=1, ignore_permissions=True)
		# cancelled: clear and recreate
		frappe.db.set_value(
			"Sales Invoice", si_name, "custom_commission_accrual_jv", None, update_modified=False
		)

	cost_center = si.cost_center
	if not cost_center and project:
		cost_center = frappe.db.get_value("Project", project, "cost_center")
	if not cost_center:
		cost_center = frappe.get_cached_value("Company", company, "cost_center")

	remark = commission_accrual_remark(si_name)
	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Journal Entry"
	je.company = company
	je.posting_date = getdate(posting_date or si.posting_date or today())
	je.user_remark = remark
	je.bill_no = si_name

	common = {"project": project, "cost_center": cost_center, "user_remark": remark}
	je.append(
		"accounts",
		{
			"account": accounts["expense_account"],
			"debit_in_account_currency": amount,
			**common,
		},
	)

	payable_row = {
		"account": accounts["payable_account"],
		"credit_in_account_currency": amount,
		**common,
	}
	# Payable-type accounts require party; use Sales Person employee when available.
	payable_account_type = frappe.get_cached_value(
		"Account", accounts["payable_account"], "account_type"
	)
	if payable_account_type in ("Receivable", "Payable"):
		employee = _get_sales_invoice_commission_employee(si_name)
		if employee:
			payable_row.update({"party_type": "Employee", "party": employee})
		else:
			je.party_not_required = 1

	je.append("accounts", payable_row)

	je.flags.ignore_permissions = True
	je.insert()
	je.submit()

	frappe.db.set_value(
		"Sales Invoice",
		si_name,
		"custom_commission_accrual_jv",
		je.name,
		update_modified=False,
	)
	return je.name


def cancel_commission_accrual_jv(si_name: str) -> None:
	"""Cancel linked commission accrual JV and clear SI link."""
	if not si_name:
		return
	if not frappe.db.has_column("Sales Invoice", "custom_commission_accrual_jv"):
		return

	jv_name = frappe.db.get_value("Sales Invoice", si_name, "custom_commission_accrual_jv")
	# Clear link first so JV cancel is not blocked by Sales Invoice Link field.
	frappe.db.set_value(
		"Sales Invoice", si_name, "custom_commission_accrual_jv", None, update_modified=False
	)

	if not jv_name or not frappe.db.exists("Journal Entry", jv_name):
		return

	docstatus = frappe.db.get_value("Journal Entry", jv_name, "docstatus")
	if docstatus == 1:
		je = frappe.get_doc("Journal Entry", jv_name)
		je.flags.ignore_permissions = True
		je.cancel()
	elif docstatus == 0:
		frappe.delete_doc("Journal Entry", jv_name, force=1, ignore_permissions=True)


def is_commission_accrual_journal(voucher_no: str | None) -> bool:
	"""True when JV is a sales-commission accrual booking (exclude from 'received' ledgers)."""
	if not voucher_no:
		return False
	remark = frappe.db.get_value("Journal Entry", voucher_no, "user_remark") or ""
	if remark.startswith(COMMISSION_ACCRUAL_REMARK_PREFIX):
		return True
	if frappe.db.has_column("Sales Invoice", "custom_commission_accrual_jv"):
		return bool(
			frappe.db.exists(
				"Sales Invoice", {"custom_commission_accrual_jv": voucher_no}
			)
		)
	return False


def _get_sales_invoice_commission_employee(si_name: str) -> str | None:
	"""Best-effort Employee from Sales Team / Sales Person on the invoice."""
	rows = frappe.get_all(
		"Sales Team",
		filters={"parent": si_name, "parenttype": "Sales Invoice"},
		fields=["sales_person"],
		order_by="idx asc",
		limit=1,
	)
	if not rows or not rows[0].sales_person:
		return None
	return frappe.db.get_value("Sales Person", rows[0].sales_person, "employee")


def _get_sales_invoice_commission_amount(si_name: str) -> float:
	"""Prefer Sales Team incentives; fall back to SI.total_commission."""
	incentives = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(incentives), 0)
		FROM `tabSales Team`
		WHERE parent = %s AND parenttype = 'Sales Invoice'
		""",
		(si_name,),
	)[0][0]
	amount = flt(incentives)
	if amount > 0:
		return amount
	return flt(frappe.db.get_value("Sales Invoice", si_name, "total_commission"))


def backfill_commission_accrual_jvs(company: str | None = None) -> dict:
	"""
	Create missing accrual JVs for Sales Invoices that already have
	custom_commission_recorded=1 but no submitted commission accrual JV.

	Skips companies where BOQ commission accounts are not configured.
	"""
	if not frappe.db.has_column("Sales Invoice", "custom_commission_recorded"):
		return {"skipped": 0, "created": 0, "errors": 0, "companies_skipped": []}

	if not frappe.db.has_column("Sales Invoice", "custom_commission_accrual_jv"):
		return {"skipped": 0, "created": 0, "errors": 0, "companies_skipped": []}

	companies = [company] if company else frappe.get_all("BOQ Settings", pluck="name")
	stats = {"skipped": 0, "created": 0, "errors": 0, "companies_skipped": []}

	for co in companies:
		accounts = get_commission_posting_accounts(co)
		if not accounts.get("expense_account") or not accounts.get("payable_account"):
			stats["companies_skipped"].append(co)
			continue

		rows = frappe.db.sql(
			"""
			SELECT name, project, company, posting_date, custom_commission_accrual_jv
			FROM `tabSales Invoice`
			WHERE docstatus = 1
			  AND IFNULL(is_return, 0) = 0
			  AND IFNULL(custom_commission_recorded, 0) = 1
			  AND company = %s
			ORDER BY posting_date ASC, name ASC
			""",
			(co,),
			as_dict=True,
		)

		for row in rows:
			existing = row.custom_commission_accrual_jv
			if existing and frappe.db.exists("Journal Entry", existing):
				if frappe.db.get_value("Journal Entry", existing, "docstatus") == 1:
					stats["skipped"] += 1
					continue

			amount = _get_sales_invoice_commission_amount(row.name)
			if amount <= 0:
				stats["skipped"] += 1
				continue

			try:
				jv = create_or_update_commission_accrual_jv(
					si_name=row.name,
					amount=amount,
					project=row.project,
					company=row.company,
					posting_date=row.posting_date,
				)
				if jv:
					stats["created"] += 1
				else:
					stats["skipped"] += 1
			except Exception:
				stats["errors"] += 1
				frappe.log_error(
					title=f"Commission accrual backfill failed: {row.name}",
					message=frappe.get_traceback(),
				)

	return stats
