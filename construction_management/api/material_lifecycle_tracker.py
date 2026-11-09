"""Material lifecycle tracker: MR → PO → GRN → Transfer → Consumption → PI → Payment.

	bench --site <site> execute construction_management.api.material_lifecycle_tracker.send_overdue_grn_reminders
"""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from construction_management.api.controlled_procurement import (
	CATALOG_ROLES,
	_active_company,
	_allowed_companies,
	_require,
)

TRACKER_ROLES = CATALOG_ROLES

STAGES = (
	"mr_only",
	"ordered",
	"partly_ordered",
	"grn_pending",
	"partly_received",
	"received",
	"transferred",
	"consumed",
	"invoiced",
	"paid",
)


def _company() -> str:
	company = _active_company()
	if not company or company not in _allowed_companies():
		frappe.throw(_("Select an accessible company."), frappe.PermissionError)
	return company


def derive_stage(
	requested: float,
	ordered: float,
	received: float,
	transferred: float,
	consumed: float,
	invoiced: float,
	paid: float,
	*,
	required_date=None,
	as_of=None,
) -> str:
	"""Derive the furthest lifecycle stage for a line (paid wins over earlier stages)."""
	requested, ordered, received = flt(requested), flt(ordered), flt(received)
	transferred, consumed = flt(transferred), flt(consumed)
	invoiced, paid = flt(invoiced), flt(paid)
	as_of = getdate(as_of or today())

	if ordered <= 0 and requested > 0:
		return "mr_only"
	if paid > 0 and paid + 0.0001 >= max(invoiced, received, ordered) * 0.99:
		return "paid"
	if invoiced > 0 and invoiced + 0.0001 >= received * 0.99 and received > 0:
		return "invoiced"
	if consumed > 0:
		return "consumed"
	if transferred > 0:
		return "transferred"
	if received > 0 and received + 0.0001 >= ordered * 0.99 and ordered > 0:
		return "received"
	if received > 0:
		return "partly_received"
	if ordered > 0 and required_date and getdate(required_date) < as_of and received + 0.0001 < ordered:
		return "grn_pending"
	if ordered > 0 and requested > 0 and ordered + 0.0001 < requested:
		return "partly_ordered"
	if ordered > 0:
		return "ordered"
	return "mr_only"


def is_overdue_grn(ordered: float, received: float, required_date, as_of=None) -> bool:
	if not required_date or flt(ordered) <= 0:
		return False
	as_of = getdate(as_of or today())
	return getdate(required_date) < as_of and flt(received) + 0.0001 < flt(ordered)


@frappe.whitelist(methods=["GET"])
def get_material_lifecycle_tracker(
	project: str = "",
	item_code: str = "",
	warehouse: str = "",
	stage: str = "",
	overdue_grn_only: int | str = 0,
	from_date: str = "",
	to_date: str = "",
	limit: int | str = 500,
) -> dict:
	"""Return lifecycle rows for the active company (PO lines + orphan MR lines)."""
	_require(TRACKER_ROLES)
	company = _company()
	overdue_only = cint(overdue_grn_only)
	limit = min(max(cint(limit) or 500, 1), 2000)
	stage = (stage or "").strip().lower()
	if stage and stage not in STAGES:
		frappe.throw(_("Invalid stage filter."))

	rows = _build_po_rows(company, project, item_code, warehouse, from_date, to_date)
	rows.extend(_orphan_mr_rows(company, project, item_code, from_date, to_date, existing=rows))

	filtered = []
	for row in rows:
		row["stage"] = derive_stage(
			row["requested_qty"],
			row["ordered_qty"],
			row["received_qty"],
			row["transferred_qty"],
			row["consumed_qty"],
			row["invoiced_qty"],
			row["paid_qty"],
			required_date=row.get("required_date"),
		)
		row["overdue_grn"] = is_overdue_grn(row["ordered_qty"], row["received_qty"], row.get("required_date"))
		if overdue_only and not row["overdue_grn"]:
			continue
		if stage and row["stage"] != stage:
			continue
		filtered.append(row)

	filtered.sort(key=lambda r: (r.get("required_date") or "9999", r.get("purchase_order") or "", r.get("item_code") or ""))
	return {
		"company": company,
		"stages": list(STAGES),
		"count": len(filtered[:limit]),
		"rows": filtered[:limit],
	}


