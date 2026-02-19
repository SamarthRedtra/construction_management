# Copyright (c) 2026, Construction Management
# License: MIT
# Patch: Ensure deduction and advance items exist and are purchase-enabled

import frappe


def execute():
	"""Create deduction/advance items if missing, mark all as purchase-enabled"""
	items = [
		("RETENTION-DEDUCTION", "Retention Deduction", "Retention amount deducted from purchase invoices"),
		("ADVANCE-DEDUCTION", "Advance Deduction", "Advance payment deducted from purchase invoices"),
		("PURCHASE-ADVANCE", "Purchase Advance", "Advance payment to supplier/subcontractor"),
	]

	for item_code, item_name, description in items:
		if frappe.db.exists("Item", item_code):
			frappe.db.set_value("Item", item_code, "is_purchase_item", 1)
		else:
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

	frappe.db.commit()
