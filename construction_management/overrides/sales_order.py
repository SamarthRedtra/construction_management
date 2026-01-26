# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt, today
from construction_management.api.boq_ledger import create_ledger_entry, recalculate_ledger_for_item


def validate(doc, method=None):
	"""
	Calculate retention and net amount on save.
	"""
	calculate_retention_and_net_amount(doc)


def on_submit(doc, method=None):
	"""
	When Sales Order is submitted, create BOQ Progress Ledger entries.
	"""
	create_ledger_entries(doc)


def on_cancel(doc, method=None):
	# When Sales Order is cancelled, reverse BOQ Progress Ledger entries.
	# Skip reversal if this is an amendment (the new revision will update these entries)
	if doc.flags.get("is_amending"):
		return

	# Check if linked to Payment Certificate
	if frappe.db.exists("Payment Certificate", {"sales_order": doc.name, "docstatus": ["!=", 2]}):
		frappe.throw(_("Cannot cancel Sales Order {0} as it is linked to a Payment Certificate").format(doc.name))
		
	create_reversing_ledger_entries(doc)


def on_update_after_submit(doc, method=None):
	"""
	Handle revisions to submitted Sales Order.
	"""
	calculate_retention_and_net_amount(doc)
	update_ledger_entries_on_revision(doc)


def calculate_retention_and_net_amount(doc):
	"""
	Calculate retention amount and net amount based on project settings.
	"""
	retention_pct = 0
	if doc.project:
		retention_pct = flt(frappe.db.get_value("Project", doc.project, "retention_percentage"))
	
	total_amount = sum(flt(item.base_amount) for item in doc.items)
	
	doc.custom_retention_amount = flt(total_amount * (retention_pct / 100))
	doc.custom_net_amount = flt(total_amount - doc.custom_retention_amount)


def create_ledger_entries(doc):
	"""
	Create BOQ Progress Ledger entries for each item in the Sales Order.
	"""
	if not frappe.db.exists("DocType", "BOQ Progress Ledger"):
		return

	# Determine retention pro-rating
	retention_pct = 0
	if doc.project:
		retention_pct = flt(frappe.db.get_value("Project", doc.project, "retention_percentage"))
	
	total_order_amount = sum(flt(item.amount) for item in doc.items if item.boq_item)
	total_retention = total_order_amount * (retention_pct / 100)

	for item in doc.items:
		if not item.boq_item:
			continue

		try:
			# Pro-rate retention to this item
			retention_share = 0
			if total_order_amount:
				retention_share = total_retention * (flt(item.amount) / total_order_amount)

			# Create or update ledger entry
			ledger_entry = None
			
			# Case 1: Amendment - Try to find entry from the original SO
			if doc.amended_from:
				ledger_entry = frappe.db.get_value(
					"BOQ Progress Ledger",
					{
						"boq_item": item.boq_item,
						"reference_doctype": "Sales Order",
						"reference_name": doc.amended_from
					},
					"name"
				)

			# Case 2: Normal submit or missing entry
			if not ledger_entry:
				ledger_entry = frappe.db.get_value(
					"BOQ Progress Ledger",
					{
						"boq_item": item.boq_item,
						"reference_doctype": "Sales Order",
						"reference_name": doc.name
					},
					"name"
				)

			update_data = {
				"qty": flt(item.qty),
				"amount": flt(item.amount),
				"proforma_amount": flt(item.amount), # Keeping this for backward compatibility in reports
				"retention_amount": flt(retention_share),
				"percentage": flt(item.get("custom_billing_percentage", 0)),
				"posting_date": doc.transaction_date or today(),
				"source": "Order",
				"reference_doctype": "Sales Order",
				"reference_name": doc.name,
				"remarks": f"Sales Order {doc.name}"
			}

			if ledger_entry:
				frappe.db.set_value("BOQ Progress Ledger", ledger_entry, update_data, update_modified=False)
			else:
				create_ledger_entry(
					boq_item=item.boq_item,
					qty=flt(item.qty),
					amount=flt(item.amount),
					source="Order",
					percentage=flt(item.get("custom_billing_percentage", 0)),
					reference_doctype="Sales Order",
					reference_name=doc.name,
					posting_date=doc.transaction_date or today(),
					remarks=f"Sales Order {doc.name}",
					proforma_amount=flt(item.amount),
					retention_amount=flt(retention_share)
				)

			recalculate_ledger_for_item(item.boq_item)
		except Exception as e:
			frappe.log_error(
				f"Error creating ledger for Sales Order {doc.name}, Item {item.boq_item}: {str(e)}",
				"Sales Order Ledger Error"
			)
			raise


