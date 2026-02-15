import frappe


def execute():
	from construction_management.setup.install import setup_advanced_general_ledger

	setup_advanced_general_ledger()
	frappe.db.commit()
