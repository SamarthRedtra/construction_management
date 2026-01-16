import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.model.utils.rename_field import rename_field


def execute():
	"""
	Rename the existing Purchase Invoice Data field `bill_no` to `supplier_invoice_no`
	and introduce a new `bill_no` Link field pointing to Project Bill.
	"""
	doctype = "Purchase Invoice"
	meta = frappe.get_meta(doctype)

	# 1) Rename DB column if needed (bill_no -> supplier_invoice_no)
	if frappe.db.has_column(doctype, "bill_no") and not frappe.db.has_column(doctype, "supplier_invoice_no"):
		try:
			frappe.db.sql(
				"""ALTER TABLE `tabPurchase Invoice` CHANGE COLUMN `bill_no` `supplier_invoice_no` VARCHAR(140)"""
			)
		except Exception:
			frappe.log_error("Could not rename column bill_no -> supplier_invoice_no on Purchase Invoice", "CM Patch")

	# 2) Rename DocField to supplier_invoice_no if the standard bill_no docfield exists
	if frappe.db.exists("DocField", {"parent": doctype, "fieldname": "bill_no"}):
		frappe.db.sql(
			"""UPDATE `tabDocField`
			   SET fieldname='supplier_invoice_no', label='Supplier Invoice No'
			   WHERE parent=%s AND fieldname='bill_no'""",
			(doctype,),
		)

	# 2b) Remove legacy custom fields that clash with the new naming
	# - Any custom supplier_invoice_no field (we rely on core field)
	# - Any custom bill_no that isn't the Project Bill link
	for fname in ("supplier_invoice_no", "bill_no"):
		cf = frappe.db.get_value(
			"Custom Field",
			{"dt": doctype, "fieldname": fname},
			["name", "fieldtype", "options"],
			as_dict=True,
		)
		if cf:
			is_project_bill_link = cf.fieldtype == "Link" and cf.options == "BOQ Bill"
			# Keep only the desired Project Bill link; remove everything else to avoid duplicate labels
			if fname == "bill_no" and is_project_bill_link:
				pass
			else:
				frappe.delete_doc("Custom Field", cf.name, force=1, ignore_permissions=True)

	# 3) Create new Bill No link to Project Bill if the name is free
	if not frappe.get_meta(doctype, cached=False).get_field("bill_no"):
		custom_fields = {
			doctype: [
				{
					"fieldname": "bill_no",
					"label": "Bill No",
					"fieldtype": "Link",
					"options": "BOQ Bill",
					"insert_after": "project",
				}
			]
		}
		create_custom_fields(custom_fields, update=True)

	frappe.clear_cache(doctype=doctype)
