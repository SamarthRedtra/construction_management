"""Consume controlled Consumables still sitting in MRG site warehouses, one issue per original transfer."""

import frappe
from frappe import _
from frappe.utils import flt

from construction_management.api import bulk_material_issue
from construction_management.api.consumable_receipt import TRANSFER_LINK
from construction_management.api.purchase_receipt_utils import get_warehouse_project

MRG_COMPANY = "M R G INSULATION WORKS L.L.C"
SKIP_FIELD = "custom_skip_auto_consumption_for_consumables"


def execute():
	if not frappe.db.exists("Company", MRG_COMPANY) or not _prerequisites_installed():
		return
	summary = {"issues": [], "qty": 0.0, "skipped": []}
	allocations = _allocations_by_transfer(summary)
	for transfer_name in sorted(allocations, key=lambda name: allocations[name]["posting_date"], reverse=True):
		_issue_transfer(transfer_name, allocations[transfer_name]["rows"], summary)
	_print_summary(summary)


def _prerequisites_installed() -> bool:
	return all((
		frappe.db.has_column("Warehouse", SKIP_FIELD),
		frappe.db.has_column("Stock Entry", TRANSFER_LINK),
		frappe.db.has_column("BOQ Settings", "auto_consume_consumables_at_site"),
	))


def _allocations_by_transfer(summary: dict) -> dict:
	allocations = {}
	for balance in _site_consumable_balances():
		project = get_warehouse_project(balance.warehouse, company=MRG_COMPANY)
		if not project:
			summary["skipped"].append((balance.warehouse, balance.item_code, balance.actual_qty, "warehouse has no project"))
			continue
		remaining = flt(balance.actual_qty)
		for line in _unconsumed_transfer_lines(balance.warehouse, balance.item_code):
			if remaining <= 0:
				break
			qty = min(remaining, flt(line.qty) - flt(line.issued_qty))
			if qty <= 0:
				continue
			remaining -= qty
			entry = allocations.setdefault(line.parent, {"posting_date": line.posting_date, "rows": []})
			entry["rows"].append({
				"source_doctype": bulk_material_issue.SOURCE_STOCK_ENTRY,
				"source_name": line.parent,
				"source_posting_date": line.posting_date,
				"source_line_name": line.name,
				"company": MRG_COMPANY,
				"item_code": balance.item_code,
				"warehouse": balance.warehouse,
				"qty": qty,
				"project": project,
				"boq_item": line.boq_item,
			})
		if remaining > 0:
			summary["skipped"].append((balance.warehouse, balance.item_code, remaining, "no unconsumed transfer after last reconciliation"))
	return allocations


def _site_consumable_balances():
	return frappe.db.sql(
		f"""
		select bin.warehouse, bin.item_code, bin.actual_qty
		from `tabBin` bin
		join `tabWarehouse` wh on wh.name = bin.warehouse
		join `tabItem` item on item.name = bin.item_code
		where wh.company = %(company)s and wh.is_group = 0
			and ifnull(wh.`{SKIP_FIELD}`, 0) = 0
			and item.controlled_procurement_catalog = 1 and item.controlled_item_type = 'Consumable'
			and bin.actual_qty > 0
		order by bin.warehouse, bin.item_code
		""",
		{"company": MRG_COMPANY},
		as_dict=True,
	)


def _unconsumed_transfer_lines(warehouse: str, item_code: str):
	issued_qty = "ifnull(sed.custom_material_issued_qty, 0)" if frappe.db.has_column(
		"Stock Entry Detail", "custom_material_issued_qty"
	) else "0"
	boq_item = "sed.boq_item" if frappe.db.has_column("Stock Entry Detail", "boq_item") else "null"
	return frappe.db.sql(
		f"""
		select sed.name, sed.parent, sed.qty, {issued_qty} as issued_qty, {boq_item} as boq_item, se.posting_date
		from `tabStock Entry Detail` sed
		join `tabStock Entry` se on se.name = sed.parent
		where se.docstatus = 1 and se.company = %(company)s and se.purpose = 'Material Transfer'
			and se.stock_entry_type = 'Material Transfer' and ifnull(se.is_return, 0) = 0
			and sed.t_warehouse = %(warehouse)s and sed.item_code = %(item_code)s
			and se.posting_date > ifnull((
				select max(sle.posting_date) from `tabStock Ledger Entry` sle
				where sle.voucher_type = 'Stock Reconciliation' and sle.is_cancelled = 0
					and sle.warehouse = %(warehouse)s and sle.item_code = %(item_code)s
			), '1900-01-01')
			and not exists (
				select 1 from `tabStock Entry` issue
				where issue.`{TRANSFER_LINK}` = se.name and issue.docstatus != 2
			)
		order by se.posting_date desc, se.posting_time desc, sed.idx
		""",
		{"company": MRG_COMPANY, "warehouse": warehouse, "item_code": item_code},
		as_dict=True,
	)


def _issue_transfer(transfer_name: str, rows: list[dict], summary: dict):
	savepoint = f"mrg_consume_{frappe.generate_hash(length=8)}"
	frappe.db.savepoint(savepoint)
	try:
		issue = bulk_material_issue._create_material_issue_for_source(
			rows, stock_entry_type=bulk_material_issue.MATERIAL_ISSUE_TYPE
		)
		if not issue:
			return
		frappe.db.set_value("Stock Entry", issue.name, TRANSFER_LINK, transfer_name, update_modified=False)
		frappe.get_doc("Stock Entry", transfer_name).add_comment(
			"Info", _("Consumables auto-consumed by Material Issue {0}.").format(issue.name)
		)
	except Exception as error:
		frappe.db.rollback(save_point=savepoint)
		frappe.clear_messages()
		for row in rows:
			summary["skipped"].append((row["warehouse"], row["item_code"], row["qty"], f"{transfer_name}: {error}"))
		return
	summary["issues"].append(issue.name)
	summary["qty"] += sum(flt(row["qty"]) for row in rows)


def _print_summary(summary: dict):
	print(f"MRG consumable back-fill: {len(summary['issues'])} Material Issues, total qty {summary['qty']:.3f}")
	no_project = sorted({row[0] for row in summary["skipped"] if row[3] == "warehouse has no project"})
	if no_project:
		print("Link these warehouses to a project and re-run the patch:")
		for warehouse in no_project:
			print(f"  - {warehouse}")
	for warehouse, item_code, qty, reason in summary["skipped"]:
		if reason != "warehouse has no project":
			print(f"  skipped {item_code} @ {warehouse} ({flt(qty):.3f}): {reason}")
