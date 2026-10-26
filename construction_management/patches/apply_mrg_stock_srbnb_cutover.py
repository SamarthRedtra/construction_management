# Copyright (c) 2026, Construction Management
# License: MIT

"""MRG 30-Sep stock cutover on migrate: zero legacy duplicates + remap MAT-RECO to SRBNB.

1. Create MRG-DUP-* Stock Reconciliations (difference account = Stock Received But Not Billed - MRG)
   for verified old/new duplicate balances.
2. Cancel+amend every submitted MAT-RECO on 2026-09-30 still on Stock Adjustment → SRBNB.
3. Finish captured Repost Item Valuation jobs from the DUP manifest when present.

Idempotent: skips DUP apply if MRG-DUP vouchers already exist; rebook skips vouchers already on SRBNB.
Requires packaged linking + stock report workbooks under construction_management/data/.
"""

from __future__ import annotations

import frappe

from construction_management.scripts.mrg_stock_duplicate_repair.data import COMPANY, PREFIX


def execute():
	"""Run on every site migrate; no-ops when MRG company or source data is absent."""
	if not frappe.db.exists("Company", COMPANY):
		print(f"Skip MRG stock SRBNB cutover: company missing ({COMPANY})")
		return

	ensure_inventory_dimension_backend_column()

	site = frappe.local.site
	print(f"MRG stock SRBNB cutover on {site}")

	dup_result = apply_duplicate_repair(site)
	print(f"Duplicate repair status: {dup_result.get('status')}")

	try:
		rebook_result = apply_mat_reco_rebook(site)
	except Exception as exc:
		still_sa = count_mat_reco_on_stock_adjustment()
		if still_sa:
			raise
		print(
			f"MAT-RECO rebook raised after work completed ({exc}); "
			f"no MAT-RECO remain on Stock Adjustment — continuing."
		)
		rebook_result = {"planned": [], "rebooked": [], "skipped": [], "errors": [{"error": str(exc)}]}

	print(
		f"MAT-RECO rebook: planned={len(rebook_result.get('planned', []))} "
		f"rebooked={len(rebook_result.get('rebooked', []))} "
		f"skipped={len(rebook_result.get('skipped', []))} "
		f"errors={len(rebook_result.get('errors', []))}"
	)
	still_sa = count_mat_reco_on_stock_adjustment()
	if rebook_result.get("errors") and still_sa:
		frappe.throw(
			f"MAT-RECO SRBNB rebook had errors and {still_sa} vouchers still on "
			f"Stock Adjustment: {rebook_result['errors'][0]}"
		)
	if still_sa:
		frappe.throw(f"{still_sa} submitted MAT-RECO on 2026-09-30 still use Stock Adjustment - MRG")
	if rebook_result.get("errors") and not still_sa:
		print(
			f"Rebook reported errors but no MAT-RECO remain on Stock Adjustment; continuing. "
			f"First error was: {rebook_result['errors'][0]}"
		)

	if dup_result.get("plan_hash") and dup_result.get("status") in (
		"applied", "already_applied", "already_present",
	):
		finish_revaluations(site, dup_result["plan_hash"])

	frappe.db.commit()
	print("MRG stock SRBNB cutover finished")


def apply_duplicate_repair(site: str) -> dict:
	from construction_management.scripts.mrg_stock_duplicate_repair.planner import build_plan
	from construction_management.scripts.mrg_stock_duplicate_repair.runner import run

	existing = frappe.get_all(
		"Stock Reconciliation",
		filters={"company": COMPANY, "name": ["like", PREFIX + "%"], "docstatus": ["in", [0, 1]]},
		pluck="name",
		order_by="name",
	)
	if existing:
		print(f"MRG-DUP already present ({len(existing)}); skip create")
		return {
			"status": "already_present",
			"plan_hash": load_existing_plan_hash(existing),
			"documents": existing,
		}

	plan = build_plan()
	if not plan.get("eligible"):
		print("No eligible legacy duplicate balances; skip MRG-DUP create")
		return {"status": "skipped_no_eligible", "plan_hash": plan.get("plan_hash")}

	return run(
		dry_run=0,
		expected_site=site,
		plan_hash=plan["plan_hash"],
		allow_production=1,
	)


def load_existing_plan_hash(voucher_names: list[str]) -> str | None:
	import json

	files = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Stock Reconciliation",
			"attached_to_name": ["in", voucher_names],
			"file_name": ["like", "mrg_duplicate_repair_manifest%.json"],
		},
		pluck="name",
	)
	if not files:
		return None
	manifest = json.loads(frappe.get_doc("File", files[0]).get_content())
	return (manifest.get("plan") or {}).get("plan_hash") or (manifest.get("result") or {}).get("plan_hash")


def apply_mat_reco_rebook(site: str) -> dict:
	from construction_management.scripts.mrg_stock_duplicate_repair.rebook_expense_to_srbnb import (
		execute as rebook,
	)

	return rebook(dry_run=0, expected_site=site, allow_production=1, include_mrg_dup=0)


def count_mat_reco_on_stock_adjustment() -> int:
	return frappe.db.count(
		"Stock Reconciliation",
		{
			"company": COMPANY,
			"posting_date": "2026-09-30",
			"docstatus": 1,
			"name": ["like", "MAT-RECO-%"],
			"expense_account": "Stock Adjustment - MRG",
		},
	)


def finish_revaluations(site: str, plan_hash: str) -> None:
	from construction_management.scripts.mrg_stock_duplicate_repair.revaluation import finish

	try:
		result = finish(
			dry_run=0,
			expected_site=site,
			plan_hash=plan_hash,
			allow_production=1,
		)
		print(f"Revaluation status: {result.get('status')} reconciled={result.get('inventory_reconciled')}")
	except Exception as exc:
		# DUP/rebook already committed useful work; do not fail migrate if jobs need manual finish.
		print(f"Revaluation finish deferred (run manually if needed): {exc}")


def ensure_inventory_dimension_backend_column():
	column = "mandatory_depends_on_backend"
	if frappe.db.has_column("Inventory Dimension", column):
		return
	frappe.reload_doc("stock", "doctype", "inventory_dimension", force=True)
	frappe.db.updatedb("Inventory Dimension")
	if frappe.db.has_column("Inventory Dimension", column):
		return
	from frappe.database.schema import add_column

	add_column("Inventory Dimension", column, "Small Text")
	frappe.clear_cache(doctype="Inventory Dimension")
