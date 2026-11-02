"""Relink submitted Sales Invoice lines to the Sales Order lines they bill.

Lines added through the invoice's "Add BOQ service" dialog (and their retention/advance rows)
were saved without `sales_order` / `so_detail`, so Sales Order billing, the Unbilled Receivables
reversal and the BOQ Progress Ledger ignored them.

    bench --site <site> execute construction_management.api.relink_si_sales_orders.run
    bench --site <site> execute construction_management.api.relink_si_sales_orders.run --kwargs "{'dry_run': 0}"
"""

import frappe
from frappe.utils import cint, flt

from construction_management.overrides.sales_invoice import DEDUCTION_ITEM_CODES, link_deduction_rows

MAX_VOUCHERS_PER_REPOST = 50


def run(dry_run: int = 1, invoices: list | str | None = None) -> list[dict]:
	"""Report (dry run) or apply the Sales Order links, then queue a GL repost for changed invoices."""
	if isinstance(invoices, str):
		invoices = [name.strip() for name in invoices.split(",") if name.strip()]
	report, changed = [], []
	for name in invoices or _candidate_invoices():
		try:
			rows, linked = _relink_invoice(name, dry_run=cint(dry_run))
		except Exception as error:
			frappe.db.rollback()
			report.append({"invoice": name, "result": f"error: {error}"})
			continue
		report.extend(rows)
		if linked and not cint(dry_run):
			frappe.db.commit()
			changed.append(name)
	if changed:
		report.extend(_queue_gl_repost(changed))
	_print_report(report)
	return report


def _candidate_invoices() -> list[str]:
	return frappe.db.sql_list(
		"""
		SELECT DISTINCT si.name
		FROM `tabSales Invoice` si
		INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		WHERE si.docstatus = 1 AND si.is_return = 0 AND IFNULL(si.project, '') != ''
			AND IFNULL(si.custom_payment_certificate, '') = '' AND IFNULL(si.custom_proforma_invoice, '') = ''
			AND IFNULL(si.custom_is_advanced, 0) = 0 AND IFNULL(si.custom_is_advance_release, 0) = 0
			AND IFNULL(sii.sales_order, '') = ''
			AND (
				sii.item_code IN %(deductions)s
				OR (IFNULL(sii.boq_item, '') != ''
					AND (IFNULL(si.custom_sales_order, '') != '' OR IFNULL(si.custom_source_sales_orders, '') != ''))
			)
		ORDER BY si.posting_date, si.name
		""",
		{"deductions": DEDUCTION_ITEM_CODES},
	)


def _relink_invoice(name: str, dry_run: bool) -> tuple[list[dict], list]:
	si = frappe.get_doc("Sales Invoice", name)
	report, linked_work = [], []
	orders = _named_orders(si)
	header_lines = _header_order_lines(orders)
	# invoices that name no Sales Order were billed directly from the BOQ on purpose
	work_rows = [row for row in si.items if orders and not row.get("sales_order")
		and row.item_code not in DEDUCTION_ITEM_CODES and row.get("boq_item")]
	for row in work_rows:
		match, rule = header_lines.get((row.boq_item, row.item_code, row.uom)), "header order"
		if not match:
			match, rule = _single_open_order_line(si.project, row)
		if match:
			row.sales_order, row.so_detail = match
			linked_work.append(row)
		report.append(_report_row(si, row, rule if match else "skipped: " + rule))

	linked_deductions = link_deduction_rows(si.items)
	for row in linked_deductions:
		report.append(_report_row(si, row, "deduction follows its work line"))
	for row in si.items:
		if row.item_code in DEDUCTION_ITEM_CODES and not row.get("sales_order") and not cint(row.get("custom_service_deduction")):
			report.append(_report_row(si, row, "skipped: no matching Sales Order deduction line"))

	linked = linked_work + linked_deductions
	if linked and dry_run:
		report.append({"invoice": si.name, "result": "GL change after repost: " + _gl_change_preview(si)})
	if linked and not dry_run:
		so_uoms = dict(frappe.get_all("Sales Order Item", filters={"name": ["in", [row.so_detail for row in linked_deductions]]},
			fields=["name", "uom"], as_list=True)) if linked_deductions else {}
		for row in linked:
			values = {"sales_order": row.sales_order, "so_detail": row.so_detail}
			# deduction rows carry the Sales Order line's UOM, as a draft save does (_normalize_deduction_uoms)
			if so_uoms.get(row.so_detail):
				values["uom"] = so_uoms[row.so_detail]
			frappe.db.set_value("Sales Invoice Item", row.name, values, update_modified=False)
		si.update_prevdoc_status()
		for row in linked_work:
			_merge_boq_ledger_row(si, row)
	return report, linked


def _named_orders(si) -> list[str]:
	orders = [si.get("custom_sales_order")] + (si.get("custom_source_sales_orders") or "").split(",")
	return list(dict.fromkeys(order.strip() for order in orders if order and order.strip()))


