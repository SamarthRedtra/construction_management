# Copyright (c) 2026, Construction Management
# License: MIT

"""Project SOA expense drill-down — 3-level tree aligned with get_project_cost_breakdown."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

VALID_CATEGORIES = frozenset({"material", "labor", "subcontractor", "commission", "other"})

_ROUTE_MAP = {
	"Daily Progress Record": "daily-progress-record",
	"Stock Entry": "stock-entry",
	"Journal Entry": "journal-entry",
	"Purchase Invoice": "purchase-invoice",
	"Purchase Receipt": "purchase-receipt",
	"Sales Invoice": "sales-invoice",
	"Proforma Invoice": "proforma-invoice",
}


def categorize_project_cost_entry(entry: dict, comm_accounts: list[str] | None = None) -> str | None:
	"""Return cost category for a GL expense row, or None if commission (skipped)."""
	comm_accounts = comm_accounts or []
	if entry.get("account") in comm_accounts:
		return None

	account_type = entry.get("account_type") or ""
	voucher_type = entry.get("voucher_type") or ""
	account = entry.get("account") or ""

	# Purchase vouchers: Supplier → material, Subcontractor → subcontractor
	if voucher_type in ("Purchase Invoice", "Purchase Receipt"):
		from construction_management.api.purchase_receipt_utils import get_purchase_cost_category

		return get_purchase_cost_category(voucher_type, entry.get("voucher_no"))

	if account_type == "Service" or "Subcontract" in account:
		return "subcontractor"
	if account_type == "Cost of Goods Sold" or voucher_type == "Stock Entry" or "Material" in account:
		return "material"
	if account_type == "Payroll" or "Labour" in account or "Labor" in account or "Salary" in account:
		return "labor"
	return "other"


def _doc_link(doctype: str, name: str) -> str:
	slug = _ROUTE_MAP.get(doctype) or frappe.scrub(doctype).replace("_", "-")
	return f"/app/{slug}/{name}"


def _get_commission_accounts(company: str | None) -> list[str]:
	if not company or not frappe.db.exists("BOQ Settings", company):
		return []
	settings = frappe.db.get_value(
		"BOQ Settings",
		company,
		["sales_person_commission_account", "sales_partner_commission_account"],
		as_dict=True,
	) or {}
	return [a for a in (settings.sales_person_commission_account, settings.sales_partner_commission_account) if a]


def _get_expense_account_names() -> set[str]:
	return set(frappe.db.sql_list("SELECT name FROM `tabAccount` WHERE root_type = 'Expense'"))


def _get_commission_total(project: str) -> float:
	commission_kpi = {"sales_person_commission_total": 0.0, "sales_partner_commission_total": 0.0}
	try:
		from redtra_customisation.api.project_commission_kpi import get_project_commission_totals

		commission_kpi = get_project_commission_totals(project) or commission_kpi
	except Exception:
		pass
	return flt(commission_kpi.get("sales_person_commission_total", 0)) + flt(
		commission_kpi.get("sales_partner_commission_total", 0)
	)


def _fetch_gl_expense_entries(project: str) -> list[dict]:
	return frappe.db.sql(
		"""
		SELECT
			gle.voucher_type,
			gle.voucher_no,
			gle.account,
			acc.account_type,
			acc.root_type,
			(gle.debit - gle.credit) AS amount,
			gle.boq_item,
			gle.posting_date
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.project = %s
			AND gle.is_cancelled = 0
			AND acc.root_type = 'Expense'
		""",
		project,
		as_dict=True,
	)


def _fetch_non_expense_pi_atoms(project: str, expense_accounts: set[str]) -> list[dict]:
	from construction_management.api.purchase_receipt_utils import get_purchase_cost_category

	atoms = []
	pi_items = frappe.db.sql(
		"""
		SELECT
			pi.name AS voucher_no,
			pi.supplier,
			pi.posting_date,
			pi.custom_suppliersubcontractor,
			pii.item_code,
			pii.item_name,
			pii.base_net_amount AS amount,
			pii.boq_item,
			pii.expense_account
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
		WHERE pii.project = %s AND pi.docstatus = 1
		""",
		project,
		as_dict=True,
	)
	category_cache: dict[str, str] = {}
	for row in pi_items:
		if row.expense_account in expense_accounts:
			continue
		if row.voucher_no not in category_cache:
			category_cache[row.voucher_no] = get_purchase_cost_category(
				"Purchase Invoice", row.voucher_no
			)
		atoms.append({
			"category": category_cache[row.voucher_no],
			"amount": flt(row.amount),
			"voucher_type": "Purchase Invoice",
			"voucher_no": row.voucher_no,
			"account": row.expense_account,
			"boq_item": row.boq_item,
			"supplier": row.supplier,
			"item_code": row.item_code,
			"item_name": row.item_name,
			"posting_date": row.posting_date,
			"unallocated": not row.boq_item,
		})
	return atoms


def _atom_from_gl(entry: dict, category: str) -> dict:
	return {
		"category": category,
		"amount": flt(entry.amount),
		"voucher_type": entry.voucher_type,
		"voucher_no": entry.voucher_no,
		"account": entry.account,
		"boq_item": entry.boq_item,
		"posting_date": entry.get("posting_date"),
		"unallocated": not entry.boq_item,
	}


def _parse_comma_separated_names(value: str | None) -> set[str]:
	if not value:
		return set()
	return {name.strip() for name in value.split(",") if name.strip()}


def _get_dpr_linked_stock_entries(project: str) -> set[str]:
	names: set[str] = set()
	for row in frappe.db.sql(
		"""
		SELECT DISTINCT dm.stock_entry AS name
		FROM `tabDPR Material` dm
		INNER JOIN `tabDaily Progress Record` dpr ON dpr.name = dm.parent
		WHERE dpr.project = %s AND dpr.docstatus = 1 AND IFNULL(dm.stock_entry, '') != ''
		""",
		project,
		as_dict=True,
	):
		names.add(row.name)

	for stock_entries in frappe.get_all(
		"Daily Progress Record",
		filters={"project": project, "docstatus": 1},
		pluck="stock_entries",
	):
		names.update(_parse_comma_separated_names(stock_entries))
	return names


def _get_dpr_linked_journal_entries(project: str) -> set[str]:
	names: set[str] = set()
	for journal_entries in frappe.get_all(
		"Daily Progress Record",
		filters={"project": project, "docstatus": 1},
		pluck="journal_entries",
	):
		names.update(_parse_comma_separated_names(journal_entries))

	for row in frappe.db.sql(
		"""
		SELECT journal_entry AS name FROM (
			SELECT DISTINCT doh.journal_entry
			FROM `tabDPR Overhead` doh
			INNER JOIN `tabDaily Progress Record` dpr ON dpr.name = doh.parent
			WHERE dpr.project = %s AND dpr.docstatus = 1 AND IFNULL(doh.journal_entry, '') != ''
			UNION
			SELECT DISTINCT de.journal_entry
			FROM `tabDPR Expense` de
			INNER JOIN `tabDaily Progress Record` dpr ON dpr.name = de.parent
			WHERE dpr.project = %s AND dpr.docstatus = 1 AND IFNULL(de.journal_entry, '') != ''
		) linked_je
		WHERE IFNULL(journal_entry, '') != ''
		""",
		(project, project),
		as_dict=True,
	):
		names.add(row.name)
	return names


def _append_linked_voucher_remark(remarks: str, voucher_type: str, voucher_name: str) -> str:
	note = f"{voucher_type}: {voucher_name}"
	return f"{remarks} · {note}" if remarks else note


def _collect_gl_atoms(project: str) -> list[dict]:
	company = frappe.db.get_value("Project", project, "company")
	comm_accounts = _get_commission_accounts(company)
	expense_accounts = _get_expense_account_names()
	atoms = []

	for entry in _fetch_gl_expense_entries(project):
		category = categorize_project_cost_entry(entry, comm_accounts)
		if not category:
			continue
		atoms.append(_atom_from_gl(entry, category))

	atoms.extend(_fetch_non_expense_pi_atoms(project, expense_accounts))
	return atoms


def _build_tree_from_atoms(atoms: list[dict]) -> list[dict]:
	"""Nest flat atoms into groups → lines → sources."""
	groups: dict[str, dict] = {}

	for atom in atoms:
		group_key = atom.get("group_key") or _("Uncategorized")
		group_label = atom.get("group_label") or group_key
		line_key = atom.get("line_key") or atom.get("voucher_no") or group_key
		line_label = atom.get("line_label") or line_key

		group = groups.setdefault(group_key, {
			"key": group_key,
			"label": group_label,
			"amount": 0.0,
			"lines": {},
		})
		group["amount"] += flt(atom.get("amount"))

		lines = group["lines"]
		line = lines.get(line_key)
		if not line:
			line = {
				"key": line_key,
				"label": line_label,
				"amount": 0.0,
				"qty": None,
				"uom": atom.get("uom"),
				"rate": None,
				"sources": [],
			}
			lines[line_key] = line

		line["amount"] += flt(atom.get("amount"))
		atom_qty = flt(atom.get("qty"))
		if atom_qty:
			line["qty"] = flt(line.get("qty") or 0) + atom_qty
			if atom.get("uom"):
				line["uom"] = atom.get("uom")
			line["rate"] = flt(line["amount"]) / flt(line["qty"]) if line["qty"] else flt(atom.get("rate"))
		elif line.get("rate") is None and atom.get("rate"):
			line["rate"] = flt(atom.get("rate"))

		source = {
			"doctype": atom.get("source_doctype") or atom.get("voucher_type"),
			"document": atom.get("source_document") or atom.get("voucher_no"),
			"date": atom.get("date") or atom.get("posting_date"),
			"amount": flt(atom.get("amount")),
			"qty": flt(atom.get("qty")) or None,
			"uom": atom.get("uom"),
			"rate": flt(atom.get("rate")) or None,
			"remarks": atom.get("remarks") or "",
			"link": atom.get("link") or _doc_link(
				atom.get("source_doctype") or atom.get("voucher_type"),
				atom.get("source_document") or atom.get("voucher_no"),
			),
			"unallocated": bool(atom.get("unallocated")),
		}
		line["sources"].append(source)

	result = []
	for group in sorted(groups.values(), key=lambda g: g["label"]):
		group["lines"] = sorted(group["lines"].values(), key=lambda l: l["label"])
		group["amount"] = flt(group["amount"])
		for line in group["lines"]:
			line["amount"] = flt(line["amount"])
		result.append(group)
	return result


def _expand_stock_entry_atoms(atom: dict) -> list[dict]:
	rows = frappe.db.sql(
		"""
		SELECT sed.item_code, sed.item_name, sed.qty, sed.uom, sed.basic_amount AS amount,
			COALESCE(i.item_group, %s) AS item_group
		FROM `tabStock Entry Detail` sed
		INNER JOIN `tabStock Entry` se ON se.name = sed.parent
		LEFT JOIN `tabItem` i ON i.name = sed.item_code
		WHERE sed.parent = %s AND se.docstatus = 1
		""",
		(_("Uncategorized"), atom["voucher_no"]),
		as_dict=True,
	)
	if not rows:
		return [atom]

	expanded = []
	for row in rows:
		amount = flt(row.amount) or flt(atom["amount"])
		qty = flt(row.qty)
		rate = flt(amount / qty) if qty else 0
		expanded.append({
			**atom,
			"group_key": row.item_group or _("Uncategorized"),
			"group_label": row.item_group or _("Uncategorized"),
			"line_key": row.item_code,
			"line_label": row.item_name or row.item_code,
			"qty": qty,
			"uom": row.uom,
			"rate": rate,
			"amount": amount,
			"source_doctype": "Stock Entry",
			"source_document": atom["voucher_no"],
			"date": atom.get("posting_date"),
			"remarks": atom.get("boq_item") or "",
			"link": _doc_link("Stock Entry", atom["voucher_no"]),
		})
	return expanded


def _build_material_atoms(project: str, gl_atoms: list[dict]) -> list[dict]:
	atoms = []
	linked_stock_entries = _get_dpr_linked_stock_entries(project)

	for row in frappe.db.sql(
		"""
		SELECT dm.item_code, dm.item_name, dm.qty, dm.uom, dm.rate, dm.amount,
			COALESCE(i.item_group, %s) AS item_group,
			dpr.name AS dpr_name, dpr.date, dpr.boq_item, dm.stock_entry
		FROM `tabDPR Material` dm
		INNER JOIN `tabDaily Progress Record` dpr ON dpr.name = dm.parent
		LEFT JOIN `tabItem` i ON i.name = dm.item_code
		WHERE dpr.project = %s AND dpr.docstatus = 1 AND dm.amount != 0
		ORDER BY dpr.date DESC, dm.item_code
		""",
		(_("Uncategorized"), project),
		as_dict=True,
	):
		remarks = row.boq_item or ""
		if row.stock_entry:
			remarks = _append_linked_voucher_remark(remarks, _("Stock Entry"), row.stock_entry)
		atoms.append({
			"amount": flt(row.amount),
			"group_key": row.item_group or _("Uncategorized"),
			"group_label": row.item_group or _("Uncategorized"),
			"line_key": row.item_code,
			"line_label": row.item_name or row.item_code,
			"qty": flt(row.qty),
			"uom": row.uom,
			"rate": flt(row.rate),
			"source_doctype": "Daily Progress Record",
			"source_document": row.dpr_name,
			"date": row.date,
			"remarks": remarks,
			"link": _doc_link("Daily Progress Record", row.dpr_name),
			"unallocated": not row.boq_item,
		})

	for atom in gl_atoms:
		if atom["voucher_type"] == "Stock Entry":
			if atom["voucher_no"] in linked_stock_entries:
				continue
			atoms.extend(_expand_stock_entry_atoms(atom))
			continue
		# Supplier purchases categorized as material — group by supplier like subcontract drill-down
		if atom["voucher_type"] in ("Purchase Invoice", "Purchase Receipt"):
			supplier = atom.get("supplier")
			if not supplier and atom["voucher_type"] == "Purchase Invoice":
				supplier = frappe.db.get_value("Purchase Invoice", atom["voucher_no"], "supplier")
			elif not supplier and atom["voucher_type"] == "Purchase Receipt":
				supplier = frappe.db.get_value("Purchase Receipt", atom["voucher_no"], "supplier")
			supplier = supplier or _("Unknown Supplier")
			atoms.append({
				**atom,
				"group_key": supplier,
				"group_label": supplier,
				"line_key": atom.get("item_code") or atom["voucher_no"],
				"line_label": atom.get("item_name") or atom.get("item_code") or atom["voucher_no"],
				"source_doctype": atom["voucher_type"],
				"source_document": atom["voucher_no"],
				"date": atom.get("posting_date"),
				"remarks": atom.get("boq_item") or "",
				"link": _doc_link(atom["voucher_type"], atom["voucher_no"]),
			})
			continue
		atoms.append({
			**atom,
			"group_key": atom.get("account") or _("GL Material"),
			"group_label": atom.get("account") or _("GL Material"),
			"line_key": atom["voucher_no"],
			"line_label": atom["voucher_no"],
			"source_doctype": atom["voucher_type"],
			"source_document": atom["voucher_no"],
			"date": atom.get("posting_date"),
			"remarks": atom.get("boq_item") or "",
			"link": _doc_link(atom["voucher_type"], atom["voucher_no"]),
		})

	return atoms


def _build_labor_atoms(project: str, gl_atoms: list[dict]) -> list[dict]:
	atoms = []
	linked_journal_entries = _get_dpr_linked_journal_entries(project)
	dpr_journal_entries: dict[str, set[str]] = {}
	for dpr in frappe.get_all(
		"Daily Progress Record",
		filters={"project": project, "docstatus": 1},
		fields=["name", "journal_entries"],
	):
		if dpr.journal_entries:
			dpr_journal_entries[dpr.name] = _parse_comma_separated_names(dpr.journal_entries)

	for row in frappe.db.sql(
		"""
		SELECT de.employee, de.employee_name, de.designation, de.amount,
			de.hours, de.rate_per_day,
			dpr.name AS dpr_name, dpr.date, dpr.boq_item
		FROM `tabDPR Employee` de
		INNER JOIN `tabDaily Progress Record` dpr ON dpr.name = de.parent
		WHERE dpr.project = %s AND dpr.docstatus = 1 AND de.amount != 0
		ORDER BY dpr.date DESC, de.employee_name
		""",
		project,
		as_dict=True,
	):
		designation = row.designation or _("Unspecified Designation")
		remarks = row.boq_item or ""
		for je_name in sorted(dpr_journal_entries.get(row.dpr_name, set())):
			remarks = _append_linked_voucher_remark(remarks, _("Journal Entry"), je_name)
		hours = flt(row.hours)
		rate = flt(row.rate_per_day) or (flt(row.amount) / hours if hours else 0)
		atoms.append({
			"amount": flt(row.amount),
			"group_key": designation,
			"group_label": designation,
			"line_key": row.employee or row.employee_name,
			"line_label": row.employee_name or row.employee,
			"qty": hours or None,
			"uom": _("Hrs") if hours else None,
			"rate": rate or None,
			"source_doctype": "Daily Progress Record",
			"source_document": row.dpr_name,
			"date": row.date,
			"remarks": remarks,
			"link": _doc_link("Daily Progress Record", row.dpr_name),
			"unallocated": not row.boq_item,
		})

	for atom in gl_atoms:
		if atom["voucher_type"] == "Journal Entry" and atom["voucher_no"] in linked_journal_entries:
			continue
		group = atom.get("account") or _("GL Labour")
		atoms.append({
			**atom,
			"group_key": group,
			"group_label": group,
			"line_key": atom["voucher_no"],
			"line_label": atom["voucher_no"],
			"source_doctype": atom["voucher_type"],
			"source_document": atom["voucher_no"],
			"date": atom.get("posting_date"),
			"remarks": atom.get("boq_item") or "",
			"link": _doc_link(atom["voucher_type"], atom["voucher_no"]),
		})

	return atoms


def _build_subcontractor_atoms(gl_atoms: list[dict]) -> list[dict]:
	atoms = []
	for atom in gl_atoms:
		supplier = ""
		if atom["voucher_type"] == "Purchase Invoice":
			supplier = frappe.db.get_value("Purchase Invoice", atom["voucher_no"], "supplier") or _("Unknown Supplier")
		elif atom["voucher_type"] == "Purchase Receipt":
			supplier = frappe.db.get_value("Purchase Receipt", atom["voucher_no"], "supplier") or _("Unknown Supplier")
		else:
			supplier = atom.get("supplier") or atom.get("account") or _("Subcontractor")

		line_key = atom.get("item_code") or atom["voucher_no"]
		line_label = atom.get("item_name") or atom.get("item_code") or atom["voucher_no"]

		atoms.append({
			**atom,
			"group_key": supplier,
			"group_label": supplier,
			"line_key": line_key,
			"line_label": line_label,
			"source_doctype": atom["voucher_type"],
			"source_document": atom["voucher_no"],
			"date": atom.get("posting_date"),
			"remarks": atom.get("boq_item") or "",
			"link": _doc_link(atom["voucher_type"], atom["voucher_no"]),
		})
	return atoms


def _build_other_atoms(gl_atoms: list[dict]) -> list[dict]:
	atoms = []
	for atom in gl_atoms:
		account = atom.get("account") or _("Other")
		remark = atom.get("boq_item") or ""
		atoms.append({
			**atom,
			"group_key": account,
			"group_label": account,
			"line_key": atom["voucher_no"],
			"line_label": atom["voucher_no"],
			"source_doctype": atom["voucher_type"],
			"source_document": atom["voucher_no"],
			"date": atom.get("posting_date"),
			"remarks": remark,
			"link": _doc_link(atom["voucher_type"], atom["voucher_no"]),
		})
	return atoms


def _build_unallocated_atoms(all_atoms: list[dict]) -> list[dict]:
	"""Shape unallocated costs (no BOQ item) from any category for Other/Unallocated drill-down."""
	atoms = []
	category_labels = {
		"subcontractor": _("Unallocated Subcontractor"),
		"material": _("Unallocated Material"),
		"labor": _("Unallocated Labour"),
		"other": _("Unallocated Other"),
	}

	for atom in all_atoms:
		if not atom.get("unallocated"):
			continue

		category = atom.get("category") or "other"
		base_group = category_labels.get(category, _("Unallocated Cost"))

		if category == "subcontractor":
			shaped = _build_subcontractor_atoms([atom])
			for shaped_atom in shaped:
				shaped_atom["group_key"] = base_group
				shaped_atom["group_label"] = base_group
				if not shaped_atom.get("remarks"):
					shaped_atom["remarks"] = _("No BOQ item linked")
				else:
					shaped_atom["remarks"] = _("No BOQ item linked") + f" · {shaped_atom['remarks']}"
				atoms.append(shaped_atom)
			continue

		if category == "material":
			line_label = atom.get("item_name") or atom.get("item_code") or atom["voucher_no"]
			atoms.append({
				**atom,
				"group_key": base_group,
				"group_label": base_group,
				"line_key": atom.get("item_code") or atom["voucher_no"],
				"line_label": line_label,
				"source_doctype": atom["voucher_type"],
				"source_document": atom["voucher_no"],
				"date": atom.get("posting_date"),
				"remarks": _("No BOQ item linked"),
				"link": _doc_link(atom["voucher_type"], atom["voucher_no"]),
			})
			continue

		if category == "labor":
			atoms.append({
				**atom,
				"group_key": base_group,
				"group_label": base_group,
				"line_key": atom["voucher_no"],
				"line_label": atom["voucher_no"],
				"source_doctype": atom["voucher_type"],
				"source_document": atom["voucher_no"],
				"date": atom.get("posting_date"),
				"remarks": _("No BOQ item linked"),
				"link": _doc_link(atom["voucher_type"], atom["voucher_no"]),
			})
			continue

		account = atom.get("account") or _("Other")
		atoms.append({
			**atom,
			"group_key": base_group,
			"group_label": base_group,
			"line_key": atom["voucher_no"],
			"line_label": f"{account} · {atom['voucher_no']}",
			"source_doctype": atom["voucher_type"],
			"source_document": atom["voucher_no"],
			"date": atom.get("posting_date"),
			"remarks": _("No BOQ item linked"),
			"link": _doc_link(atom["voucher_type"], atom["voucher_no"]),
		})

	return atoms


def _build_dpr_other_atoms(project: str) -> list[dict]:
	"""Operational DPR rows for asset/overhead/expense (GL JEs are deduplicated separately)."""
	atoms = []

	for row in frappe.db.sql(
		"""
		SELECT da.asset, da.asset_name, da.amount,
			dpr.name AS dpr_name, dpr.date, dpr.boq_item
		FROM `tabDPR Asset` da
		INNER JOIN `tabDaily Progress Record` dpr ON dpr.name = da.parent
		WHERE dpr.project = %s AND dpr.docstatus = 1 AND da.amount != 0
		ORDER BY dpr.date DESC, da.asset_name
		""",
		project,
		as_dict=True,
	):
		label = row.asset_name or row.asset or _("Asset")
		atoms.append({
			"amount": flt(row.amount),
			"group_key": _("DPR Assets"),
			"group_label": _("DPR Assets"),
			"line_key": row.asset or label,
			"line_label": label,
			"source_doctype": "Daily Progress Record",
			"source_document": row.dpr_name,
			"date": row.date,
			"remarks": row.boq_item or "",
			"link": _doc_link("Daily Progress Record", row.dpr_name),
			"unallocated": not row.boq_item,
		})

	for row in frappe.db.sql(
		"""
		SELECT doh.account, doh.account_name, doh.description, doh.amount, doh.journal_entry,
			dpr.name AS dpr_name, dpr.date, dpr.boq_item
		FROM `tabDPR Overhead` doh
		INNER JOIN `tabDaily Progress Record` dpr ON dpr.name = doh.parent
		WHERE dpr.project = %s AND dpr.docstatus = 1 AND doh.amount != 0
		ORDER BY dpr.date DESC, doh.account_name
		""",
		project,
		as_dict=True,
	):
		label = row.account_name or row.account or row.description or _("Overhead")
		remarks = row.boq_item or ""
		if row.journal_entry:
			remarks = _append_linked_voucher_remark(remarks, _("Journal Entry"), row.journal_entry)
		atoms.append({
			"amount": flt(row.amount),
			"group_key": _("DPR Overheads"),
			"group_label": _("DPR Overheads"),
			"line_key": f"{row.dpr_name}-{label}",
			"line_label": label,
			"source_doctype": "Daily Progress Record",
			"source_document": row.dpr_name,
			"date": row.date,
			"remarks": remarks,
			"link": _doc_link("Daily Progress Record", row.dpr_name),
			"unallocated": not row.boq_item,
		})

	for row in frappe.db.sql(
		"""
		SELECT de.expense_type, de.amount, de.journal_entry,
			dpr.name AS dpr_name, dpr.date, dpr.boq_item
		FROM `tabDPR Expense` de
		INNER JOIN `tabDaily Progress Record` dpr ON dpr.name = de.parent
		WHERE dpr.project = %s AND dpr.docstatus = 1 AND de.amount != 0
		ORDER BY dpr.date DESC, de.expense_type
		""",
		project,
		as_dict=True,
	):
		label = row.expense_type or _("Expense")
		remarks = row.boq_item or ""
		if row.journal_entry:
			remarks = _append_linked_voucher_remark(remarks, _("Journal Entry"), row.journal_entry)
		atoms.append({
			"amount": flt(row.amount),
			"group_key": _("DPR Expenses"),
			"group_label": _("DPR Expenses"),
			"line_key": f"{row.dpr_name}-{label}",
			"line_label": label,
			"source_doctype": "Daily Progress Record",
			"source_document": row.dpr_name,
			"date": row.date,
			"remarks": remarks,
			"link": _doc_link("Daily Progress Record", row.dpr_name),
			"unallocated": not row.boq_item,
		})

	return atoms


def _build_other_breakdown_atoms(project: str, all_atoms: list[dict]) -> list[dict]:
	linked_journal_entries = _get_dpr_linked_journal_entries(project)
	other_gl_atoms = [
		a
		for a in all_atoms
		if a["category"] == "other"
		and not a.get("unallocated")
		and not (a["voucher_type"] == "Journal Entry" and a["voucher_no"] in linked_journal_entries)
	]
	atoms = _build_other_atoms(other_gl_atoms)
	atoms.extend(_build_dpr_other_atoms(project))
	atoms.extend(_build_unallocated_atoms(all_atoms))
	return atoms


def _build_commission_atoms(project: str) -> list[dict]:
	atoms = []
	try:
		from construction_management.api.project_commission_data import build_commission_ledger

		rows, _meta = build_commission_ledger(project)
	except Exception:
		return atoms

	for row in rows:
		amount = flt(row.get("commission_amount"))
		if amount <= 0:
			continue
		person = row.get("employee_name") or row.get("sales_person") or _("Commission")
		if row.get("row_type") == "Journal Entry":
			amount = flt(row.get("commission_received")) or amount
			line_label = row.get("remarks") or row.get("source_name")
			source_doctype = "Journal Entry"
			source_document = row.get("source_name")
		else:
			line_label = row.get("invoice_no") or row.get("source_name")
			source_doctype = "Sales Invoice"
			source_document = row.get("invoice_no") or row.get("source_name")

		atoms.append({
			"amount": amount,
			"group_key": person,
			"group_label": person,
			"line_key": line_label,
			"line_label": line_label,
			"source_doctype": source_doctype,
			"source_document": source_document,
			"date": row.get("invoice_date") or row.get("sort_date"),
			"remarks": row.get("remarks") or row.get("row_type") or "",
			"link": _doc_link(source_doctype, source_document),
		})
	return atoms


def _category_total_from_summary(project: str, category: str) -> float:
	from construction_management.api.boq_tree import get_project_cost_breakdown

	summary = get_project_cost_breakdown(project) or {}
	if category == "other":
		return flt(summary.get("other", 0)) + flt(summary.get("unallocated", 0))
	return flt(summary.get(category, 0))


@frappe.whitelist()
def get_soa_expense_breakdown(project: str, category: str) -> dict:
	"""Return 3-level expense tree for a SOA category."""
	if not project:
		frappe.throw(_("Project is required"))
	category = (category or "").strip().lower()
	if category not in VALID_CATEGORIES:
		frappe.throw(_("Invalid expense category: {0}").format(category))

	total = _category_total_from_summary(project, category)
	if total <= 0:
		return {"category": category, "total": 0.0, "groups": []}

	if category == "commission":
		atoms = _build_commission_atoms(project)
	else:
		all_atoms = _collect_gl_atoms(project)
		gl_atoms = [a for a in all_atoms if a["category"] == category]
		if category == "material":
			atoms = _build_material_atoms(project, gl_atoms)
		elif category == "labor":
			atoms = _build_labor_atoms(project, gl_atoms)
		elif category == "subcontractor":
			atoms = _build_subcontractor_atoms(gl_atoms)
		else:
			atoms = _build_other_breakdown_atoms(project, all_atoms)

	groups = _build_tree_from_atoms(atoms)
	return {"category": category, "total": total, "groups": groups}


def summarize_project_cost_breakdown(project: str) -> dict:
	"""Build category totals using shared categorization (used by get_project_cost_breakdown)."""
	if not project:
		return {}

	commission_total = _get_commission_total(project)
	company = frappe.db.get_value("Project", project, "company")
	comm_accounts = _get_commission_accounts(company)

	breakdown = {
		"subcontractor": 0.0,
		"labor": 0.0,
		"material": 0.0,
		"commission": commission_total,
		"other": 0.0,
		"unallocated": 0.0,
		"total": 0.0,
	}

	for entry in _fetch_gl_expense_entries(project):
		amount = flt(entry.amount)
		category = categorize_project_cost_entry(entry, comm_accounts)
		if not category:
			continue
		if not entry.boq_item:
			breakdown["unallocated"] += amount
		breakdown[category] += amount

	expense_accounts = _get_expense_account_names()
	for atom in _fetch_non_expense_pi_atoms(project, expense_accounts):
		amount = flt(atom["amount"])
		category = atom.get("category") or "material"
		if category not in ("material", "labor", "subcontractor", "other"):
			category = "material"
		if not atom.get("boq_item"):
			breakdown["unallocated"] += amount
		breakdown[category] += amount

	breakdown["total"] = (
		breakdown["subcontractor"]
		+ breakdown["labor"]
		+ breakdown["material"]
		+ breakdown["commission"]
		+ breakdown["other"]
	)
	return breakdown
