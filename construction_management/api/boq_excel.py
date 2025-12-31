# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt
import io


@frappe.whitelist()
def export_boq_to_excel(project: str) -> str:
	"""
	Export BOQ data to Excel format with comprehensive columns matching the UI table.
	
	Args:
		project: Project name
		
	Returns:
		str: File URL for download
	"""
	try:
		import openpyxl
		from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
	except ImportError:
		frappe.throw(_("openpyxl is required for Excel export. Please install it."))
	
	# Get BOQ data
	from construction_management.api.boq_tree import get_boq_tree_data
	data = get_boq_tree_data(project)
	
	if not data or not data.get('bills'):
		frappe.throw(_("No BOQ data found for this project"))
	
	# Create workbook
	wb = openpyxl.Workbook()
	ws = wb.active
	ws.title = "BOQ"
	
	# Styles
	header_font = Font(bold=True, size=10, color="FFFFFF")
	subheader_font = Font(bold=True, size=9)
	bill_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
	thin_border = Border(
		left=Side(style='thin'),
		right=Side(style='thin'),
		top=Side(style='thin'),
		bottom=Side(style='thin')
	)
	
	# Group header colors
	revenue_fill = PatternFill(start_color="1565C0", end_color="1565C0", fill_type="solid")
	value_fill = PatternFill(start_color="E65100", end_color="E65100", fill_type="solid")
	qty_fill = PatternFill(start_color="2E7D32", end_color="2E7D32", fill_type="solid")
	billing_fill = PatternFill(start_color="C2185B", end_color="C2185B", fill_type="solid")
	estimated_fill = PatternFill(start_color="7B1FA2", end_color="7B1FA2", fill_type="solid")
	actual_fill = PatternFill(start_color="C62828", end_color="C62828", fill_type="solid")
	profit_fill = PatternFill(start_color="00695C", end_color="00695C", fill_type="solid")
	default_fill = PatternFill(start_color="424242", end_color="424242", fill_type="solid")
	
	# Row 1: Group headers
	group_headers = [
		("", 1, 1, default_fill),
		("", 2, 2, default_fill),
		("", 3, 3, default_fill),
		("", 4, 4, default_fill),
		("", 5, 5, default_fill),
		("", 6, 6, default_fill),
		("Revenue", 7, 12, revenue_fill),
		("Value Breakdown", 13, 15, value_fill),
		("Qty Breakdown", 16, 18, qty_fill),
		("Current Billing", 19, 20, billing_fill),
		("Estimated Cost", 21, 26, estimated_fill),
		("Actual Cost", 27, 32, actual_fill),
		("Profitability", 33, 34, profit_fill),
	]
	
	for label, start_col, end_col, fill in group_headers:
		if start_col == end_col:
			cell = ws.cell(row=1, column=start_col, value=label)
			cell.font = header_font
			cell.fill = fill
			cell.alignment = Alignment(horizontal='center')
		else:
			ws.merge_cells(start_row=1, start_column=start_col, end_row=1, end_column=end_col)
			cell = ws.cell(row=1, column=start_col, value=label)
			cell.font = header_font
			cell.fill = fill
			cell.alignment = Alignment(horizontal='center')
	
	# Row 2: Column headers
	headers = [
		"Bill No", "Item Code", "Description", "Unit", "Total Qty", "Rate",
		# Revenue
		"Proforma Invoice", "PC", "TAX Invoice", "Variance (-)", "BOQ Balance", "Total",
		# Value Breakdown
		"Previous/Value", "Current/Value", "Accumulated/Value",
		# Qty Breakdown
		"Previous/Qty", "Current/Qty", "Accumulated/Qty",
		# Current Billing
		"Current Qty", "Current Value",
		# Estimated Cost
		"Material", "Labour", "Asset", "S/C", "Other", "Total",
		# Actual Cost
		"Material", "Labour", "Asset", "S/C", "Other", "Total",
		# Profitability
		"GP", "GP%"
	]
	
	for col, header in enumerate(headers, 1):
		cell = ws.cell(row=2, column=col, value=header)
		cell.font = subheader_font
		cell.border = thin_border
		cell.alignment = Alignment(horizontal='center', wrap_text=True)
	
	# Data rows
	row = 3
	for bill in data['bills']:
		# Bill row (summary)
		ws.cell(row=row, column=1, value=bill['bill_no']).fill = bill_fill
		ws.cell(row=row, column=3, value=bill.get('description', '')).fill = bill_fill
		
		totals = bill.get('totals', {})
		revenue = totals.get('revenue', {})
		qty = totals.get('qty', {})
		amount = totals.get('amount', {})
		estimated = totals.get('estimated_costs', {})
		actual = totals.get('actual_costs', {})
		profitability = totals.get('profitability', {})
		
		# Add Total Qty for the Bill row
		ws.cell(row=row, column=5, value=qty.get('total', 0)).fill = bill_fill
		
		# Apply bill fill to all other cells in the row
		for col in range(1, 35):
			if col != 5: # Already set above
				ws.cell(row=row, column=col).fill = bill_fill
			ws.cell(row=row, column=col).border = thin_border
		
		row += 1
		
		# Item rows
		for item in bill.get('items', []):
			ws.cell(row=row, column=1, value=bill['bill_no'])
			ws.cell(row=row, column=2, value=item.get('item_code', ''))
			ws.cell(row=row, column=3, value=item.get('description', ''))
			ws.cell(row=row, column=4, value=item.get('unit', ''))
			
			# Ensure Total Qty is fetched correctly (Task 2.1 fix)
			total_qty = flt(item.get('total_qty')) or flt(item.get('qty', {}).get('total', 0))
			ws.cell(row=row, column=5, value=total_qty)
			
			item_amount = item.get('amount', {})
			item_qty = item.get('qty', {})
			item_revenue = item.get('revenue', {})
			item_estimated = item.get('estimated_costs', {})
			item_actual = item.get('actual_costs', {})
			item_profit = item.get('profitability', {})
			
			ws.cell(row=row, column=6, value=item_amount.get('rate', 0))
			
			# Revenue columns
			ws.cell(row=row, column=7, value=item_revenue.get('proforma', 0))
			ws.cell(row=row, column=8, value=item_revenue.get('pc', 0))
			ws.cell(row=row, column=9, value=item_revenue.get('tax_invoice', 0))
			ws.cell(row=row, column=10, value=item_revenue.get('variance', 0))
			ws.cell(row=row, column=11, value=item_revenue.get('balance', 0))
			ws.cell(row=row, column=12, value=item_revenue.get('total', 0))
			
			# Value Breakdown
			ws.cell(row=row, column=13, value=item_amount.get('prev', 0))
			ws.cell(row=row, column=14, value=item_amount.get('current', 0))
			ws.cell(row=row, column=15, value=item_amount.get('to_date', 0))
			
			# Qty Breakdown
			ws.cell(row=row, column=16, value=item_qty.get('prev', 0))
			ws.cell(row=row, column=17, value=item_qty.get('current', 0))
			ws.cell(row=row, column=18, value=item_qty.get('to_date', 0))
			
			# Current Billing
			ws.cell(row=row, column=19, value=item_qty.get('current', 0))
			ws.cell(row=row, column=20, value=item_amount.get('current', 0))
			
			# Estimated Cost
			ws.cell(row=row, column=21, value=item_estimated.get('material', 0))
			ws.cell(row=row, column=22, value=item_estimated.get('labour', 0))
			ws.cell(row=row, column=23, value=item_estimated.get('asset', 0))
			ws.cell(row=row, column=24, value=item_estimated.get('subcontract', 0))
			ws.cell(row=row, column=25, value=item_estimated.get('other', 0))
			ws.cell(row=row, column=26, value=item_estimated.get('total', 0))
			
			# Actual Cost
			ws.cell(row=row, column=27, value=item_actual.get('material', 0))
			ws.cell(row=row, column=28, value=item_actual.get('labour', 0))
			ws.cell(row=row, column=29, value=item_actual.get('asset', 0))
			ws.cell(row=row, column=30, value=item_actual.get('subcontract', 0))
			ws.cell(row=row, column=31, value=item_actual.get('other', 0))
			ws.cell(row=row, column=32, value=item_actual.get('total', 0))
			
			# Profitability
			ws.cell(row=row, column=33, value=item_profit.get('gp', 0))
			ws.cell(row=row, column=34, value=item_profit.get('gp_percent', 0))
			
			for col in range(1, 35):
				ws.cell(row=row, column=col).border = thin_border
			
			row += 1
	
	# Adjust column widths
	column_widths = [
		12, 15, 35, 8, 10, 10,  # Basic info + Total Qty
		12, 12, 12, 10, 12, 12,  # Revenue
		12, 12, 12,  # Value Breakdown
		10, 10, 10,  # Qty Breakdown
		10, 12,  # Current Billing
		10, 10, 10, 10, 10, 12,  # Estimated Cost
		10, 10, 10, 10, 10, 12,  # Actual Cost
		12, 8  # Profitability
	]
	for i, width in enumerate(column_widths, 1):
		ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = width
	
	# Save to file
	output = io.BytesIO()
	wb.save(output)
	output.seek(0)
	
	# Create file record
	file_name = f"BOQ_{project}_{frappe.utils.now_datetime().strftime('%Y%m%d_%H%M%S')}.xlsx"
	
	file_doc = frappe.get_doc({
		"doctype": "File",
		"file_name": file_name,
		"content": output.getvalue(),
		"is_private": 1,
		"attached_to_doctype": "Project",
		"attached_to_name": project
	})
	file_doc.save(ignore_permissions=True)
	
	return file_doc.file_url


