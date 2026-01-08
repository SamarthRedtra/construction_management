import frappe
from frappe import _
from frappe.utils import flt

def update_cost_from_gl(doc, method):
	"""
	Hook for GL Entry on_update.
	Updates Project and BOQ Item costs based on Real-Time GL impact.
	Requirement 2: Real-Time Costing via GL Entries.
	"""
	if not doc.project:
		return
		
	# Update Project Cost
	update_project_cost(doc.project)
	
	# Update BOQ Item Cost linked to this transaction
	dpr_name = find_dpr_via_voucher(doc.voucher_type, doc.voucher_no)
	if dpr_name:
		dpr = frappe.get_doc("Daily Progress Record", dpr_name)
		if dpr.boq_item:
			try:
				boq_item = frappe.get_doc("BOQ Item", dpr.boq_item)
				# calculate_amounts calls boq_ledger.get_cost_to_date -> New GL Logic
				boq_item.calculate_amounts()
				boq_item.flags.ignore_permissions = True
				boq_item.save(ignore_permissions=True)
			except Exception as e:
				frappe.log_error(f"Failed to update BOQ Item {dpr.boq_item} from GL Hook: {e}")

def update_project_cost(project_name):
	# Calculate total project cost from GL (Expense + WIP)
	total_cost = frappe.db.sql("""
		SELECT SUM(debit - credit) FROM `tabGL Entry`
		WHERE project = %s 
		AND is_cancelled = 0
		AND account IN (
			SELECT name FROM `tabAccount` 
			WHERE root_type = 'Expense' 
			OR account_type = 'Work In Progress'
		)
	""", project_name)[0][0] or 0
	
	# Update the project cost field (reusing existing field used by DPR)
	frappe.db.set_value("Project", project_name, "estimated_costing", flt(total_cost))

def find_dpr_via_voucher(voucher_type, voucher_no):
	# Find matching DPR via linked vouchers
	# Safer search to avoid partial matches (e.g. SE-1 vs SE-10)
	field = None
	if voucher_type == "Stock Entry":
		field = "stock_entries"
	elif voucher_type == "Journal Entry":
		field = "journal_entries"
		
	if not field:
		return None

	# Find candidates using loose search first
	candidates = frappe.get_all(
		"Daily Progress Record", 
		filters={field: ("like", f"%{voucher_no}%")}, 
		fields=["name", field]
	)
	
	for dpr in candidates:
		# Strict check in comma separated list
		entries = [x.strip() for x in (dpr.get(field) or "").split(",")]
		if voucher_no in entries:
			return dpr.name
			
	return None
