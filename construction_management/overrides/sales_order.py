# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt, getdate, today
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
	update_ledger_entries_on_revision(doc)

	before = doc.get_doc_before_save()
	if before and _sales_order_dates_changed(before, doc):
		sync_sales_order_related_dates(doc)


def _sales_order_dates_changed(before_doc, doc):
	def _read_date(source, fieldname):
		value = source.get(fieldname) if hasattr(source, "get") else getattr(source, fieldname, None)
		return getdate(value) if value else None

	before_txn = _read_date(before_doc, "transaction_date")
	current_txn = _read_date(doc, "transaction_date")
	before_delivery = _read_date(before_doc, "delivery_date")
	current_delivery = _read_date(doc, "delivery_date")
	return before_txn != current_txn or before_delivery != current_delivery


def sync_sales_order_related_dates(doc):
	"""Keep linked BOQ ledger and unearned revenue JVs aligned with SO dates."""
	posting_date = doc.transaction_date or today()

	if frappe.db.exists("DocType", "BOQ Progress Ledger"):
		for ledger in frappe.get_all(
			"BOQ Progress Ledger",
			filters={"reference_doctype": "Sales Order", "reference_name": doc.name},
			pluck="name",
		):
			frappe.db.set_value(
				"BOQ Progress Ledger",
				ledger,
				"posting_date",
				posting_date,
				update_modified=False,
			)

	if frappe.db.has_column("Journal Entry", "custom_sales_order"):
		for jv in frappe.get_all(
			"Journal Entry",
			filters={"custom_sales_order": doc.name, "docstatus": 1},
			pluck="name",
		):
			frappe.db.set_value(
				"Journal Entry",
				jv,
				"posting_date",
				posting_date,
				update_modified=False,
			)


@frappe.whitelist()
def update_sales_order_dates(
	sales_order,
	transaction_date=None,
	delivery_date=None,
	update_item_dates=1,
):
	"""Update transaction/delivery dates on a submitted Sales Order."""
	if not sales_order:
		frappe.throw(_("Sales Order is required"))

	doc = frappe.get_doc("Sales Order", sales_order)
	if doc.docstatus != 1:
		frappe.throw(_("Only submitted Sales Orders can be updated"))

	doc.check_permission("write")

	changes = {}
	if transaction_date:
		changes["transaction_date"] = getdate(transaction_date)
	if delivery_date:
		changes["delivery_date"] = getdate(delivery_date)

	if not changes:
		frappe.throw(_("Please provide Transaction Date and/or Delivery Date"))

	new_txn = changes.get("transaction_date", doc.transaction_date)
	new_delivery = changes.get("delivery_date", doc.delivery_date)
	if new_txn and new_delivery and getdate(new_txn) > getdate(new_delivery):
		frappe.throw(_("Transaction Date cannot be after Delivery Date"))

	for field, value in changes.items():
		doc.db_set(field, value, update_modified=True)

	if int(update_item_dates):
		if "transaction_date" in changes:
			for item in doc.items:
				frappe.db.set_value(
					"Sales Order Item",
					item.name,
					"transaction_date",
					changes["transaction_date"],
					update_modified=False,
				)
		if "delivery_date" in changes:
			for item in doc.items:
				frappe.db.set_value(
					"Sales Order Item",
					item.name,
					"delivery_date",
					changes["delivery_date"],
					update_modified=False,
				)

	doc.reload()
	sync_sales_order_related_dates(doc)

	return {
		"transaction_date": str(doc.transaction_date),
		"delivery_date": str(doc.delivery_date or ""),
		"message": _("Sales Order dates updated"),
	}


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


