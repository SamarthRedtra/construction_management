import frappe
from frappe import _
from frappe.utils import flt

def validate_dpr_budget(dpr_doc):
	"""
	Validate DPR cost against Project and BOQ Item budgets based on configuration.
	Called from Daily Progress Record validation.
	"""
	if dpr_doc.docstatus == 2: # Cancelled
		return

	project = frappe.get_doc("Project", dpr_doc.project)
	
	# Get configuration from custom fields
	enforcement = project.get("budget_enforcement_level")
	if not enforcement or enforcement == "None":
		enforcement = "None"
		# Fallback check if field exists but empty
		
	if enforcement == "None":
		return

	mode = project.get("budget_mode", "Soft Limit")
	threshold = flt(project.get("budget_threshold_percent", 0))
	
	cost_impact = flt(dpr_doc.total_cost)
	if cost_impact <= 0:
		return

	# BOQ Item Level Check
	if enforcement in ["BOQ Item Level", "Both"]:
		_validate_boq_item_level(dpr_doc, mode, threshold, cost_impact)

	# Project Level Check
	if enforcement in ["Project Level", "Both"]:
		_validate_project_level(dpr_doc, mode, threshold, cost_impact)

def _validate_boq_item_level(dpr, mode, threshold, cost_impact):
	boq_item = frappe.get_doc("BOQ Item", dpr.boq_item)
	estimated = flt(boq_item.total_estimated_cost)
	
	if estimated <= 0:
		return 
		
	from construction_management.api.boq_ledger import get_cost_to_date
	current_cost = get_cost_to_date(boq_item.name)
	
	potential_total = current_cost + cost_impact
	limit_amount = estimated * (1 + (threshold/100.0))
	
	if potential_total > limit_amount:
		diff = potential_total - estimated
		msg = _("Budget Exceeded for BOQ Item {0}.<br>Estimated: {1}<br>Projected Cost: {2}<br>Overruns: {3}").format(
			boq_item.item_code, 
			frappe.format(estimated, "Currency"), 
			frappe.format(potential_total, "Currency"),
			frappe.format(diff, "Currency")
		)
		_handle_violation(mode, msg, _("BOQ Item Budget Exceeded"))

def _validate_project_level(dpr, mode, threshold, cost_impact):
	current_project_cost = flt(frappe.db.sql("""
		SELECT SUM(total_cost) FROM `tabDaily Progress Record`
		WHERE project = %s AND docstatus = 1 AND name != %s
	""", (dpr.project, dpr.name))[0][0])
	
	potential_total = current_project_cost + cost_impact
	
	project = frappe.get_doc("Project", dpr.project)
	project_budget = flt(getattr(project, "estimated_cost", 0) or getattr(project, "estimated_costing", 0) or 0)
	
	if project_budget <= 0:
		return
		
	limit_amount = project_budget * (1 + (threshold/100.0))
	
	if potential_total > limit_amount:
		diff = potential_total - project_budget
		msg = _("Project Budget Exceeded.<br>Budget: {0}<br>Projected Cost: {1}<br>Overruns: {2}").format(
			frappe.format(project_budget, "Currency"), 
			frappe.format(potential_total, "Currency"),
			frappe.format(diff, "Currency")
		)
		_handle_violation(mode, msg, _("Project Budget Exceeded"))

def _handle_violation(mode, msg, title):
	if mode == "Hard Limit":
		frappe.throw(msg, title=title)
	else:
		frappe.msgprint(msg, title=title, indicator='orange')
