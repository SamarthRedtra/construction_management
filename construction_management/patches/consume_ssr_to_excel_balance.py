# Copyright (c) 2026, Construction Management
# License: MIT

"""Reduce MRG site warehouse stock to SSR Excel balances via Material Issue.

Option 3 (Excel-driven): for each SSR row,
  issue_qty = max(0, bin_qty - excel_stock)

Posting date: 2026-06-30 (SSR as-of).
Unlisted Bin items are left untouched.

Console usage (skada.local)::

    from construction_management.patches.consume_ssr_to_excel_balance import (
        preview_ssr_consumption,
        run_ssr_consumption,
    )
    preview_ssr_consumption()          # writes CSV under private/files
    # edit sites/.../private/files/ssr_item_map.csv for unmatched rows
    preview_ssr_consumption()
    run_ssr_consumption(dry_run=0)     # submit Material Issues

Migrate / patch execute() always runs dry-run only (never posts stock).
"""

from __future__ import annotations

import csv
import os
import re
from difflib import SequenceMatcher
from pathlib import Path

import frappe
from frappe.utils import cint, flt, get_files_path, getdate

try:
	import openpyxl
except ImportError:  # pragma: no cover
	openpyxl = None


COMPANY = "M R G INSULATION WORKS L.L.C"
POSTING_DATE = "2026-06-30"
REMARK_TAG = "SSR-CONSUME-2026-06-30"
STOCK_ENTRY_TYPE = "Material Issue"
ITEMS_PER_ENTRY = 40
MATCH_THRESHOLD = 0.72
DEFAULT_XLSX_NAME = "SSR ALL SITES UPTO  JUNE.30.2026.xlsx"
MAP_CSV_NAME = "ssr_item_map.csv"
REPORT_CSV_NAME = "ssr_consume_preview.csv"


def execute():
	"""Patch hook — dry-run only so migrate never posts stock."""
	preview_ssr_consumption(dry_run=1)


@frappe.whitelist()
def preview_ssr_consumption(xlsx_path: str | None = None, dry_run: int = 1) -> dict:
	"""Parse SSR, match items, write preview CSV. Never creates Stock Entries."""
	return run_ssr_consumption(xlsx_path=xlsx_path, dry_run=1)


