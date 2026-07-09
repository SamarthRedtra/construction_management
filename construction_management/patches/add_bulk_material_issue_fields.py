import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Purchase Receipt Item": [
				{
					"fieldname": "custom_material_issued_qty",
					"label": "Material Issued Qty",
					"fieldtype": "Float",
					"read_only": 1,
					"insert_after": "received_qty",
				},
				{
					"fieldname": "custom_material_issue_stock_entries",
					"label": "Material Issue Stock Entries",
					"fieldtype": "Small Text",
					"read_only": 1,
					"insert_after": "custom_material_issued_qty",
				},
			],
			"Stock Entry Detail": [
				{
					"fieldname": "custom_material_issued_qty",
					"label": "Material Issued Qty",
					"fieldtype": "Float",
					"read_only": 1,
					"insert_after": "qty",
				},
				{
					"fieldname": "custom_bulk_issue_source_line",
					"label": "Bulk Issue Source Line",
					"fieldtype": "Data",
					"hidden": 1,
					"insert_after": "custom_material_issued_qty",
				},
			],
			"Stock Entry": [
				{
					"fieldname": "custom_bulk_issue_source_doctype",
					"label": "Bulk Issue Source DocType",
					"fieldtype": "Link",
					"options": "DocType",
					"read_only": 1,
					"insert_after": "stock_entry_type",
				},
				{
					"fieldname": "custom_bulk_issue_source_name",
					"label": "Bulk Issue Source Name",
					"fieldtype": "Dynamic Link",
					"options": "custom_bulk_issue_source_doctype",
					"read_only": 1,
					"insert_after": "custom_bulk_issue_source_doctype",
				},
			],
		},
		update=True,
	)
