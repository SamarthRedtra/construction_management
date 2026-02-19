# Copyright (c) 2026, Construction Management
# License: MIT
# Patch: Enable is_purchase_item on RETENTION-DEDUCTION and ADVANCE-DEDUCTION items

import frappe


def execute():
	"""Mark RETENTION-DEDUCTION and ADVANCE-DEDUCTION items as purchase items"""
	for item_code in ("RETENTION-DEDUCTION", "ADVANCE-DEDUCTION", "PURCHASE-ADVANCE"):
		if frappe.db.exists("Item", item_code):
			frappe.db.set_value("Item", item_code, "is_purchase_item", 1)

	frappe.db.commit()