def _build_po_rows(company, project, item_code, warehouse, from_date, to_date) -> list[dict]:
	conditions = ["po.company = %(company)s", "po.docstatus = 1"]
	params: dict = {"company": company}
	if project:
		conditions.append("coalesce(nullif(poi.project, ''), po.project) = %(project)s")
		params["project"] = project
	if item_code:
		conditions.append("poi.item_code = %(item_code)s")
		params["item_code"] = item_code
	if from_date:
		conditions.append("po.transaction_date >= %(from_date)s")
		params["from_date"] = from_date
	if to_date:
		conditions.append("po.transaction_date <= %(to_date)s")
		params["to_date"] = to_date
	if warehouse:
		conditions.append("coalesce(nullif(poi.warehouse, ''), po.set_warehouse) = %(warehouse)s")
		params["warehouse"] = warehouse

	po_rows = frappe.db.sql(
		f"""
		SELECT
			poi.name AS po_detail,
			poi.parent AS purchase_order,
			poi.item_code,
			poi.item_name,
			poi.uom,
			poi.qty AS ordered_qty,
			poi.received_qty,
			poi.billed_amt,
			poi.rate,
			poi.amount,
			poi.schedule_date AS required_date,
			poi.material_request,
			poi.material_request_item,
			poi.warehouse AS poi_warehouse,
			po.set_warehouse,
			po.transaction_date AS po_date,
			po.supplier,
			po.project AS po_project,
			poi.project AS poi_project,
			mri.qty AS requested_qty,
			mri.warehouse AS mr_warehouse,
			mr.transaction_date AS mr_date
		FROM `tabPurchase Order Item` poi
		INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
		LEFT JOIN `tabMaterial Request Item` mri ON mri.name = poi.material_request_item
		LEFT JOIN `tabMaterial Request` mr ON mr.name = poi.material_request
		WHERE {" AND ".join(conditions)}
		ORDER BY po.transaction_date DESC, poi.idx
		LIMIT 2000
		""",
		params,
		as_dict=True,
	)
	if not po_rows:
		return []

	po_details = [r.po_detail for r in po_rows]
	grn_map = _receipts_by_po_detail(po_details)
	transfer_map = _transfers_by_receipts({name for names in grn_map.values() for name in names})
	consume_map = _consumption_by_po_detail(po_details)
	invoice_map = _invoices_by_po_detail(po_details)
	payment_map = _payments_by_invoices({inv for invs in invoice_map.values() for inv in invs})

	rows = []
	for r in po_rows:
		grns = grn_map.get(r.po_detail, [])
		transfers = []
		for grn in grns:
			transfers.extend(transfer_map.get(grn, []))
		invoices = invoice_map.get(r.po_detail, [])
		payments = []
		for inv in invoices:
			payments.extend(payment_map.get(inv, []))
		consumed = consume_map.get(r.po_detail, {"qty": 0.0, "docs": []})
		received = flt(r.received_qty)
		invoiced_qty = _invoice_qty_for_detail(r.po_detail, invoices)
		paid_qty = _paid_qty_for_invoices(invoices, payments)
		last_wh = _last_warehouse(grns, transfers) or r.poi_warehouse or r.set_warehouse or r.mr_warehouse
		rows.append(
			{
				"row_key": r.po_detail,
				"project": r.poi_project or r.po_project,
				"item_code": r.item_code,
				"item_name": r.item_name,
				"uom": r.uom,
				"material_request": r.material_request,
				"mr_date": r.mr_date,
				"purchase_order": r.purchase_order,
				"po_date": r.po_date,
				"supplier": r.supplier,
				"required_date": r.required_date,
				"requested_qty": flt(r.requested_qty) or (0.0 if r.material_request else flt(r.ordered_qty)),
				"ordered_qty": flt(r.ordered_qty),
				"received_qty": received,
				"transferred_qty": sum(flt(t.get("qty")) for t in transfers),
				"consumed_qty": flt(consumed["qty"]),
				"invoiced_qty": invoiced_qty,
				"paid_qty": paid_qty,
				"warehouse": last_wh,
				"receipts": grns,
				"transfers": [t["name"] for t in transfers],
				"consumptions": consumed["docs"],
				"invoices": invoices,
				"payments": payments,
				"timeline": _timeline(r, grns, transfers, consumed["docs"], invoices, payments),
			}
		)
	return rows


