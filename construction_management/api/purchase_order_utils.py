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


@frappe.whitelist()
def make_advance_purchase_invoice(purchase_order):
	"""
	Create a draft Purchase Invoice from a Purchase Order with advance settings pre-configured.
	- custom_is_advance is ticked
	- Items from PO are mapped
	- PURCHASE-ADVANCE item is auto-added based on PO advance %
	Returns the new Purchase Invoice name.
	"""
	if not purchase_order:
		frappe.throw(_("Purchase Order is required"))

	po = frappe.get_doc("Purchase Order", purchase_order)

	if po.docstatus != 1:
		frappe.throw(_("Purchase Order must be submitted"))

	advance_pct = flt(po.get("custom_advance_"))
	if advance_pct <= 0:
		frappe.throw(_("Purchase Order does not have an Advance % configured"))

	# Ensure deduction items exist
	from construction_management.overrides.purchase_invoice import _ensure_purchase_deduction_items
	_ensure_purchase_deduction_items()

	# Create Purchase Invoice
	pi = frappe.new_doc("Purchase Invoice")
	pi.supplier = po.supplier
	pi.company = po.company
	pi.project = po.project
	pi.currency = po.currency
	pi.conversion_rate = po.conversion_rate
	pi.buying_price_list = po.buying_price_list
	pi.price_list_currency = po.price_list_currency
	pi.plc_conversion_rate = po.plc_conversion_rate
	pi.cost_center = po.cost_center
	pi.custom_is_advance = 1
	pi.update_billed_amount_in_purchase_order = 0
	pi.custom_suppliersubcontractor = po.get("custom_suppliersubcontractor") or ""

	# Copy BOQ dimension fields if present
	if po.get("bill_no"):
		pi.bill_no = po.bill_no
	if po.get("boq_item"):
		pi.boq_item = po.boq_item

	# Add PURCHASE-ADVANCE item only (no PO line items for advance invoices)
	advance_amount = flt(po.grand_total * advance_pct / 100, 2)
	if advance_amount > 0:
		default_expense_account = frappe.db.get_value("Company", po.company, "default_expense_account")
		default_cost_center = po.cost_center or frappe.db.get_value("Company", po.company, "cost_center")

		pi.append("items", {
			"item_code": "PURCHASE-ADVANCE",
			"item_name": "Purchase Advance",
			"qty": 1,
			"rate": advance_amount,
			"amount": advance_amount,
			"uom": "Nos",
			"conversion_factor": 1.0,
			"description": f"Advance payment ({advance_pct}% of PO {po.name})",
			"expense_account": default_expense_account,
			"cost_center": default_cost_center,
			"project": po.project,
		})

	pi.flags.ignore_permissions = True
	pi.set_missing_values()
	pi.save()

	frappe.msgprint(_("Advance Purchase Invoice {0} created").format(pi.name))

	return pi.name
