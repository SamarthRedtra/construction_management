"""Export the held MRG Item Tree rows with action-oriented correction guidance."""

from __future__ import annotations

import csv
from collections import Counter
from io import StringIO
from pathlib import Path

import frappe
from frappe.utils.file_manager import save_file

from construction_management.api import item_tree_part_2_expanded_import as expanded_import


SOURCE_PATH = Path("/Users/samarthupare/Downloads/Item Tree Part 2 (3).xlsx")
REQUEST_NAME = "CCR-02250"
COMPANY = "M R G INSULATION WORKS L.L.C"


@frappe.whitelist(methods=["POST"])
def export(path: str = str(SOURCE_PATH)) -> dict:
	"""Create an ERP attachment listing every held source row and its remedy."""
	frappe.only_for(("System Manager", "CEO", "Accounts Manager", "Stock Manager"))
	source = Path(path)
	_, held, _, _ = expanded_import._prepare(source)
	source_rows = dict(expanded_import._source_rows(source))
	csv_content = _csv_content(held, source_rows)
	attachment = save_file(
		"MRG_Item_Tree_Corrections_Required.csv",
		csv_content.encode(),
		"Controlled Catalog Request" if frappe.db.exists("Controlled Catalog Request", REQUEST_NAME) else "Company",
		REQUEST_NAME if frappe.db.exists("Controlled Catalog Request", REQUEST_NAME) else COMPANY,
		is_private=1,
	)
	return {
		"file_url": attachment.file_url,
		"held_rows": len(held),
		"by_issue": dict(sorted(Counter(reason for _, _, reason in held).items())),
	}


def _csv_content(held: list[tuple], source_rows: dict[int, tuple]) -> str:
	output = StringIO()
	writer = csv.writer(output)
	writer.writerow([
		"Sheet", "Source Row", "Item Group", "Description", "Supplier", "UOM", "Buying Rate",
		"Allocation", "Import Issue", "Required Correction",
	])
	for row_number, description, reason in held:
		group, _, supplier, uom, rate, allocation = source_rows[row_number]
		writer.writerow([
			"Sheet2", row_number, _clean(group), description, _clean(supplier), _clean(uom), rate,
			_clean(allocation), reason, _correction(reason),
		])
	return output.getvalue()


def _correction(reason: str) -> str:
	if reason == "Supplier master not found":
		return "Create/approve this supplier master, or replace it with the exact name of an existing approved supplier."
	if reason == "Positive buying rate required":
		return "Enter the approved buying rate; it must be greater than zero."
	if reason == "Conflicting buying rates for the same supplier":
		return "For this item and supplier, use one approved rate on every duplicate row, or give genuinely different items distinct descriptions."
	if reason == "Conflicting item group or accounting mapping":
		return "Use one Item Group and one classification/accounting mapping for this description, or split genuinely different items into distinct descriptions."
	if reason == "Multiple existing Items have this UOM":
		return "Confirm the intended existing Item Code to adopt, or use a distinct description so a duplicate master is not created."
	if reason == "Existing controlled Item conflicts with this type/UOM":
		return "Match the existing controlled item's UOM and allocation/type, or use a distinct description for a genuinely different item."
	return "Correct the source details so this row has one unambiguous catalog definition."


def _clean(value) -> str:
	return " ".join(str(value or "").split())
