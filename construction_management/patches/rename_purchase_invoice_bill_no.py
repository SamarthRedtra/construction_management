import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.model.utils.rename_field import rename_field


def execute():
	"""
	Rename the existing Purchase Invoice Data field `bill_no` to `supplier_invoice_no`
	and introduce a new `bill_no` Link field pointing to Project Bill.
	"""
	meta = frappe.get_meta("Purchase Invoice")
	bill_df = meta.get_field("bill_no")
	supplier_df = meta.get_field("supplier_invoice_no")

	# Try to free up bill_no by renaming only if it still exists and supplier_invoice_no is absent
	if bill_df and not supplier_df:
		try:
			if frappe.db.has_column("Purchase Invoice", "bill_no") and not frappe.db.has_column("Purchase Invoice", "supplier_invoice_no"):
				rename_field("Purchase Invoice", "bill_no", "supplier_invoice_no")
				meta = frappe.get_meta("Purchase Invoice")  # refresh
				bill_df = meta.get_field("bill_no")
		except Exception:
			# If rename fails (e.g., already moved/removed), log and continue without breaking migration
			frappe.log_error("Could not rename Purchase Invoice.bill_no to supplier_invoice_no", "CM Patch: rename_purchase_invoice_bill_no")

	# Ensure the new Bill No (Project Bill) link exists only if the name is free
	custom_fields = {
		"Purchase Invoice": [
			{
				"fieldname": "bill_no",
				"label": "Bill No",
				"fieldtype": "Link",
				"options": "Project Bill",
				"insert_after": "project"
			}
		]
	}

	if not frappe.get_meta("Purchase Invoice").get_field("bill_no"):
		create_custom_fields(custom_fields, update=True)

	frappe.clear_cache(doctype="Purchase Invoice")
