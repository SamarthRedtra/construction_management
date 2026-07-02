# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt
from typing import Optional


def is_opening_journal_entry(je) -> bool:
	if getattr(je, "voucher_type", None) == "Opening Entry":
		return True
	return getattr(je, "is_opening", None) == "Yes"


def get_boq_sales_accounts(company: str) -> dict:
	if not company or not frappe.db.exists("BOQ Settings", company):
		return {}
	return frappe.db.get_value(
		"BOQ Settings",
		company,
		["advance_account", "retention_account"],
		as_dict=True,
	) or {}


def get_row_collected_amount(row) -> float:
	"""Net amount that increases advance/retention pool for this JE account row."""
	root_type = frappe.db.get_value("Account", row.account, "root_type")
	if root_type in ("Liability", "Equity", "Income"):
		return flt(row.credit) - flt(row.debit)
	return flt(row.debit) - flt(row.credit)


def _advance_reference(je_name: str, project: str) -> str:
	return f"{je_name}::{project}"


def upsert_boq_advance_from_opening(je, row, amount: float):
	reference = _advance_reference(je.name, row.project)
	precision = frappe.get_precision("BOQ Advance Payment", "amount") or 2
	amount = flt(amount, precision)

	existing = frappe.db.get_value(
		"BOQ Advance Payment",
		{"reference": reference, "docstatus": ["!=", 2]},
		"name",
	)

	if existing:
		bap = frappe.get_doc("BOQ Advance Payment", existing)
		if bap.docstatus == 1 and flt(bap.amount) == amount:
			return bap.name
		if bap.docstatus == 1:
			bap.flags.ignore_permissions = True
			bap.cancel()

	bap = frappe.new_doc("BOQ Advance Payment")
	bap.project = row.project
	bap.bill_no = row.get("bill_no")
	bap.boq_item = row.get("boq_item")
	bap.amount = amount
	bap.reference = reference
	bap.date = je.posting_date
	bap.remarks = _("Opening balance from Journal Entry {0}").format(je.name)
	bap.flags.ignore_permissions = True
	bap.insert()
	bap.submit()
	return bap.name


def sync_opening_journal_entry(doc, method=None):
	"""Create BOQ Advance Payment rows from opening Journal Entry account lines."""
	je = doc if getattr(doc, "doctype", None) == "Journal Entry" else frappe.get_doc("Journal Entry", doc)

	if not is_opening_journal_entry(je) or je.docstatus != 1:
		return

	accounts = get_boq_sales_accounts(je.company)
	advance_account = accounts.get("advance_account")
	if not advance_account:
		return

	for row in je.get("accounts") or []:
		if row.account != advance_account or not row.project:
			continue

		amount = get_row_collected_amount(row)
		if amount <= 0:
			continue

		upsert_boq_advance_from_opening(je, row, amount)


def cancel_opening_journal_entry(doc, method=None):
	"""Cancel BOQ Advance Payment rows linked to an opening Journal Entry."""
	je = doc if getattr(doc, "doctype", None) == "Journal Entry" else frappe.get_doc("Journal Entry", doc)

	if not is_opening_journal_entry(je):
		return

	linked = frappe.get_all(
		"BOQ Advance Payment",
		filters=[
			["reference", "like", f"{je.name}%"],
			["docstatus", "=", 1],
		],
		pluck="name",
	)

	for name in linked:
		bap = frappe.get_doc("BOQ Advance Payment", name)
		bap.flags.ignore_permissions = True
		bap.cancel()


def get_opening_retention_balance(project: str, company: Optional[str] = None) -> float:
	"""Sum opening JE balances on BOQ Settings retention_account for a project."""
	if not project:
		return 0.0

	if not company:
		company = frappe.db.get_value("Project", project, "company")
	if not company:
		return 0.0

	accounts = get_boq_sales_accounts(company)
	retention_account = accounts.get("retention_account")
	if not retention_account:
		return 0.0

	result = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(
			CASE
				WHEN acc.root_type IN ('Liability', 'Equity', 'Income') THEN gle.credit - gle.debit
				ELSE gle.debit - gle.credit
			END
		), 0) AS total
		FROM `tabGL Entry` gle
		INNER JOIN `tabJournal Entry` je
			ON je.name = gle.voucher_no AND gle.voucher_type = 'Journal Entry'
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.is_cancelled = 0
			AND gle.project = %s
			AND gle.company = %s
			AND gle.account = %s
			AND je.docstatus = 1
			AND (je.is_opening = 'Yes' OR je.voucher_type = 'Opening Entry')
		""",
		(project, company, retention_account),
	)

	return flt(result[0][0]) if result else 0.0