def create_reversing_ledger_entries(doc):
	"""
	Reverse BOQ Progress Ledger entries when Sales Order is cancelled.
	"""
	for item in doc.items:
		if not item.boq_item:
			continue

		ledger_entry = frappe.db.get_value(
			"BOQ Progress Ledger",
			{
				"boq_item": item.boq_item,
				"reference_doctype": "Sales Order",
				"reference_name": doc.name
			},
			"name"
		)

		if ledger_entry:
			frappe.db.set_value(
				"BOQ Progress Ledger",
				ledger_entry,
				{
					"qty": 0,
					"amount": 0,
					"proforma_amount": 0,
					"retention_amount": 0,
					"remarks": f"Cancellation of Sales Order {doc.name}",
					"source": "Order Reversal"
				},
				update_modified=False
			)
			recalculate_ledger_for_item(item.boq_item)


def update_ledger_entries_on_revision(doc):
	"""
	Update BOQ Progress Ledger entries when Sales Order is revised.
	"""
	# Similar to create_ledger_entries but handles removed items
	existing_entries = frappe.get_all(
		"BOQ Progress Ledger",
		filters={
			"reference_doctype": "Sales Order",
			"reference_name": doc.name
		},
		fields=["name", "boq_item"]
	)
	
	existing_map = {e.boq_item: e for e in existing_entries}
	
	# Current items logic
	retention_pct = 0
	if doc.project:
		retention_pct = flt(frappe.db.get_value("Project", doc.project, "retention_percentage"))
	
	total_order_amount = sum(flt(item.amount) for item in doc.items if item.boq_item)
	total_retention = total_order_amount * (retention_pct / 100)

	for item in doc.items:
		if not item.boq_item:
			continue
			
		retention_share = 0
		if total_order_amount:
			retention_share = total_retention * (flt(item.amount) / total_order_amount)
			
		existing = existing_map.get(item.boq_item)
		if existing:
			frappe.db.set_value(
				"BOQ Progress Ledger",
				existing.name,
				{
					"qty": flt(item.qty),
					"amount": flt(item.amount),
					"proforma_amount": flt(item.amount),
					"retention_amount": flt(retention_share),
					"posting_date": doc.transaction_date or today(),
					"remarks": f"Revised Sales Order {doc.name}"
				},
				update_modified=False
			)
			del existing_map[item.boq_item]
		else:
			create_ledger_entry(
				boq_item=item.boq_item,
				qty=flt(item.qty),
				amount=flt(item.amount),
				source="Order",
				reference_doctype="Sales Order",
				reference_name=doc.name,
				posting_date=doc.transaction_date or today(),
				remarks=f"Added in revision of Sales Order {doc.name}",
				proforma_amount=flt(item.amount),
				retention_amount=flt(retention_share)
			)
		
		recalculate_ledger_for_item(item.boq_item)

	# Handle removed items
	for boq_item, existing in existing_map.items():
		frappe.db.set_value(
			"BOQ Progress Ledger",
			existing.name,
			{
				"qty": 0,
				"amount": 0,
				"proforma_amount": 0,
				"retention_amount": 0,
				"remarks": f"Removed in revision of Sales Order {doc.name}",
				"source": "Order Reversal"
			},
			update_modified=False
		)
		recalculate_ledger_for_item(boq_item)
