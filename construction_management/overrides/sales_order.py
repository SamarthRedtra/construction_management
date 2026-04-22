# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt, today
from construction_management.api.boq_ledger import create_ledger_entry, recalculate_ledger_for_item
from construction_management.overrides.unearned_revenue import create_so_unearned_revenue_jv


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
	create_so_unearned_revenue_jv(doc)


def on_cancel(doc, method=None):
	# When Sales Order is cancelled, reverse or delete BOQ Progress Ledger entries.
	# Skip if this is an amendment (the new revision will update these entries)
	if doc.flags.get("is_amending"):
		return

	# Check if linked to Payment Certificate
	if frappe.db.exists("Payment Certificate", {"sales_order": doc.name, "docstatus": ["!=", 2]}):
		frappe.throw(_("Cannot cancel Sales Order {0} as it is linked to a Payment Certificate").format(doc.name))
	
	# Check if any Sales Invoice has been created against this Sales Order
	# We check Sales Invoice Item for the link to this SO
	has_invoice = frappe.db.exists("Sales Invoice Item", {"sales_order": doc.name, "docstatus": ["!=", 2]})
	
	if not has_invoice:
		# If no invoice exists, delete the ledger entries entirely
		delete_ledger_entries(doc)
	else:
		# If invoice exists, just zero out the values (reversal)
		create_reversing_ledger_entries(doc)


def on_trash(doc, method=None):
	"""
	When Sales Order is deleted, ensure all linked BOQ Progress Ledger entries are removed.
	"""
	delete_ledger_entries(doc)


def on_update_after_submit(doc, method=None):
	"""
	Handle revisions to submitted Sales Order.
	"""
	# calculate_retention_and_net_amount(doc)
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


def get_item_tax_amount(doc, item):
	"""Extract tax amount for a specific item from item_wise_tax_details child table"""
	if not doc.get("item_wise_tax_details"):
		return 0
	
	total_tax = 0
	for detail in doc.item_wise_tax_details:
		if detail.item_row == item.name:
			total_tax += flt(detail.amount)
	
	return total_tax


def get_effective_tax_rate(doc):
	"""Extract effective tax rate from taxes table"""
	if not doc.get("taxes"):
		return 0
	
	total_tax_rate = 0
	for tax_row in doc.taxes:
		if tax_row.rate:
			total_tax_rate += flt(tax_row.rate)
	
	return total_tax_rate / 100  # Convert percentage to decimal



