"""Production-safe runner for the MRG project-stock consumption exercise.

Run with ``bench --site <site> execute``.  It previews by default and only
creates submitted Material Issues when ``dry_run=0`` is supplied explicitly.
This module is intentionally *not* listed in patches.txt: financial entries
must never be created automatically during a migrate operation.
"""

from collections import defaultdict

import frappe
from frappe.utils import cint, flt, getdate, nowdate


DEFAULT_COMPANY = "M R G INSULATION WORKS L.L.C"
STORES_WAREHOUSE = "Stores - MRG"

STAGE_CLOSING_PROJECTS = "closing_projects"
STAGE_CLOSING_TRANSIT = "closing_transit"
STAGE_CURRENT_PROJECTS = "current_projects"
VALID_STAGES = {
	STAGE_CLOSING_PROJECTS,
	STAGE_CLOSING_TRANSIT,
	STAGE_CURRENT_PROJECTS,
}


def execute(
	company=DEFAULT_COMPANY,
	cutoff_date="2026-06-30",
	posting_date=None,
	stages="closing_projects,closing_transit,current_projects",
	run_id="mrg-project-stock-consumption-2026",
	dry_run=1,
):
	"""Preview or create the project-stock Material Issues used in this exercise.

	Stages:
	- ``closing_projects``: positive project-site stock at the cutoff date,
	  excluding Stores and Transit warehouses.
	- ``closing_transit``: positive Transit stock at the cutoff date, only where
	  the Transit warehouse is mapped to a project.
	- ``current_projects``: current positive stock in every project-mapped
	  warehouse, including mapped Transit and excluding Stores.

	Every created entry contains a stable run marker. Re-running the same run ID
	skips item/warehouse rows already posted by this runner. Review the preview
	first; use ``dry_run=0`` only after approval.
	"""
	if not frappe.db.exists("Company", company):
		frappe.throw(f"Company not found: {company}")

	cutoff_date = getdate(cutoff_date)
	posting_date = getdate(posting_date or nowdate())
	dry_run = bool(cint(dry_run))
	stages = _normalise_stages(stages)

	results = []
	for stage in stages:
		stage_posting_date = cutoff_date if stage != STAGE_CURRENT_PROJECTS else posting_date
		rows = _get_stage_rows(stage, company, cutoff_date)
		rows = _exclude_already_posted(rows, company, stage, run_id)
		result = _run_stage(
			stage=stage,
			rows=rows,
			company=company,
			posting_date=stage_posting_date,
			run_id=run_id,
			dry_run=dry_run,
		)
		results.append(result)

		if not dry_run:
			frappe.db.commit()

	return {
		"dry_run": dry_run,
		"company": company,
		"cutoff_date": str(cutoff_date),
		"posting_date": str(posting_date),
		"run_id": run_id,
		"stages": results,
	}


def _normalise_stages(stages):
	if isinstance(stages, str):
		stages = [stage.strip() for stage in stages.split(",") if stage.strip()]
	if not stages:
		frappe.throw("Select at least one consumption stage")

	invalid = set(stages) - VALID_STAGES
	if invalid:
		frappe.throw(f"Unsupported consumption stage(s): {', '.join(sorted(invalid))}")
	return stages


