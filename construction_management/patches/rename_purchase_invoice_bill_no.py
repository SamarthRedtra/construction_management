import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.model.utils.rename_field import rename_field


def execute():
	"""
	Rename the existing Purchase Invoice Data field `bill_no` to `supplier_invoice_no`
	and introduce a new `bill_no` Link field pointing to Project Bill.
	"""
	# Rename core field only once
	if frappe.db.has_column("Purchase Invoice", "bill_no") and not frappe.db.has_column("Purchase Invoice", "supplier_invoice_no"):
		rename_field("Purchase Invoice", "bill_no", "supplier_invoice_no")

	# Ensure the new Bill No (Project Bill) link exists
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

	create_custom_fields(custom_fields, update=True)
	frappe.clear_cache(doctype="Purchase Invoice")
