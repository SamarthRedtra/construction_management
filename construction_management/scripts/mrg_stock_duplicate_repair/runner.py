"""Preview or atomically apply a fingerprinted MRG duplicate-stock repair."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict

import frappe
from frappe.utils import cint

from .data import COMPANY, EXPENSE_ACCOUNT, POSTING_DATE, POSTING_TIME, PREFIX
from .planner import build_plan, quantities_match
from .planner import plan_hash as fingerprint
from .report import capture_balances, write_report


def run(dry_run=True, expected_site=None, plan_hash=None, allow_production=False, output_dir=None):
	"""Require an explicit site and matching preview hash for every apply.

	No migration hook calls this function. The caller owns the final transaction commit.
	"""
	dry_run = bool(cint(dry_run))
	if not dry_run:
		validate_apply_site(frappe.local.site, expected_site, bool(cint(allow_production)))
		if not isinstance(plan_hash, str) or len(plan_hash) != 64 or any(c not in "0123456789abcdef" for c in plan_hash):
			raise ValueError("Apply requires the 64-character plan_hash from a fresh preview")
		if not frappe.db.has_column("Inventory Dimension", "mandatory_depends_on_backend"):
			raise ValueError("Sync Inventory Dimension with the installed ERPNext schema before applying")
	lock = "mrg_duplicate_repair:" + frappe.local.site
	if not frappe.db.sql("SELECT GET_LOCK(%s,0)", (lock,))[0][0]:
		raise ValueError("Another MRG duplicate repair is running")
	try:
		return execute_run(dry_run, plan_hash, output_dir)
	finally:
		frappe.db.sql("SELECT RELEASE_LOCK(%s)", (lock,))


def execute_run(dry_run, requested_hash, output_dir):
	# Ignore cancelled originals left after an SRBNB rebook; only live drafts/submitted count.
	existing = frappe.get_all(
		"Stock Reconciliation",
		filters={"company": COMPANY, "name": ["like", PREFIX + "%"], "docstatus": ["in", [0, 1]]},
		fields=["name", "docstatus"],
		order_by="name",
	)
	if existing:
		return existing_result(existing, requested_hash, output_dir)
	plan = build_plan()
	before = capture_balances()
	result = {"site": frappe.local.site, "status": "preview", "plan_hash": plan["plan_hash"],
		"summary": plan["summary"], "before": before, "documents": [], "voucher_checks": []}
	if not dry_run:
		if requested_hash != plan["plan_hash"]:
			raise ValueError("Plan changed since preview. Generate and review a fresh plan.")
		if any(row.status in ("In Progress", "Failed") for row in plan["pending_revaluations"]):
			raise ValueError("Resolve running/failed MRG revaluations before applying the repair")
		if not plan["eligible"]:
			raise ValueError("No verified duplicate balances are eligible")
		frappe.db.savepoint("mrg_duplicate_repair")
		try:
			protected = protected_balances(plan)
			result["documents"] = apply_documents(plan)
			result["voucher_checks"] = verify_documents(plan, result["documents"])
			if protected != protected_balances(plan):
				raise ValueError("New-item stock changed during legacy retirement")
			result["after"] = capture_balances()
			verify_changes(plan, result)
			result["status"] = "applied"
			save_manifest(plan, result)
		except Exception:
			frappe.db.rollback(save_point="mrg_duplicate_repair")
			raise
	if output_dir:
		result["report_directory"] = write_report(output_dir, plan, result)
	return result


def validate_apply_site(actual, expected, allow_production):
	if not expected or actual != expected:
		raise ValueError("expected_site must exactly match the connected site")
	if not actual.endswith((".local", ".localhost")) and not allow_production:
		raise ValueError("Production apply requires explicit allow_production=1 after CA approval")


def apply_documents(plan):
	by_warehouse = defaultdict(list)
	for row in plan["eligible"]:
		by_warehouse[row["warehouse"]].append(row)
	names = []
	for warehouse, rows in sorted(by_warehouse.items()):
		document = frappe.new_doc("Stock Reconciliation")
		document.company = COMPANY
		document.purpose = "Stock Reconciliation"
		document.set_posting_time = 1
		document.posting_date = POSTING_DATE
		document.posting_time = POSTING_TIME
		document.expense_account = EXPENSE_ACCOUNT
		document.cost_center = frappe.get_cached_value("Company", COMPANY, "cost_center")
		for row in rows:
			document.append("items", {"item_code": row["old_code"], "warehouse": warehouse,
				"qty": 0, "valuation_rate": row["old_rate"]})
		name = PREFIX + hashlib.sha256(warehouse.encode()).hexdigest()[:12]
		document.insert(set_name=name)
		document.submit()
		document.add_comment("Info", "Retire duplicate legacy stock already recorded under the CP catalog. "
			f"Difference account: {EXPENSE_ACCOUNT}. Plan SHA256: {plan['plan_hash']}. "
			"Source evidence attached to the batch's first voucher.")
		names.append(document.name)
	return names


def verify_documents(plan, names):
	checks = []
	expected = defaultdict(float)
	for row in plan["eligible"]:
		expected[row["warehouse"]] += row["old_value"]
	for name in names:
		stock = frappe.db.sql("""
			SELECT warehouse,SUM(stock_value_difference) AS value_change
			FROM `tabStock Ledger Entry` WHERE company=%s AND voucher_type='Stock Reconciliation'
			  AND voucher_no=%s AND is_cancelled=0 GROUP BY warehouse
		""", (COMPANY, name), as_dict=True)
		gl = frappe.db.sql("""
			SELECT COALESCE(SUM(debit-credit),0) FROM `tabGL Entry`
			WHERE company=%s AND voucher_type='Stock Reconciliation' AND voucher_no=%s
			  AND is_cancelled=0 AND account=%s
		""", (COMPANY, name, EXPENSE_ACCOUNT))[0][0]
		if len(stock) != 1 or abs(float(stock[0].value_change) + float(gl)) > 0.011:
			raise ValueError(f"Stock/GL mismatch on {name}")
		if abs(float(gl) - expected[stock[0].warehouse]) > 0.011:
			raise ValueError(f"Unexpected correction value on {name}")
		checks.append({"voucher": name, "warehouse": stock[0].warehouse,
			"stock_value_change": float(stock[0].value_change), "difference_account_debit": float(gl)})
	for row in plan["eligible"]:
		balance = frappe.db.get_value("Bin", {"item_code": row["old_code"], "warehouse": row["warehouse"]},
			["actual_qty", "stock_value"], as_dict=True)
		if not balance or not quantities_match(float(balance.actual_qty), 0) or abs(float(balance.stock_value)) > 0.011:
			raise ValueError(f"Legacy balance not cleared: {row['old_code']} / {row['warehouse']}")
	# No legacy future movements are eligible, so submission needs no asynchronous recalculation.
	if frappe.db.exists("Repost Item Valuation", {"voucher_type": "Stock Reconciliation",
		"voucher_no": ["in", names], "status": ["not in", ["Completed", "Skipped"]]}):
		raise ValueError("Correction generated a pending revaluation; batch was not finalized")
	return checks


def protected_balances(plan):
	pairs = {(row["new_code"], row["warehouse"]) for row in plan["eligible"]}
	rows = frappe.get_all("Bin", filters={"item_code": ["in", sorted({pair[0] for pair in pairs})],
		"warehouse": ["in", sorted({pair[1] for pair in pairs})]},
		fields=["item_code", "warehouse", "actual_qty", "stock_value", "valuation_rate"])
	return {(row.item_code, row.warehouse): (row.actual_qty, row.stock_value, row.valuation_rate)
		for row in rows if (row.item_code, row.warehouse) in pairs}


def verify_changes(plan, result):
	# Difference account is SRBNB (liability); inventory falls by debit, P&L must not move.
	debit = sum(row["difference_account_debit"] for row in result["voucher_checks"])
	for date, before in result["before"]["inventory"].items():
		after = result["after"]["inventory"][date]
		if abs(after["stock_ledger"] - before["stock_ledger"] + debit) > 0.02:
			raise ValueError(f"Unexpected total stock ledger movement at {date}")
		if abs(after["inventory_gl"] - before["inventory_gl"] + debit) > 0.02:
			raise ValueError(f"Unexpected total inventory GL movement at {date}")
	for account, before in result["before"]["pnl"].items():
		after = result["after"]["pnl"][account]
		if abs(after["September"] - before["September"]) > 0.02:
			raise ValueError(f"Unexpected September P&L movement: {account}")
		if abs(after["October"] - before["October"]) > 0.011:
			raise ValueError(f"Unexpected October P&L movement: {account}")


def save_manifest(plan, result):
	from frappe.utils.file_manager import save_file

	save_file("mrg_duplicate_repair_manifest.json", json.dumps({"plan": plan, "result": result}, default=str, indent=2).encode(),
		"Stock Reconciliation", result["documents"][0], is_private=1)


def existing_result(existing, requested_hash, output_dir):
	if any(row.docstatus != 1 for row in existing):
		raise ValueError("An existing repair voucher is not submitted; inspect the batch manually")
	files = frappe.get_all("File", filters={"attached_to_doctype": "Stock Reconciliation",
		"attached_to_name": ["in", [row.name for row in existing]],
		"file_name": ["like", "mrg_duplicate_repair_manifest%.json"]}, pluck="name")
	if len(files) != 1:
		raise ValueError("Existing correction batch has no unique audit manifest")
	manifest = json.loads(frappe.get_doc("File", files[0]).get_content())
	plan, original = manifest["plan"], manifest["result"]
	if fingerprint(plan) != plan["plan_hash"]:
		raise ValueError("Stored correction manifest failed its checksum")
	if requested_hash and requested_hash != plan["plan_hash"]:
		raise ValueError("Existing batch belongs to a different plan")
	if set(original["documents"]) != {row.name for row in existing}:
		raise ValueError("Existing repair voucher list differs from its manifest")
	checks = verify_documents(plan, original["documents"])
	result = dict(original, status="already_applied", after=capture_balances(), voucher_checks=checks)
	if output_dir:
		result["report_directory"] = write_report(output_dir, plan, result)
	return result
