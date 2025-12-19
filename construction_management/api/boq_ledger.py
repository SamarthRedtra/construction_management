# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt, today


@frappe.whitelist()
def get_previous_qty(boq_item: str) -> float:
	"""
	Get sum of ledger qty excluding current period drafts.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		float: Previous quantity from submitted invoices
	"""
	# Sum all ledger entries from submitted invoices
	result = frappe.db.sql("""
		SELECT COALESCE(SUM(pl.qty), 0) as total
		FROM `tabBOQ Progress Ledger` pl
		LEFT JOIN `tabSales Invoice` si ON pl.reference_name = si.name
		WHERE pl.boq_item = %s
		AND pl.source IN ('Invoice', 'Reversal')
		AND (si.docstatus = 1 OR pl.reference_doctype != 'Sales Invoice')
	""", boq_item)
	
	return flt(result[0][0]) if result else 0


@frappe.whitelist()
def get_previous_amount(boq_item: str) -> float:
	"""
	Get sum of ledger amount excluding current period drafts.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		float: Previous amount from submitted invoices
	"""
	result = frappe.db.sql("""
		SELECT COALESCE(SUM(pl.amount), 0) as total
		FROM `tabBOQ Progress Ledger` pl
		LEFT JOIN `tabSales Invoice` si ON pl.reference_name = si.name
		WHERE pl.boq_item = %s
		AND pl.source IN ('Invoice', 'Reversal')
		AND (si.docstatus = 1 OR pl.reference_doctype != 'Sales Invoice')
	""", boq_item)
	
	return flt(result[0][0]) if result else 0


@frappe.whitelist()
def get_to_date_qty(boq_item: str) -> float:
	"""
	Get sum of all ledger qty up to current date.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		float: To-date quantity
	"""
	result = frappe.db.sql("""
		SELECT COALESCE(SUM(qty), 0) as total
		FROM `tabBOQ Progress Ledger`
		WHERE boq_item = %s
		AND posting_date <= %s
	""", (boq_item, today()))
	
	return flt(result[0][0]) if result else 0


@frappe.whitelist()
def get_to_date_amount(boq_item: str) -> float:
	"""
	Get sum of all ledger amount up to current date.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		float: To-date amount
	"""
	result = frappe.db.sql("""
		SELECT COALESCE(SUM(amount), 0) as total
		FROM `tabBOQ Progress Ledger`
		WHERE boq_item = %s
		AND posting_date <= %s
	""", (boq_item, today()))
	
	return flt(result[0][0]) if result else 0


@frappe.whitelist()
def get_cost_to_date(boq_item: str) -> float:
	"""
	Get sum of all DPR costs for a BOQ Item.
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		float: Total cost to date
	"""
	result = frappe.db.sql("""
		SELECT COALESCE(SUM(
			COALESCE(labour_cost, 0) + 
			COALESCE(material_cost, 0) + 
			COALESCE(asset_cost, 0) + 
			COALESCE(subcontract_cost, 0) + 
			COALESCE(expense_cost, 0)
		), 0) as total
		FROM `tabDaily Progress Record`
		WHERE boq_item = %s
		AND date <= %s
	""", (boq_item, today()))
	
	return flt(result[0][0]) if result else 0


def create_ledger_entry(
	boq_item: str,
	qty: float,
	amount: float,
	source: str,
	reference_doctype: str = None,
	reference_name: str = None,
	posting_date: str = None,
	remarks: str = None
) -> str:
	"""
	Create a BOQ Progress Ledger entry.
	
	Args:
		boq_item: BOQ Item name
		qty: Quantity
		amount: Amount
		source: Source type (Invoice/Adjustment/Reversal)
		reference_doctype: Reference DocType
		reference_name: Reference document name
		posting_date: Posting date (defaults to today)
		remarks: Optional remarks
		
	Returns:
		str: Created ledger entry name
	"""
	# Get BOQ Item details
	item = frappe.get_doc("BOQ Item", boq_item)
	
	ledger = frappe.new_doc("BOQ Progress Ledger")
	ledger.project = item.project
	ledger.project_boq = item.project_boq
	ledger.bill_no = item.parent_bill
	ledger.boq_item = boq_item
	ledger.posting_date = posting_date or today()
	ledger.qty = flt(qty)
	ledger.amount = flt(amount)
	ledger.source = source
	ledger.reference_doctype = reference_doctype
	ledger.reference_name = reference_name
	ledger.remarks = remarks
	ledger.insert(ignore_permissions=True)
	
	return ledger.name


@frappe.whitelist()
def rebuild_ledger(project: str = None):
	"""
	Rebuild ledger entries from invoices for data integrity.
	
	Args:
		project: Optional project filter
	"""
	frappe.only_for("System Manager")
	
	filters = {}
	if project:
		filters["project"] = project
	
	# Get all BOQ Items
	boq_items = frappe.get_all(
		"BOQ Item",
		filters=filters,
		fields=["name", "project"]
	)
	
	for item in boq_items:
		# Get all invoices for this item
		invoices = frappe.db.sql("""
			SELECT si.name, si.posting_date, si.docstatus,
				   sii.qty, sii.amount
			FROM `tabSales Invoice` si
			JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
			WHERE sii.boq_item = %s
			AND si.docstatus = 1
		""", item.name, as_dict=True)
		
		# Check existing ledger entries
		existing = frappe.get_all(
			"BOQ Progress Ledger",
			filters={"boq_item": item.name},
			fields=["name", "reference_name", "qty", "amount"]
		)
		
		existing_refs = {e.reference_name: e for e in existing}
		
		# Create missing entries
		for inv in invoices:
			if inv.name not in existing_refs:
				create_ledger_entry(
					boq_item=item.name,
					qty=inv.qty,
					amount=inv.amount,
					source="Invoice",
					reference_doctype="Sales Invoice",
					reference_name=inv.name,
					posting_date=inv.posting_date,
					remarks="Rebuilt from invoice"
				)
				frappe.logger().info(f"Created ledger entry for {item.name} from {inv.name}")
	
	frappe.db.commit()
	frappe.msgprint(_("Ledger rebuild completed"))
