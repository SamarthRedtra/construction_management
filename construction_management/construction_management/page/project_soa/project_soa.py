# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt, getdate
from construction_management.api.boq_tree import get_project_cost_breakdown


@frappe.whitelist()
def get_project_soa_data(project: str) -> dict:
	"""
	Exposed API method to fetch all data required for the Project Statement of Account (SOA) page.
	
	Args:
		project: Project name/ID
		
	Returns:
		dict containing:
			- services: List of BOQ services (description, area, unit price, total amount)
			- total_project_value: Sum of BOQ items total amount
			- invoices: List of merged Proforma/Tax invoices and their payments/cheques
			- summary: Total invoice, total received, balance, retention, any deduction
			- expenses: Breakdown of material, labor, subcontractor, commission, other expenses
			- profit_loss: Net profit/loss metric
	"""
	if not project:
		frappe.throw(_("Project is required"))
		
	# 1. Fetch BOQ Services
	services = []
	total_project_value = 0.0
	
	# Fetch BOQ items associated with the project's active BOQ
	boq_items = frappe.db.get_all(
		"BOQ Item",
		filters={"project": project},
		fields=["description", "total_qty", "rate", "total_amount", "item_code", "label"],
		order_by="idx"
	)
	
	for idx, item in enumerate(boq_items, start=1):
		amount = flt(item.total_amount)
		total_project_value += amount
		services.append({
			"idx": idx,
			"service": item.description or item.label or item.item_code,
			"area": flt(item.total_qty),
			"unit_price": flt(item.rate),
			"total_amount": amount
		})
		
	# 2. Fetch Invoices and Payment Transactions
	# We query all submitted Sales Invoices for the project (excluding advance billing invoices if needed, but standard is fine)
	sales_invoices = frappe.db.get_all(
		"Sales Invoice",
		filters={"project": project, "docstatus": 1},
		fields=["name", "posting_date", "grand_total", "custom_proforma_invoice", "custom_sales_order", "custom_retention_amount"],
		order_by="posting_date asc, name asc"
	)
	
	# We also query all submitted Proforma Invoices that are NOT converted to Sales Invoices
	proforma_invoices = frappe.db.get_all(
		"Proforma Invoice",
		filters={"project": project, "docstatus": 1, "status": ["!=", "Converted"]},
		fields=["name", "posting_date", "amount"],
		order_by="posting_date asc, name asc"
	)
	
	invoice_rows = []
	invoice_serial = 1
	
	# We'll map Sales Orders and Proforma Invoices to easily query dates
	so_names = [si.custom_sales_order for si in sales_invoices if si.custom_sales_order]
	pfi_names = [si.custom_proforma_invoice for si in sales_invoices if si.custom_proforma_invoice]
	
	so_dates = {}
	if so_names:
		so_data = frappe.db.get_all("Sales Order", filters={"name": ["in", so_names]}, fields=["name", "transaction_date"])
		so_dates = {d.name: d.transaction_date for d in so_data}
		
	pfi_dates = {}
	if pfi_names:
		pfi_data = frappe.db.get_all("Proforma Invoice", filters={"name": ["in", pfi_names]}, fields=["name", "posting_date"])
		pfi_dates = {d.name: d.posting_date for d in pfi_data}
		
	# Process Sales Invoices (Tax Invoices)
	for si in sales_invoices:
		# Determine Proforma Date: linked Proforma Invoice date, or linked Sales Order date, or fallback to Sales Invoice date
		proforma_date = None
		if si.custom_proforma_invoice and si.custom_proforma_invoice in pfi_dates:
			proforma_date = pfi_dates[si.custom_proforma_invoice]
		elif si.custom_sales_order and si.custom_sales_order in so_dates:
			proforma_date = so_dates[si.custom_sales_order]
		else:
			# If there's a standard Sales Order link
			standard_so = frappe.db.get_value("Sales Invoice Item", {"parent": si.name, "sales_order": ["is", "set"]}, "sales_order")
			if standard_so:
				proforma_date = frappe.db.get_value("Sales Order", standard_so, "transaction_date")
			else:
				proforma_date = si.posting_date
				
		# Get Payments for this Sales Invoice
		payments = frappe.db.sql(
			"""
			SELECT
				pe.reference_no,
				pe.posting_date,
				per.allocated_amount
			FROM `tabPayment Entry Reference` per
			INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
			WHERE pe.docstatus = 1
			  AND per.reference_doctype = 'Sales Invoice'
			  AND per.reference_name = %s
			ORDER BY pe.posting_date asc, pe.name asc
			""",
			si.name,
			as_dict=True
		)
		
		invoice_amount = flt(si.grand_total)
		
		if not payments:
			invoice_rows.append({
				"serial_no": invoice_serial,
				"proforma_date": proforma_date,
				"tax_invoice_date": si.posting_date,
				"invoice_no": si.name,
				"invoice_type": "Tax Invoice",
				"amount": invoice_amount,
				"cheque_no": "",
				"cheque_date": "",
				"cheque_amount": 0.0
			})
		else:
			for pe in payments:
				invoice_rows.append({
					"serial_no": invoice_serial,
					"proforma_date": proforma_date,
					"tax_invoice_date": si.posting_date,
					"invoice_no": si.name,
					"invoice_type": "Tax Invoice",
					"amount": invoice_amount,
					"cheque_no": pe.reference_no or "",
					"cheque_date": pe.posting_date,
					"cheque_amount": flt(pe.allocated_amount)
				})
		invoice_serial += 1
		
	# Process unconverted Proforma Invoices
	for pi in proforma_invoices:
		# Get Payments for this Proforma Invoice (if any linked directly)
		payments = frappe.db.sql(
			"""
			SELECT
				pe.reference_no,
				pe.posting_date,
				per.allocated_amount
			FROM `tabPayment Entry Reference` per
			INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
			WHERE pe.docstatus = 1
			  AND per.reference_doctype = 'Proforma Invoice'
			  AND per.reference_name = %s
			ORDER BY pe.posting_date asc, pe.name asc
			""",
			pi.name,
			as_dict=True
		)
		
		pi_amount = flt(pi.amount)
		
		if not payments:
			invoice_rows.append({
				"serial_no": invoice_serial,
				"proforma_date": pi.posting_date,
				"tax_invoice_date": pi.posting_date,
				"invoice_no": pi.name,
				"invoice_type": "Proforma Invoice",
				"amount": pi_amount,
				"cheque_no": "",
				"cheque_date": "",
				"cheque_amount": 0.0
			})
		else:
			for pe in payments:
				invoice_rows.append({
					"serial_no": invoice_serial,
					"proforma_date": pi.posting_date,
					"tax_invoice_date": pi.posting_date,
					"invoice_no": pi.name,
					"invoice_type": "Proforma Invoice",
					"amount": pi_amount,
					"cheque_no": pe.reference_no or "",
					"cheque_date": pe.posting_date,
					"cheque_amount": flt(pe.allocated_amount)
				})
		invoice_serial += 1
		
	# 3. Compute Summary Metrics
	# Sum up invoice grand totals (deduplicated by invoice number to get true sum)
	seen_invoices = set()
	total_invoice_amount = 0.0
	for row in invoice_rows:
		if row["invoice_no"] not in seen_invoices:
			total_invoice_amount += row["amount"]
			seen_invoices.add(row["invoice_no"])
			
	# Sum up received amounts
	total_received_amount = sum(row["cheque_amount"] for row in invoice_rows)
	balance = total_invoice_amount - total_received_amount
	
	# Sum retention deductions from Sales Invoice items (item_code = 'RETENTION-DEDUCTION')
	retention_amount = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(ABS(sii.amount)), 0) AS total
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.project = %s
			AND si.docstatus = 1
			AND sii.item_code = 'RETENTION-DEDUCTION'
		""",
		project
	)[0][0] or 0.0
	
	# If no retention items, fallback to custom_retention_amount sum
	if retention_amount == 0.0:
		retention_amount = sum(flt(si.custom_retention_amount) for si in sales_invoices)
		
	# Sum advance deductions from Sales Invoice items (item_code = 'ADVANCE-DEDUCTION')
	any_deduction = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(ABS(sii.amount)), 0) AS total
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.project = %s
			AND si.docstatus = 1
			AND sii.item_code = 'ADVANCE-DEDUCTION'
		""",
		project
	)[0][0] or 0.0
	
	summary = {
		"total_invoice_amount": total_invoice_amount,
		"total_received_amount": total_received_amount,
		"balance": balance,
		"retention_amount": retention_amount,
		"any_deduction": any_deduction
	}
	
	# 4. Fetch Expenses Breakdown from GL
	gl_breakdown = get_project_cost_breakdown(project) or {}
	
	material_cost = flt(gl_breakdown.get("material", 0.0))
	labor_cost = flt(gl_breakdown.get("labor", 0.0))
	subcontractor_cost = flt(gl_breakdown.get("subcontractor", 0.0))
	commission = flt(gl_breakdown.get("commission", 0.0))
	other_cost = flt(gl_breakdown.get("other", 0.0)) + flt(gl_breakdown.get("unallocated", 0.0))
	total_project_cost = material_cost + labor_cost + subcontractor_cost + commission + other_cost
	
	expenses = [
		{"idx": 1, "category": _("Material Cost"), "cost": material_cost},
		{"idx": 2, "category": _("Labour Cost"), "cost": labor_cost},
		{"idx": 3, "category": _("Subcontractor Cost"), "cost": subcontractor_cost},
		{"idx": 4, "category": _("Commission"), "cost": commission},
		{"idx": 5, "category": _("Other/Unallocated Cost"), "cost": other_cost},
		{"idx": 6, "category": _("Total Project Cost"), "cost": total_project_cost, "is_total": True}
	]
	
	# 5. Profit/Loss
	profit_loss = total_received_amount - total_project_cost
	
	return {
		"services": services,
		"total_project_value": total_project_value,
		"invoices": invoice_rows,
		"summary": summary,
		"expenses": expenses,
		"profit_loss": profit_loss
	}
