"""Make "UAE VAT Exempted" Item Tax Templates charge 0% on the standard VAT account.

ERPNext builds each line's tax map from the header taxes plus the line's Item Tax Template. The
Exempted template only listed the "VAT Exempted" account, so an exempt line inside a 5% order was
still charged 5%. Adding the company's standard VAT account at 0% makes exempt lines tax-free while
keeping them tagged Exempt for VAT reporting.
"""

import frappe


def execute():
	for template in frappe.get_all(
		"Item Tax Template", filters={"title": ["like", "%VAT%Exempt%"]}, fields=["name", "company"]
	):
		standard = frappe.db.get_value(
			"Purchase Taxes and Charges Template",
			{"company": template.company, "is_default": 1},
			"name",
		)
		if not standard:
			continue
		accounts = frappe.get_all(
			"Purchase Taxes and Charges", filters={"parent": standard, "rate": [">", 0]}, pluck="account_head"
		)
		doc = frappe.get_doc("Item Tax Template", template.name)
		existing = {row.tax_type for row in doc.taxes}
		missing = [account for account in accounts if account not in existing]
		if not missing:
			continue
		for account in missing:
			doc.append("taxes", {"tax_type": account, "tax_rate": 0})
		doc.save(ignore_permissions=True)
