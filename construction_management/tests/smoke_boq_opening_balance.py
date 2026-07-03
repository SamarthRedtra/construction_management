"""One-off smoke checks for opening JE -> BOQ advance/retention sync."""

import frappe
from frappe.utils import flt

from construction_management.api.boq_opening_balance import (
	get_boq_sales_accounts,
	get_opening_retention_balance,
	is_opening_journal_entry,
)
from construction_management.api.boq_tree import get_advance_summary, get_retention_summary


def run():
	print("=" * 60)
	print("SMOKE TEST: Opening JE -> BOQ Advance/Retention Sync")
	print("=" * 60)

	# 1. Hook module import
	print("\n[1] Module import ... OK")

	# 2. BOQ Settings accounts per company
	companies = frappe.get_all("BOQ Settings", fields=["name", "company", "advance_account", "retention_account"])
	print(f"\n[2] BOQ Settings with sales accounts: {len(companies)}")
	for row in companies:
		accounts = get_boq_sales_accounts(row.company)
		print(
			f"    {row.company}: advance={accounts.get('advance_account') or '-'}, "
			f"retention={accounts.get('retention_account') or '-'}"
		)

	# 3. Opening JEs touching advance/retention accounts
	opening_jes = frappe.db.sql(
		"""
		SELECT DISTINCT je.name, je.company, je.posting_date, je.is_opening, je.voucher_type
		FROM `tabJournal Entry` je
		INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
		INNER JOIN `tabBOQ Settings` bs ON bs.company = je.company
		WHERE je.docstatus = 1
			AND (je.is_opening = 'Yes' OR je.voucher_type = 'Opening Entry')
			AND IFNULL(jea.project, '') != ''
			AND (
				(jea.account = bs.advance_account AND IFNULL(bs.advance_account, '') != '')
				OR (jea.account = bs.retention_account AND IFNULL(bs.retention_account, '') != '')
			)
		ORDER BY je.posting_date DESC
		LIMIT 20
		""",
		as_dict=True,
	)
	print(f"\n[3] Opening JEs with project on advance/retention account: {len(opening_jes)}")
	for je in opening_jes[:10]:
		doc = frappe.get_doc("Journal Entry", je.name)
		print(f"    {je.name} | {je.company} | opening={is_opening_journal_entry(doc)}")

	# 4. BAP rows linked to opening JEs (reference prefix match)
	bap_rows = frappe.db.sql(
		"""
		SELECT bap.name, bap.project, bap.reference, bap.amount, bap.docstatus
		FROM `tabBOQ Advance Payment` bap
		WHERE bap.reference LIKE '%::%'
			AND bap.docstatus = 1
		ORDER BY bap.modified DESC
		LIMIT 20
		""",
		as_dict=True,
	)
	print(f"\n[4] BOQ Advance Payments from opening JEs (JE::project ref): {len(bap_rows)}")
	for row in bap_rows[:10]:
		print(f"    {row.name} | {row.project} | ref={row.reference} | amount={row.amount}")

	# 5. Per-project KPI spot check for projects with opening JE lines
	project_checks = frappe.db.sql(
		"""
		SELECT DISTINCT jea.project, je.company
		FROM `tabJournal Entry` je
		INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
		INNER JOIN `tabBOQ Settings` bs ON bs.company = je.company
		WHERE je.docstatus = 1
			AND (je.is_opening = 'Yes' OR je.voucher_type = 'Opening Entry')
			AND IFNULL(jea.project, '') != ''
			AND (
				jea.account = bs.advance_account
				OR jea.account = bs.retention_account
			)
		LIMIT 10
		""",
		as_dict=True,
	)
	print(f"\n[5] Project KPI spot checks ({len(project_checks)} projects):")
	for pc in project_checks:
		adv = get_advance_summary(pc.project)
		ret = get_retention_summary(pc.project)
		opening_ret = get_opening_retention_balance(pc.project, pc.company)
		print(f"    Project: {pc.project}")
		print(f"      Advance  collected={adv['total_collected']} balance={adv['balance']}")
		print(
			f"      Retention total={ret['total_retained']} opening={ret.get('opening_retained', opening_ret)} "
			f"balance={ret['retention_balance']}"
		)

	# 6. Consistency: opening JEs with advance lines should have matching BAP
	mismatches = []
	for je in opening_jes:
		accounts = get_boq_sales_accounts(je.company)
		advance_account = accounts.get("advance_account")
		if not advance_account:
			continue
		for row in frappe.get_all(
			"Journal Entry Account",
			filters={"parent": je.name, "account": advance_account},
			fields=["project", "debit", "credit"],
		):
			if not row.project:
				continue
			ref = f"{je.name}::{row.project}"
			bap = frappe.db.get_value(
				"BOQ Advance Payment",
				{"reference": ref, "docstatus": 1},
				["name", "amount"],
				as_dict=True,
			)
			root_type = frappe.db.get_value("Account", advance_account, "root_type")
			if root_type in ("Liability", "Equity", "Income"):
				expected = flt(row.credit) - flt(row.debit)
			else:
				expected = flt(row.debit) - flt(row.credit)
			if expected > 0 and not bap:
				mismatches.append(f"MISSING BAP for {ref} expected {expected}")
			elif bap and flt(bap.amount) != flt(expected):
				mismatches.append(f"AMOUNT MISMATCH {ref}: BAP={bap.amount} expected={expected}")

	print(f"\n[6] Advance BAP consistency check: {len(mismatches)} issue(s)")
	for m in mismatches[:10]:
		print(f"    {m}")
	if not mismatches:
		print("    All opening advance JE lines have matching BAP rows.")

	print("\n" + "=" * 60)
	print("SMOKE TEST COMPLETE")
	print("=" * 60)


