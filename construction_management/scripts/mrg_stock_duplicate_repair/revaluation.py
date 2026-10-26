"""Finish the captured item-merge revaluations using ERPNext's resumable jobs."""

from __future__ import annotations

import json

import frappe
from frappe.utils import cint

from .chains import find_gaps, rebuild_remaining
from .data import COMPANY, PREFIX
from .planner import plan_hash as fingerprint
from .report import capture_balances, snapshot_timing_review, write_report
from .runner import validate_apply_site, verify_documents


def finish(dry_run=True, expected_site=None, plan_hash=None, allow_production=False,
	output_dir=None, job_names=None, max_jobs=0):
	"""Process only jobs captured in this repair's manifest; native jobs commit checkpoints.

	A restart skips completed jobs. It never edits ledger tables or creates replacement jobs.
	"""
	dry_run = bool(cint(dry_run))
	if not dry_run:
		validate_apply_site(frappe.local.site, expected_site, bool(cint(allow_production)))
	plan, original, attached_to = load_manifest(plan_hash)
	selected = select_jobs(plan, job_names, cint(max_jobs))
	lock = "mrg_duplicate_revaluation:" + frappe.local.site
	if not frappe.db.sql("SELECT GET_LOCK(%s,0)", (lock,))[0][0]:
		raise ValueError("Another repair revaluation run is active")
	try:
		result = {"site": frappe.local.site, "status": "revaluation_preview" if dry_run else "revalued",
			"plan_hash": plan["plan_hash"], "before": original["before"],
			"after_legacy_retirement": original["after"], "before_revaluation_run": capture_balances(),
			"summary": plan["summary"], "documents": original["documents"], "jobs": []}
		for name in selected:
			document = frappe.get_doc("Repost Item Valuation", name)
			if document.company != COMPANY or document.docstatus != 1 or document.based_on != "Item and Warehouse":
				raise ValueError(f"Unexpected job scope: {name}")
			if document.status in ("Failed", "In Progress"):
				raise ValueError(f"Inspect {name} before continuing: {document.status}")
			if not dry_run and document.status == "Queued":
				print(f"Reposting {name}: {document.item_code} / {document.warehouse}", flush=True)
				document.repost_now()
				document.reload()
				if document.status not in ("Completed", "Skipped"):
					# ERPNext records job failures itself; preserve that evidence before failing.
					frappe.db.commit()
					raise ValueError(f"Revaluation {name} stopped with status {document.status}")
				frappe.db.commit()
			result["jobs"].append({"name": name, "status": document.status})
		result["accounting_jobs"] = finish_accounting_jobs(plan, dry_run)
		result["additional_chain_gaps"], result["additional_chain_jobs"] = rebuild_remaining(dry_run)
		if result["additional_chain_jobs"] and not dry_run:
			result["additional_accounting_jobs"] = finish_accounting_jobs(plan, dry_run,
				parent_names=result["additional_chain_jobs"])
		result["after"] = capture_balances()
		result["voucher_checks"] = verify_documents(plan, original["documents"])
		result["remaining_captured_jobs"] = frappe.get_all("Repost Item Valuation",
			filters={"name": ["in", [row["name"] for row in plan["pending_revaluations"]]],
				"status": ["not in", ["Completed", "Skipped"]]}, fields=["name", "status"])
		result["remaining_accounting_jobs"] = [row for row in result["accounting_jobs"]
			if row["status"] not in ("Completed", "Skipped")]
		result["remaining_chain_gaps"] = find_gaps()
		result["snapshot_timing_review"] = snapshot_timing_review()
		result["inventory_reconciled"] = all(abs(row["gl_minus_stock"]) <= 0.02
			for row in result["after"]["inventory"].values())
		if result["remaining_chain_gaps"] and not dry_run:
			result["status"] = "revalued_with_remaining_chain_gaps"
		elif not result["inventory_reconciled"] and not dry_run:
			result["status"] = "revalued_with_remaining_accounting_gap"
		if not dry_run:
			from frappe.utils.file_manager import save_file
			save_file("mrg_duplicate_revaluation_result.json", json.dumps(result, default=str, indent=2).encode(),
				"Stock Reconciliation", attached_to, is_private=1)
		if output_dir:
			result["report_directory"] = write_report(output_dir, plan, result)
		return result
	finally:
		frappe.db.sql("SELECT RELEASE_LOCK(%s)", (lock,))


def finish_accounting_jobs(plan, dry_run, parent_names=None):
	"""ERPNext can defer GL rebuilding to child jobs linked to the captured revaluations."""
	parents = parent_names if parent_names is not None else [row["name"] for row in plan["pending_revaluations"]]
	jobs = frappe.get_all("Repost Item Valuation", filters={"company": COMPANY, "docstatus": 1,
		"reposting_reference": ["in", parents],
		"repost_only_accounting_ledgers": 1}, fields=["name", "status"], order_by="creation,name")
	for row in jobs:
		if row.status in ("Failed", "In Progress"):
			raise ValueError(f"Inspect accounting job {row.name}: {row.status}")
		if not dry_run and row.status == "Queued":
			document = frappe.get_doc("Repost Item Valuation", row.name)
			print(f"Rebuilding GL {row.name}: {document.voucher_type} {document.voucher_no}", flush=True)
			document.repost_now()
			document.reload()
			row.status = document.status
			frappe.db.commit()
			if row.status not in ("Completed", "Skipped"):
				raise ValueError(f"Accounting job {row.name} stopped: {row.status}")
	return jobs


def load_manifest(requested_hash):
	if not isinstance(requested_hash, str) or len(requested_hash) != 64:
		raise ValueError("The original repair plan_hash is required")
	files = frappe.get_all("File", filters={"attached_to_doctype": "Stock Reconciliation",
		"attached_to_name": ["like", PREFIX + "%"],
		"file_name": ["like", "mrg_duplicate_repair_manifest%.json"]}, fields=["name", "attached_to_name"])
	if len(files) != 1:
		raise ValueError("No unique repair manifest was found")
	manifest = json.loads(frappe.get_doc("File", files[0].name).get_content())
	plan = manifest["plan"]
	if fingerprint(plan) != plan["plan_hash"] or requested_hash != plan["plan_hash"]:
		raise ValueError("Repair manifest checksum does not match")
	return plan, manifest["result"], files[0].attached_to_name


def select_jobs(plan, names, limit):
	captured = [row["name"] for row in plan["pending_revaluations"]]
	if names is not None:
		if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
			raise ValueError("job_names must be a list of strings")
		if set(names) - set(captured):
			raise ValueError("Revaluation job was not captured in the repair manifest")
		captured = list(dict.fromkeys(names))
	if limit < 0:
		raise ValueError("max_jobs cannot be negative")
	return captured[:limit] if limit else captured
