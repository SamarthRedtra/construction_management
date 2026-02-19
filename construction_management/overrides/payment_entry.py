# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from construction_management.overrides.sales_invoice import create_boq_advance_payment_from_invoice

def on_submit(doc, method):
	"""Handle Payment Entry submission to check for linked advance invoices"""
	for ref in doc.get("references"):
		if ref.reference_doctype == "Sales Invoice":
			# Get the latest state of the invoice
			si = frappe.get_doc("Sales Invoice", ref.reference_name)
			
			# Check if it's an advance invoice and if it's now Paid
			# Payment Entry updates invoice status to "Paid" via db_set in Frappe,
			# but si.status should reflect the current database state if fetched now.
			if si.get("custom_is_advanced") and si.status == "Paid" and si.docstatus == 1:
				create_boq_advance_payment_from_invoice(si)

		elif ref.reference_doctype == "Purchase Invoice":
			# Get the latest state of the purchase invoice
			pi = frappe.get_doc("Purchase Invoice", ref.reference_name)

			# Check if it's an advance purchase invoice and if it's now Paid
			if pi.get("custom_is_advance") and pi.status == "Paid" and pi.docstatus == 1:
				from construction_management.overrides.purchase_invoice import (
					_is_subcontractor_purchase,
					create_purchase_advance_payment,
				)
				if _is_subcontractor_purchase(pi):
					create_purchase_advance_payment(pi)
