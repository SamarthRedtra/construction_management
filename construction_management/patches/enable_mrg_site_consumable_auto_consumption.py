"""Turn on site auto-consumption of controlled Consumables for MRG only."""

import frappe

from construction_management.setup.install import create_warehouse_custom_fields

MRG_COMPANY = "M R G INSULATION WORKS L.L.C"
SKIP_FIELD = "custom_skip_auto_consumption_for_consumables"
NON_SITE_WAREHOUSES = (
	"Stores - MRG",
	"Goods In Transit - MRG",
	"Work In Progress - MRG",
	"Finished Goods - MRG",
)


def execute():
	if not frappe.db.exists("Company", MRG_COMPANY) or not frappe.db.exists("BOQ Settings", MRG_COMPANY):
		return
	create_warehouse_custom_fields()
	frappe.clear_cache(doctype="Warehouse")
	for warehouse in _non_site_warehouses():
		frappe.db.set_value("Warehouse", warehouse, SKIP_FIELD, 1, update_modified=False)
	frappe.db.set_value(
		"BOQ Settings", MRG_COMPANY, "auto_consume_consumables_at_site", 1, update_modified=False
	)


def _non_site_warehouses() -> set[str]:
	names = set(NON_SITE_WAREHOUSES)
	default_warehouse = frappe.db.get_value("BOQ Settings", MRG_COMPANY, "default_warehouse")
	if default_warehouse:
		names.add(default_warehouse)
	return set(frappe.get_all(
		"Warehouse",
		filters={"name": ["in", list(names)], "company": MRG_COMPANY},
		pluck="name",
	))
