"""Controlled import for the 07 October 2026 MRG stock snapshot."""

from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from io import StringIO
from pathlib import Path

import frappe
from frappe.utils import flt, getdate
from frappe.utils.file_manager import save_file
from openpyxl import load_workbook

from construction_management.api import controlled_procurement as catalog
from construction_management.api import item_tree_part_2_expanded_import as expanded_import


COMPANY = "M R G INSULATION WORKS L.L.C"
POSTING_DATE = "2026-10-07"
ITEM_TREE_PATH = Path("/Users/samarthupare/Downloads/Item Tree Part 2 (3).xlsx")
STOCK_REPORT_PATH = Path("/Users/samarthupare/Downloads/MRG Stock Report ( Upto 07.10.2026 ).xlsx")
CORRECTION_RATES = {"filler board": 39.0, "utility knife": 4.0}


def preflight(
	item_tree_path: str = str(ITEM_TREE_PATH),
	stock_report_path: str = str(STOCK_REPORT_PATH),
) -> dict:
	"""Validate and normalize the positive MRG stock-snapshot balances."""
	tree_rates, tree_types = _tree_metadata(Path(item_tree_path))
	rows = _report_rows(Path(stock_report_path))
	items, non_stock_items = _catalog_items()
	warehouses = _warehouses()
	targets, held, errors = _targets(rows, items, non_stock_items, warehouses, tree_rates, tree_types)
	_apply_valuation_rates(targets, tree_rates)
	missing_rates = [target for target in targets if target["valuation_rate"] is None]
	if missing_rates:
		errors.extend({
			"reason": "No existing valuation rate or finalized Item Tree buying rate",
			"item": target["item_name"],
			"warehouse": target["warehouse"],
		} for target in missing_rates)
	return {
		"company": COMPANY,
		"posting_date": POSTING_DATE,
		"source_rows": len(rows),
		"target_lines": len(targets),
		"warehouses": len({target["warehouse"] for target in targets}),
		"held_rows": held,
		"errors": errors,
		"targets": targets,
	}


def run(
	item_tree_path: str = str(ITEM_TREE_PATH),
	stock_report_path: str = str(STOCK_REPORT_PATH),
) -> dict:
	"""Create missing unambiguous masters and reconcile only changed MRG balances."""
	frappe.set_user("Administrator")
	item_tree = Path(item_tree_path)
	stock_report = Path(stock_report_path)
	result = preflight(str(item_tree), str(stock_report))
	catalog_requests = _create_missing_catalog_requests(item_tree, result["errors"])
	if catalog_requests:
		result = preflight(str(item_tree), str(stock_report))
	if result["errors"]:
		audit_file = _save_audit(result, [], catalog_requests, None)
		frappe.throw(
			"MRG stock snapshot preflight failed; no Stock Reconciliations were created. "
			f"Audit: {audit_file.file_url}"
		)

	mismatches = _mismatched_targets(result["targets"])
	if not mismatches:
		audit_file = _save_audit(result, mismatches, catalog_requests, None)
		return _run_result(result, catalog_requests, [], mismatches, audit_file.file_url)

	documents = _create_reconciliations(mismatches)
	audit_file = _save_audit(result, mismatches, catalog_requests, documents)
	for source in (item_tree, stock_report):
		save_file(source.name, source.read_bytes(), documents[0].doctype, documents[0].name, is_private=1)
	for document in documents:
		document.submit()
	return _run_result(result, catalog_requests, documents, mismatches, audit_file.file_url)


def submit(
	item_tree_path: str = str(ITEM_TREE_PATH),
	stock_report_path: str = str(STOCK_REPORT_PATH),
) -> dict:
	"""Backward-compatible alias for the idempotent MRG snapshot job."""
	return run(item_tree_path, stock_report_path)


def verify(
	item_tree_path: str = str(ITEM_TREE_PATH),
	stock_report_path: str = str(STOCK_REPORT_PATH),
) -> dict:
	"""Compare every eligible report target with the resulting MRG Bin balance."""
	result = preflight(item_tree_path, stock_report_path)
	mismatches = _mismatched_targets(result["targets"])
	return {
		"target_lines": result["target_lines"],
		"warehouses": result["warehouses"],
		"held_rows": result["held_rows"],
		"preflight_errors": result["errors"],
		"mismatches": mismatches,
	}


def _tree_metadata(path: Path) -> tuple[dict[str, float], dict[str, str]]:
	book = load_workbook(path, read_only=True, data_only=True)
	if "Sheet2" not in book:
		frappe.throw("The finalized Item Tree must contain Sheet2.")
	rates = dict(CORRECTION_RATES)
	types = {}
	for row in book["Sheet2"].iter_rows(min_row=3, values_only=True):
		if not row[1]:
			continue
		name = _key(row[1])
		types.setdefault(name, _allocation_type(row[5]))
		if flt(row[4]) > 0:
			rates.setdefault(name, flt(row[4]))
	return rates, types


