import frappe


def execute():
	for fieldname in ("transaction_date", "delivery_date"):
		frappe.make_property_setter(
			{
				"doctype": "Sales Order",
				"fieldname": fieldname,
				"property": "allow_on_submit",
				"value": "1",
				"property_type": "Check",
			},
			validate_fields_for_doctype=False,
		)
