# Copyright (c) 2026, Construction Management
# License: MIT

"""Repair package UOM quantities listed in Book1 (4).xlsx.

Run a report first:
    bench --site <site> execute \
        construction_management.scripts.workbook_material_uom_repair.run

Apply explicitly (the registered patch calls this mode during migrate):
    bench --site <site> execute \
        construction_management.scripts.workbook_material_uom_repair.run \
        --kwargs '{"dry_run": false}'
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import frappe
from frappe.utils import flt


@dataclass(frozen=True)
class MaterialSpec:
	item_code: str
	stock_uom: str
	package_uom: str
	conversion_factor: float
	workbook_rate: float
	accepted_package_rates: tuple[float, ...]
	aliases: tuple[str, ...] = ("Nos",)


SPECS = (
	MaterialSpec(
		"GEOTEC -120GSM GEOTEXTILE  (3 X 100)300 M²/ ROLL",
		"M2", "Nos", 300, 385, (330, 360, 385), ("Nos", "ROLL"),
	),
	MaterialSpec(
		"GEOTEC 250 GSM GEOTEXTILE  (6 X 100) 600 M² /ROLL",
		"M2", "Nos", 600, 1500, (1500,), ("Nos", "ROLL"),
	),
	MaterialSpec(
		"NW 120 GSM PET -WHITE (3 MTR *100 MTR)",
		"M2", "Nos", 300, 360, (330, 360, 365), ("Nos", "ROLL"),
	),
	MaterialSpec(
		"NW 250 GSM PET -WHITE (3 MTR *100 MTR)",
		"M2", "Nos", 300, 745, (745,), ("Nos", "ROLL"),
	),
	MaterialSpec(
		"NEOPOL SRS 45  (220KG) DRUM",
		"Kg", "Nos", 220, 2596, (2508, 2596), ("Nos", "DRUM"),
	),
	MaterialSpec(
		"NEONATE MDI (250KG) DRUM",
		"Kg", "Nos", 250, 2950, (2850, 2950), ("Nos", "DRUM"),
	),
	MaterialSpec(
		"WEBERDRY SPF 45W -PART A (250KG) DRUM",
		"Kg", "Nos", 250, 2728, (2728, 2772, 3100, 3125), ("Nos", "DRUM"),
	),
	MaterialSpec(
		"WEBERDRY SPF 45W -PART B (220KG) DRUM",
		"Kg", "Nos", 220, 3100, (2720, 2750, 3100, 3150), ("Nos", "DRUM"),
	),
	MaterialSpec(
		"RHEOSEAL RBE350 ( 200 LTR PER DRUM )",
		"Litre", "Nos", 200, 365, (365,), ("Nos", "DRUM"),
	),
	MaterialSpec(
		"HUNTSMAN SP 45 (220KG) DRUM",
		"Kg", "Nos", 220, 2508, (2508, 2596), ("Nos", "DRUM"),
	),
	MaterialSpec(
		"HUNTSMAN 200 (250KG) DRUM",
		"Kg", "Nos", 250, 2850, (2850, 2950), ("Nos", "DRUM"),
	),
	MaterialSpec(
		"NEOFLEX PU 25 LM (POLYURETHENE SEALANT) 600 ML-GREY",
		"TUBE", "Nos", 20, 216, (216,), ("Nos", "Box"),
	),
	MaterialSpec(
		"SIKAFLEX-428 PRECAST CONCRETE GREY",
		"PCS", "Nos", 20, 288, (288,), ("Nos", "CAR"),
	),
)


# These workbook rows already use a one-to-one stock package, so no historical
# quantity multiplication is required. They are retained in the audit output.
ONE_TO_ONE_ITEMS = {
	"NEOSEAL FLEX 588 -WHITE (PART A 26.25 KG+PART B 8.75 KG)": 112,
	"JK PROFIX WPC11- HIGH FLEXIBLE  TWO COMPONENT ACRYLIC MODIFIED CEMENTITIOUS WATERPROOF COATING  ( 20+10 KG ) 30 KG PER SET BEIGE COLOUR": 115,
	"RHEOPRIME SB  ( 200 LTR DRUM )": 890,
	"BITUMEN IMPEREGNATED BOARD 10 MM -CUTTING": 56,
	"FILLER BOARD 10MM THICK WITH 7CM CUTTING PCS": 54,
}


def run(dry_run: bool = True, repost: bool = True) -> dict:
	"""Audit or repair confirmed workbook UOM mistakes."""
	dry_run = _as_bool(dry_run)
	repost = _as_bool(repost)
	report = {
		"dry_run": dry_run,
		"master_changes": [],
		"purchase_rows": [],
		"stock_entry_rows": [],
		"dpr_rows": [],
		"repost_vouchers": [],
		"one_to_one_items": [],
	}

	_validate_items()
	for spec in SPECS:
		_sync_item_uoms(spec, dry_run, report)
		_collect_purchase_rows(spec, dry_run, report)
		_collect_dpr_rows(spec, dry_run, report)
		_collect_package_stock_entry_rows(spec, dry_run, report)

	_collect_one_to_one_items(dry_run, report)
	if not dry_run and repost:
		_repost_vouchers(report["repost_vouchers"])

	if not dry_run:
		frappe.db.commit()

	_print_report(report)
	return report


def _validate_items() -> None:
	missing = [spec.item_code for spec in SPECS if not frappe.db.exists("Item", spec.item_code)]
	if missing:
		frappe.throw("Workbook repair stopped; Item(s) not found: " + ", ".join(missing))

	wrong_stock_uom = []
	for spec in SPECS:
		actual = frappe.db.get_value("Item", spec.item_code, "stock_uom")
		if actual != spec.stock_uom:
			wrong_stock_uom.append(f"{spec.item_code}: expected {spec.stock_uom}, found {actual}")
	if wrong_stock_uom:
		frappe.throw("Workbook repair stopped; unexpected stock UOM: " + "; ".join(wrong_stock_uom))


def _sync_item_uoms(spec: MaterialSpec, dry_run: bool, report: dict) -> None:
	for uom in {spec.package_uom, *spec.aliases}:
		expected = spec.conversion_factor
		row = frappe.db.get_value(
			"UOM Conversion Detail",
			{"parent": spec.item_code, "uom": uom},
			["name", "conversion_factor"],
			as_dict=True,
		)
		if row and flt(row.conversion_factor) == expected:
			continue

		report["master_changes"].append(
			{"item_code": spec.item_code, "uom": uom, "old": flt(row.conversion_factor) if row else None, "new": expected}
		)
		if dry_run:
			continue

		if row:
			frappe.db.set_value("UOM Conversion Detail", row.name, "conversion_factor", expected, update_modified=False)
		else:
			item = frappe.get_doc("Item", spec.item_code)
			item.append("uoms", {"uom": uom, "conversion_factor": expected})
			item.flags.ignore_validate_update_after_submit = True
			item.save(ignore_permissions=True)


def _collect_purchase_rows(spec: MaterialSpec, dry_run: bool, report: dict) -> None:
	rows = frappe.db.sql(
		"""
		SELECT pri.name, pri.parent, pr.posting_date, pri.qty, pri.uom,
			pri.conversion_factor, pri.rate, pri.amount, pri.purchase_order,
			pri.purchase_order_item
		FROM `tabPurchase Receipt Item` pri
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pr.docstatus = 1 AND pri.item_code = %(item_code)s
			AND pri.uom IN %(aliases)s AND pri.conversion_factor != %(conversion_factor)s
		ORDER BY pr.posting_date, pr.posting_time, pr.creation, pri.idx
		""",
		{
			"item_code": spec.item_code,
			"aliases": spec.aliases,
			"conversion_factor": spec.conversion_factor,
		},
		as_dict=True,
	)
	for row in rows:
		if not _matches_package_rate(row.rate, spec.accepted_package_rates):
			continue

		report["purchase_rows"].append(_row_summary("Purchase Receipt", row, spec))
		_add_repost(report, "Purchase Receipt", row.parent, row.posting_date)
		if dry_run:
			continue

		_update_purchase_row("Purchase Receipt Item", row.name, spec.conversion_factor)
		_update_linked_purchase_invoice_rows(row.name, spec)
		_update_purchase_order_row(row.purchase_order_item, spec)


def _collect_dpr_rows(spec: MaterialSpec, dry_run: bool, report: dict) -> None:
	rows = frappe.db.sql(
		"""
		SELECT dm.name, dm.parent, dm.stock_entry, dm.qty, dm.uom, dm.rate, dm.amount,
			dpr.date AS posting_date
		FROM `tabDPR Material` dm
		INNER JOIN `tabDaily Progress Record` dpr ON dpr.name = dm.parent
		WHERE dpr.docstatus = 1 AND dm.item_code = %(item_code)s
			AND dm.uom IN %(uoms)s
		ORDER BY dpr.date, dpr.creation, dm.idx
		""",
		{"item_code": spec.item_code, "uoms": (spec.stock_uom, spec.package_uom)},
		as_dict=True,
	)
	for row in rows:
		if not _matches_package_rate(row.rate, spec.accepted_package_rates):
			continue
		stock_entry_needs_repair = bool(row.stock_entry) and _stock_entry_item_needs_dpr_repair(
			row.stock_entry, spec, row.qty, row.rate, row.amount
		)
		if row.uom == spec.package_uom and not stock_entry_needs_repair:
			continue

		report["dpr_rows"].append(_row_summary("DPR Material", row, spec))
		if row.stock_entry:
			_add_repost(report, "Stock Entry", row.stock_entry, row.posting_date)
		if dry_run:
			continue

		frappe.db.set_value("DPR Material", row.name, "uom", spec.package_uom, update_modified=False)
		if row.stock_entry:
			_update_stock_entry_item_from_dpr(
				row.stock_entry, spec, row.qty, row.rate, row.amount
			)


def _collect_package_stock_entry_rows(spec: MaterialSpec, dry_run: bool, report: dict) -> None:
	rows = frappe.db.sql(
		"""
		SELECT sed.name, sed.parent, se.posting_date, sed.qty, sed.uom,
			sed.conversion_factor, sed.basic_rate AS rate, sed.amount
		FROM `tabStock Entry Detail` sed
		INNER JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE se.docstatus = 1 AND sed.item_code = %(item_code)s
			AND sed.uom = %(package_uom)s AND sed.conversion_factor = 1
		ORDER BY se.posting_date, se.posting_time, se.creation, sed.idx
		""",
		{"item_code": spec.item_code, "package_uom": spec.package_uom},
		as_dict=True,
	)
	for row in rows:
		if not _matches_package_rate(row.rate, spec.accepted_package_rates):
			continue

		report["stock_entry_rows"].append(_row_summary("Stock Entry", row, spec))
		_add_repost(report, "Stock Entry", row.parent, row.posting_date)
		if not dry_run:
			_update_stock_entry_row(row.name, row.qty, row.rate, row.amount, spec)


def _update_purchase_row(doctype: str, row_name: str, conversion_factor: float) -> None:
	row = frappe.db.get_value(doctype, row_name, ["qty", "rate", "amount"], as_dict=True)
	if not row:
		return

	stock_qty = flt(row.qty) * conversion_factor
	values = {
		"conversion_factor": conversion_factor,
		"stock_qty": stock_qty,
		"stock_uom_rate": flt(row.rate) / conversion_factor if flt(row.rate) else 0,
	}
	if frappe.get_meta(doctype).has_field("valuation_rate"):
		values["valuation_rate"] = flt(row.amount) / stock_qty if stock_qty else 0
	frappe.db.set_value(doctype, row_name, values, update_modified=False)


def _update_linked_purchase_invoice_rows(pr_detail: str, spec: MaterialSpec) -> None:
	rows = frappe.get_all(
		"Purchase Invoice Item",
		filters={"pr_detail": pr_detail, "item_code": spec.item_code},
		pluck="name",
	)
	for row_name in rows:
		_update_purchase_row("Purchase Invoice Item", row_name, spec.conversion_factor)


def _update_purchase_order_row(row_name: str | None, spec: MaterialSpec) -> None:
	if not row_name or not frappe.db.exists("Purchase Order Item", row_name):
		return
	row = frappe.db.get_value(
		"Purchase Order Item", row_name, ["rate", "conversion_factor"], as_dict=True
	)
	if (
		row
		and flt(row.conversion_factor) != spec.conversion_factor
		and _matches_package_rate(row.rate, spec.accepted_package_rates)
	):
		_update_purchase_row("Purchase Order Item", row_name, spec.conversion_factor)


def _stock_entry_item_needs_dpr_repair(
	stock_entry: str, spec: MaterialSpec, package_qty: float, package_rate: float, amount: float
) -> bool:
	row = frappe.db.get_value(
		"Stock Entry Detail",
		{"parent": stock_entry, "item_code": spec.item_code},
		["qty", "uom", "conversion_factor", "transfer_qty", "basic_rate", "amount"],
		as_dict=True,
	)
	if not row:
		return False

	expected_transfer_qty = flt(package_qty) * spec.conversion_factor
	expected_stock_rate = flt(package_rate) / spec.conversion_factor
	return any(
		(
			row.uom != spec.package_uom,
			abs(flt(row.qty) - flt(package_qty)) > 0.000001,
			abs(flt(row.conversion_factor) - spec.conversion_factor) > 0.000001,
			abs(flt(row.transfer_qty) - expected_transfer_qty) > 0.000001,
			abs(flt(row.basic_rate) - expected_stock_rate) > 0.000001,
			abs(flt(row.amount) - flt(amount)) > 0.01,
		)
	)


def _update_stock_entry_item_from_dpr(
	stock_entry: str, spec: MaterialSpec, package_qty: float, package_rate: float, amount: float
) -> None:
	rows = frappe.get_all(
		"Stock Entry Detail",
		filters={"parent": stock_entry, "item_code": spec.item_code},
		pluck="name",
	)
	for row_name in rows:
		_update_stock_entry_row(row_name, package_qty, package_rate, amount, spec)


def _update_stock_entry_row(
	row_name: str, qty: float, package_rate: float, amount: float, spec: MaterialSpec
) -> None:
	transfer_qty = flt(qty) * spec.conversion_factor
	stock_rate = flt(package_rate) / spec.conversion_factor if flt(package_rate) else 0
	frappe.db.set_value(
		"Stock Entry Detail",
		row_name,
		{
			"qty": flt(qty),
			"uom": spec.package_uom,
			"conversion_factor": spec.conversion_factor,
			"transfer_qty": transfer_qty,
			"basic_rate": stock_rate,
			"basic_amount": flt(amount),
			"valuation_rate": flt(amount) / transfer_qty if transfer_qty else stock_rate,
			"amount": flt(amount),
		},
		update_modified=False,
	)


def _add_repost(report: dict, voucher_type: str, voucher_no: str, posting_date) -> None:
	key = (str(posting_date), voucher_type, voucher_no)
	if key not in report["repost_vouchers"]:
		report["repost_vouchers"].append(key)


def _repost_vouchers(vouchers: Iterable[tuple[str, str, str]]) -> None:
	for _, voucher_type, voucher_no in sorted(vouchers):
		if not frappe.db.exists(voucher_type, voucher_no):
			continue
		doc = frappe.get_doc(voucher_type, voucher_no)
		repost = frappe.new_doc("Repost Item Valuation")
		repost.based_on = "Transaction"
		repost.voucher_type = voucher_type
		repost.voucher_no = voucher_no
		repost.company = doc.company
		repost.posting_date = doc.posting_date
		repost.posting_time = doc.posting_time
		repost.recreate_stock_ledgers = 1
		repost.flags.ignore_permissions = True
		repost.insert()
		repost.submit()
		if hasattr(repost, "repost_now"):
			repost.repost_now()


def _collect_one_to_one_items(dry_run: bool, report: dict) -> None:
	for item_code, workbook_rate in ONE_TO_ONE_ITEMS.items():
		exists = bool(frappe.db.exists("Item", item_code))
		existing = frappe.db.get_value(
			"UOM Conversion Detail", {"parent": item_code, "uom": "Nos"}, "conversion_factor"
		) if exists else None
		action = "none; one NOS equals one stock package"
		if exists and existing is None:
			action = "add Nos conversion factor 1"
			report["master_changes"].append(
				{"item_code": item_code, "uom": "Nos", "old": None, "new": 1}
			)
			if not dry_run:
				item = frappe.get_doc("Item", item_code)
				item.append("uoms", {"uom": "Nos", "conversion_factor": 1})
				item.flags.ignore_validate_update_after_submit = True
				item.save(ignore_permissions=True)
		report["one_to_one_items"].append(
			{
				"item_code": item_code,
				"exists": exists,
				"workbook_rate": workbook_rate,
				"nos_conversion_factor": flt(existing) if existing is not None else None,
				"action": action,
			}
		)


def _matches_package_rate(rate: float, accepted_rates: tuple[float, ...]) -> bool:
	return any(abs(flt(rate) - accepted) <= 0.01 for accepted in accepted_rates)


def _row_summary(doctype: str, row, spec: MaterialSpec) -> dict:
	return {
		"doctype": doctype,
		"voucher": row.parent,
		"row": row.name,
		"item_code": spec.item_code,
		"qty": flt(row.qty),
		"uom": row.uom,
		"old_conversion_factor": flt(row.get("conversion_factor")),
		"new_conversion_factor": spec.conversion_factor,
		"rate": flt(row.rate),
		"amount": flt(row.amount),
	}


def _print_report(report: dict) -> None:
	mode = "DRY RUN" if report["dry_run"] else "APPLIED"
	print(f"Workbook material UOM repair: {mode}")
	for key in ("master_changes", "purchase_rows", "dpr_rows", "stock_entry_rows", "repost_vouchers"):
		print(f"{key}: {len(report[key])}")
	for row in report["purchase_rows"] + report["dpr_rows"] + report["stock_entry_rows"]:
		print(
			f"- {row['doctype']} {row['voucher']} | {row['item_code']} | "
			f"{row['qty']} {row['uom']} | CF {row['old_conversion_factor']} -> {row['new_conversion_factor']} | "
			f"AED {row['amount']} unchanged"
		)


def _as_bool(value) -> bool:
	if isinstance(value, str):
		return value.lower() not in {"0", "false", "no"}
	return bool(value)
