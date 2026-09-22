# Copyright (c) 2026, Construction Management
# License: MIT

"""Batched reads for Bulk DPR Entry. Keep N+1 lookups off the page load path."""

from __future__ import annotations

import frappe
from frappe.utils import flt, today

from construction_management.api.dpr_utils import get_employees_with_rates

EMPTY_DAY_TOTALS = {
	"labour_cost": 0,
	"material_cost": 0,
	"asset_cost": 0,
	"overhead_cost": 0,
	"total_cost": 0,
}


def empty_master_payload(company: str | None = None) -> dict:
	return {
		"project": None,
		"boq_items": [],
		"sites": [],
		"employees": get_employees_with_rates(),
		"materials": [],
		"assets": [],
		"overhead_accounts": get_overhead_accounts(company),
		"help_video_url": "",
	}


def empty_day_payload() -> dict:
	return {"existing_dprs": [], "total_dprs": 0, "day_totals": dict(EMPTY_DAY_TOTALS)}


def project_company_mismatch(project: str, company: str | None) -> bool:
	if not company:
		return False
	project_company = frappe.db.get_value("Project", project, "company")
	return bool(project_company and project_company != company)


def get_project_summary(project: str) -> dict | None:
	row = frappe.db.get_value(
		"Project", project, ["name", "company", "site_location"], as_dict=True
	)
	return row


def get_boq_items_with_balance(project: str) -> list:
	items = frappe.get_all(
		"BOQ Item",
		filters={"project": project},
		fields=["name", "item_code", "description", "unit", "total_qty"],
		order_by="idx",
	)
	if not items:
		return []

	ledgers = frappe.db.sql(
		"""
		SELECT l.boq_item, l.accumulated_qty
		FROM `tabBOQ Progress Ledger` l
		INNER JOIN (
			SELECT boq_item, MAX(CONCAT(posting_date, ' ', creation)) AS latest
			FROM `tabBOQ Progress Ledger`
			WHERE project = %s
			GROUP BY boq_item
		) latest
			ON latest.boq_item = l.boq_item
			AND CONCAT(l.posting_date, ' ', l.creation) = latest.latest
		""",
		project,
		as_dict=True,
	)
	to_date = {row.boq_item: flt(row.accumulated_qty) for row in ledgers}
	for item in items:
		item["balance"] = flt(item.total_qty) - to_date.get(item.name, 0)
	return items


def get_project_sites(project: str) -> list:
	return frappe.get_all(
		"Project Sites", filters={"project": project}, fields=["name", "site_name"]
	)


def get_overhead_accounts(company: str | None = None) -> list:
	filters = {"root_type": ["in", ["Expense"]], "is_group": 0}
	if company:
		filters["company"] = company
	accounts = frappe.get_all("Account", filters=filters, fields=["name", "account_name"])
	for acc in accounts:
		acc["display_label"] = f"{acc.get('name', '')} - {acc.get('account_name', '')}"
	return accounts


def get_materials(project: str | None = None) -> list:
	if not project:
		return []
	warehouse = frappe.db.get_value("Project", project, "site_location")
	if not warehouse:
		return []

	bin_items = frappe.get_all(
		"Bin",
		filters={"warehouse": warehouse, "actual_qty": [">", 0]},
		fields=["item_code", "actual_qty", "valuation_rate"],
	)
	if not bin_items:
		return []

	qty_map = {row.item_code: row for row in bin_items}
	items = frappe.get_all(
		"Item",
		filters={"name": ["in", list(qty_map)], "disabled": 0},
		fields=["name", "item_name", "item_code", "stock_uom", "valuation_rate"],
	)
	for item in items:
		bin_row = qty_map.get(item.name)
		item["balance"] = flt(bin_row.actual_qty) if bin_row else 0
		item["valuation_rate"] = flt(item.valuation_rate) or flt(
			bin_row.valuation_rate if bin_row else 0
		)
	return items


def get_project_assets_with_rates(project: str, date: str | None = None) -> list:
	if not project:
		return []
	as_of = date or today()
	rows = frappe.db.sql(
		"""
		SELECT a.name, a.asset_name, a.status,
			pab.value_per_hour, pab.value_per_day, pab.effective_from
		FROM `tabProject Asset Billing` pab
		INNER JOIN `tabAsset` a ON a.name = pab.asset
		WHERE pab.project = %s
			AND pab.effective_from <= %s
			AND a.status IN ('Submitted', 'Partially Depreciated')
		ORDER BY pab.asset ASC, pab.effective_from DESC
		""",
		(project, as_of),
		as_dict=True,
	)
	assets = []
	seen = set()
	for row in rows:
		if row.name in seen:
			continue
		seen.add(row.name)
		assets.append(
			{
				"name": row.name,
				"asset_name": row.asset_name,
				"status": row.status,
				"rate_per_hour": flt(row.value_per_hour),
				"rate_per_day": flt(row.value_per_day),
			}
		)
	return assets