def _report_rows(path: Path) -> list[dict]:
	book = load_workbook(path, read_only=True, data_only=True)
	sheet = book.active
	return [
		{
			"source_row": number,
			"item_name": str(row[0]).strip(),
			"warehouse": str(row[2]).strip(),
			"report_uom": str(row[3] or "").strip(),
			"qty": flt(row[4]),
		}
		for number, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), 2)
		if row[0]
	]


def _catalog_items() -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
	items, non_stock_items = defaultdict(list), defaultdict(list)
	for row in frappe.get_all(
		"Item",
		filters={"disabled": 0, "controlled_procurement_catalog": 1},
		fields=["name", "item_name", "stock_uom", "controlled_item_type", "is_stock_item"],
		limit_page_length=0,
	):
		if row.controlled_item_type in {"Stockable", "Consumable"}:
			(items if row.is_stock_item else non_stock_items)[_key(row.item_name)].append(row)
	return items, non_stock_items


def _warehouses() -> set[str]:
	return set(frappe.get_all(
		"Warehouse",
		filters={"company": COMPANY, "is_group": 0, "disabled": 0},
		pluck="name",
		limit_page_length=0,
	))


def _targets(rows: list[dict], items: dict, non_stock_items: dict, warehouses: set[str], tree_rates: dict, tree_types: dict) -> tuple[list[dict], list[dict], list[dict]]:
	targets, held, errors = {}, [], []
	for row in rows:
		if row["qty"] < 0:
			held.append({**row, "reason": "Negative report balance held for separate adjustment"})
			continue
		if tree_types.get(_key(row["item_name"])) == "Asset":
			held.append({**row, "reason": "Finalized Item Tree classifies this row as an Asset"})
			continue
		if row["warehouse"] not in warehouses:
			errors.append({**row, "reason": "Active MRG warehouse not found"})
			continue
		matches = items.get(_key(row["item_name"]), [])
		if not matches and non_stock_items.get(_key(row["item_name"])):
			held.append({**row, "reason": "Controlled master cannot enable stock after submitted transactions"})
			continue
		if len(matches) != 1:
			errors.append({**row, "reason": "Canonical controlled stock item was not uniquely resolved"})
			continue
		item = matches[0]
		if _key(row["item_name"]) not in tree_rates:
			errors.append({**row, "reason": "Finalized Item Tree buying rate not found"})
			continue
		key = (item.name, row["warehouse"])
		target = targets.setdefault(key, {
			"item_code": item.name,
			"item_name": item.item_name,
			"stock_uom": item.stock_uom,
			"warehouse": row["warehouse"],
			"qty": 0.0,
			"source_rows": [],
			"valuation_rate": None,
		})
		target["qty"] += row["qty"]
		target["source_rows"].append(row["source_row"])
	return sorted(targets.values(), key=lambda target: (target["warehouse"], target["item_code"])), held, errors


def _apply_valuation_rates(targets: list[dict], tree_rates: dict) -> None:
	bins = {
		(row.item_code, row.warehouse): row.valuation_rate
		for row in frappe.get_all(
			"Bin",
			fields=["item_code", "warehouse", "valuation_rate"],
			limit_page_length=0,
		)
	}
	for target in targets:
		bin_key = (target["item_code"], target["warehouse"])
		existing_rate = flt(bins[bin_key]) if bin_key in bins else 0
		target["valuation_rate"] = existing_rate or tree_rates.get(_key(target["item_name"]))


def _mismatched_targets(targets: list[dict]) -> list[dict]:
	"""Return only balances that need a Stock Reconciliation on this rerun."""
	bins = {
		(row.item_code, row.warehouse): flt(row.actual_qty)
		for row in frappe.get_all("Bin", fields=["item_code", "warehouse", "actual_qty"], limit_page_length=0)
	}
	return [
		{**target, "actual_qty": bins.get((target["item_code"], target["warehouse"]), 0.0)}
		for target in targets
		if abs(bins.get((target["item_code"], target["warehouse"]), 0.0) - target["qty"]) > 0.000001
	]


def _create_missing_catalog_requests(item_tree: Path, errors: list[dict]) -> list[str]:
	"""Create one approval-controlled request for unambiguous report-item gaps."""
	missing_names = {
		_key(error["item_name"])
		for error in errors
		if error["reason"] == "Canonical controlled stock item was not uniquely resolved"
	}
	if not missing_names:
		return []

	selected, _, _, _ = expanded_import._prepare(item_tree)
	candidates = defaultdict(list)
	for row in selected:
		if _key(row["item_name"]) in missing_names and row["action"] in {"Create", "Adopt"}:
			candidates[_key(row["item_name"])].append(row)
	payloads = [rows[0] for name, rows in candidates.items() if len(rows) == 1 and name in missing_names]
	if not payloads:
		return []

	for group in {row["item_group"] for row in payloads}:
		catalog._ensure_group(group)
	checksum = hashlib.sha256(
		"|".join(sorted(f"{row['item_name']}:{row['stock_uom']}:{row['supplier']}:{row['rate']}" for row in payloads)).encode()
	).hexdigest()
	existing = frappe.db.get_value(
		"Controlled Catalog Request", {"company": COMPANY, "checksum": checksum}, "name"
	)
	if existing:
		return [existing]
	request = catalog.create_catalog_request({
		"company": COMPANY,
		"source": "Workbook Import",
		"checksum": checksum,
		"items": payloads,
	})
	return [request["name"]]


