import frappe
from frappe.utils import flt

def execute():
	"""
	Patch to create BOQ Advance Payment records for all existing Payment Entries 
	linked to Advance Sales Invoices.
	"""
	# 1. Find all Advance Sales Invoices (Submitted)
	advance_invoices = frappe.get_all("Sales Invoice", filters={
		"custom_is_advanced": 1,
		"docstatus": 1
	}, fields=["name", "project", "base_net_total", "base_grand_total"])

	print(f"Found {len(advance_invoices)} advance invoices to process.")

	for si in advance_invoices:
		# Calculate net/gross ratio to get the net portion of each payment
		if flt(si.base_grand_total) <= 0:
			continue
		ratio = flt(si.base_net_total) / flt(si.base_grand_total)

		# 2. Find all Payment Entries referencing this invoice
		payments = frappe.db.sql("""
			SELECT 
				per.parent as pe_name, 
				per.allocated_amount,
				pe.posting_date,
				pe.project
			FROM `tabPayment Entry Reference` per
			JOIN `tabPayment Entry` pe ON pe.name = per.parent
			WHERE per.reference_name = %s 
			AND pe.docstatus = 1
		""", si.name, as_dict=True)

		for pay in payments:
			# Check if a BOQ Advance Payment already exists for this Payment Entry + Invoice combo
			# We'll use the 'reference' field to store the Payment Entry name
			if frappe.db.exists("BOQ Advance Payment", {
				"linked_invoice": si.name,
				"reference": pay.pe_name,
				"docstatus": ["!=", 2]
			}):
				continue

			# Calculate the net portion of the allocated amount
			net_amount = flt(flt(pay.allocated_amount) * ratio, 2)

			if net_amount > 0:
				adv = frappe.new_doc("BOQ Advance Payment")
				adv.project = pay.project or si.project
				adv.amount = net_amount
				adv.linked_invoice = si.name
				adv.reference = pay.pe_name
				adv.date = pay.posting_date
				adv.remarks = f"Automatically created from Payment Entry {pay.pe_name} for Advance Invoice {si.name}"
				
				adv.flags.ignore_permissions = True
				adv.insert()
				adv.submit()
				print(f"  - Created {adv.name} for PE {pay.pe_name} (Amount: {net_amount})")

	frappe.db.commit()
