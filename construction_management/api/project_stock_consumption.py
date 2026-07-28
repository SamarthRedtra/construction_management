"""Authenticated HTTP API for the project-stock consumption runner."""

import frappe
from frappe.utils import cint

from construction_management.patches.project_stock_consumption import (
	DEFAULT_COMPANY,
	execute as run_consumption,
)


@frappe.whitelist()
def run(
	company=DEFAULT_COMPANY,
	cutoff_date="2026-06-30",
	posting_date=None,
	stages="closing_projects,closing_transit,current_projects",
	run_id=None,
	dry_run=1,
):
	"""Preview or submit project-stock Material Issues through the REST method API.

	A System Manager must call this method.  Use ``dry_run=1`` first.  A posted
	request requires a caller-provided run ID so it can be safely retried without
	creating duplicate issues.
	"""
	frappe.only_for("System Manager")
	dry_run = bool(cint(dry_run))
	if not dry_run and not run_id:
		frappe.throw("run_id is required when dry_run is 0")

	return run_consumption(
		company=company,
		cutoff_date=cutoff_date,
		posting_date=posting_date,
		stages=stages,
		run_id=run_id or "project-stock-consumption-preview",
		dry_run=dry_run,
	)
