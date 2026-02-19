# Copyright (c) 2026, Construction Management
# License: MIT
# API utilities for Purchase Order purchase history dashboard

import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_purchase_history(purchase_order):
	"""
	Get purchase history summary for a Purchase Order.
	Returns advance payments, invoice totals, and retention totals.
	"""
	if not purchase_order:
		return {}

	po = frappe.get_cached_doc("Purchase Order", purchase_order)
	retention_pct = flt(po.get("custom_retention_"))
	advance_pct = flt(po.get("custom_advance_"))

	# --- Advance Payments ---
	advances = frappe.get_all(
		"Purchase Advance Payment",
		filters={"purchase_order": purchase_order, "docstatus": 1},
		fields=["name", "amount", "allocated_amount", "unallocated_amount", "status", "date", "linked_purchase_invoice"]
	)
	total_advance = sum(flt(a.amount) for a in advances)
	total_advance_allocated = sum(flt(a.allocated_amount) for a in advances)
	total_advance_unallocated = sum(flt(a.unallocated_amount) for a in advances)

	# --- Purchase Invoices ---
	pi_items = frappe.db.sql("""
		SELECT
			pi.name, pi.posting_date, pi.status, pi.net_total, pi.grand_total,
			pi.custom_is_advance, pi.total_taxes_and_charges
		FROM `tabPurchase Invoice` pi
		INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
		WHERE pii.purchase_order = %s AND pi.docstatus = 1
		GROUP BY pi.name
		ORDER BY pi.posting_date DESC
	""", purchase_order, as_dict=True)

	total_invoice_amount = sum(flt(pi.grand_total) for pi in pi_items)
	total_advance_invoices = sum(flt(pi.grand_total) for pi in pi_items if pi.custom_is_advance)
	total_regular_invoices = total_invoice_amount - total_advance_invoices
	total_tax = sum(flt(pi.total_taxes_and_charges) for pi in pi_items)
	total_net = sum(flt(pi.net_total) for pi in pi_items)

	# --- Retention from Invoices ---
	# Deduction items don't have purchase_order set on the row itself,
	# so find invoices linked to this PO via other items, then sum deductions
	retention_deducted_pi = abs(flt(frappe.db.sql("""
		SELECT COALESCE(SUM(pii.amount), 0)
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
		WHERE pii.item_code = 'RETENTION-DEDUCTION'
		AND pi.docstatus = 1
		AND pi.name IN (
			SELECT DISTINCT parent FROM `tabPurchase Invoice Item`
			WHERE purchase_order = %s
		)
	""", purchase_order)[0][0]))

	# --- Retention from Purchase Receipts ---
	retention_deducted_pr = abs(flt(frappe.db.sql("""
		SELECT COALESCE(SUM(pri.amount), 0)
		FROM `tabPurchase Receipt Item` pri
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pri.item_code = 'RETENTION-DEDUCTION'
		AND pr.docstatus = 1
		AND pr.name IN (
			SELECT DISTINCT parent FROM `tabPurchase Receipt Item`
			WHERE purchase_order = %s
		)
	""", purchase_order)[0][0]))

	total_retention_deducted = retention_deducted_pi 

	# --- Advance deducted from Invoices ---
	advance_deducted_pi = abs(flt(frappe.db.sql("""
		SELECT COALESCE(SUM(pii.amount), 0)
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
		WHERE pii.item_code = 'ADVANCE-DEDUCTION'
		AND pi.docstatus = 1
		AND pi.name IN (
			SELECT DISTINCT parent FROM `tabPurchase Invoice Item`
			WHERE purchase_order = %s
		)
	""", purchase_order)[0][0]))

	# --- PO totals ---
	po_grand_total = flt(po.grand_total)
	expected_retention = flt(po_grand_total * retention_pct / 100, 2) if retention_pct else 0
	retention_balance = expected_retention - total_retention_deducted

	# Override allocated/unallocated on advance records using actual deductions
	# since the doctype fields are not auto-updated
	remaining_deducted = advance_deducted_pi
	for adv in advances:
		adv_amount = flt(adv.amount)
		if remaining_deducted >= adv_amount:
			adv.allocated_amount = adv_amount
			adv.unallocated_amount = 0
			adv.status = "Fully Utilized"
			remaining_deducted -= adv_amount
		elif remaining_deducted > 0:
			adv.allocated_amount = remaining_deducted
			adv.unallocated_amount = adv_amount - remaining_deducted
			adv.status = "Partially Utilized"
			remaining_deducted = 0
		else:
			adv.allocated_amount = 0
			adv.unallocated_amount = adv_amount

	total_advance_allocated = sum(flt(a.allocated_amount) for a in advances)
	total_advance_unallocated = sum(flt(a.unallocated_amount) for a in advances)

	return {
		"po_grand_total": po_grand_total,
		"retention_pct": retention_pct,
		"advance_pct": advance_pct,

		# Advance summary
		"advances": advances,
		"total_advance": total_advance,
		"total_advance_allocated": total_advance_allocated,
		"total_advance_unallocated": total_advance_unallocated,

		# Invoice summary
		"invoices": pi_items,
		"total_invoice_amount": total_invoice_amount,
		"total_advance_invoices": total_advance_invoices,
		"total_regular_invoices": total_regular_invoices,
		"total_tax": total_tax,
		"total_net": total_net,
		"net_billed": total_invoice_amount - advance_deducted_pi - total_retention_deducted,

		# Retention summary
		"expected_retention": expected_retention,
		"total_retention_deducted": total_retention_deducted,
		"retention_balance": retention_balance,

		# Advance deducted
		"advance_deducted": advance_deducted_pi,
		"advance_balance": total_advance - advance_deducted_pi,
	}
