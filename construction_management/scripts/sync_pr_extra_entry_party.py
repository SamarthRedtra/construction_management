# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe.utils import cint, flt


def run(dry_run=False, voucher_no=None):
	"""Repost GL for PRs whose Additional Entries have party but GL rows are missing it."""
	dry_run = cint(dry_run)
	vouchers_by_company = _get_affected_vouchers_by_company(voucher_no=voucher_no)
	missing_count = _count_missing_party_gl_rows(voucher_no=voucher_no)

	print(f"Extra-entry GL rows missing party: {missing_count}")
	print(f"Affected companies: {len(vouchers_by_company)}")

	for company, voucher_names in sorted(vouchers_by_company.items()):
		print(f"  {company}: {len(voucher_names)} Purchase Receipt(s)")
		for name in voucher_names:
			print(f"    - {name}")

	if dry_run:
		print("Dry run — no repost performed.")
		return {
			"dry_run": True,
			"missing_party_gl_rows": missing_count,
			"companies": {k: list(v) for k, v in vouchers_by_company.items()},
		}

	if not vouchers_by_company:
		print("No vouchers to repost.")
		return {"reposted": 0, "missing_party_gl_rows": missing_count}

	reposted = 0
	for company, voucher_names in vouchers_by_company.items():
		# Repost Accounting Ledger runs synchronously only for <= 5 vouchers per doc.
		for batch_start in range(0, len(voucher_names), 5):
			batch = voucher_names[batch_start : batch_start + 5]
			repost_doc = frappe.new_doc("Repost Accounting Ledger")
			repost_doc.company = company
			for name in batch:
				repost_doc.append("vouchers", {"voucher_type": "Purchase Receipt", "voucher_no": name})
			repost_doc.flags.ignore_permissions = True
			repost_doc.insert()
			repost_doc.submit()
			reposted += len(batch)
			print(f"Reposted {len(batch)} voucher(s) for {company} via {repost_doc.name}")

	frappe.db.commit()
	remaining = _count_missing_party_gl_rows(voucher_no=voucher_no)
	print(f"Repost complete. Remaining missing-party GL rows: {remaining}")

	return {
		"reposted": reposted,
		"missing_party_gl_rows_before": missing_count,
		"missing_party_gl_rows_after": remaining,
	}


def _get_affected_vouchers_by_company(voucher_no=None):
	conditions = [
		"pr.docstatus = 1",
		"pre.party_type IS NOT NULL",
		"pre.party_type != ''",
		"pre.party IS NOT NULL",
		"pre.party != ''",
	]
	args = {}
	if voucher_no:
		conditions.append("pr.name = %(voucher_no)s")
		args["voucher_no"] = voucher_no

	rows = frappe.db.sql(
		f"""
		SELECT DISTINCT pr.name, pr.company
		FROM `tabPurchase Receipt` pr
		INNER JOIN `tabPurchase Receipt Extra Entry` pre ON pre.parent = pr.name
		WHERE {' AND '.join(conditions)}
		ORDER BY pr.company, pr.name
		""",
		args,
		as_dict=True,
	)

	vouchers_by_company = {}
	for row in rows:
		vouchers_by_company.setdefault(row.company, []).append(row.name)
	return vouchers_by_company


def _count_missing_party_gl_rows(voucher_no=None):
	conditions = [
		"gle.voucher_type = 'Purchase Receipt'",
		"gle.is_cancelled = 0",
		"gle.remarks LIKE 'Extra entry from Purchase Receipt%%'",
		"pre.party_type IS NOT NULL",
		"pre.party_type != ''",
		"pre.party IS NOT NULL",
		"pre.party != ''",
		"(gle.party_type IS NULL OR gle.party_type = '' OR gle.party IS NULL OR gle.party = '')",
	]
	args = {}
	if voucher_no:
		conditions.append("gle.voucher_no = %(voucher_no)s")
		args["voucher_no"] = voucher_no

	result = frappe.db.sql(
		f"""
		SELECT COUNT(*) AS cnt
		FROM `tabGL Entry` gle
		INNER JOIN `tabPurchase Receipt Extra Entry` pre
			ON pre.parent = gle.voucher_no
			AND pre.account = gle.account
			AND ABS(pre.debit - gle.debit) < 0.01
			AND ABS(pre.credit - gle.credit) < 0.01
		WHERE {' AND '.join(conditions)}
		""",
		args,
	)
	return flt(result[0][0] if result else 0)
