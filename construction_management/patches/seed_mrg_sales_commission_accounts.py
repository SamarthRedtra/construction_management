# Copyright (c) 2026, Construction Management
# License: MIT

"""Seed MRG BOQ Settings sales commission expense + payable accounts."""

import frappe

MRG_COMPANY = "M R G INSULATION WORKS L.L.C"
EXPENSE_ACCOUNT = "Sales commission Project - MRG"
PAYABLE_ACCOUNT = "Sales Commission Payable - MRG"


def execute():
	if not frappe.db.exists("Company", MRG_COMPANY):
		print(f"Skip MRG commission seed: company {MRG_COMPANY} not found")
		return

	if not frappe.db.exists("DocType", "BOQ Settings"):
		print("Skip MRG commission seed: BOQ Settings missing")
		return

	if not frappe.db.exists("Account", EXPENSE_ACCOUNT):
		print(f"Skip MRG commission seed: account {EXPENSE_ACCOUNT} not found")
		return
	if not frappe.db.exists("Account", PAYABLE_ACCOUNT):
		print(f"Skip MRG commission seed: account {PAYABLE_ACCOUNT} not found")
		return

	if not frappe.db.exists("BOQ Settings", MRG_COMPANY):
		from construction_management.construction_management.doctype.boq_settings.boq_settings import (
			create_default_boq_settings,
		)

		create_default_boq_settings(MRG_COMPANY)

	values = {
		"sales_person_commission_account": EXPENSE_ACCOUNT,
		"sales_commission_payable_account": PAYABLE_ACCOUNT,
	}
	# Always set known MRG accounts when they exist (idempotent).
	frappe.db.set_value("BOQ Settings", MRG_COMPANY, values, update_modified=False)
	frappe.db.commit()
	print(
		f"Seeded BOQ Settings commission accounts for {MRG_COMPANY}: "
		f"{EXPENSE_ACCOUNT} / {PAYABLE_ACCOUNT}"
	)
