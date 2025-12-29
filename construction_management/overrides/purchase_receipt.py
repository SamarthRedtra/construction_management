# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from construction_management.api.purchase_receipt_utils import get_warehouse_project


def validate(doc, method):
	"""Validate Purchase Receipt before save"""
	validate_items_in_purchase_order(doc)
	ensure_item_projects(doc)


def before_submit(doc, method):
	"""Validate Purchase Receipt before submit"""
	validate_items_in_purchase_order(doc)
	ensure_item_projects(doc, make_mandatory=True)


def validate_items_in_purchase_order(doc):
	"""
	Validate that all items in Purchase Receipt exist in the linked Purchase Order.
	Throws error if any item is not found in the PO.
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
	
	# Check each item in Purchase Receipt
	invalid_items = []
	for row in doc.items:
		if row.item_code and row.item_code not in po_items_set:
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


def ensure_item_projects(doc, make_mandatory=False):
	"""
	Ensure each item has project set by pulling from the row or linked warehouses.
	This safeguards against client-side values being cleared during save/submit.
	"""
	for row in doc.get("items", []):
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