def get_existing_dprs(
	project: str, date: str, start: int = 0, page_length: int = 20, company: str | None = None
) -> dict:
	if project_company_mismatch(project, company):
		return {"dprs": [], "total": 0}

	filters = {"project": project, "date": date, "docstatus": ["<", 2]}
	total = frappe.db.count("Daily Progress Record", filters)
	dprs = frappe.get_all(
		"Daily Progress Record",
		filters=filters,
		fields=[
			"name",
			"boq_item",
			"project_sites as site",
			"remarks",
			"warehouse",
			"docstatus",
			"area_covered",
			"asset_cost",
			"labour_cost",
			"material_cost",
			"overhead_cost",
			"expense_cost",
			"total_cost",
		],
		start=start,
		page_length=page_length,
		order_by="creation desc",
	)
	if not dprs:
		return {"dprs": [], "total": total}

	names = [row.name for row in dprs]
	employees = _group_children(
		"DPR Employee",
		names,
		["parent", "employee", "employee_name", "hours", "rate_per_day", "amount"],
	)
	materials = _group_children(
		"DPR Material", names, ["parent", "item_code", "item_name", "qty", "rate", "amount"]
	)
	overheads = _group_children(
		"DPR Overhead", names, ["parent", "account", "account_name", "description", "amount"]
	)
	absent = _group_children("DPR Absent Employee", names, ["parent", "employee"])
	absent_names = _employee_names(
		{row.employee for rows in absent.values() for row in rows if row.employee}
	)

	processed = []
	for dpr in dprs:
		processed.append(
			{
				"name": dpr.name,
				"docstatus": dpr.docstatus,
				"boq_item": dpr.boq_item,
				"site": dpr.site,
				"area_covered": flt(dpr.area_covered),
				"remarks": dpr.remarks,
				"employees": [
					{
						"name": row.employee,
						"employee": row.employee,
						"employee_name": row.employee_name,
						"hours": row.hours,
						"rate_per_day": row.rate_per_day,
						"amount": row.amount,
					}
					for row in employees.get(dpr.name, [])
				],
				"absent_employees": [
					{
						"name": row.employee,
						"employee": row.employee,
						"employee_name": absent_names.get(row.employee) or row.employee,
					}
					for row in absent.get(dpr.name, [])
				],
				"materials": [
					{
						"name": row.item_code,
						"item_code": row.item_code,
						"item_name": row.item_name,
						"qty": row.qty,
						"rate": row.rate,
						"amount": row.amount,
						"description": "",
					}
					for row in materials.get(dpr.name, [])
				],
				"overheads": [
					{
						"name": row.account,
						"account": row.account,
						"account_name": row.account_name,
						"description": row.description,
						"amount": row.amount,
					}
					for row in overheads.get(dpr.name, [])
				],
				"labour_cost": dpr.labour_cost,
				"material_cost": dpr.material_cost,
				"asset_cost": dpr.asset_cost,
				"overhead_cost": dpr.overhead_cost,
				"expense_cost": dpr.expense_cost,
				"total_cost": dpr.total_cost,
			}
		)
	return {"dprs": processed, "total": total}


def get_day_totals(project: str, date: str) -> dict:
	totals = frappe.db.get_value(
		"Daily Progress Record",
		filters={"project": project, "date": date, "docstatus": ["<", 2]},
		fieldname=[
			{"SUM": "labour_cost", "as": "labour_cost"},
			{"SUM": "material_cost", "as": "material_cost"},
			{"SUM": "asset_cost", "as": "asset_cost"},
			{"SUM": "overhead_cost", "as": "overhead_cost"},
			{"SUM": "total_cost", "as": "total_cost"},
		],
		as_dict=True,
	)
	return totals or dict(EMPTY_DAY_TOTALS)


def _group_children(doctype: str, parents: list[str], fields: list[str]) -> dict:
	rows = frappe.get_all(doctype, filters={"parent": ["in", parents]}, fields=fields)
	grouped = {}
	for row in rows:
		grouped.setdefault(row.parent, []).append(row)
	return grouped


def _employee_names(employee_ids: set[str]) -> dict:
	if not employee_ids:
		return {}
	rows = frappe.get_all(
		"Employee", filters={"name": ["in", list(employee_ids)]}, fields=["name", "employee_name"]
	)
	return {row.name: row.employee_name for row in rows}
