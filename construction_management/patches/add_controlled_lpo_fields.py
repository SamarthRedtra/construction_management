"""Install LPO metadata without changing historical document status."""

import frappe

from construction_management.setup.install import create_lpo_fields


def execute():
	create_lpo_fields()
	frappe.clear_cache(doctype="Purchase Order")
	if frappe.get_meta("Purchase Order").has_field("custom_is_provisional_po"):
		frappe.db.sql("""update `tabPurchase Order`
			set custom_lpo_type = 'Open'
			where custom_is_provisional_po = 1 and coalesce(custom_lpo_type, 'Standard') = 'Standard'""")
