import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	doctype = "Purchase Invoice"

	# Ensure DB column uses supplier_invoice_no
	if frappe.db.has_column(doctype, "bill_no") and not frappe.db.has_column(doctype, "supplier_invoice_no"):
		try:
			frappe.db.sql(
				"""ALTER TABLE `tabPurchase Invoice` CHANGE COLUMN `bill_no` `supplier_invoice_no` VARCHAR(140)"""
			)
		except Exception:
			frappe.log_error("Could not rename column bill_no -> supplier_invoice_no on Purchase Invoice", "CM Patch Cleanup")

	# Ensure the DocField name/label is supplier_invoice_no (core data field)
	if frappe.db.exists("DocField", {"parent": doctype, "fieldname": "bill_no"}):
		frappe.db.sql(
			"""UPDATE `tabDocField`
			   SET fieldname='supplier_invoice_no', label='Supplier Invoice No'
			   WHERE parent=%s AND fieldname='bill_no'""",
			(doctype,),
		)

	# # Remove clashing custom fields (supplier_invoice_no or bill_no not meant for Project Bill link)
	# for fname in ("supplier_invoice_no", "bill_no"):
	# 	customs = frappe.get_all(
	# 		"Custom Field",
	# 		filters={"dt": doctype, "fieldname": fname},
	# 		fields=["name", "fieldtype", "options"],
	# 	)
	# 	for cf in customs:
	# 		is_project_bill_link = cf.fieldtype == "Link" and (cf.options == "Project Bill" or cf.options == "BOQ Bill")
	# 		if fname == "bill_no" and is_project_bill_link:
	# 			continue
	# 		frappe.delete_doc("Custom Field", cf.name, force=1, ignore_permissions=True)

	# # 3) Create new Bill No link to Project Bill if the name is free
	# if not frappe.get_meta(doctype, cached=False).get_field("bill_no"):
	# 	custom_fields = {
	# 		doctype: [
	# 			{
	# 				"fieldname": "bill_no",
	# 				"label": "Project Bill",
	# 				"fieldtype": "Link",
	# 				"options": "BOQ Bill",
	# 				"insert_after": "supplier_invoice_no",
	# 			}
	# 		]
	# 	}
	# 	create_custom_fields(custom_fields, update=True)
	# else:
	# 	# Normalize existing Project Bill link so it actually shows up on the form
	# 	custom_bill_no = frappe.get_all(
	# 		"Custom Field",
	# 		filters={"dt": doctype, "fieldname": "bill_no", "fieldtype": "Link", "options": "BOQ Bill"},
	# 		fields=["name"],
	# 	)
	# 	# if custom_bill_no:
	# 	# 	insert_after = "supplier_invoice_no" if frappe.get_meta(doctype, cached=False).get_field("supplier_invoice_no") else "project"
	# 	# 	for cf in custom_bill_no:
	# 	# 		frappe.db.set_value(
	# 	# 			"Custom Field",
	# 	# 			cf.name,
	# 	# 			{
	# 	# 				"hidden": 0,
	# 	# 				"label": "Project Bill",
	# 	# 				"insert_after": insert_after,
	# 	# 			},
	# 	# 		)

	frappe.clear_cache(doctype=doctype)