@frappe.whitelist()
def run_ssr_consumption(xlsx_path: str | None = None, dry_run: int = 1) -> dict:
	"""Preview or create Material Issues to bring Bin qty down to SSR balances."""
	dry_run = cint(dry_run)
	xlsx = _resolve_xlsx_path(xlsx_path)
	rows = parse_ssr_excel(xlsx)
	override_map = load_item_map()
	already = _already_issued_pairs()

	report_rows: list[dict] = []
	issue_plan: dict[tuple[str, str], list[dict]] = {}  # (warehouse, project) -> lines

	for row in rows:
		project_nos = split_project_nos(row["project_no"])
		warehouses = resolve_warehouses(project_nos)
		if not warehouses:
			report_rows.append(
				_report_line(
					row,
					warehouse="",
					item_code="",
					score=0,
					bin_qty=0,
					issue_qty=0,
					status="no_warehouse",
				)
			)
			continue

		override_item = _lookup_override(override_map, row["project_no"], row["material"])
		match = match_material_to_bin(
			row["material"],
			warehouses,
			override_item=override_item,
		)
		if not match:
			report_rows.append(
				_report_line(
					row,
					warehouse="",
					item_code="",
					score=0,
					bin_qty=0,
					issue_qty=0,
					status="unmatched",
				)
			)
			continue

		warehouse = match["warehouse"]
		item_code = match["item_code"]
		project = match["project"]
		bin_qty = flt(match["bin_qty"])
		excel_stock = flt(row["stock"])
		score = flt(match["score"])

		# For combined sites (1099 & 1148), one SSR row must issue from a single
		# warehouse only — if any candidate WH already consumed this item under
		# the SSR tag, skip the row entirely.
		candidate_warehouses = {w["warehouse"] for w in warehouses}
		if (warehouse, item_code) in already or any(
			(wh, item_code) in already for wh in candidate_warehouses
		):
			report_rows.append(
				_report_line(
					row,
					warehouse=warehouse,
					item_code=item_code,
					score=score,
					bin_qty=bin_qty,
					issue_qty=0,
					status="already_done",
					project=project,
				)
			)
			continue

		if excel_stock > bin_qty + 0.0001:
			report_rows.append(
				_report_line(
					row,
					warehouse=warehouse,
					item_code=item_code,
					score=score,
					bin_qty=bin_qty,
					issue_qty=0,
					status="excel_gt_bin",
					project=project,
				)
			)
			continue

		issue_qty = flt(bin_qty - excel_stock, 6)
		if issue_qty <= 0:
			report_rows.append(
				_report_line(
					row,
					warehouse=warehouse,
					item_code=item_code,
					score=score,
					bin_qty=bin_qty,
					issue_qty=0,
					status="skip_equal",
					project=project,
				)
			)
			continue

		report_rows.append(
			_report_line(
				row,
				warehouse=warehouse,
				item_code=item_code,
				score=score,
				bin_qty=bin_qty,
				issue_qty=issue_qty,
				status="issue",
				project=project,
			)
		)
		issue_plan.setdefault((warehouse, project), []).append(
			{
				"item_code": item_code,
				"qty": issue_qty,
				"excel_material": row["material"],
			}
		)

	csv_path = write_report_csv(report_rows)

	created: list[str] = []
	errors: list[str] = []
	if not dry_run:
		created, errors = create_material_issues(issue_plan)
		frappe.db.commit()

	summary = _summarize(report_rows, created, errors, csv_path, dry_run=dry_run)
	_log_summary(summary)
	return summary


def parse_ssr_excel(xlsx_path: str) -> list[dict]:
	if openpyxl is None:
		frappe.throw("openpyxl is required to read the SSR Excel file")

	wb = openpyxl.load_workbook(xlsx_path, data_only=True)
	ws = wb.active
	cur_proj = None
	cur_name = None
	rows: list[dict] = []

	for row in ws.iter_rows(min_row=4, values_only=True):
		cells = list(row) + [None] * 8
		_sno, pname, pno, _eng, mat, unit, stock, remark = cells[:8]
		if pno or pname:
			cur_proj = str(pno).strip() if pno not in (None, "") else cur_proj
			cur_name = str(pname).strip() if pname not in (None, "") else cur_name
		if not mat or stock is None:
			continue
		rows.append(
			{
				"project_no": cur_proj or "",
				"project_name": cur_name or "",
				"material": str(mat).strip(),
				"unit": str(unit).strip() if unit else "",
				"stock": flt(stock),
				"remark": str(remark).strip() if remark else "",
			}
		)
	return rows


def split_project_nos(project_no: str) -> list[str]:
	if not project_no:
		return []
	parts = re.split(r"\s*&\s*|\s*,\s*", str(project_no).strip())
	return [p.strip() for p in parts if p and p.strip()]


def resolve_warehouses(project_nos: list[str]) -> list[dict]:
	"""Return [{project, warehouse, company}, ...] for site_location warehouses."""
	out: list[dict] = []
	seen = set()
	for project in project_nos:
		if not frappe.db.exists("Project", project):
			continue
		info = frappe.db.get_value(
			"Project",
			project,
			["name", "site_location", "company"],
			as_dict=True,
		)
		if not info or not info.site_location:
			continue
		if info.company and info.company != COMPANY:
			# Still allow if site warehouse belongs to MRG
			wh_company = frappe.db.get_value("Warehouse", info.site_location, "company")
			if wh_company and wh_company != COMPANY:
				continue
		key = (info.name, info.site_location)
		if key in seen:
			continue
		seen.add(key)
		out.append(
			{
				"project": info.name,
				"warehouse": info.site_location,
				"company": info.company or COMPANY,
			}
		)
	return out


