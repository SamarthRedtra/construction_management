# Copyright (c) 2026, Construction Management
# License: MIT

"""Add Controlled Catalog Check on Purchase Order Item and backfill from Item."""

from __future__ import annotations

import frappe

from construction_management.setup.install import create_custom_field_if_not_exists


def execute():
	create_custom_field_if_not_exists({
		"dt": "Purchase Order Item",
		"fieldname": "controlled_procurement_catalog",
		"label": "Controlled Catalog",
		"fieldtype": "Check",
		"insert_after": "controlled_item_type",
		"fetch_from": "item_code.controlled_procurement_catalog",
		"read_only": 1,
		"in_list_view": 1,
		"description": "Item is in the controlled procurement catalogue",
	})
	# Sync DB column from Custom Field definition.
	frappe.db.updatedb("Purchase Order Item")
	if not frappe.db.has_column("Purchase Order Item", "controlled_procurement_catalog"):
		from frappe.database.schema import add_column

		add_column("Purchase Order Item", "controlled_procurement_catalog", "Check")

	frappe.db.sql("""
		UPDATE `tabPurchase Order Item` poi
		INNER JOIN `tabItem` item ON item.name = poi.item_code
		SET poi.controlled_procurement_catalog = IFNULL(item.controlled_procurement_catalog, 0)
	""")
	frappe.clear_cache(doctype="Purchase Order")
	frappe.clear_cache(doctype="Purchase Order Item")
	print("Purchase Order Item.controlled_procurement_catalog created and backfilled")
