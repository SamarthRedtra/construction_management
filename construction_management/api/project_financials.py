# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe.utils import flt

from construction_management.api.boq_opening_balance import get_boq_sales_accounts


@frappe.whitelist()
def get_project_journal_entries(project: str) -> dict:
	"""Return submitted Journal Entries with account lines for a project."""
	if not project:
		return {"summary": {}, "rows": [], "journal_entries": []}

	company = frappe.db.get_value("Project", project, "company")
	accounts = get_boq_sales_accounts(company) if company else {}
	boq_accounts = {
		a for a in (accounts.get("advance_account"), accounts.get("retention_account")) if a
	}

	rows = frappe.db.sql(
		"""
		SELECT
			je.name AS je_name,
			je.posting_date,
			je.voucher_type,
			je.is_opening,
			je.remark AS remarks,
			je.company,
			jea.account,
			jea.debit,
			jea.credit,
			jea.idx AS line_idx
		FROM `tabJournal Entry` je
		INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
		WHERE je.docstatus = 1
			AND jea.project = %s
		ORDER BY je.posting_date DESC, je.name DESC, jea.idx ASC
		""",
		project,
		as_dict=True,
	)

	je_meta = {}
	for row in rows:
		row["is_boq_account"] = row.account in boq_accounts
		row["is_opening_entry"] = row.is_opening == "Yes" or row.voucher_type == "Opening Entry"
		row["link"] = f"/app/journal-entry/{row.je_name}"

		meta = je_meta.setdefault(
			row.je_name,
			{
				"je_name": row.je_name,
				"posting_date": row.posting_date,
				"voucher_type": row.voucher_type,
				"is_opening_entry": row["is_opening_entry"],
				"remarks": row.remarks,
				"total_debit": 0.0,
				"total_credit": 0.0,
				"has_boq_account": False,
			},
		)
		meta["total_debit"] += flt(row.debit)
		meta["total_credit"] += flt(row.credit)
		if row["is_boq_account"]:
			meta["has_boq_account"] = True

	journal_entries = sorted(je_meta.values(), key=lambda x: (x["posting_date"], x["je_name"]), reverse=True)

	summary = {
		"count": len(journal_entries),
		"opening_count": sum(1 for j in journal_entries if j["is_opening_entry"]),
		"boq_account_count": sum(1 for j in journal_entries if j["has_boq_account"]),
		"total_debit": sum(flt(j["total_debit"]) for j in journal_entries),
		"total_credit": sum(flt(j["total_credit"]) for j in journal_entries),
	}

	return {
		"summary": summary,
		"rows": rows,
		"journal_entries": journal_entries,
	}


def get_project_journal_entry_summary(project: str) -> dict:
	"""Lightweight JE counts for KPI grid."""
	data = get_project_journal_entries(project)
	return data.get("summary") or {}