def load_item_map() -> dict[tuple[str, str], str]:
	"""Load optional override map: (project_no, material_norm) -> item_code."""
	path = _map_csv_path()
	mapping: dict[tuple[str, str], str] = {}
	if not os.path.exists(path):
		_ensure_map_template(path)
		return mapping

	with open(path, newline="", encoding="utf-8") as fh:
		reader = csv.DictReader(fh)
		for row in reader:
			if not row:
				continue
			material = (row.get("material_description") or "").strip()
			item_code = (row.get("item_code") or "").strip()
			if not material or not item_code:
				continue
			project_no = (row.get("project_no") or "").strip()
			mapping[(project_no, normalize_text(material))] = item_code
			# also allow blank project_no as global override
			if project_no:
				mapping[("", normalize_text(material))] = mapping.get(
					("", normalize_text(material)), item_code
				)
	return mapping


def _lookup_override(
	mapping: dict[tuple[str, str], str], project_no: str, material: str
) -> str | None:
	norm = normalize_text(material)
	for key in (
		(project_no or "", norm),
		("", norm),
	):
		if key in mapping:
			return mapping[key]
	# try each split project
	for part in split_project_nos(project_no):
		if (part, norm) in mapping:
			return mapping[(part, norm)]
	return None


def get_warehouse_bins(warehouse: str) -> list[dict]:
	return frappe.db.sql(
		"""
		SELECT b.item_code, b.actual_qty, i.item_name, i.stock_uom
		FROM `tabBin` b
		JOIN `tabItem` i ON i.name = b.item_code
		WHERE b.warehouse = %s AND b.actual_qty > 0 AND IFNULL(i.disabled, 0) = 0
		ORDER BY b.item_code
		""",
		warehouse,
		as_dict=True,
	)


def match_material_to_bin(
	material: str,
	warehouses: list[dict],
	override_item: str | None = None,
) -> dict | None:
	"""Match SSR material description to a Bin item in candidate warehouses."""
	candidates: list[dict] = []

	for wh in warehouses:
		bins = get_warehouse_bins(wh["warehouse"])
		if override_item:
			for b in bins:
				if b.item_code == override_item:
					candidates.append(
						{
							"warehouse": wh["warehouse"],
							"project": wh["project"],
							"item_code": b.item_code,
							"item_name": b.item_name,
							"bin_qty": flt(b.actual_qty),
							"score": 1.0,
						}
					)
			# override may exist with zero qty — still record for excel_gt_bin
			if not any(c["warehouse"] == wh["warehouse"] for c in candidates):
				qty = flt(
					frappe.db.get_value(
						"Bin",
						{"item_code": override_item, "warehouse": wh["warehouse"]},
						"actual_qty",
					)
				)
				if frappe.db.exists("Item", override_item):
					candidates.append(
						{
							"warehouse": wh["warehouse"],
							"project": wh["project"],
							"item_code": override_item,
							"item_name": frappe.db.get_value("Item", override_item, "item_name"),
							"bin_qty": qty,
							"score": 1.0,
						}
					)
			continue

		for b in bins:
			score = score_material_match(material, b.item_code, b.item_name)
			if score >= MATCH_THRESHOLD:
				candidates.append(
					{
						"warehouse": wh["warehouse"],
						"project": wh["project"],
						"item_code": b.item_code,
						"item_name": b.item_name,
						"bin_qty": flt(b.actual_qty),
						"score": score,
					}
				)

	if not candidates:
		return None

	# Prefer higher score, then higher bin qty (for combined 1099 & 1148)
	candidates.sort(key=lambda c: (c["score"], c["bin_qty"]), reverse=True)
	best = candidates[0]

	# Ambiguity: another candidate within 0.02 score on same warehouse with different item
	same_wh = [
		c
		for c in candidates
		if c["warehouse"] == best["warehouse"] and c["item_code"] != best["item_code"]
	]
	if same_wh and abs(same_wh[0]["score"] - best["score"]) < 0.02 and same_wh[0]["score"] >= MATCH_THRESHOLD:
		# too close — treat as unmatched unless override was used
		if best["score"] < 1.0:
			return None

	return best


