# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt


def on_submit(doc, method):
	"""Update cost tracking for BOQ items from Purchase Invoice"""
	for item in doc.items:
		if item.get("boq_item"):
			update_boq_item_cost(item)


def on_cancel(doc, method):
	"""Reverse cost tracking for BOQ items on Purchase Invoice cancel"""
	for item in doc.items:
		if item.get("boq_item"):
			# Cost tracking is done via DPR, not directly from Purchase Invoice
			# This hook is for future enhancement if needed
			pass


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