def _orphan_mr_rows(company, project, item_code, from_date, to_date, existing: list[dict]) -> list[dict]:
	linked = {row["material_request"] for row in existing if row.get("material_request")}
	conditions = ["mr.company = %(company)s", "mr.docstatus = 1", "mr.material_request_type = 'Purchase'"]
	params: dict = {"company": company}
	has_mri_project = frappe.db.has_column("Material Request Item", "project")
	if project:
		if has_mri_project:
			conditions.append("IFNULL(mri.project, '') = %(project)s")
			params["project"] = project
		else:
			# No project dimension on MR — skip orphan MR rows when filtering by project
			return []
	if item_code:
		conditions.append("mri.item_code = %(item_code)s")
		params["item_code"] = item_code
	if from_date:
		conditions.append("mr.transaction_date >= %(from_date)s")
		params["from_date"] = from_date
	if to_date:
		conditions.append("mr.transaction_date <= %(to_date)s")
		params["to_date"] = to_date

	project_select = "mri.project AS mri_project" if has_mri_project else "NULL AS mri_project"
	mr_rows = frappe.db.sql(
		f"""
		SELECT mri.name AS mr_detail, mri.parent AS material_request, mri.item_code, mri.item_name,
			mri.uom, mri.qty AS requested_qty, mri.ordered_qty, mri.warehouse, mri.schedule_date AS required_date,
			{project_select}, mr.transaction_date AS mr_date
		FROM `tabMaterial Request Item` mri
		INNER JOIN `tabMaterial Request` mr ON mr.name = mri.parent
		WHERE {" AND ".join(conditions)}
			AND IFNULL(mri.ordered_qty, 0) < mri.qty
		LIMIT 500
		""",
		params,
		as_dict=True,
	)
	out = []
	for r in mr_rows:
		if r.material_request in linked:
			continue
		out.append(
			{
				"row_key": r.mr_detail,
				"project": r.mri_project,
				"item_code": r.item_code,
				"item_name": r.item_name,
				"uom": r.uom,
				"material_request": r.material_request,
				"mr_date": r.mr_date,
				"purchase_order": None,
				"po_date": None,
				"supplier": None,
				"required_date": r.required_date,
				"requested_qty": flt(r.requested_qty),
				"ordered_qty": flt(r.ordered_qty),
				"received_qty": 0.0,
				"transferred_qty": 0.0,
				"consumed_qty": 0.0,
				"invoiced_qty": 0.0,
				"paid_qty": 0.0,
				"warehouse": r.warehouse,
				"receipts": [],
				"transfers": [],
				"consumptions": [],
				"invoices": [],
				"payments": [],
				"timeline": [
					{"doctype": "Material Request", "name": r.material_request, "date": r.mr_date, "label": "Material Request"}
				],
			}
		)
	return out