GENERIC_TOKENS = {
	"MM",
	"KG",
	"LTR",
	"LTS",
	"SET",
	"DRUM",
	"ROLL",
	"AE",
	"THE",
	"AND",
	"OF",
	"X",
	"M",
	"PART",
	"A",
	"B",
	"WHITE",
	"GREY",
	"GRAY",
	"BLACK",
	"LIGHT",
	"DARK",
	"FULL",
	"EMPTY",
	"NOS",
	"BOX",
	"BUNDLE",
	"BUCKETS",
	"PALLET",
}


def normalize_text(value: str) -> str:
	return re.sub(r"[^A-Z0-9]+", " ", (value or "").upper()).strip()


def _distinctive_tokens(text: str) -> set[str]:
	tokens = set(normalize_text(text).split()) - GENERIC_TOKENS
	# Keep short numeric/product codes (152, 550, D41, P12, E35, 4MM → 4 kept via digit)
	return {t for t in tokens if len(t) >= 2}


def _product_codes(text: str) -> set[str]:
	"""Digits / alnum product markers that must align when present on SSR side."""
	codes = set()
	for tok in normalize_text(text).split():
		if tok in GENERIC_TOKENS:
			continue
		if re.search(r"\d", tok):
			codes.add(tok)
			# Also split embedded digits: FLEX550 → 550, D41 → D41 + 41
			for part in re.findall(r"\d+", tok):
				if part not in GENERIC_TOKENS:
					codes.add(part)
	return codes


def score_material_match(material: str, item_code: str, item_name: str) -> float:
	mat = normalize_text(material)
	code = normalize_text(item_code)
	name = normalize_text(item_name)
	hay = f"{code} {name}".strip()

	if not mat or not hay:
		return 0.0
	if mat == code or mat == name:
		return 1.0

	# If SSR has numeric product codes (152, 550, 41…), require each digit group in the item.
	mat_digits = {c for c in _product_codes(material) if c.isdigit()}
	hay_digits = {c for c in (_product_codes(item_code) | _product_codes(item_name)) if c.isdigit()}
	if mat_digits and not mat_digits.issubset(hay_digits):
		return min(0.4, SequenceMatcher(None, mat, name).ratio())

	mat_tokens = _distinctive_tokens(material)
	hay_tokens = _distinctive_tokens(item_code) | _distinctive_tokens(item_name)
	mat_compact = mat.replace(" ", "")
	hay_compact = hay.replace(" ", "")

	if mat in hay or mat_compact in hay_compact:
		return 0.95
	if mat_tokens and mat_tokens <= hay_tokens:
		return 0.92

	# Token-wise: SSR token is prefix/substring of an item token (SIKATOP≈SIKA+TOP via compact)
	token_hits = 0
	for tok in mat_tokens:
		if tok in hay_tokens or any(tok in ht or ht in tok for ht in hay_tokens if len(tok) >= 3):
			token_hits += 1
	overlap = token_hits / max(len(mat_tokens), 1) if mat_tokens else 0
	fuzzy = SequenceMatcher(None, mat, name).ratio()
	compact_fuzzy = SequenceMatcher(None, mat_compact, hay_compact[: max(len(mat_compact) * 3, 1)]).ratio()

	# Generic short SSR names (PU FOAM, MESH) need near-full distinctive overlap
	if len(mat_tokens) <= 2 and overlap < 0.99:
		return max(overlap * 0.7, compact_fuzzy if compact_fuzzy >= 0.8 else 0)
	return max(fuzzy, compact_fuzzy * 0.9, overlap * 0.95)


