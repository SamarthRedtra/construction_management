import frappe
from frappe.utils import flt, today
from construction_management.api.boq_invoice import create_invoice_from_boq_item
from construction_management.api.boq_ledger import recalculate_ledger_for_item

def setup_test_data():
	"""Setup Project, BOQ Item, and Tax Template"""
	# Setup Company
	company = frappe.db.get_value("Company", {}, "name")
	
	# Setup Tax Template
	tax_template_name = "Test Tax 5%"
	if not frappe.db.exists("Sales Taxes and Charges Template", tax_template_name):
		tax_template = frappe.new_doc("Sales Taxes and Charges Template")
		tax_template.title = tax_template_name
		tax_template.company = company
		tax_template.append("taxes", {
			"charge_type": "On Net Total",
			"account_head": frappe.db.get_value("Account", {"account_type": "Tax", "company": company}, "name"),
			"description": "Test Tax @ 5%",
			"rate": 5.0
		})
		tax_template.insert()
	
	# Setup Project
	project_title = "Test BOQ Tax Calculation Project"
	project_id = frappe.db.get_value("Project", {"project_name": project_title}, "name")
	
	if not project_id:
		project = frappe.new_doc("Project")
		project.project_name = project_title
		project.status = "Open"
		project.customer = frappe.db.get_value("Customer", {}, "name") or "Test Customer"
		project.company = company
		project.insert()
		project_id = project.name
	
	project = frappe.get_doc("Project", project_id)
	
	# Setup BOQ Item
	boq_item_description = "Test BOQ Tax Calculation Item"
	item = frappe.get_all("BOQ Item", filters={"description": boq_item_description}, limit=1)
	if not item:
		# Create Project BOQ
		project_boq = frappe.new_doc("Project BOQ")
		project_boq.project = project.name
		project_boq.boq_name = "Test BOQ Tax"
		project_boq.status = "Draft"
		project_boq.insert()

		boq_bill = frappe.new_doc("BOQ Bill")
		boq_bill.bill_no = "B-TAX-001"
		boq_bill.project = project.name
		boq_bill.project_boq = project_boq.name
		boq_bill.insert()
		
		item = frappe.new_doc("BOQ Item")
		item.description = boq_item_description
		item.project = project.name
		item.project_boq = project_boq.name
		item.parent_bill = boq_bill.name
		item.total_qty = 100
		item.rate = 100  # 10,000 total value
		item.unit = "Nos"
		item.insert()
	else:
		item = frappe.get_doc("BOQ Item", item[0].name)
		
	return project, item, tax_template_name, company


def test_boq_tax_on_adjusted_amount():
	"""
	Test that tax is calculated on the adjusted amount (after deductions), not gross amount.
	
	Scenario:
	- BOQ item amount: 3000 (30 qty × 100 rate)
	- Variance: -500
	- Advance: -200
	- Retention: -300
	- Expected base for tax: 3000 - 500 - 200 - 300 = 2000
	- Tax @ 5%: 2000 × 0.05 = 100
	- Expected total: 2000 + 100 = 2100
	"""
	print("\n--- Testing BOQ Tax Calculation on Adjusted Amount ---")
	project, boq_item, tax_template_name, company = setup_test_data()
	
	# Get variance item
	variance_item_code = frappe.db.get_value("BOQ Settings", company, "varience_item")
	if not variance_item_code:
		print("WARNING: Variance item not configured in BOQ Settings")
		variance_item_code = None
	
	# Create Sales Invoice
	si = frappe.new_doc("Sales Invoice")
	si.customer = project.customer
	si.project = project.name
	si.company = company
	si.posting_date = today()
	si.due_date = today()
	si.taxes_and_charges = tax_template_name
	
	# Add default cost center
	default_cost_center = frappe.db.get_value("Company", company, "cost_center")
	
	# Main BOQ Item (3000)
	si.append("items", {
		"item_code": boq_item.linked_item,
		"qty": 30,
		"rate": 100,
		"boq_item": boq_item.name,
		"income_account": frappe.db.get_value("Company", company, "default_income_account"),
		"cost_center": default_cost_center
	})
	
	# Variance (-500)
	if variance_item_code:
		si.append("items", {
			"item_code": variance_item_code,
			"qty": 1,
			"rate": -500,
			"boq_item": boq_item.name,
			"income_account": frappe.db.get_value("Company", company, "default_income_account"),
			"cost_center": default_cost_center
		})
	
	# Advance (-200)
	si.append("items", {
		"item_code": "ADVANCE-DEDUCTION",
		"qty": 1,
		"rate": -200,
		"boq_item": boq_item.name,
		"income_account": frappe.db.get_value("Company", company, "default_income_account"),
		"cost_center": default_cost_center
	})
	
	# Retention (-300)
	si.append("items", {
		"item_code": "RETENTION-DEDUCTION",
		"qty": 1,
		"rate": -300,
		"boq_item": boq_item.name,
		"income_account": frappe.db.get_value("Company", company, "default_income_account"),
		"cost_center": default_cost_center
	})
	
	# Set taxes
	si.append("taxes", {
		"charge_type": "On Net Total",
		"account_head": frappe.db.get_value("Account", {"account_type": "Tax", "company": company}, "name"),
		"description": "Test Tax @ 5%",
		"rate": 5.0
	})
	
	# Calculate totals
	si.calculate_taxes_and_totals()
	
	print(f"\nSales Invoice Items:")
	for item in si.items:
		print(f"  - {item.item_code}: Qty={item.qty}, Rate={item.rate}, Amount={item.amount}")
	
	print(f"\nNet Total (before tax): {si.net_total}")
	print(f"Total Tax: {si.total_taxes_and_charges}")
	print(f"Grand Total: {si.grand_total}")
	
	# Submit invoice
	si.submit()
	print(f"\nSales Invoice {si.name} submitted")
	
	# Check BOQ Progress Ledger
	ledger_entry = frappe.db.get_value(
		"BOQ Progress Ledger",
		{"boq_item": boq_item.name, "tax_invoice": si.name},
		["amount", "retention_amount", "advance_deduction", "variance"],
		as_dict=True
	)
	
	if ledger_entry:
		print(f"\nBOQ Progress Ledger Entry:")
		print(f"  - Amount: {ledger_entry.amount}")
		print(f"  - Retention: {ledger_entry.retention_amount}")
		print(f"  - Advance: {ledger_entry.advance_deduction}")
		print(f"  - Variance: {ledger_entry.variance}")
		
		# Calculate expected values
		base_amount = 3000 - 500 - 200 - 300  # 2000
		expected_tax = base_amount * 0.05  # 100
		expected_total = base_amount + expected_tax  # 2100
		
		print(f"\nExpected Calculation:")
		print(f"  - Base (3000 - 500 - 200 - 300): {base_amount}")
		print(f"  - Tax @ 5% on base: {expected_tax}")
		print(f"  - Expected Total: {expected_total}")
		
		# Verify
		tolerance = 0.01
		if abs(ledger_entry.amount - expected_total) < tolerance:
			print(f"\n✓ SUCCESS: BOQ ledger amount ({ledger_entry.amount}) matches expected ({expected_total})")
			return True
		else:
			print(f"\n✗ FAILURE: BOQ ledger amount ({ledger_entry.amount}) does not match expected ({expected_total})")
			return False
	else:
		print("\n✗ FAILURE: No BOQ Progress Ledger entry found")
		return False


def run_tests():
	try:
		success = test_boq_tax_on_adjusted_amount()
		return success
	finally:
		frappe.db.rollback()

if __name__ == "__main__":
	run_tests()