def _receipts_by_po_detail(po_details: list[str]) -> dict[str, list[str]]:
	if not po_details:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT pri.purchase_order_item AS po_detail, pri.parent AS receipt
		FROM `tabPurchase Receipt Item` pri
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pr.docstatus = 1 AND pri.purchase_order_item IN %(details)s
		""",
		{"details": po_details},
		as_dict=True,
	)
	out = defaultdict(list)
	for row in rows:
		if row.receipt not in out[row.po_detail]:
			out[row.po_detail].append(row.receipt)
	return out


def _transfers_by_receipts(receipts: set[str]) -> dict[str, list[dict]]:
	if not receipts:
		return {}
	has_source = frappe.db.has_column("Stock Entry", "custom_source_purchase_receipt")
	out = defaultdict(list)
	if has_source:
		rows = frappe.db.sql(
			"""
			SELECT name, custom_source_purchase_receipt AS receipt, posting_date,
				(SELECT SUM(ABS(sed.qty)) FROM `tabStock Entry Detail` sed WHERE sed.parent = se.name) AS qty
			FROM `tabStock Entry` se
			WHERE se.docstatus = 1 AND se.purpose = 'Material Transfer'
				AND se.custom_source_purchase_receipt IN %(receipts)s
			""",
			{"receipts": list(receipts)},
			as_dict=True,
		)
		for row in rows:
			out[row.receipt].append({"name": row.name, "qty": flt(row.qty), "date": row.posting_date})
	return out


def _consumption_by_po_detail(po_details: list[str]) -> dict[str, dict]:
	"""Material Issue / DPR stock against PO via purchase_order_item on Stock Entry Detail when present."""
	if not po_details:
		return {}
	out = {d: {"qty": 0.0, "docs": []} for d in po_details}
	if not frappe.db.has_column("Stock Entry Detail", "purchase_order_item"):
		return out
	rows = frappe.db.sql(
		"""
		SELECT sed.purchase_order_item AS po_detail, se.name, se.posting_date, SUM(ABS(sed.qty)) AS qty
		FROM `tabStock Entry Detail` sed
		INNER JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE se.docstatus = 1 AND se.purpose = 'Material Issue'
			AND sed.purchase_order_item IN %(details)s
		GROUP BY sed.purchase_order_item, se.name, se.posting_date
		""",
		{"details": po_details},
		as_dict=True,
	)
	for row in rows:
		bucket = out.setdefault(row.po_detail, {"qty": 0.0, "docs": []})
		bucket["qty"] += flt(row.qty)
		if row.name not in bucket["docs"]:
			bucket["docs"].append(row.name)
	return out


def _invoices_by_po_detail(po_details: list[str]) -> dict[str, list[str]]:
	if not po_details:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT pii.po_detail, pii.parent AS invoice
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
		WHERE pi.docstatus = 1 AND IFNULL(pii.po_detail, '') != '' AND pii.po_detail IN %(details)s
		""",
		{"details": po_details},
		as_dict=True,
	)
	out = defaultdict(list)
	for row in rows:
		if row.invoice not in out[row.po_detail]:
			out[row.po_detail].append(row.invoice)
	return out


