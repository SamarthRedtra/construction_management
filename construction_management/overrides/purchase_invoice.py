# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt


def validate(doc, method):
	"""Auto-add retention and advance deduction items based on linked Purchase Order percentages"""
	if doc.docstatus != 0 or doc.get("custom_is_advance"):
		return

	# Only apply deductions for Subcontractor type purchases (checked on PO level)
	if not _is_subcontractor_purchase(doc):
		return

	apply_purchase_deductions(doc)


def on_submit(doc, method):
	"""Update cost tracking for BOQ items from Purchase Invoice"""
	for item in doc.items:
		if item.get("boq_item"):
			update_boq_item_cost(item)


def before_cancel(doc, method):
	"""Cancel linked Purchase Advance Payment before Frappe's link check"""
	_cancel_linked_advance_payment(doc)


def on_cancel(doc, method):
	"""Reverse cost tracking for BOQ items on Purchase Invoice cancel"""
	for item in doc.items:
		if item.get("boq_item"):
			update_boq_item_cost(item)


def update_boq_item_cost(item):
	"""
	Update BOQ Item cost tracking from Purchase Invoice.

	Note: Primary cost tracking is done via Daily Progress Record (DPR).
	This function can be used for additional cost allocation if needed.

	Args:
		item: Purchase Invoice Item with boq_item set
	"""
	# Get BOQ Item
	boq_item = frappe.get_doc("BOQ Item", item.boq_item)

	# Recalculate cost fields
	boq_item.calculate_amounts()
	boq_item.db_update()

	frappe.logger().info(f"Updated cost tracking for BOQ Item {item.boq_item}")


def apply_purchase_deductions(doc):
	"""
	Auto-add RETENTION-DEDUCTION and ADVANCE-DEDUCTION items based on
	linked Purchase Order's retention/advance percentages.
	"""
	# Find linked Purchase Order from items
	purchase_order = _get_linked_purchase_order(doc)
	if not purchase_order:
		return

	# Read PO percentages
	po_doc = frappe.get_cached_doc("Purchase Order", purchase_order)
	retention_pct = flt(po_doc.get("custom_retention_"))
	advance_pct = flt(po_doc.get("custom_advance_"))

	if retention_pct <= 0 and advance_pct <= 0:
		return

	# Check if deductions already present on this invoice
	has_retention = False
	has_advance = False
	for item in doc.items:
		if item.item_code == "RETENTION-DEDUCTION":
			has_retention = True
		if item.item_code == "ADVANCE-DEDUCTION":
			has_advance = True

	if has_retention and has_advance:
		return

	# Check if deductions already exist on linked Purchase Receipts
	# to avoid double-deducting when PI is created from a PR
	pr_has_retention, pr_has_advance = _check_pr_deductions(doc)
	if pr_has_retention:
		has_retention = True
	if pr_has_advance:
		has_advance = True

	if has_retention and has_advance:
		return

	# Calculate total billable amount (exclude deduction items)
	total_billable = sum(
		flt(item.amount) for item in doc.items
		if item.item_code not in ["RETENTION-DEDUCTION", "ADVANCE-DEDUCTION"]
	)

	if total_billable <= 0:
		return

	# Ensure deduction items exist and are purchasable
	_ensure_purchase_deduction_items()

	default_expense_account = frappe.db.get_value("Company", doc.company, "default_expense_account")
	default_cost_center = doc.cost_center or frappe.db.get_value("Company", doc.company, "cost_center")

	# Add Retention Deduction
	if retention_pct > 0 and not has_retention:
		retention_amount = flt(total_billable * retention_pct / 100, 2)
		if retention_amount > 0:
			doc.append("items", {
				"item_code": "RETENTION-DEDUCTION",
				"item_name": "Retention Deduction",
				"qty": 1,
				"rate": -retention_amount,
				"amount": -retention_amount,
				"description": f"Retention deduction ({retention_pct}%)",
				"project": doc.project,
				"expense_account": default_expense_account,
				"cost_center": default_cost_center,
				"uom": "Nos",
				"conversion_factor": 1.0,
			})

	# Add Advance Deduction
	if advance_pct > 0 and not has_advance:
		advance_amount = flt(total_billable * advance_pct / 100, 2)
		if advance_amount > 0:
			doc.append("items", {
				"item_code": "ADVANCE-DEDUCTION",
				"item_name": "Advance Deduction",
				"qty": 1,
				"rate": -advance_amount,
				"amount": -advance_amount,
				"description": f"Advance deduction ({advance_pct}%)",
				"project": doc.project,
				"expense_account": default_expense_account,
				"cost_center": default_cost_center,
				"uom": "Nos",
				"conversion_factor": 1.0,
			})


