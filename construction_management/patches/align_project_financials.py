
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
	# Layout: Section -> [Col 1: Revenue/Cost/GP] -> Col Break -> [Col 2: Retention/Advance]
	
	custom_fields = {
		"Project": [
			# Section Break
			{
				"fieldname": "financial_section_break",
				"label": "Project Financials",
				"fieldtype": "Section Break",
				"insert_after": "construction_dashboard",
				"collapsible": 1
			},
			# Column 1
			{
				"fieldname": "total_revenue",
				"label": "Total Revenue",
				"fieldtype": "Currency",
				"read_only": 1,
				"insert_after": "financial_section_break"
			},
			{
				"fieldname": "total_estimated_cost",
				"label": "Total Estimated Cost",
				"fieldtype": "Currency",
				"read_only": 1,
				"insert_after": "total_revenue"
			},
			{
				"fieldname": "total_actual_cost",
				"label": "Total Actual Cost", 
				"fieldtype": "Currency",
				"read_only": 1,
				"insert_after": "total_estimated_cost"
			},
			{
				"fieldname": "total_estimated_gp",
				"label": "Total Estimated GP",
				"fieldtype": "Currency",
				"read_only": 1,
				"insert_after": "total_actual_cost"
			},
			{
				"fieldname": "project_gp_percentage",
				"label": "Project GP %",
				"fieldtype": "Percent",
				"read_only": 1,
				"insert_after": "total_estimated_gp"
			},
			
			# Column Break
			{
				"fieldname": "financial_column_break",
				"fieldtype": "Column Break",
				"insert_after": "project_gp_percentage"
			},
			
			# Column 2
			{
				"fieldname": "total_retention_retained",
				"label": "Total Retention Retained",
				"fieldtype": "Currency",
				"read_only": 1,
				"insert_after": "financial_column_break"
			},
			{
				"fieldname": "total_retention_released",
				"label": "Total Retention Released",
				"fieldtype": "Currency",
				"read_only": 1,
				"insert_after": "total_retention_retained"
			},
			{
				"fieldname": "total_retention_balance",
				"label": "Total Retention Balance",
				"fieldtype": "Currency",
				"read_only": 1,
				"insert_after": "total_retention_released"
			},
			{
				"fieldname": "total_advance_given",
				"label": "Total Advance Given",
				"fieldtype": "Currency",
				"read_only": 1,
				"insert_after": "total_retention_balance"
			},
			{
				"fieldname": "total_advance_utilized",
				"label": "Total Advance Utilized",
				"fieldtype": "Currency",
				"read_only": 1,
				"insert_after": "total_advance_given"
			},
			{
				"fieldname": "total_advance_available",
				"label": "Total Advance Available",
				"fieldtype": "Currency",
				"read_only": 1,
				"insert_after": "total_advance_utilized"
			},
			{
				"fieldname": "project_net_receivable",
				"label": "Project Net Receivable",
				"fieldtype": "Currency",
				"read_only": 1,
				"insert_after": "total_advance_available"
			}
		]
	}
	
	create_custom_fields(custom_fields, update=True)
