# Copyright (c) 2026, Construction Management
# License: MIT

"""Fix MRG-GRN-00782 HUNTSMAN 200 drum UOM and repost stock valuation."""

from __future__ import annotations

import frappe
from frappe.utils import flt

from construction_management.api.drum_uom_utils import get_drum_conversion_factor

PR_NAME = "MRG-GRN-00782"
PI_NAME = "MRG-PI-00864"
PO_NAME = "MRG-LPO-00451"
ITEM_CODE = "HUNTSMAN 200 (250KG) DRUM"
WAREHOUSE = "Stores - MRG"

_CHILD_PARENT_DOCTYPE = {
	"Purchase Receipt Item": "Purchase Receipt",
	"Purchase Invoice Item": "Purchase Invoice",
	"Purchase Order Item": "Purchase Order",
}


def execute():
	if not frappe.db.exists("Purchase Receipt", PR_NAME):
		return

	drum_cf = get_drum_conversion_factor(ITEM_CODE, "Nos")
	if not drum_cf:
		frappe.throw(f"DRUM conversion factor not found for {ITEM_CODE}")

	if _already_fixed(drum_cf):
		frappe.logger("construction_management").info(
			f"Skip {PR_NAME}: {ITEM_CODE} already uses drum conversion factor {drum_cf}"
		)
		return

	_fix_purchase_line("Purchase Receipt Item", PR_NAME, drum_cf)
	_fix_purchase_line("Purchase Invoice Item", PI_NAME, drum_cf)
	_fix_purchase_line("Purchase Order Item", PO_NAME, drum_cf)

	_repost_purchase_receipt_stock()
	frappe.db.commit()


def _already_fixed(drum_cf: float) -> bool:
	cf = frappe.db.get_value(
		"Purchase Receipt Item",
		{"parent": PR_NAME, "item_code": ITEM_CODE},
		"conversion_factor",
	)
	return flt(cf) == flt(drum_cf)


def _fix_purchase_line(child_doctype: str, parent: str, drum_cf: float) -> None:
	parent_doctype = _CHILD_PARENT_DOCTYPE.get(child_doctype)
	if not parent or not parent_doctype or not frappe.db.exists(parent_doctype, parent):
		return

	row = frappe.db.get_value(
		child_doctype,
		{"parent": parent, "item_code": ITEM_CODE},
		["name", "qty", "rate", "amount"],
		as_dict=True,
	)
	if not row:
		return

	stock_qty = flt(row.qty) * drum_cf
	stock_uom_rate = flt(row.rate) / drum_cf if flt(row.rate) else 0
	valuation_rate = flt(row.amount) / stock_qty if stock_qty else 0

	values = {
		"conversion_factor": drum_cf,
		"stock_qty": stock_qty,
		"stock_uom_rate": stock_uom_rate,
	}
	if frappe.get_meta(child_doctype).has_field("valuation_rate"):
		values["valuation_rate"] = valuation_rate

	frappe.db.set_value(child_doctype, row.name, values, update_modified=False)


def _repost_purchase_receipt_stock() -> None:
	pr = frappe.get_doc("Purchase Receipt", PR_NAME)
	pr.update_valuation_rate()
	for item in pr.items:
		if item.item_code == ITEM_CODE:
			item.db_set("valuation_rate", item.valuation_rate, update_modified=False)

	repost = frappe.new_doc("Repost Item Valuation")
	repost.based_on = "Transaction"
	repost.voucher_type = "Purchase Receipt"
	repost.voucher_no = PR_NAME
	repost.company = pr.company
	repost.posting_date = pr.posting_date
	repost.posting_time = pr.posting_time
	repost.recreate_stock_ledgers = 1
	repost.flags.ignore_permissions = True
	repost.insert()
	repost.submit()
	repost.repost_now()

	bin_data = frappe.db.get_value(
		"Bin",
		{"item_code": ITEM_CODE, "warehouse": WAREHOUSE},
		["actual_qty", "valuation_rate", "stock_value"],
		as_dict=True,
	)
	frappe.logger("construction_management").info(
		f"Reposted {PR_NAME} for {ITEM_CODE}. Bin @ {WAREHOUSE}: {bin_data}"
	)