def _get_linked_purchase_order(doc):
	"""Find the linked Purchase Order from Purchase Invoice items"""
	for item in doc.items:
		if item.get("purchase_order"):
			return item.purchase_order
	return None


def _is_subcontractor_purchase(doc):
	"""Check if the linked Purchase Order is for a Subcontractor"""
	po = _get_linked_purchase_order(doc)
	if not po:
		return False
	po_type = frappe.db.get_value("Purchase Order", po, "custom_suppliersubcontractor")
	return po_type == "Subcontractor"


def _check_pr_deductions(doc):
	"""
	Check if linked Purchase Receipts already have retention/advance deduction items.
	Returns (has_retention, has_advance) tuple.
	"""
	has_retention = False
	has_advance = False

	# Collect linked Purchase Receipts from PI items
	purchase_receipts = set()
	for item in doc.items:
		if item.get("purchase_receipt"):
			purchase_receipts.add(item.purchase_receipt)

	if not purchase_receipts:
		return has_retention, has_advance

	# Check if any linked PR has deduction items
	for pr_name in purchase_receipts:
		pr_items = frappe.db.get_all(
			"Purchase Receipt Item",
			filters={"parent": pr_name, "item_code": ["in", ["RETENTION-DEDUCTION", "ADVANCE-DEDUCTION"]]},
			fields=["item_code"]
		)
		for pr_item in pr_items:
			if pr_item.item_code == "RETENTION-DEDUCTION":
				has_retention = True
			if pr_item.item_code == "ADVANCE-DEDUCTION":
				has_advance = True

	return has_retention, has_advance


def _ensure_purchase_deduction_items():
	"""Ensure RETENTION-DEDUCTION and ADVANCE-DEDUCTION items exist and are purchase-enabled"""
	for item_code, item_name, description in [
		("RETENTION-DEDUCTION", "Retention Deduction", "Retention amount deducted from purchase invoices"),
		("ADVANCE-DEDUCTION", "Advance Deduction", "Advance payment deducted from purchase invoices"),
	]:
		if not frappe.db.exists("Item", item_code):
			item = frappe.new_doc("Item")
			item.item_code = item_code
			item.item_name = item_name
			item.item_group = "Services"
			item.stock_uom = "Nos"
			item.is_stock_item = 0
			item.is_sales_item = 1
			item.is_purchase_item = 1
			item.description = description
			item.insert(ignore_permissions=True)
		else:
			# Ensure existing item is also purchase-enabled
			existing = frappe.get_doc("Item", item_code)
			if not existing.is_purchase_item:
				existing.is_purchase_item = 1
				existing.save(ignore_permissions=True)


def create_purchase_advance_payment(doc):
	"""Automatically create Purchase Advance Payment record from a Paid Advance Purchase Invoice"""
	# Check if already exists to avoid duplication
	if frappe.db.exists(
		"Purchase Advance Payment",
		{"linked_purchase_invoice": doc.name, "docstatus": ["!=", 2]}
	):
		return

	adv = frappe.new_doc("Purchase Advance Payment")
	adv.project = doc.project
	adv.supplier = doc.supplier
	adv.purchase_order = _get_linked_purchase_order(doc)
	adv.amount = doc.net_total
	adv.linked_purchase_invoice = doc.name
	adv.date = doc.posting_date
	adv.remarks = f"Automatically created from Advance Purchase Invoice {doc.name}"

	adv.flags.ignore_permissions = True
	adv.insert()
	adv.submit()
	frappe.msgprint(_("Purchase Advance Payment {0} created automatically.").format(adv.name))
	frappe.db.commit()


def _cancel_linked_advance_payment(doc):
	"""Cancel and delete linked Purchase Advance Payment if not utilized"""
	advance_payments = frappe.get_all(
		"Purchase Advance Payment",
		filters={"linked_purchase_invoice": doc.name, "docstatus": 1},
		fields=["name", "allocated_amount"]
	)

	for adv in advance_payments:
		if flt(adv.allocated_amount) > 0:
			frappe.throw(
				_("Cannot cancel Purchase Invoice {0} because the linked Purchase Advance Payment {1} "
				  "has been partially or fully utilized (Allocated: {2}). "
				  "Please reverse the advance allocation first.").format(
					doc.name, adv.name, adv.allocated_amount
				)
			)

		# Cancel and delete the advance payment
		adv_doc = frappe.get_doc("Purchase Advance Payment", adv.name)
		adv_doc.flags.ignore_permissions = True
		adv_doc.flags.ignore_links = True
		adv_doc.cancel()
		frappe.delete_doc("Purchase Advance Payment", adv.name, force=True, ignore_permissions=True)
		frappe.msgprint(_("Purchase Advance Payment {0} cancelled and deleted.").format(adv.name))