def _build_boq_ledger_values(doc):
	"""Return cumulative BOQ values represented by a Sales Order."""
	variance_item_code = None
	company = doc.company or frappe.defaults.get_user_default("Company")
	if frappe.db.exists("BOQ Settings", company):
		variance_item_code = frappe.db.get_value("BOQ Settings", company, "varience_item")

	boq_items = {}
	global_deductions = {"retention": 0.0, "advance": 0.0, "variance": 0.0}
	item_deductions = {}
	total_boq_amount = 0.0

	for item in doc.items:
		is_retention = item.item_code == "RETENTION-DEDUCTION"
		is_advance = item.item_code == "ADVANCE-DEDUCTION"
		is_variance = variance_item_code and item.item_code == variance_item_code

		if not (is_retention or is_advance or is_variance) and item.get("boq_item"):
			values = boq_items.setdefault(
				item.boq_item,
				{"qty": 0.0, "gross_amount": 0.0, "billing_percentage": 0.0},
			)
			values["qty"] += flt(item.qty)
			values["gross_amount"] += flt(item.amount)
			values["billing_percentage"] = max(
				values["billing_percentage"], flt(item.get("custom_billing_percentage"))
			)
			total_boq_amount += flt(item.amount)
		elif is_retention or is_advance or is_variance:
			target = item.get("boq_item")
			bucket = item_deductions.setdefault(
				target, {"retention": 0.0, "advance": 0.0, "variance": 0.0}
			) if target else global_deductions
			if is_retention:
				bucket["retention"] += flt(item.amount)
			elif is_advance:
				bucket["advance"] += flt(item.amount)
			elif is_variance:
				bucket["variance"] += flt(item.amount)

	tax_rate = get_effective_tax_rate(doc)
	discount_amount = flt(getattr(doc, "discount_amount", 0))
	discount_share = discount_amount / len(boq_items) if discount_amount and boq_items else 0.0

	for boq_item, values in boq_items.items():
		deductions = item_deductions.get(
			boq_item, {"retention": 0.0, "advance": 0.0, "variance": 0.0}
		).copy()
		if total_boq_amount:
			share = values["gross_amount"] / total_boq_amount
			for fieldname in deductions:
				deductions[fieldname] += global_deductions[fieldname] * share

		base_amount = values["gross_amount"] + sum(deductions.values())
		if doc.apply_discount_on == "Net Total" and discount_share > 0:
			base_amount = max(0, base_amount - discount_share)

		net_amount = base_amount * (1 + tax_rate)
		if doc.apply_discount_on == "Grand Total" and discount_share > 0:
			net_amount = max(0, net_amount - discount_share)

		values.update({
			"amount": flt(net_amount),
			"retention": abs(flt(deductions["retention"])),
			"advance": abs(flt(deductions["advance"])),
			"variance": abs(flt(deductions["variance"])),
		})

	return boq_items


def _get_previous_cumulative_values(doc, boq_item):
	"""Get the last submitted cumulative certificate before this Sales Order."""
	previous_name = frappe.db.sql(
		"""
		SELECT so.name
		FROM `tabSales Order` so
		INNER JOIN `tabSales Order Item` soi ON soi.parent = so.name
		WHERE so.docstatus = 1
		  AND so.name != %s
		  AND soi.boq_item = %s
		  AND COALESCE(soi.custom_billing_percentage, 0) > 0
		  AND (
			so.transaction_date < %s
			OR (so.transaction_date = %s AND so.creation < %s)
		  )
		ORDER BY so.transaction_date DESC, so.creation DESC
		LIMIT 1
		""",
		(doc.name, boq_item, doc.transaction_date, doc.transaction_date, doc.creation),
	)
	if not previous_name:
		return None

	previous_doc = frappe.get_doc("Sales Order", previous_name[0][0])
	return _build_boq_ledger_values(previous_doc).get(boq_item)


def _as_incremental_values(doc, boq_item, values):
	"""Convert cumulative certificate values into this period's movement."""
	result = values.copy()
	if flt(values.get("billing_percentage")) <= 0:
		return result

	previous = _get_previous_cumulative_values(doc, boq_item)
	if not previous:
		return result

	for fieldname in ("qty", "amount", "retention", "advance", "variance"):
		result[fieldname] = flt(values.get(fieldname)) - flt(previous.get(fieldname))
	return result



def create_ledger_entries(doc):
	"""
	Create BOQ Progress Ledger entries for each item in the Sales Order.
	Aggregates multiple lines for the same BOQ item to avoid overwriting.
	Matches logic from Sales Invoice for deduction allocation.
	"""
	if not frappe.db.exists("DocType", "BOQ Progress Ledger"):
		return

	boq_items_map = _build_boq_ledger_values(doc)
	for boq_item, cumulative_values in boq_items_map.items():
		try:
			data = _as_incremental_values(doc, boq_item, cumulative_values)
			
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
				"amount": flt(data["amount"]),
				"proforma_amount": flt(data["amount"]),
				"retention_amount": flt(data["retention"]),
				"advance_deduction": flt(data["advance"]),
				"variance": flt(data["variance"]),
				"percentage": flt(cumulative_values["billing_percentage"]),
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
					amount=flt(data["amount"]),
					source="Order",
					percentage=flt(cumulative_values["billing_percentage"]),
					reference_doctype="Sales Order",
					reference_name=doc.name,
					posting_date=doc.transaction_date or today(),
					remarks=f"Sales Order {doc.name}",
					proforma_amount=flt(data["amount"]),
					retention_amount=flt(data["retention"]),
					advance_deduction=flt(data["advance"]),
					variance=flt(data["variance"])
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
	"""Resync a submitted Sales Order and clear rows removed by the revision."""
	existing_entries = frappe.get_all(
		"BOQ Progress Ledger",
		filters={
			"reference_doctype": "Sales Order",
			"reference_name": doc.name
		},
		fields=["name", "boq_item"]
	)
	existing_map = {entry.boq_item: entry for entry in existing_entries}
	current_boq_items = set(_build_boq_ledger_values(doc))

	create_ledger_entries(doc)

	# Handle removed items
	for boq_item in set(existing_map) - current_boq_items:
		existing = existing_map[boq_item]
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