def create_ledger_entries(doc):
	"""
	Create BOQ Progress Ledger entries for each item in the Sales Order.
	Aggregates multiple lines for the same BOQ item to avoid overwriting.
	Matches logic from Sales Invoice for deduction allocation.
	"""
	if not frappe.db.exists("DocType", "BOQ Progress Ledger"):
		return

	# 1. First Pass: Identify variance item code and total gross BOQ amount
	variance_item_code = None
	company = doc.company or frappe.defaults.get_user_default("Company")
	if frappe.db.exists("BOQ Settings", company):
		variance_item_code = frappe.db.get_value("BOQ Settings", company, "varience_item")
		
	# Buckets for allocation
	boq_items_map = {} # {boq_item: {qty, amount, billing_percentage, tax, doc_item}} 
	global_deductions = {
		"retention": 0,
		"advance": 0,
		"variance": 0
	}
	item_specific_deductions = {} # {boq_item_id: {"retention": 0, "advance": 0, "variance": 0}}
	
	total_boq_amount = 0

	for item in doc.items:
		is_retention = item.item_code == "RETENTION-DEDUCTION"
		is_advance = item.item_code == "ADVANCE-DEDUCTION"
		is_variance = variance_item_code and item.item_code == variance_item_code
		
		if not (is_retention or is_advance or is_variance) and item.get("boq_item"):
			# Aggregate main BOQ items
			boq_id = item.boq_item
			if boq_id not in boq_items_map:
				boq_items_map[boq_id] = {
					"qty": 0.0,
					"amount": 0.0,
					"billing_percentage": 0.0
				}
			
			boq_items_map[boq_id]["qty"] += flt(item.qty)
			boq_items_map[boq_id]["amount"] += flt(item.amount)
			boq_items_map[boq_id]["billing_percentage"] = max(
				boq_items_map[boq_id]["billing_percentage"], 
				flt(item.get("custom_billing_percentage", 0))
			)
			
			total_boq_amount += flt(item.amount)
			
		elif (is_retention or is_advance or is_variance):
			target_boq_item = item.get("boq_item")
			val = flt(item.amount) # Deductions are usually negative in rate/amount
			
			if target_boq_item:
				if target_boq_item not in item_specific_deductions:
					item_specific_deductions[target_boq_item] = {"retention": 0, "advance": 0, "variance": 0}
				
				if is_retention: item_specific_deductions[target_boq_item]["retention"] += val
				if is_advance: item_specific_deductions[target_boq_item]["advance"] += val
				if is_variance: item_specific_deductions[target_boq_item]["variance"] += val
			else:
				if is_retention: global_deductions["retention"] += val
				if is_advance: global_deductions["advance"] += val
				if is_variance: global_deductions["variance"] += val

	# 2. Second Pass: Create ledger entries with combined deductions
	# Get tax rate once for all items
	tax_rate = get_effective_tax_rate(doc)
	discount_amount = flt(getattr(doc, "discount_amount", 0))
	discount_share = 0
	if discount_amount > 0 and boq_items_map:
		discount_share = discount_amount / len(boq_items_map)
	
	for boq_item, data in boq_items_map.items():
		try:
			gross_amount = flt(data["amount"])
			
			# Specific deductions
			spec = item_specific_deductions.get(boq_item, {"retention": 0, "advance": 0, "variance": 0})
			
			# Pro-rated global deductions
			allocated = {"retention": 0, "advance": 0, "variance": 0}
			if total_boq_amount > 0:
				share = gross_amount / total_boq_amount
				allocated["retention"] = global_deductions["retention"] * share
				allocated["advance"] = global_deductions["advance"] * share
				allocated["variance"] = global_deductions["variance"] * share
			
			# Total deductions for this item (Values are usually negative)
			item_retention = spec["retention"] + allocated["retention"]
			item_advance = spec["advance"] + allocated["advance"]
			item_variance = spec["variance"] + allocated["variance"]
			
			# Calculate base amount (after deductions)
			# (Deductions are negative, so adding them reduces the amount)
			base_amount = gross_amount + item_retention + item_advance + item_variance
			
			# Apply additional discount evenly across BOQ items
			if doc.apply_discount_on == "Net Total"  and discount_share > 0:
				base_amount = max(0, base_amount - discount_share)
			
			
			# Calculate tax on the adjusted base amount
			item_tax = base_amount * tax_rate
			
			# Final BOQ Value = Base Amount + Tax (calculated on adjusted amount)
			net_amount = base_amount + item_tax

			if doc.apply_discount_on == "Grand Total" and discount_share > 0:
				net_amount = max(0, net_amount - discount_share)
			
			# Create or update ledger entry
			ledger_entry = None
			
			# Case 1: Amendment - Try to find entry from the original SO
			if doc.amended_from:
				ledger_entry = frappe.db.get_value(
					"BOQ Progress Ledger",
					{
						"boq_item": boq_item,
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
						"boq_item": boq_item,
						"reference_doctype": "Sales Order",
						"reference_name": doc.name
					},
					"name"
				)

			update_data = {
				"qty": flt(data["qty"]),
				"amount": flt(net_amount),
				"proforma_amount": flt(net_amount), # Using net amount as the tracked amount
				"retention_amount": abs(item_retention),
				"advance_deduction": abs(item_advance),
				"variance": abs(item_variance),
				"percentage": flt(data["billing_percentage"]),
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
					boq_item=boq_item,
					qty=flt(data["qty"]),
					amount=flt(net_amount),
					source="Order",
					percentage=flt(data["billing_percentage"]),
					reference_doctype="Sales Order",
					reference_name=doc.name,
					posting_date=doc.transaction_date or today(),
					remarks=f"Sales Order {doc.name}",
					proforma_amount=flt(net_amount),
					retention_amount=abs(item_retention),
					advance_deduction=abs(item_advance),
					variance=abs(item_variance)
				)

			recalculate_ledger_for_item(boq_item)
		except Exception as e:
			frappe.log_error(
				f"Error creating ledger for Sales Order {doc.name}, Item {boq_item}: {str(e)}",
				"Sales Order Ledger Error"
			)
			raise


def create_reversing_ledger_entries(doc):
	"""
	Reverse BOQ Progress Ledger entries when Sales Order is cancelled.
	Zeroes out the entries to maintain a trace that the order existed but was cancelled.
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


def delete_ledger_entries(doc):
	"""
	Permanently delete BOQ Progress Ledger entries related to this Sales Order.
	Used when cancelling an SO with no invoices, or when deleting an SO.
	"""
	ledger_entries = frappe.get_all(
		"BOQ Progress Ledger",
		filters={
			"reference_doctype": "Sales Order",
			"reference_name": doc.name
		},
		fields=["name", "boq_item"]
	)

	items_to_recalculate = set()
	frappe.flags.allow_boq_ledger_deletion = True
	try:
		for entry in ledger_entries:
			items_to_recalculate.add(entry.boq_item)
			frappe.delete_doc("BOQ Progress Ledger", entry.name, ignore_permissions=True, force=True)
	finally:
		frappe.flags.allow_boq_ledger_deletion = False

	for boq_item in items_to_recalculate:
		recalculate_ledger_for_item(boq_item)


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
