# Copyright (c) 2026, Construction Management
# License: MIT

"""One-time: transfer all stock from Projects 1156 & 1157 into Project 1145.

Creates submitted Material Transfer Stock Entries from each source site warehouse
into 1145's site warehouse, then:
- points source warehouses at Project 1145 (custom_project)
- marks Projects 1156 / 1157 inactive

Safe to re-run: skips when source warehouses already have no positive stock.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, nowdate, nowtime

SOURCE_PROJECTS = ("1156", "1157")
TARGET_PROJECT = "1145"
STOCK_ENTRY_TYPE = "Material Transfer"
ITEMS_PER_ENTRY = 40


def execute():
	if not frappe.db.exists("Project", TARGET_PROJECT):
		frappe.logger("construction_management").warning(
			f"Skip stock consolidate: target Project {TARGET_PROJECT} not found"
		)
		return

	target = frappe.db.get_value(
		"Project",
		TARGET_PROJECT,
		["name", "company", "site_location"],
		as_dict=True,
	)
	if not target.site_location:
		frappe.throw(
			f"Project {TARGET_PROJECT} has no site_location (warehouse). "
			"Set Site Warehouse before running this patch."
		)

	if not frappe.db.exists("Warehouse", target.site_location):
		frappe.throw(f"Target warehouse {target.site_location!r} does not exist")

	created_entries = []
	for source_project in SOURCE_PROJECTS:
		created_entries.extend(_transfer_project_stock(source_project, target))

	_repoint_source_warehouses(target)
	_deactivate_source_projects()

	frappe.db.commit()

	msg = (
		f"Consolidated stock into {TARGET_PROJECT}. "
		f"Created {len(created_entries)} Material Transfer(s): {', '.join(created_entries) or 'none'}"
	)
	frappe.logger("construction_management").info(msg)
	try:
		frappe.msgprint(msg, alert=True)
	except Exception:
		pass


def _transfer_project_stock(source_project: str, target) -> list[str]:
	if not frappe.db.exists("Project", source_project):
		frappe.logger("construction_management").warning(
			f"Skip {source_project}: Project not found"
		)
		return []

	source_warehouses = _get_source_warehouses(source_project, target.company)
	if not source_warehouses:
		frappe.logger("construction_management").warning(
			f"Skip {source_project}: no warehouses found"
		)
		return []

	created = []
	for warehouse in source_warehouses:
		if warehouse == target.site_location:
			continue

		bins = frappe.db.sql(
			"""
			SELECT item_code, actual_qty, stock_uom
			FROM `tabBin`
			WHERE warehouse = %s AND actual_qty > 0
			ORDER BY item_code
			""",
			warehouse,
			as_dict=True,
		)
		if not bins:
			continue

		for chunk in _chunk(bins, ITEMS_PER_ENTRY):
			se_name = _create_material_transfer(
				company=target.company,
				project=TARGET_PROJECT,
				source_warehouse=warehouse,
				target_warehouse=target.site_location,
				bins=chunk,
				source_project=source_project,
			)
			if se_name:
				created.append(se_name)

	return created


def _get_source_warehouses(project: str, company: str | None) -> list[str]:
	warehouses: list[str] = []

	site_location = frappe.db.get_value("Project", project, "site_location")
	if site_location:
		warehouses.append(site_location)

	# Match by Warehouse.custom_project when set
	if frappe.db.has_column("Warehouse", "custom_project"):
		for name in frappe.get_all(
			"Warehouse",
			filters={"custom_project": project, "disabled": 0},
			pluck="name",
		):
			if name not in warehouses:
				warehouses.append(name)

	# Also match warehouses whose name clearly belongs to this project no.
	# (1157 site WH had null custom_project in production.)
	like_patterns = [f"{project} %", f"% {project} %", f"{project}-%", f"%{project} -%"]
	for pattern in like_patterns:
		for row in frappe.get_all(
			"Warehouse",
			filters={"name": ("like", pattern), "disabled": 0},
			fields=["name", "company"],
		):
			if company and row.company and row.company != company:
				continue
			# Avoid matching unrelated warehouses that merely contain digits
			if not _warehouse_belongs_to_project(row.name, project):
				continue
			if row.name not in warehouses:
				warehouses.append(row.name)

	# Filter to company when known
	if company:
		filtered = []
		for wh in warehouses:
			wh_company = frappe.db.get_value("Warehouse", wh, "company")
			if not wh_company or wh_company == company:
				filtered.append(wh)
		warehouses = filtered

	return warehouses


def _warehouse_belongs_to_project(warehouse_name: str, project: str) -> bool:
	name = (warehouse_name or "").strip()
	if name == project or name.startswith(f"{project} ") or name.startswith(f"{project}-"):
		return True
	# e.g. "1156 - 1156-Ginco ..."
	if f" {project} " in f" {name} " or f" {project}-" in f" {name}":
		return True
	return False


def _create_material_transfer(
	*,
	company: str,
	project: str,
	source_warehouse: str,
	target_warehouse: str,
	bins: list[dict],
	source_project: str,
) -> str | None:
	se = frappe.new_doc("Stock Entry")
	se.company = company
	se.stock_entry_type = STOCK_ENTRY_TYPE
	se.purpose = STOCK_ENTRY_TYPE
	se.posting_date = nowdate()
	se.posting_time = nowtime()
	se.set_posting_time = 1
	se.project = project
	se.from_warehouse = source_warehouse
	se.to_warehouse = target_warehouse
	se.remarks = (
		f"One-time consolidate: move stock from Project {source_project} "
		f"({source_warehouse}) to Project {project} ({target_warehouse})"
	)

	for row in bins:
		qty = flt(row.actual_qty)
		if qty <= 0:
			continue

		# Re-read live qty to avoid over-transfer if stock moved mid-run
		live_qty = flt(
			frappe.db.get_value(
				"Bin",
				{"warehouse": source_warehouse, "item_code": row.item_code},
				"actual_qty",
			)
		)
		qty = min(qty, live_qty)
		if qty <= 0:
			continue

		item_row = {
			"item_code": row.item_code,
			"qty": qty,
			"uom": row.stock_uom,
			"stock_uom": row.stock_uom,
			"conversion_factor": 1,
			"s_warehouse": source_warehouse,
			"t_warehouse": target_warehouse,
			"project": project,
			"allow_zero_valuation_rate": 1,
		}
		se.append("items", item_row)

	if not se.items:
		return None

	se.flags.ignore_permissions = True
	se.insert()
	se.submit()
	return se.name


def _repoint_source_warehouses(target) -> None:
	"""Point source warehouses at 1145 so future stock is attributed correctly."""
	if not frappe.db.has_column("Warehouse", "custom_project"):
		return

	for source_project in SOURCE_PROJECTS:
		for warehouse in _get_source_warehouses(source_project, target.company):
			if warehouse == target.site_location:
				continue
			frappe.db.set_value(
				"Warehouse",
				warehouse,
				"custom_project",
				TARGET_PROJECT,
				update_modified=False,
			)


def _deactivate_source_projects() -> None:
	for source_project in SOURCE_PROJECTS:
		if not frappe.db.exists("Project", source_project):
			continue
		values = {}
		if frappe.db.has_column("Project", "is_active"):
			values["is_active"] = "No"
		if frappe.db.has_column("Project", "status"):
			values["status"] = "Completed"
		if values:
			frappe.db.set_value("Project", source_project, values, update_modified=True)


def _chunk(rows: list, size: int):
	for i in range(0, len(rows), size):
		yield rows[i : i + size]
