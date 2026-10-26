"""Remap 30-Sep Stock Reconciliations from Stock Adjustment to SRBNB.

Default: every submitted MAT-RECO-* on POSTING_DATE still using Stock
Adjustment - MRG. Cancels and amends onto Stock Received But Not Billed - MRG.
Pass include_mrg_dup=1 to also remount MRG-DUP-* still on Stock Adjustment.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import frappe
from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import StockReconciliation
from frappe.utils import cint, flt

from .data import COMPANY, EXPENSE_ACCOUNT, POSTING_DATE, PREFIX
from .runner import validate_apply_site


FROM_ACCOUNT = "Stock Adjustment - MRG"
TO_ACCOUNT = EXPENSE_ACCOUNT
MAT_RECO_PREFIX = "MAT-RECO-%"


def execute(dry_run=True, expected_site=None, allow_production=False, include_mrg_dup=False):
	"""Remap difference accounts on the target voucher set. Caller owns the final commit."""
	dry_run = bool(cint(dry_run))
	include_mrg_dup = bool(cint(include_mrg_dup))
	if not dry_run:
		validate_apply_site(frappe.local.site, expected_site, bool(cint(allow_production)))
	lock = "mrg_rebook_srbnb:" + frappe.local.site
	if not frappe.db.sql("SELECT GET_LOCK(%s,0)", (lock,))[0][0]:
		raise ValueError("Another SRBNB rebook is running")
	try:
		return run_rebook(dry_run, include_mrg_dup)
	finally:
		frappe.db.sql("SELECT RELEASE_LOCK(%s)", (lock,))


def run_rebook(dry_run, include_mrg_dup):
	assert_to_account()
	targets = list_targets(include_mrg_dup)
	before = account_totals([row.name for row in targets])
	result = {
		"site": frappe.local.site,
		"dry_run": dry_run,
		"include_mrg_dup": include_mrg_dup,
		"posting_date": POSTING_DATE,
		"from_account": FROM_ACCOUNT,
		"to_account": TO_ACCOUNT,
		"target_count": len(targets),
		"before": before,
		"planned": [],
		"rebooked": [],
		"skipped": [],
		"errors": [],
	}
	for row in targets:
		if row.expense_account == TO_ACCOUNT:
			result["skipped"].append({"voucher": row.name, "reason": "already_on_srbnb"})
			continue
		if row.expense_account != FROM_ACCOUNT:
			result["skipped"].append({
				"voucher": row.name,
				"reason": f"unexpected_expense_account:{row.expense_account}",
			})
			continue
		from_net = voucher_account_net(row.name, FROM_ACCOUNT)
		plan_row = {
			"voucher": row.name,
			"expense_account": row.expense_account,
			"from_account_net": from_net,
			"posting_date": str(row.posting_date),
		}
		result["planned"].append(plan_row)
		if dry_run:
			continue
		try:
			amended_name = rebook_one(row.name)
			# Commit each voucher so a long batch can resume after a mid-run failure.
			frappe.db.commit()
			result["rebooked"].append({
				"cancelled": row.name,
				"amended": amended_name,
				"from_account_net": from_net,
				"to_account_net": voucher_account_net(amended_name, TO_ACCOUNT),
			})
		except Exception as exc:
			frappe.db.rollback()
			result["errors"].append({"voucher": row.name, "error": str(exc)})
	result["after"] = account_totals(live_names_from_result(result, targets))
	result["already_on_srbnb_count"] = count_mat_reco_on_account(TO_ACCOUNT)
	if not dry_run:
		verify_rebook(result)
		update_manifest(result)
		if result["errors"]:
			raise ValueError(
				f"Rebook finished with {len(result['errors'])} errors; "
				f"rebooked={len(result['rebooked'])}. First: {result['errors'][0]}"
			)
	return result


def assert_to_account():
	account = frappe.db.get_value(
		"Account", TO_ACCOUNT, ["name", "company", "root_type", "is_group", "disabled"], as_dict=True,
	)
	if not account or account.company != COMPANY or cint(account.is_group) or cint(account.disabled):
		raise ValueError(f"Account missing or invalid for MRG: {TO_ACCOUNT}")
	if account.root_type != "Liability":
		raise ValueError(f"{TO_ACCOUNT} must be a Liability account, got {account.root_type}")


def list_targets(include_mrg_dup):
	"""Submitted MAT-RECO on cutover date still on Stock Adjustment (+ optional MRG-DUP)."""
	rows = frappe.get_all(
		"Stock Reconciliation",
		filters={
			"company": COMPANY,
			"posting_date": POSTING_DATE,
			"docstatus": 1,
			"name": ["like", MAT_RECO_PREFIX],
			"expense_account": FROM_ACCOUNT,
		},
		fields=["name", "expense_account", "posting_date"],
		order_by="name",
	)
	if include_mrg_dup:
		rows.extend(frappe.get_all(
			"Stock Reconciliation",
			filters={
				"company": COMPANY,
				"name": ["like", PREFIX + "%"],
				"docstatus": 1,
				"expense_account": FROM_ACCOUNT,
			},
			fields=["name", "expense_account", "posting_date"],
			order_by="name",
		))
	return rows


def count_mat_reco_on_account(account):
	return frappe.db.count(
		"Stock Reconciliation",
		{
			"company": COMPANY,
			"posting_date": POSTING_DATE,
			"docstatus": 1,
			"name": ["like", MAT_RECO_PREFIX],
			"expense_account": account,
		},
	)


def live_names_from_result(result, targets):
	"""Live submitted vouchers for GL totals after the pass."""
	names = [row["amended"] for row in result["rebooked"]]
	names.extend(
		row["voucher"] for row in result["skipped"] if row["reason"] == "already_on_srbnb"
	)
	if result["dry_run"]:
		names.extend(row["voucher"] for row in result["planned"])
	# Include any target that failed so after totals still reflect leftover Stock Adjustment.
	names.extend(row["voucher"] for row in result.get("errors", []))
	return sorted(set(names))


def account_totals(voucher_names):
	names = sorted({name for name in voucher_names if name})
	if not names:
		return {FROM_ACCOUNT: 0.0, TO_ACCOUNT: 0.0}
	rows = frappe.db.sql("""
		SELECT account, COALESCE(SUM(debit - credit), 0) AS net
		FROM `tabGL Entry`
		WHERE company=%s AND voucher_type='Stock Reconciliation'
		  AND voucher_no IN ({}) AND is_cancelled=0
		  AND account IN (%s, %s)
		GROUP BY account
	""".format(",".join(["%s"] * len(names))),
		(COMPANY, *names, FROM_ACCOUNT, TO_ACCOUNT), as_dict=True)
	totals = {FROM_ACCOUNT: 0.0, TO_ACCOUNT: 0.0}
	for row in rows:
		totals[row.account] = float(row.net)
	return totals


def voucher_account_net(voucher_no, account):
	return float(frappe.db.sql("""
		SELECT COALESCE(SUM(debit - credit), 0) FROM `tabGL Entry`
		WHERE company=%s AND voucher_type='Stock Reconciliation' AND voucher_no=%s
		  AND is_cancelled=0 AND account=%s
	""", (COMPANY, voucher_no, account))[0][0])


def rebook_one(name):
	original = frappe.get_doc("Stock Reconciliation", name)
	if original.docstatus != 1:
		raise ValueError(f"{name} is not submitted")
	# Broken private attachments block cancel/copy; drop missing file rows only.
	detach_missing_attachments("Stock Reconciliation", name)
	# Cancel restores qty; later issues may leave temporary negative bins mid-repost.
	with allow_negative_stock_for_reconciliations():
		original.cancel()
		amended = frappe.copy_doc(original)
		amended.amended_from = original.name
		amended.expense_account = TO_ACCOUNT
		amended.set_posting_time = 1
		amended.posting_date = original.posting_date
		amended.posting_time = original.posting_time
		amended.insert()
		amended.submit()
	amended.add_comment(
		"Info",
		f"Remapped difference account from {FROM_ACCOUNT} to {TO_ACCOUNT}. "
		f"Cancelled voucher: {original.name}.",
	)
	return amended.name


def detach_missing_attachments(doctype, name):
	from pathlib import Path

	site_path = Path(frappe.get_site_path())
	for row in frappe.get_all(
		"File",
		filters={"attached_to_doctype": doctype, "attached_to_name": name},
		fields=["name", "file_url", "is_private"],
	):
		url = (row.file_url or "").lstrip("/")
		if not url:
			continue
		path = site_path / url
		if path.is_file():
			continue
		frappe.delete_doc("File", row.name, force=1, ignore_permissions=True)


@contextmanager
def allow_negative_stock_for_reconciliations():
	"""Same approach as the MRG corrected-stock patch: force allow_negative on SLE write."""
	original_update = StockReconciliation.update_stock_ledger
	original_validate = StockReconciliation.validate_data

	def update_stock_ledger(document, allow_negative_stock=False):
		return original_update(document, allow_negative_stock=True)

	def validate_data(document):
		try:
			return original_validate(document)
		except frappe.ValidationError:
			document.validation_messages = [
				message
				for message in document.validation_messages
				if not str(message).endswith("Negative Quantity is not allowed")
			]
			if document.validation_messages:
				raise frappe.ValidationError(document.validation_messages)

	StockReconciliation.update_stock_ledger = update_stock_ledger
	StockReconciliation.validate_data = validate_data
	try:
		yield
	finally:
		StockReconciliation.update_stock_ledger = original_update
		StockReconciliation.validate_data = original_validate


def verify_rebook(result):
	"""Confirm amended vouchers sit on SRBNB with stock/GL in balance.

	Do not require amended SRBNB net to equal the pre-cancel Stock Adjustment net:
	cancel/amend mid-batch reposts the SLE chain, so GL amounts can change while the
	voucher still correctly uses TO_ACCOUNT.
	"""
	if result["errors"]:
		return
	if abs(result["after"][FROM_ACCOUNT]) > 0.011:
		raise ValueError(
			f"Live Stock Adjustment net still present on target vouchers: "
			f"{result['after'][FROM_ACCOUNT]}"
		)
	remaining = frappe.db.count(
		"Stock Reconciliation",
		{
			"company": COMPANY,
			"posting_date": POSTING_DATE,
			"docstatus": 1,
			"name": ["like", MAT_RECO_PREFIX],
			"expense_account": FROM_ACCOUNT,
		},
	)
	if remaining and not result.get("include_mrg_dup"):
		raise ValueError(
			f"{remaining} submitted MAT-RECO on {POSTING_DATE} still use {FROM_ACCOUNT}"
		)
	rebooked_from = sum(flt(row["from_account_net"]) for row in result["rebooked"])
	rebooked_to = sum(flt(row["to_account_net"]) for row in result["rebooked"])
	if result["rebooked"] and abs(rebooked_to - rebooked_from) > 0.02:
		# Informational only — SLE repost during the batch can change amounts.
		print(
			f"Note: amended SRBNB net {rebooked_to} differs from pre-cancel "
			f"Stock Adjustment net {rebooked_from} (expected when batch cancel/amend "
			f"reposts stock).",
			flush=True,
		)
	for row in result["rebooked"]:
		if abs(flt(row["to_account_net"])) < 0.000001 and abs(flt(row["from_account_net"])) > 0.011:
			# Amended voucher posted no SRBNB but original had a SA balance — real problem.
			sa_left = voucher_account_net(row["amended"], FROM_ACCOUNT)
			if abs(sa_left) > 0.011:
				raise ValueError(
					f"Amended {row['amended']} still posts to {FROM_ACCOUNT} ({sa_left})"
				)
		stock = frappe.db.sql("""
			SELECT COALESCE(SUM(stock_value_difference), 0) FROM `tabStock Ledger Entry`
			WHERE company=%s AND voucher_type='Stock Reconciliation'
			  AND voucher_no=%s AND is_cancelled=0
		""", (COMPANY, row["amended"]))[0][0]
		if abs(float(stock) + float(row["to_account_net"])) > 0.011:
			# Allow tiny imbalance only when TO is the account in use; else fail.
			raise ValueError(f"Stock/GL mismatch on amended {row['amended']}")


def update_manifest(result):
	"""Point the DUP audit manifest at amended names when DUP vouchers were rebooked."""
	from frappe.utils.file_manager import save_file

	if not result["rebooked"]:
		return
	rename = {
		row["cancelled"]: row["amended"]
		for row in result["rebooked"]
		if row["cancelled"].startswith(PREFIX)
	}
	if not rename:
		return
	files = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Stock Reconciliation",
			"attached_to_name": ["in", sorted(rename)],
			"file_name": ["like", "mrg_duplicate_repair_manifest%.json"],
		},
		pluck="name",
	)
	if not files:
		return
	manifest = json.loads(frappe.get_doc("File", files[0]).get_content())
	manifest["result"]["documents"] = [
		rename.get(name, name) for name in manifest["result"]["documents"]
	]
	for check in manifest["result"].get("voucher_checks", []):
		if check.get("voucher") in rename:
			check["voucher"] = rename[check["voucher"]]
		if "stock_adjustment_debit" in check:
			check["difference_account_debit"] = check.pop("stock_adjustment_debit")
	manifest["result"]["rebooked_to_srbnb"] = result["rebooked"]
	first_amended = manifest["result"]["documents"][0]
	for name in frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Stock Reconciliation",
			"attached_to_name": first_amended,
			"file_name": "mrg_duplicate_repair_manifest.json",
		},
		pluck="name",
	):
		frappe.delete_doc("File", name, force=1, ignore_permissions=True)
	save_file(
		"mrg_duplicate_repair_manifest.json",
		json.dumps(manifest, default=str, indent=2).encode(),
		"Stock Reconciliation",
		first_amended,
		is_private=1,
	)