def list_projects_for_ui():
	"""Print project names + desk links for opening JE sync data."""
	import frappe
	from frappe.utils import flt
	from construction_management.api.boq_tree import get_advance_summary, get_retention_summary

	rows = frappe.db.sql(
		"""
		SELECT DISTINCT je.name AS je_name, je.company, je.posting_date,
			jea.project, p.project_name, p.customer
		FROM `tabJournal Entry` je
		INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
		INNER JOIN `tabBOQ Settings` bs ON bs.company = je.company
		LEFT JOIN `tabProject` p ON p.name = jea.project
		WHERE je.docstatus = 1
			AND (je.is_opening = 'Yes' OR je.voucher_type = 'Opening Entry')
			AND IFNULL(jea.project, '') != ''
			AND (
				jea.account = bs.advance_account
				OR jea.account = bs.retention_account
			)
		ORDER BY je.posting_date DESC, jea.project
		""",
		as_dict=True,
	)

	site = frappe.local.site
	base = f"http://{site}"

	print("OPENING JE SYNC — PROJECTS TO OPEN IN DESK")
	print("=" * 70)
	seen = set()
	for r in rows:
		key = r.project
		if key in seen:
			continue
		seen.add(key)
		adv = get_advance_summary(r.project)
		ret = get_retention_summary(r.project)
		bap = frappe.get_all(
			"BOQ Advance Payment",
			filters={"project": r.project, "reference": ["like", "%::%"], "docstatus": 1},
			fields=["name", "reference", "amount"],
		)
		jes = [x.je_name for x in rows if x.project == r.project]
		print(f"\nProject ID: {r.project}")
		print(f"  Name:     {r.project_name or '-'}")
		print(f"  Customer: {r.customer or '-'}")
		print(f"  Company:  {r.company}")
		print(f"  Advance balance:   {flt(adv['balance']):,.2f}")
		print(f"  Retention balance: {flt(ret['retention_balance']):,.2f}")
		print(f"  Opening JEs: {', '.join(sorted(set(jes)))}")
		if bap:
			print(f"  BOQ Advance Payment: {', '.join(f'{b.name} ({b.amount:,.2f})' for b in bap)}")
		print(f"  Open Project: {base}/app/project/{r.project}")

	for r in sorted(set(x.je_name for x in rows)):
		print(f"\n  Open JE {r}: {base}/app/journal-entry/{r}")


def inspect_and_sync(je_name: str):
	"""Debug helper: inspect one JE and run advance sync."""
	import frappe
	from construction_management.api.boq_opening_balance import get_boq_sales_accounts, sync_opening_journal_entry

	je = frappe.get_doc("Journal Entry", je_name)
	accounts = get_boq_sales_accounts(je.company)
	print("JE:", je.name, "docstatus", je.docstatus, "is_opening", je.is_opening, "voucher_type", je.voucher_type)
	print("advance_account:", accounts.get("advance_account"))
	for row in je.accounts:
		if row.account in (accounts.get("advance_account"), accounts.get("retention_account")):
			print("  row", row.idx, row.account, "project", row.project, "debit", row.debit, "credit", row.credit)

	sync_opening_journal_entry(je)
	bap = frappe.get_all(
		"BOQ Advance Payment",
		filters={"reference": ["like", f"{je_name}%"]},
		fields=["name", "reference", "amount", "docstatus"],
	)
	print("BAP after sync:", bap)
