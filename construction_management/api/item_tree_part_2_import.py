"""Approval-gated import of new MRG stock items from Item Tree Part 2."""

import csv
import hashlib
from collections import defaultdict
from io import BytesIO, StringIO
from pathlib import Path

import frappe
from frappe.utils.file_manager import save_file
from openpyxl import Workbook, load_workbook

from construction_management.api import controlled_procurement as catalog


COMPANY = "M R G INSULATION WORKS L.L.C"
PACKAGE_SOURCE = Path(__file__).resolve().parents[1] / "data" / "controlled_procurement_catalog_item_tree_part_2_v2.xlsx"
PACKAGE_SHA256 = "bf62b0dc65c27336f99d9c1799bc646d2afea8296c51f888133fb9da3a37bea4"
EXPECTED_INITIAL_CREATE_COUNT = 105
HEADERS = ["Item Code", "Description", "Item Group", "Item Type", "Stock UOM",
    "Asset Category", "Expense Account", "Supplier", "Rates"]


def _key(value):
	return " ".join(str(value or "").split()).casefold()


def _source_rows(path):
	book = load_workbook(path, read_only=True, data_only=True)
	if "Sheet2" not in book:
		frappe.throw("Sheet2 is missing from the source workbook.")
	return [(number, values) for number, values in enumerate(book["Sheet2"].values, 1)
		if number > 2 and len(values) > 5 and values[0] and values[1]
		and _key(values[0]) != "item group"]


def _prepare(path):
	items = {_key(row.item_name) for row in frappe.get_all("Item", fields=["item_name"], limit_page_length=0)}
	suppliers = frappe.get_all("Supplier", fields=["name", "supplier_name"], limit_page_length=0)
	supplier_ids = {_key(value): row.name for row in suppliers for value in (row.name, row.supplier_name)}
	groups = {_key(name): name for name in frappe.get_all("Item Group", pluck="name", limit_page_length=0)}
	by_name = defaultdict(list)
	held = []
	for number, values in _source_rows(path):
		name = _key(values[1])
		if name in items:
			continue
		if _key(values[5]) not in {"material in stock", "consumable"}:
			held.append((number, values[1], "Asset/Service: accounting mapping required"))
			continue
		by_name[name].append((number, values))
	selected = []
	missing_groups = set()
	for entries in by_name.values():
		identity = {(_key(row[0]), _key(row[2]), _key(row[3]), row[4], _key(row[5]))
			for _, row in entries}
		if len(identity) != 1:
			held.extend((number, row[1], "Conflicting duplicate description or rate") for number, row in entries)
			continue
		number, row = entries[0]
		supplier = supplier_ids.get(_key(row[2]))
		if not supplier:
			held.append((number, row[1], "Supplier master not found"))
			continue
		group = str(row[0]).strip()
		if _key(group) not in groups:
			missing_groups.add(group)
		uom = catalog._catalog_uom(row[3])
		if not isinstance(row[4], (int, float)) or row[4] <= 0:
			held.append((number, row[1], "Positive buying rate required"))
			continue
		selected.append((number, ["", str(row[1]).strip(), groups.get(_key(group), group),
			"Stockable" if _key(row[5]) == "material in stock" else "Consumable", uom,
			"", "", supplier, row[4]]))
	return selected, sorted(held), sorted(missing_groups)


def _normalized_workbook(selected):
	book = Workbook()
	sheet = book.active
	sheet.title = "Catalog Items"
	sheet.append(HEADERS)
	for _, values in selected:
		sheet.append(values)
	stream = BytesIO()
	book.save(stream)
	return stream.getvalue()


def _exception_csv(held):
	stream = StringIO()
	writer = csv.writer(stream)
	writer.writerow(["Sheet", "Source row", "Description", "Reason"])
	for number, description, reason in held:
		writer.writerow(["Sheet2", number, description, reason])
	return stream.getvalue().encode("utf-8-sig")


def _source_checksum(path: Path) -> str:
	return hashlib.sha256(path.read_bytes()).hexdigest()


def _existing_request(source_checksum: str):
	return frappe.db.get_value(
		"Controlled Catalog Request",
		{"full_source_checksum": source_checksum},
		["name", "status"],
		as_dict=True,
	)


def _validate_packaged_source(path: Path, selected: list) -> None:
	if path.resolve() != PACKAGE_SOURCE.resolve():
		return
	if _source_checksum(path) != PACKAGE_SHA256:
		frappe.throw("The packaged Item Tree Part 2 workbook checksum is invalid.")
	if len(selected) != EXPECTED_INITIAL_CREATE_COUNT:
		frappe.throw(
			f"Expected {EXPECTED_INITIAL_CREATE_COUNT} new Item Tree Part 2 items; found {len(selected)}. "
			"Review the existing catalog before importing."
		)


def preview(path: str | None = None):
	"""Read-only preflight for the selected source workbook."""
	path = Path(path or PACKAGE_SOURCE)
	selected, held, groups = _prepare(path)
	return {"selected": len(selected), "stockable": sum(row[3] == "Stockable" for _, row in selected),
		"consumable": sum(row[3] == "Consumable" for _, row in selected),
		"missing_groups": groups, "held": held,
		"source_sha256": _source_checksum(path)}


def submit(path: str | None = None):
	"""Create missing groups and one normal catalog approval request as Administrator."""
	frappe.set_user("Administrator")
	source = Path(path or PACKAGE_SOURCE)
	source_checksum = _source_checksum(source)
	existing = _existing_request(source_checksum)
	if existing:
		return {"name": existing.name, "status": existing.status, "already_imported": True}
	selected, held, groups = _prepare(source)
	_validate_packaged_source(source, selected)
	if not selected:
		return {"name": "", "status": "", "already_imported": True, "reason": "No missing catalog items"}
	for group in groups:
		if not frappe.db.exists("Item Group", group):
			frappe.get_doc({"doctype": "Item Group", "item_group_name": group,
				"parent_item_group": "All Item Groups", "is_group": 0}).insert()
	frappe.defaults.set_user_default("company", COMPANY)
	normalized = save_file("item_tree_part_2_controlled_import.xlsx", _normalized_workbook(selected),
		None, None, is_private=1)
	preview_result = catalog.preview_catalog_workbook(normalized.file_url)
	if preview_result["errors"] or preview_result["valid_rows"] != len(selected) or preview_result["create"] != len(selected):
		frappe.throw("Normalized workbook preview did not confirm the expected new, valid items.")
	result = catalog.import_catalog_workbook(normalized.file_url)
	request_name = result["name"]
	full_source = save_file(source.name, source.read_bytes(), None, None, is_private=1)
	for file_doc in (
		normalized,
		full_source,
		save_file("item_tree_part_2_exceptions.csv", _exception_csv(held), None, None, is_private=1),
	):
		file_doc.reload()
		file_doc.attached_to_doctype = "Controlled Catalog Request"
		file_doc.attached_to_name = request_name
		file_doc.save(ignore_permissions=True)
	request = frappe.get_doc("Controlled Catalog Request", request_name)
	request.full_source_file = full_source.file_url
	request.full_source_checksum = source_checksum
	request.save(ignore_permissions=True)
	request.add_comment("Info", f"Source Sheet2 SHA-256: {source_checksum}. "
		f"Selected {len(selected)} new Stockable/Consumable items; {len(held)} source rows held in the attached exception report.")
	return {**result, "preview": {key: preview_result[key] for key in ("valid_rows", "create", "reuse", "errors")},
		"held_rows": len(held), "missing_groups_created": groups, "source_file": normalized.file_url}