def _header_order_lines(orders: list[str]) -> dict:
	"""(BOQ item, item, UOM) -> (Sales Order, line) for the orders the invoice names, first order wins.

	ERPNext requires a linked invoice line to keep its Sales Order line's item and UOM.
	"""
	if not orders:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT soi.parent, soi.name, soi.boq_item, soi.item_code, soi.uom
		FROM `tabSales Order Item` soi
		INNER JOIN `tabSales Order` so ON so.name = soi.parent
		WHERE so.docstatus = 1 AND so.name IN %(orders)s
			AND IFNULL(soi.boq_item, '') != '' AND soi.item_code NOT IN %(deductions)s
		ORDER BY soi.idx
		""",
		{"orders": orders, "deductions": DEDUCTION_ITEM_CODES},
		as_dict=True,
	)
	lines = {}
	for line in sorted(rows, key=lambda line: orders.index(line.parent)):
		lines.setdefault((line.boq_item, line.item_code, line.uom), (line.parent, line.name))
	return lines


def _single_open_order_line(project: str, row) -> tuple[tuple | None, str]:
	"""The only project order whose BOQ Progress Ledger row for this item is not invoiced yet."""
	boq_item = row.boq_item
	orders = frappe.db.sql_list(
		"""
		SELECT DISTINCT bpl.reference_name
		FROM `tabBOQ Progress Ledger` bpl
		INNER JOIN `tabSales Order` so ON so.name = bpl.reference_name
		WHERE bpl.boq_item = %s AND bpl.reference_doctype = 'Sales Order' AND bpl.source = 'Order'
			AND IFNULL(bpl.tax_invoice, '') = '' AND bpl.amount > 0
			AND so.docstatus = 1 AND so.project = %s
		""",
		(boq_item, project),
	)
	if len(orders) != 1:
		return None, ("no open Sales Order line" if not orders else f"several open Sales Orders ({', '.join(orders)})")
	so_detail = frappe.db.get_value(
		"Sales Order Item",
		{"parent": orders[0], "boq_item": boq_item, "item_code": row.item_code, "uom": row.uom},
		"name",
		order_by="idx asc",
	)
	return ((orders[0], so_detail), "only open project order") if so_detail else (None, "Sales Order line has a different item or UOM")


def _gl_change_preview(si) -> str:
	"""Per-account change (debit - credit) the repost would make, using the in-memory links."""
	current = dict(frappe.db.sql(
		"""SELECT account, SUM(debit - credit) FROM `tabGL Entry`
		WHERE voucher_type = 'Sales Invoice' AND voucher_no = %s AND is_cancelled = 0 GROUP BY account""",
		si.name,
	))
	reposted = {}
	for entry in si.get_gl_entries():
		reposted[entry.account] = flt(reposted.get(entry.account)) + flt(entry.debit) - flt(entry.credit)
	changes = {account: flt(reposted.get(account)) - flt(current.get(account)) for account in set(current) | set(reposted)}
	return ", ".join(f"{account} {change:+,.2f}" for account, change in sorted(changes.items()) if abs(change) >= 0.01) or "none"


def _merge_boq_ledger_row(si, row) -> None:
	"""Move the invoice's own BOQ Progress Ledger row onto the order's uninvoiced row, as a linked invoice would."""
	from construction_management.api.boq_ledger import recalculate_ledger_for_item

	own = frappe.db.get_value(
		"BOQ Progress Ledger",
		{"boq_item": row.boq_item, "reference_doctype": "Sales Invoice", "reference_name": si.name},
		["name", "amount", "tax_invoice_amount", "retention_amount", "advance_deduction", "variance"],
		as_dict=True,
	)
	order_row = frappe.db.get_value(
		"BOQ Progress Ledger",
		{"boq_item": row.boq_item, "reference_doctype": "Sales Order", "reference_name": row.sales_order,
			"tax_invoice": ["is", "not set"]},
		"name",
		order_by="creation asc",
	)
	if not own or not order_row:
		return
	frappe.db.set_value(
		"BOQ Progress Ledger",
		order_row,
		{"tax_invoice": si.name, "tax_invoice_amount": own.tax_invoice_amount, "source": "Invoice", "amount": own.amount,
			"retention_amount": own.retention_amount, "advance_deduction": own.advance_deduction, "variance": own.variance},
		update_modified=False,
	)
	frappe.flags.allow_boq_ledger_deletion = True
	try:
		frappe.delete_doc("BOQ Progress Ledger", own.name, force=1, ignore_permissions=True)
	finally:
		frappe.flags.allow_boq_ledger_deletion = False
	recalculate_ledger_for_item(row.boq_item)


def _queue_gl_repost(invoices: list[str]) -> list[dict]:
	"""Repost GL so the Unbilled Receivables reversal is booked for the newly linked lines."""
	by_company = {}
	for name, company in frappe.get_all("Sales Invoice", filters={"name": ["in", invoices]}, fields=["name", "company"],
			order_by="posting_date asc", as_list=True):
		by_company.setdefault(company, []).append(name)
	report = []
	for company, names in by_company.items():
		for start in range(0, len(names), MAX_VOUCHERS_PER_REPOST):
			batch = names[start:start + MAX_VOUCHERS_PER_REPOST]
			try:
				repost = frappe.get_doc({
					"doctype": "Repost Accounting Ledger",
					"company": company,
					"vouchers": [{"voucher_type": "Sales Invoice", "voucher_no": name} for name in batch],
				}).insert()
				repost.submit()
				frappe.db.commit()
				result = f"GL repost queued: {repost.name}"
			except Exception as error:
				frappe.db.rollback()
				result = f"GL repost failed: {error}"
			report.extend({"invoice": name, "result": result} for name in batch)
	return report


def _report_row(si, row, result: str) -> dict:
	return {"invoice": si.name, "idx": row.idx, "item_code": row.item_code, "boq_item": row.get("boq_item"),
		"sales_order": row.get("sales_order"), "so_detail": row.get("so_detail"), "result": result}


def _print_report(report: list[dict]) -> None:
	for entry in report:
		print(" | ".join(str(entry.get(key) or "") for key in ("invoice", "idx", "item_code", "boq_item", "sales_order", "so_detail", "result")))
