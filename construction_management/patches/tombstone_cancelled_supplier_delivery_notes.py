# Copyright (c) 2026, Construction Management
# License: MIT

"""Free Supplier DO No. values locked on cancelled Purchase Receipts."""

from __future__ import annotations

import frappe

from construction_management.api.controlled_procurement import SUPPLIER_DO_CANCELLED_MARKER


def execute():
	rows = frappe.db.sql(
		"""
		SELECT name, supplier_delivery_note
		FROM `tabPurchase Receipt`
		WHERE docstatus = 2
			AND IFNULL(supplier_delivery_note, '') != ''
			AND supplier_delivery_note NOT LIKE %s
		""",
		(f"%{SUPPLIER_DO_CANCELLED_MARKER}%",),
		as_dict=True,
	)
	updated = 0
	for row in rows:
		tombstone = f"{row.supplier_delivery_note}{SUPPLIER_DO_CANCELLED_MARKER}{row.name}"
		# Skip if another row already holds this tombstone (should not happen).
		if frappe.db.exists("Purchase Receipt", {"supplier_delivery_note": tombstone, "name": ["!=", row.name]}):
			tombstone = f"{tombstone}-{updated}"
		frappe.db.set_value(
			"Purchase Receipt",
			row.name,
			"supplier_delivery_note",
			tombstone,
			update_modified=False,
		)
		updated += 1
	print(f"Tombstoned supplier_delivery_note on {updated} cancelled Purchase Receipt(s)")
