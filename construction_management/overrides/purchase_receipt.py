# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt
from construction_management.api.purchase_receipt_utils import get_warehouse_project

# Item codes that should be excluded from PO item validation
DEDUCTION_ITEM_CODES = {"RETENTION-DEDUCTION", "ADVANCE-DEDUCTION"}


def validate(doc, method):
	"""Validate Purchase Receipt before save"""
	validate_items_in_purchase_order(doc)
	ensure_item_projects(doc)
	apply_purchase_deductions(doc)


def before_submit(doc, method):
	"""Validate Purchase Receipt before submit"""
	validate_items_in_purchase_order(doc)
	ensure_item_projects(doc, make_mandatory=True)


def validate_items_in_purchase_order(doc):
	"""
	Validate that all items in Purchase Receipt exist in the linked Purchase Order.
	Throws error if any item is not found in the PO.
	Skips deduction items (RETENTION-DEDUCTION, ADVANCE-DEDUCTION).
	"""
	# Only validate if custom_purchase_order is set
	if not doc.get("custom_purchase_order"):
		return
	
	purchase_order = doc.custom_purchase_order
	
	# Get all items from the linked Purchase Order
	po_items = frappe.get_all(
		"Purchase Order Item",
		filters={"parent": purchase_order},
		fields=["item_code"],
		pluck="item_code"
	)
	
	if not po_items:
		frappe.throw(
			_("No items found in Purchase Order {0}. Please check the Purchase Order.").format(purchase_order),
			title=_("Invalid Purchase Order")
		)
	
	# Convert to set for faster lookup
	po_items_set = set(po_items)
	
	# Check each item in Purchase Receipt (skip deduction items)
	invalid_items = []
	for row in doc.items:
		if row.item_code and row.item_code not in po_items_set and row.item_code not in DEDUCTION_ITEM_CODES:
			invalid_items.append(row.item_code)
	
	if invalid_items:
		# Format error message with all invalid items
		items_list = "<br>".join([f"• <b>{item}</b>" for item in invalid_items])
		frappe.throw(
			_("The following items are not present in Purchase Order <b>{0}</b>:<br><br>{1}<br><br>"
			  "Please remove these items or select items from the linked Purchase Order.").format(
				purchase_order, items_list
			),
			title=_("Items Not in Purchase Order")
		)


def apply_purchase_deductions(doc):
	"""
	Auto-add RETENTION-DEDUCTION and ADVANCE-DEDUCTION items based on
	linked Purchase Order's retention/advance percentages.
	"""
	if doc.docstatus != 0:
		return

	# Find linked Purchase Order
	purchase_order = doc.get("custom_purchase_order")
	if not purchase_order:
		# Try to find from items
		for item in doc.items:
			if item.get("purchase_order"):
				purchase_order = item.purchase_order
				break

	if not purchase_order:
		return

	# Only apply deductions for Subcontractor type purchases (checked on PO level)
	po_type = frappe.db.get_value("Purchase Order", purchase_order, "custom_suppliersubcontractor")
	if po_type != "Subcontractor":
		return

	# Read PO percentages
	po_doc = frappe.get_cached_doc("Purchase Order", purchase_order)
	retention_pct = flt(po_doc.get("custom_retention_"))
	advance_pct = flt(po_doc.get("custom_advance_"))

	if retention_pct <= 0 and advance_pct <= 0:
		return

	# Check if deductions already present
	has_retention = any(item.item_code == "RETENTION-DEDUCTION" for item in doc.items)
	has_advance = any(item.item_code == "ADVANCE-DEDUCTION" for item in doc.items)

	if has_retention and has_advance:
		return

	# Calculate total billable amount (exclude deduction items)
	total_billable = sum(
		flt(item.amount) for item in doc.items
		if item.item_code not in DEDUCTION_ITEM_CODES
	)

	if total_billable <= 0:
		return

	# Ensure deduction items exist and are purchasable
	from construction_management.overrides.purchase_invoice import _ensure_purchase_deduction_items
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


def ensure_item_projects(doc, make_mandatory=False):
	"""
	Ensure each item has project set by pulling from the row or linked warehouses.
	This safeguards against client-side values being cleared during save/submit.
	"""
	for row in doc.get("items", []):
		# Skip deduction items for project requirement
		if row.item_code in DEDUCTION_ITEM_CODES:
			continue

		project = row.get("project")

		# Try accepted warehouse first, then rejected warehouse
		if not project and row.get("warehouse"):
			project = get_warehouse_project(row.warehouse, company=doc.company)
		if not project and row.get("rejected_warehouse"):
			project = get_warehouse_project(row.rejected_warehouse, company=doc.company)

		if project:
			# Validate company alignment early to give clearer errors
			project_company = frappe.db.get_value("Project", project, "company")
			if project_company and project_company != doc.company:
				frappe.throw(
					_("Row {0}: Project {1} belongs to {2}, but the Purchase Receipt is for {3}. Please select a project for {3}.").format(
						row.idx or row.name, frappe.utils.bold(project), frappe.utils.bold(project_company), frappe.utils.bold(doc.company)
					),
					title=_("Project Company Mismatch"),
				)

			row.project = project
		elif make_mandatory:
			frappe.throw(
				_("Row {0}: Please set a Project for warehouse {1}").format(
					row.idx or row.name, row.warehouse or row.rejected_warehouse
				),
				title=_("Project Required"),
			)