def create_material_issues(
	issue_plan: dict[tuple[str, str], list[dict]],
) -> tuple[list[str], list[str]]:
	created: list[str] = []
	errors: list[str] = []

	for (warehouse, project), lines in sorted(issue_plan.items()):
		company = frappe.db.get_value("Project", project, "company") or COMPANY
		# re-read live qty and rebuild chunks
		live_lines: list[dict] = []
		for line in lines:
			live_qty = flt(
				frappe.db.get_value(
					"Bin",
					{"item_code": line["item_code"], "warehouse": warehouse},
					"actual_qty",
				)
			)
			qty = min(flt(line["qty"]), live_qty)
			if qty <= 0:
				continue
			live_lines.append({**line, "qty": qty})

		for chunk in _chunk(live_lines, ITEMS_PER_ENTRY):
			name = None
			# Prefer SSR as-of date; fall back to today when backdated stock check fails.
			for posting_date in (POSTING_DATE, frappe.utils.nowdate()):
				savepoint = f"ssr_{frappe.generate_hash(length=8)}"
				frappe.db.savepoint(savepoint)
				try:
					name = _create_material_issue(
						company=company,
						project=project,
						warehouse=warehouse,
						lines=chunk,
						posting_date_override=posting_date,
					)
					if name:
						created.append(name)
						frappe.db.commit()
					break
				except Exception as exc:
					frappe.db.rollback(save_point=savepoint)
					if posting_date == frappe.utils.nowdate():
						errors.append(f"{warehouse}: {exc}")
						frappe.log_error(
							title=f"SSR consume failed for {warehouse}",
							message=frappe.get_traceback(),
						)

	return created, errors


def _create_material_issue(
	*,
	company: str,
	project: str,
	warehouse: str,
	lines: list[dict],
	posting_date_override: str | None = None,
) -> str | None:
	posting_date = getdate(posting_date_override or POSTING_DATE)
	se = frappe.new_doc("Stock Entry")
	se.company = company
	se.stock_entry_type = STOCK_ENTRY_TYPE
	se.purpose = STOCK_ENTRY_TYPE
	se.posting_date = posting_date
	se.set_posting_time = 1
	se.posting_time = "23:59:59"
	se.project = project
	se.from_warehouse = warehouse
	se.remarks = (
		f"{REMARK_TAG}: reduce site stock to SSR balance as of {POSTING_DATE} "
		f"(Project {project}, WH {warehouse}; posted {posting_date})"
	)

	for line in lines:
		qty = flt(line["qty"])
		if qty <= 0:
			continue
		# Cap again at submit time against current Bin
		live_qty = flt(
			frappe.db.get_value(
				"Bin",
				{"item_code": line["item_code"], "warehouse": warehouse},
				"actual_qty",
			)
		)
		qty = min(qty, live_qty)
		if qty <= 0:
			continue
		se.append(
			"items",
			{
				"item_code": line["item_code"],
				"qty": qty,
				"s_warehouse": warehouse,
				"project": project,
				"allow_zero_valuation_rate": 1,
			},
		)

	if not se.items:
		return None

	se.flags.ignore_permissions = True
	se.insert()
	se.submit()
	return se.name


def _already_issued_pairs() -> set[tuple[str, str]]:
	"""(warehouse, item_code) already consumed by a submitted SSR SE."""
	rows = frappe.db.sql(
		"""
		SELECT sed.s_warehouse AS warehouse, sed.item_code
		FROM `tabStock Entry` se
		JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
		WHERE se.docstatus = 1
		  AND se.stock_entry_type = %s
		  AND se.remarks LIKE %s
		""",
		(STOCK_ENTRY_TYPE, f"%{REMARK_TAG}%"),
		as_dict=True,
	)
	return {(r.warehouse, r.item_code) for r in rows if r.warehouse and r.item_code}


