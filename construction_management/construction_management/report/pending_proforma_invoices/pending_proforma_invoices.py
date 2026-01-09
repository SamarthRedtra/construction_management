# Copyright (c) 2024, Construction Management
# License: MIT

"""
Pending Proforma Invoices Report

Property 17: Pending Proforma Report Filtering
Property 18: Report Filter Functionality

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today, date_diff


def execute(filters=None):
	"""Execute the report"""
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	"""
	Get report columns.
	Requirements: 9.2 - Show columns: Project, Bill No, BOQ Item, Proforma No, Date, Amount, Age
	Requirements: 4.3 - Add PC Status, Tax Invoice link, Action columns
	"""
	return [
		{
			"fieldname": "name",
			"label": _("Proforma No"),
			"fieldtype": "Link",
			"options": "Proforma Invoice",
			"width": 140
		},
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 150
		},
		{
			"fieldname": "customer",
			"label": _("Customer"),
			"fieldtype": "Link",
			"options": "Customer",
			"width": 150
		},
		{
			"fieldname": "bill_no",
			"label": _("Bill No"),
			"fieldtype": "Link",
			"options": "BOQ Bill",
			"width": 120
		},
		{
			"fieldname": "boq_item",
			"label": _("BOQ Item"),
			"fieldtype": "Link",
			"options": "BOQ Item",
			"width": 120
		},
		{
			"fieldname": "description",
			"label": _("Description"),
			"fieldtype": "Data",
			"width": 250
		},
		{
			"fieldname": "posting_date",
			"label": _("Date"),
			"fieldtype": "Date",
			"width": 100
		},
		{
			"fieldname": "amount",
			"label": _("Amount"),
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"fieldname": "net_amount",
			"label": _("Net Amount"),
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"fieldname": "age_days",
			"label": _("Age (Days)"),
			"fieldtype": "Int",
			"width": 90
		},
		{
			"fieldname": "pc_status",
			"label": _("PC Status"),
			"fieldtype": "HTML",
			"width": 110
		},
		{
			"fieldname": "payment_certificate",
			"label": _("Payment Certificate"),
			"fieldtype": "Link",
			"options": "Payment Certificate",
			"width": 140
		},
		{
			"fieldname": "tax_invoice",
			"label": _("Tax Invoice"),
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 140
		},
		{
			"fieldname": "action",
			"label": _("Action"),
			"fieldtype": "HTML",
			"width": 120,
			"align": "center"
		}
	]


def get_data(filters):
	"""
	Get report data.
	
	Property 17: For any Proforma Invoice in the Pending Proforma Report, 
	there SHALL NOT exist a linked Payment Certificate.
	
	Property 18: For any filter applied, the results SHALL only include 
	records matching all filter criteria.
	"""
	filters = filters or {}
	conditions = get_conditions(filters)
	
	# Get proformas with PC status
	data = frappe.db.sql("""
		SELECT 
			pi.name,
			pi.project,
			pi.bill_no,
			pi.boq_item,
			pi.customer,
			pi.posting_date,
			pi.amount,
			pi.net_amount,
			pi.description,
			DATEDIFF(CURDATE(), pi.posting_date) as age_days,
			pc.name as payment_certificate,
			pc.status as pc_status,
			pc.tax_invoice
		FROM `tabProforma Invoice` pi
		LEFT JOIN `tabPayment Certificate` pc ON pc.proforma_invoice = pi.name AND pc.docstatus != 2
		WHERE pi.docstatus = 1
		AND pi.status IN ('Submitted', 'Partially Certified')
		{conditions}
		ORDER BY pi.posting_date DESC
	""".format(conditions=conditions), filters, as_dict=True)
	
	# Add action based on PC status
	for row in data:
		if not row.payment_certificate:
			row["action"] = "Create PC"
			row["pc_status"] = "Pending"
		elif row.pc_status == "Draft":
			row["action"] = "Submit PC"
		elif row.pc_status in ["Submitted", "Invoiced", "Paid"]:
			row["action"] = "View"
		else:
			row["action"] = "Create PC"
			row["pc_status"] = "Pending"
	
	return data


def get_conditions(filters):
	"""Build SQL conditions from filters"""
	conditions = []
	
	if filters.get("project"):
		conditions.append("AND pi.project = %(project)s")
	
	if filters.get("customer"):
		conditions.append("AND pi.customer = %(customer)s")
	
	if filters.get("from_date"):
		conditions.append("AND pi.posting_date >= %(from_date)s")
	
	if filters.get("to_date"):
		conditions.append("AND pi.posting_date <= %(to_date)s")
	
	if filters.get("min_amount"):
		conditions.append("AND pi.amount >= %(min_amount)s")
	
	if filters.get("max_amount"):
		conditions.append("AND pi.amount <= %(max_amount)s")
	
	if filters.get("bill_no"):
		conditions.append("AND pi.bill_no = %(bill_no)s")
	
	return " ".join(conditions)