def _get_stage_rows(stage, company, cutoff_date):
	if stage == STAGE_CURRENT_PROJECTS:
		return frappe.db.sql(
			"""
			SELECT
				w.name AS warehouse,
				w.custom_project AS project,
				b.item_code,
				b.actual_qty AS qty,
				b.stock_value AS estimated_value
			FROM `tabBin` b
			INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
			WHERE w.company = %(company)s
				AND IFNULL(w.custom_project, '') != ''
				AND w.name != %(stores_warehouse)s
				AND b.actual_qty > 0.000001
			ORDER BY w.name, b.item_code
			""",
			{"company": company, "stores_warehouse": STORES_WAREHOUSE},
			as_dict=True,
		)

	transit_condition = (
		"IFNULL(w.warehouse_type, '') = 'Transit'"
		if stage == STAGE_CLOSING_TRANSIT
		else "IFNULL(w.warehouse_type, '') != 'Transit'"
	)
	return frappe.db.sql(
		f"""
		SELECT
			w.name AS warehouse,
			w.custom_project AS project,
			sle.item_code,
			SUM(sle.actual_qty) AS qty,
			SUM(sle.stock_value_difference) AS estimated_value
		FROM `tabStock Ledger Entry` sle
		INNER JOIN `tabWarehouse` w ON w.name = sle.warehouse
		WHERE sle.company = %(company)s
			AND sle.posting_date <= %(cutoff_date)s
			AND IFNULL(sle.is_cancelled, 0) = 0
			AND IFNULL(w.custom_project, '') != ''
			AND w.name != %(stores_warehouse)s
			AND {transit_condition}
		GROUP BY w.name, w.custom_project, sle.item_code
		HAVING SUM(sle.actual_qty) > 0.000001
		ORDER BY w.name, sle.item_code
		""",
		{
			"company": company,
			"cutoff_date": cutoff_date,
			"stores_warehouse": STORES_WAREHOUSE,
		},
		as_dict=True,
	)


def _exclude_already_posted(rows, company, stage, run_id):
	marker = _marker(stage, run_id)
	entries = frappe.get_all(
		"Stock Entry",
		filters={
			"company": company,
			"docstatus": 1,
			"stock_entry_type": "Material Issue",
			"remarks": ["like", f"%{marker}%"],
		},
		pluck="name",
	)
	if not entries:
		return rows

	posted = set()
	for entry in entries:
		for item in frappe.get_all(
			"Stock Entry Detail",
			filters={"parent": entry},
			fields=["s_warehouse", "item_code"],
		):
			posted.add((item.s_warehouse, item.item_code))

	return [row for row in rows if (row.warehouse, row.item_code) not in posted]


def _run_stage(stage, rows, company, posting_date, run_id, dry_run):
	groups = defaultdict(list)
	for row in rows:
		groups[(row.warehouse, row.project)].append(row)

	result = {
		"stage": stage,
		"posting_date": str(posting_date),
		"item_rows": len(rows),
		"warehouses": len(groups),
		"estimated_value": round(sum(flt(row.estimated_value) for row in rows), 3),
		"submitted_entries": [],
		"submitted_lines": 0,
		"failed_lines": [],
	}
	if dry_run:
		return result

	for (warehouse, project), issue_rows in groups.items():
		savepoint = f"{stage}_{frappe.generate_hash(length=8)}"
		frappe.db.savepoint(savepoint)
		try:
			entry = _create_issue(issue_rows, company, posting_date, stage, run_id)
			result["submitted_entries"].append(entry.name)
			result["submitted_lines"] += len(issue_rows)
		except Exception:
			frappe.db.rollback(save_point=savepoint)
			# Do not let one unavailable item block other items at the same site.
			for row in issue_rows:
				item_savepoint = f"{stage}_{frappe.generate_hash(length=8)}"
				frappe.db.savepoint(item_savepoint)
				try:
					entry = _create_issue([row], company, posting_date, stage, run_id)
					result["submitted_entries"].append(entry.name)
					result["submitted_lines"] += 1
				except Exception as exc:
					frappe.db.rollback(save_point=item_savepoint)
					result["failed_lines"].append(
						{
							"warehouse": row.warehouse,
							"project": row.project,
							"item_code": row.item_code,
							"qty": flt(row.qty),
							"error": str(exc).split("\n")[0],
						}
					)

	return result


def _create_issue(rows, company, posting_date, stage, run_id):
	first = rows[0]
	entry = frappe.new_doc("Stock Entry")
	entry.stock_entry_type = "Material Issue"
	entry.company = company
	entry.posting_date = posting_date
	entry.posting_time = "23:59:59"
	entry.set_posting_time = 1
	entry.project = first.project
	entry.remarks = _marker(stage, run_id)

	for row in rows:
		entry.append(
			"items",
			{
				"item_code": row.item_code,
				"qty": flt(row.qty),
				"s_warehouse": row.warehouse,
				"project": row.project,
			},
		)

	entry.insert()
	entry.submit()
	return entry


def _marker(stage, run_id):
	return f"[Project Stock Consumption:{run_id}:{stage}]"
