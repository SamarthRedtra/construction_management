# Copyright (c) 2026, Construction Management
# License: MIT

"""Force-enable Maintain Stock on CSV consumables and book GRN qty via Stock Reconciliation.

Preview (default):
	bench --site <site> execute \\
		construction_management.scripts.enable_consumable_stock_from_grn.preview

Apply:
	bench --site <site> execute \\
		construction_management.scripts.enable_consumable_stock_from_grn.run \\
		--kwargs "{'dry_run': 0}"
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

import frappe
from frappe.utils import cint, flt, getdate

CSV_NAME = "consumable_enable_stock_2026_11_03.csv"
DEFAULT_FROM_DATE = "2026-09-01"
POSTING_TIME = "00:00:01"
MAX_SR_LINES = 200

# Charge / service-like catalog rows: enable Maintain Stock, but do not book Bin qty.
SERVICE_EXCLUSION_PATTERNS = tuple(
	re.compile(pattern, re.IGNORECASE)
	for pattern in (
		r"pump\s*charges?",
		r"pumping\s*shifting",
		r"technician\s*charges?",
		r"mobilization",
		r"mobilisation",
		r"excess\s*concrete\s*charges?",
		r"static\s*line",
		r"slurry\s*mix",
		r"extra\s*pipe\s*line",
		r"business\s*card\s*printing",
		r"full\s*load\s*\)",
	)
)


def preview(from_date: str = DEFAULT_FROM_DATE) -> dict:
	"""Report what enable + Stock Reconciliation would do without writing."""
	return run(dry_run=1, from_date=from_date)


def run(dry_run: int | bool = 1, from_date: str = DEFAULT_FROM_DATE) -> dict:
	"""Enable Maintain Stock for CSV items; book physical GRN qty from from_date."""
	dry_run = bool(cint(dry_run))
	from_date = getdate(from_date)
	item_codes = load_item_codes()
	items = frappe.get_all(
		"Item",
		filters={"name": ["in", item_codes]},
		fields=["name", "item_name", "is_stock_item", "controlled_item_type", "disabled", "stock_uom"],
	)
	found = {row.name: row for row in items}
	missing = sorted(code for code in item_codes if code not in found)
	to_enable = sorted(
		code for code, row in found.items() if not cint(row.is_stock_item) and not cint(row.disabled)
	)
	already_stock = sorted(code for code, row in found.items() if cint(row.is_stock_item))

	if not dry_run:
		for code in to_enable:
			frappe.db.set_value("Item", code, "is_stock_item", 1, update_modified=False)

	grn_lines = fetch_grn_lines(item_codes, from_date)
	excluded_lines, bookable_lines = partition_service_lines(grn_lines, found)
	aggregates = aggregate_stock_rows(bookable_lines)
	skipped_warehouses = []
	sr_rows_by_company = defaultdict(list)
	for row in aggregates:
		warehouse = row["warehouse"]
		if not warehouse:
			skipped_warehouses.append({**row, "reason": "missing warehouse"})
			continue
		meta = frappe.db.get_value(
			"Warehouse", warehouse, ["company", "is_group", "disabled"], as_dict=True
		)
		if not meta or meta.company != row["company"] or cint(meta.is_group) or cint(meta.disabled):
			skipped_warehouses.append({**row, "reason": "invalid warehouse"})
			continue
		sr_rows_by_company[row["company"]].append(row)

	documents = []
	if not dry_run:
		for company, rows in sorted(sr_rows_by_company.items()):
			documents.extend(submit_stock_reconciliations(company, rows, from_date))
		frappe.db.commit()

	summary = {
		"site": frappe.local.site,
		"status": "preview" if dry_run else "applied",
		"from_date": str(from_date),
		"csv_items": len(item_codes),
		"missing_items": missing,
		"already_stock": already_stock,
		"enabled_count": len(to_enable),
		"enabled_items": to_enable,
		"grn_line_count": len(grn_lines),
		"grn_item_count": len({row["item_code"] for row in grn_lines}),
		"excluded_service_line_count": len(excluded_lines),
		"excluded_service_items": sorted({row["item_code"] for row in excluded_lines}),
		"bookable_aggregate_count": sum(len(v) for v in sr_rows_by_company.values()),
		"bookable_qty": sum(row["qty"] for rows in sr_rows_by_company.values() for row in rows),
		"skipped_warehouses": skipped_warehouses,
		"companies": {
			company: {
				"lines": len(rows),
				"qty": sum(flt(r["qty"]) for r in rows),
				"value": sum(flt(r["qty"]) * flt(r["valuation_rate"]) for r in rows),
			}
			for company, rows in sorted(sr_rows_by_company.items())
		},
		"documents": documents,
		"aggregates": [
			row for company in sorted(sr_rows_by_company) for row in sr_rows_by_company[company]
		],
	}
	return summary


def load_item_codes(csv_path: Path | None = None) -> list[str]:
	path = csv_path or default_csv_path()
	if not path.is_file():
		frappe.throw(f"CSV not found: {path}")
	codes = []
	seen = set()
	with path.open(newline="", encoding="utf-8-sig") as handle:
		for row in csv.DictReader(handle):
			code = (row.get("Item Code") or "").strip()
			if not code or code in seen:
				continue
			seen.add(code)
			codes.append(code)
	if not codes:
		frappe.throw(f"No item codes in {path}")
	return codes


def default_csv_path() -> Path:
	return Path(frappe.get_app_path("construction_management", "data", CSV_NAME))


def is_service_charge(item_code: str, item_name: str = "") -> bool:
	text = f"{item_code or ''} {item_name or ''}"
	return any(pattern.search(text) for pattern in SERVICE_EXCLUSION_PATTERNS)


def fetch_grn_lines(item_codes: list[str], from_date) -> list[dict]:
	if not item_codes:
		return []
	return frappe.db.sql(
		"""
		SELECT
			pri.item_code,
			pr.company,
			IFNULL(pri.warehouse, '') AS warehouse,
			pr.name AS purchase_receipt,
			pr.posting_date,
			pr.is_return,
			pri.stock_qty AS qty,
			pri.amount AS amount
		FROM `tabPurchase Receipt Item` pri
		JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pri.item_code IN %(codes)s
			AND pr.docstatus = 1
			AND pr.posting_date >= %(from_date)s
		ORDER BY pr.posting_date, pr.name, pri.idx
		""",
		{"codes": item_codes, "from_date": from_date},
		as_dict=True,
	)


def partition_service_lines(grn_lines: list[dict], items: dict) -> tuple[list[dict], list[dict]]:
	excluded, bookable = [], []
	for row in grn_lines:
		item = items.get(row["item_code"])
		name = item.item_name if item else ""
		if is_service_charge(row["item_code"], name):
			excluded.append(row)
		else:
			bookable.append(row)
	return excluded, bookable


def aggregate_stock_rows(grn_lines: list[dict]) -> list[dict]:
	"""Net qty and weighted-average rate per item / company / warehouse."""
	buckets: dict[tuple[str, str, str], dict] = {}
	for row in grn_lines:
		key = (row["item_code"], row["company"], row["warehouse"] or "")
		bucket = buckets.setdefault(
			key,
			{
				"item_code": row["item_code"],
				"company": row["company"],
				"warehouse": row["warehouse"] or "",
				"qty": 0.0,
				"amount": 0.0,
				"receipts": set(),
			},
		)
		qty = flt(row["qty"])
		amount = flt(row["amount"])
		# Purchase returns usually store positive qty with is_return=1; flip sign.
		if cint(row.get("is_return")) and qty > 0:
			qty = -qty
			amount = -abs(amount)
		bucket["qty"] += qty
		bucket["amount"] += amount
		bucket["receipts"].add(row["purchase_receipt"])

	rows = []
	for bucket in buckets.values():
		qty = flt(bucket["qty"])
		if qty <= 0:
			continue
		amount = flt(bucket["amount"])
		rows.append(
			{
				"item_code": bucket["item_code"],
				"company": bucket["company"],
				"warehouse": bucket["warehouse"],
				"qty": qty,
				"valuation_rate": abs(amount / qty) if qty else 0.0,
				"amount": amount,
				"receipt_count": len(bucket["receipts"]),
			}
		)
	rows.sort(key=lambda row: (row["company"], row["warehouse"], row["item_code"]))
	return rows


def submit_stock_reconciliations(company: str, rows: list[dict], from_date) -> list[dict]:
	expense_account = frappe.db.get_value(
		"Account",
		{"company": company, "account_name": "Stock Adjustment", "is_group": 0, "disabled": 0},
		"name",
	)
	if not expense_account:
		frappe.throw(f"Stock Adjustment account missing for {company}")
	cost_center = frappe.get_cached_value("Company", company, "cost_center")
	documents = []
	for index, chunk in enumerate(_chunks(rows, MAX_SR_LINES), start=1):
		doc = frappe.new_doc("Stock Reconciliation")
		doc.company = company
		doc.purpose = "Stock Reconciliation"
		doc.set_posting_time = 1
		doc.posting_date = getdate(from_date)
		doc.posting_time = POSTING_TIME
		doc.expense_account = expense_account
		if cost_center:
			doc.cost_center = cost_center
		for row in chunk:
			doc.append(
				"items",
				{
					"item_code": row["item_code"],
					"warehouse": row["warehouse"],
					"qty": row["qty"],
					"valuation_rate": row["valuation_rate"],
				},
			)
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		doc.add_comment(
			"Info",
			(
				"Enable Maintain Stock cutover for controlled consumables: book net GRN qty "
				f"from {from_date} at weighted average rate. Difference account: {expense_account}. "
				f"Batch {index}."
			),
		)
		documents.append(
			{
				"name": doc.name,
				"company": company,
				"lines": len(chunk),
				"qty": sum(flt(r["qty"]) for r in chunk),
			}
		)
	return documents


def _chunks(rows: list[dict], size: int):
	for start in range(0, len(rows), size):
		yield rows[start : start + size]
