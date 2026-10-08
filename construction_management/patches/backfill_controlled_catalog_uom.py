"""Keep older catalog requests valid after adding their stock UOM field."""

import frappe


def execute():
	if not frappe.db.has_column("Controlled Catalog Request Item", "stock_uom"):
		return
	frappe.db.sql("""
		UPDATE `tabControlled Catalog Request Item` request_item
		LEFT JOIN `tabItem` item ON item.name = request_item.result_item
		SET request_item.stock_uom = COALESCE(NULLIF(item.stock_uom, ''), 'Nos')
		WHERE request_item.stock_uom IS NULL OR request_item.stock_uom = ''
	""")