def _payments_by_invoices(invoices: set[str]) -> dict[str, list[str]]:
	if not invoices:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT per.reference_name AS invoice, pe.name AS payment
		FROM `tabPayment Entry Reference` per
		INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
		WHERE pe.docstatus = 1 AND per.reference_doctype = 'Purchase Invoice'
			AND per.reference_name IN %(invoices)s
		""",
		{"invoices": list(invoices)},
		as_dict=True,
	)
	out = defaultdict(list)
	for row in rows:
		if row.payment not in out[row.invoice]:
			out[row.invoice].append(row.payment)
	return out


def _invoice_qty_for_detail(po_detail: str, invoices: list[str]) -> float:
	if not invoices:
		return 0.0
	return flt(
		frappe.db.sql(
			"""
			SELECT SUM(qty) FROM `tabPurchase Invoice Item`
			WHERE po_detail = %s AND parent IN %s
			""",
			(po_detail, invoices),
		)[0][0]
	)


def _paid_qty_for_invoices(invoices: list[str], payments: list[str]) -> float:
	"""Paid qty ≈ invoiced qty when invoices are fully paid; else scale by amount paid."""
	if not invoices or not payments:
		return 0.0
	invoiced_qty = flt(
		frappe.db.sql(
			"""SELECT SUM(qty) FROM `tabPurchase Invoice Item` WHERE parent IN %s""",
			(invoices,),
		)[0][0]
	)
	totals = frappe.db.sql(
		"""
		SELECT SUM(grand_total) AS grand_total, SUM(outstanding_amount) AS outstanding
		FROM `tabPurchase Invoice` WHERE name IN %s
		""",
		(invoices,),
		as_dict=True,
	)[0]
	grand_total = flt(totals.grand_total)
	outstanding = flt(totals.outstanding)
	if grand_total <= 0:
		return 0.0
	if outstanding <= 0.0001:
		return invoiced_qty
	paid_ratio = max(0.0, min(1.0, (grand_total - outstanding) / grand_total))
	return invoiced_qty * paid_ratio


def _last_warehouse(grns: list[str], transfers: list[dict]) -> str | None:
	if transfers:
		last = transfers[-1]["name"]
		wh = frappe.db.sql(
			"""
			SELECT t_warehouse FROM `tabStock Entry Detail`
			WHERE parent = %s AND IFNULL(t_warehouse, '') != '' LIMIT 1
			""",
			last,
		)
		if wh:
			return wh[0][0]
	if grns:
		return frappe.db.get_value("Purchase Receipt", grns[-1], "set_warehouse")
	return None


def _timeline(po_row, grns, transfers, consumptions, invoices, payments) -> list[dict]:
	events = []
	if po_row.material_request:
		events.append(
			{"doctype": "Material Request", "name": po_row.material_request, "date": po_row.mr_date, "label": "Material Request"}
		)
	events.append(
		{"doctype": "Purchase Order", "name": po_row.purchase_order, "date": po_row.po_date, "label": "Purchase Order"}
	)
	for name in grns:
		events.append(
			{
				"doctype": "Purchase Receipt",
				"name": name,
				"date": frappe.db.get_value("Purchase Receipt", name, "posting_date"),
				"label": "Receive Note",
			}
		)
	for t in transfers:
		events.append({"doctype": "Stock Entry", "name": t["name"], "date": t.get("date"), "label": "Stock Transfer"})
	for name in consumptions:
		events.append(
			{
				"doctype": "Stock Entry",
				"name": name,
				"date": frappe.db.get_value("Stock Entry", name, "posting_date"),
				"label": "Consumption",
			}
		)
	for name in invoices:
		events.append(
			{
				"doctype": "Purchase Invoice",
				"name": name,
				"date": frappe.db.get_value("Purchase Invoice", name, "posting_date"),
				"label": "Purchase Invoice",
			}
		)
	for name in payments:
		events.append(
			{
				"doctype": "Payment Entry",
				"name": name,
				"date": frappe.db.get_value("Payment Entry", name, "posting_date"),
				"label": "Payment",
			}
		)
	return events


@frappe.whitelist(methods=["GET"])
def get_overdue_grn_summary() -> dict:
	"""Overdue Receive Note lines for the active company (required date passed, qty short)."""
	data = get_material_lifecycle_tracker(overdue_grn_only=1, limit=2000)
	return {
		"company": data["company"],
		"count": data["count"],
		"rows": data["rows"],
	}


def send_overdue_grn_reminders() -> dict:
	"""Daily job: notify Purchase Managers about overdue GRNs per company."""
	companies = frappe.get_all("Company", pluck="name")
	notified = 0
	for company in companies:
		try:
			rows = _overdue_rows_for_company(company)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "overdue_grn_reminders")
			continue
		if not rows:
			continue
		recipients = _purchase_manager_users(company)
		if not recipients:
			continue
		message = _(
			"{0}: {1} Purchase Order line(s) are past required date with Receive Note still pending."
		).format(company, len(rows))
		for user in recipients:
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"subject": _("Overdue Receive Notes — {0}").format(company),
					"email_content": message
					+ "<br>"
					+ "<br>".join(
						f"{r['purchase_order']} · {r['item_code']} · due {r.get('required_date')}"
						for r in rows[:25]
					),
					"for_user": user,
					"type": "Alert",
					"document_type": "Purchase Order",
					"document_name": rows[0]["purchase_order"],
				}
			).insert(ignore_permissions=True)
			notified += 1
		frappe.db.commit()
	return {"notified": notified}


def _overdue_rows_for_company(company: str) -> list[dict]:
	rows = frappe.db.sql(
		"""
		SELECT poi.parent AS purchase_order, poi.item_code, poi.schedule_date AS required_date,
			poi.qty AS ordered_qty, poi.received_qty, po.project
		FROM `tabPurchase Order Item` poi
		INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
		WHERE po.company = %s AND po.docstatus = 1
			AND poi.schedule_date IS NOT NULL AND poi.schedule_date < %s
			AND IFNULL(poi.received_qty, 0) < poi.qty
		ORDER BY poi.schedule_date
		LIMIT 200
		""",
		(company, today()),
		as_dict=True,
	)
	return [dict(r) for r in rows]


def _purchase_manager_users(company: str) -> list[str]:
	users = frappe.get_all(
		"Has Role",
		filters={"role": ["in", ["Purchase Manager", "Purchase User", "System Manager"]], "parenttype": "User"},
		pluck="parent",
	)
	# Prefer enabled users only
	enabled = frappe.get_all("User", filters={"name": ["in", users or [""]], "enabled": 1}, pluck="name")
	return [u for u in enabled if u not in ("Guest", "Administrator")] or ["Administrator"]