def _create_reconciliations(targets: list[dict]) -> list:
	by_warehouse = defaultdict(list)
	for target in targets:
		by_warehouse[target["warehouse"]].append(target)
	documents = []
	for warehouse, warehouse_targets in sorted(by_warehouse.items()):
		document = frappe.new_doc("Stock Reconciliation")
		document.company = COMPANY
		document.purpose = "Stock Reconciliation"
		document.posting_date = getdate(POSTING_DATE)
		for target in warehouse_targets:
			document.append("items", {
				"item_code": target["item_code"],
				"warehouse": warehouse,
				"qty": target["qty"],
				"valuation_rate": target["valuation_rate"],
			})
		document.flags.ignore_permissions = True
		document.insert()
		documents.append(document)
	return documents


def _save_audit(result: dict, mismatches: list[dict], catalog_requests: list[str], documents: list | None = None):
	"""Persist a run-level audit, including no-op checks and business-held rows."""
	document_by_warehouse = {
		doc.items[0].warehouse: doc.name for doc in (documents or [])
	}
	mismatch_keys = {(target["item_code"], target["warehouse"]) for target in mismatches}
	audit = StringIO()
	writer = csv.writer(audit)
	writer.writerow(["MRG Catalog and Stock Check", "Value"])
	writer.writerow(["Posting Date", POSTING_DATE])
	writer.writerow(["Eligible Report Balances", result["target_lines"]])
	writer.writerow(["Matched / No-op Balances", result["target_lines"] - len(mismatches)])
	writer.writerow(["Balances Requiring Reconciliation", len(mismatches)])
	writer.writerow(["Catalog Requests", ", ".join(catalog_requests)])
	writer.writerow(["Held Report Rows", len(result["held_rows"])])
	writer.writerow([])
	writer.writerow(["Status", "Stock Reconciliation", "Warehouse", "Item Code", "Item Name", "Final UOM", "Report Qty", "Current Qty", "Valuation Rate", "Source Rows"])
	for target in result["targets"]:
		writer.writerow([
			"Reconcile" if (target["item_code"], target["warehouse"]) in mismatch_keys else "Matched",
			document_by_warehouse.get(target["warehouse"], ""), target["warehouse"], target["item_code"],
			target["item_name"], target["stock_uom"], target["qty"], target.get("actual_qty", target["qty"]), target["valuation_rate"],
			", ".join(map(str, target["source_rows"])),
		])
	writer.writerow([])
	writer.writerow(["Held Source Row", "Item Name", "Warehouse", "Report Qty", "Reason"])
	for held in result["held_rows"]:
		writer.writerow([held["source_row"], held["item_name"], held["warehouse"], held["qty"], held["reason"]])
	content = audit.getvalue().encode()
	filename = f"MRG_Stock_Catalog_Check_{POSTING_DATE}_{hashlib.sha256(content).hexdigest()[:8]}.csv"
	if documents:
		doctype, name = documents[0].doctype, documents[0].name
	else:
		doctype, name = "Company", COMPANY
	existing = frappe.get_all(
		"File",
		filters={"file_name": filename, "attached_to_doctype": doctype, "attached_to_name": name},
		pluck="name",
		limit_page_length=1,
	)
	if existing:
		return frappe.get_doc("File", existing[0])
	return save_file(filename, content, doctype, name, is_private=1)


def _run_result(result: dict, catalog_requests: list[str], documents: list, mismatches: list[dict], audit_file: str) -> dict:
	return {
		"posting_date": POSTING_DATE,
		"catalog_requests": catalog_requests,
		"stock_reconciliations": [document.name for document in documents],
		"submitted_documents": len(documents),
		"target_lines": result["target_lines"],
		"matched_balances": result["target_lines"] - len(mismatches),
		"reconciliation_balances": len(mismatches),
		"held_rows": result["held_rows"],
		"audit_file": audit_file,
		"no_op": not catalog_requests and not documents,
	}


def _key(value) -> str:
	return " ".join(str(value or "").split()).casefold()


def _allocation_type(value) -> str:
	return {
		"material in stock": "Stockable",
		"consumable": "Consumable",
		"asset": "Asset",
		"service": "Service",
	}.get(_key(value), "")