@frappe.whitelist()
def import_boq_from_excel(project: str, file_url: str) -> dict:
	"""
	Import BOQ data from Excel file.
	
	Args:
		project: Project name
		file_url: URL of uploaded Excel file
		
	Returns:
		dict with import results
	"""
	try:
		import openpyxl
	except ImportError:
		frappe.throw(_("openpyxl is required for Excel import. Please install it."))
	
	# Get file content
	file_doc = frappe.get_doc("File", {"file_url": file_url})
	file_path = file_doc.get_full_path()
	
	wb = openpyxl.load_workbook(file_path)
	ws = wb.active
	
	# Get or create Project BOQ
	project_boq = frappe.db.get_value("Project BOQ", {"project": project}, "name")
	if not project_boq:
		boq_doc = frappe.new_doc("Project BOQ")
		boq_doc.project = project
		boq_doc.boq_name = f"BOQ - {project}"
		boq_doc.status = "Draft"
		boq_doc.insert()
		project_boq = boq_doc.name
	
	# Check if BOQ is locked
	from construction_management.construction_management.doctype.project_boq.project_boq import is_boq_locked
	if is_boq_locked(project_boq):
		frappe.throw(_("Cannot import to a locked BOQ"))
	
	# Parse data
	bills_created = 0
	items_created = 0
	items_updated = 0
	errors = []
	
	current_bill = None
	
	for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
		try:
			bill_no = row[0]
			item_code = row[1]
			description = row[2]
			unit = row[3]
			total_qty = flt(row[4])
			rate = flt(row[5])
			current_qty = flt(row[9]) if len(row) > 9 else 0
			
			if not bill_no:
				continue
			
			# Get or create bill
			if current_bill is None or current_bill.bill_no != bill_no:
				existing_bill = frappe.db.get_value(
					"BOQ Bill",
					{"project_boq": project_boq, "bill_no": bill_no},
					"name"
				)
				
				if existing_bill:
					current_bill = frappe.get_doc("BOQ Bill", existing_bill)
				else:
					current_bill = frappe.new_doc("BOQ Bill")
					current_bill.project_boq = project_boq
					current_bill.bill_no = bill_no
					current_bill.description = description if not item_code else ""
					current_bill.insert()
					bills_created += 1
			
			# Skip bill summary rows (no item_code)
			if not item_code and not description:
				continue
			
			# Create or update item
			if description:
				existing_item = frappe.db.get_value(
					"BOQ Item",
					{"parent_bill": current_bill.name, "description": description},
					"name"
				)
				
				if existing_item:
					# Update existing item
					item = frappe.get_doc("BOQ Item", existing_item)
					
					# Validate previous qty matches ledger
					from construction_management.api.boq_ledger import get_previous_qty
					ledger_prev = get_previous_qty(existing_item)
					import_prev = flt(row[7]) if len(row) > 7 else 0
					
					if abs(ledger_prev - import_prev) > 0.001:
						errors.append(f"Row {row_num}: Previous qty mismatch for '{description[:30]}...' (Ledger: {ledger_prev}, Import: {import_prev})")
						continue
					
					# Update current qty only
					if current_qty > 0:
						item.current_qty = current_qty
						item.save()
						items_updated += 1
				else:
					# Create new item
					item = frappe.new_doc("BOQ Item")
					item.parent_bill = current_bill.name
					item.item_code = item_code
					item.description = description
					item.unit = unit
					item.total_qty = total_qty
					item.rate = rate
					item.current_qty = current_qty
					item.insert()
					items_created += 1
					
		except Exception as e:
			errors.append(f"Row {row_num}: {str(e)}")
	
	frappe.db.commit()
	
	return {
		"success": True,
		"bills_created": bills_created,
		"items_created": items_created,
		"items_updated": items_updated,
		"errors": errors
	}