def write_report_csv(report_rows: list[dict]) -> str:
	path = _report_csv_path()
	os.makedirs(os.path.dirname(path), exist_ok=True)
	fields = [
		"project",
		"project_no",
		"project_name",
		"warehouse",
		"excel_material",
		"matched_item",
		"match_score",
		"bin_qty",
		"excel_stock",
		"issue_qty",
		"status",
		"unit",
		"remark",
	]
	with open(path, "w", newline="", encoding="utf-8") as fh:
		writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
		writer.writeheader()
		for row in report_rows:
			writer.writerow(row)
	return path


def _report_line(
	row: dict,
	*,
	warehouse: str,
	item_code: str,
	score: float,
	bin_qty: float,
	issue_qty: float,
	status: str,
	project: str | None = None,
) -> dict:
	return {
		"project": project or (split_project_nos(row["project_no"])[:1] or [""])[0],
		"project_no": row["project_no"],
		"project_name": row["project_name"],
		"warehouse": warehouse,
		"excel_material": row["material"],
		"matched_item": item_code,
		"match_score": round(flt(score), 4),
		"bin_qty": flt(bin_qty),
		"excel_stock": flt(row["stock"]),
		"issue_qty": flt(issue_qty),
		"status": status,
		"unit": row.get("unit") or "",
		"remark": row.get("remark") or "",
	}


def _summarize(
	report_rows: list[dict],
	created: list[str],
	errors: list[str],
	csv_path: str,
	*,
	dry_run: int,
) -> dict:
	counts: dict[str, int] = {}
	for r in report_rows:
		counts[r["status"]] = counts.get(r["status"], 0) + 1
	return {
		"dry_run": bool(dry_run),
		"posting_date": POSTING_DATE,
		"total_rows": len(report_rows),
		"status_counts": counts,
		"issue_qty_total": sum(flt(r["issue_qty"]) for r in report_rows if r["status"] == "issue"),
		"created_stock_entries": created,
		"errors": errors,
		"report_csv": csv_path,
		"map_csv": _map_csv_path(),
	}


def _log_summary(summary: dict):
	msg = (
		f"SSR consume ({'dry-run' if summary['dry_run'] else 'SUBMITTED'}): "
		f"{summary['status_counts']} issue_qty_total={summary['issue_qty_total']} "
		f"SEs={summary['created_stock_entries'] or 'none'} "
		f"report={summary['report_csv']}"
	)
	frappe.logger("construction_management").info(msg)
	try:
		frappe.msgprint(msg, alert=True)
	except Exception:
		pass


def _resolve_xlsx_path(xlsx_path: str | None) -> str:
	if xlsx_path and os.path.exists(xlsx_path):
		return xlsx_path

	bench_root = Path(frappe.utils.get_bench_path())
	candidates = [
		bench_root / DEFAULT_XLSX_NAME,
		bench_root / "SSR ALL SITES UPTO JUNE.30.2026.xlsx",
		Path(get_files_path(is_private=True)) / DEFAULT_XLSX_NAME,
		Path(get_files_path(is_private=False)) / DEFAULT_XLSX_NAME,
	]
	for path in candidates:
		if path.exists():
			return str(path)

	frappe.throw(
		f"SSR Excel not found. Place `{DEFAULT_XLSX_NAME}` in the bench root "
		f"or pass xlsx_path=..."
	)


def _private_files_dir() -> str:
	return get_files_path(is_private=True)


def _map_csv_path() -> str:
	return os.path.join(_private_files_dir(), MAP_CSV_NAME)


def _report_csv_path() -> str:
	return os.path.join(_private_files_dir(), REPORT_CSV_NAME)


def _ensure_map_template(path: str):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	if os.path.exists(path):
		return
	with open(path, "w", newline="", encoding="utf-8") as fh:
		writer = csv.DictWriter(
			fh, fieldnames=["project_no", "material_description", "item_code"]
		)
		writer.writeheader()


def _chunk(seq: list, size: int):
	for i in range(0, len(seq), size):
		yield seq[i : i + size]
