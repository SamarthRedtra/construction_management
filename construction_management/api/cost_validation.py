# Copyright (c) 2024, Construction Management
# License: MIT

"""
Cost Validation Service for DPR Submission

This module provides validation methods to ensure DPR costs don't exceed
BOQ Item estimated costs.

Properties validated:
- Property 5: DPR Total Cost Validation
- Property 6: DPR Component Cost Validation
"""

import frappe
from frappe import _
from frappe.utils import flt
from dataclasses import dataclass, field
from typing import List, Optional, Any


@dataclass
class ValidationResult:
	is_valid: bool = True
	has_errors: bool = False
	has_warnings: bool = False
	errors: List[str] = field(default_factory=list)
	warnings: List[str] = field(default_factory=list)

@frappe.whitelist()
def update_estimated_costs(boq_item: str, new_values: Any, old_values: Any) -> dict:
	"""
	Update estimated costs for a BOQ Item with audit logging.
	
	Requires Project Manager role or System Manager role.
	
	Args:
		boq_item: BOQ Item name
		new_values: Dict with new estimated cost values
		old_values: Dict with old estimated cost values (for audit)
	
	Returns:
		Dict with success status and message
	
	Property 9: Estimated Cost Audit Logging
	Validates: Requirements 5.7
	"""
	import json
	
	# Parse JSON if strings
	if isinstance(new_values, str):
		new_values = json.loads(new_values)
	if isinstance(old_values, str):
		old_values = json.loads(old_values)
	
	# Check permission
	if not (frappe.has_permission("BOQ Item", "write", boq_item) or 
			"Project Manager" in frappe.get_roles() or 
			"System Manager" in frappe.get_roles()):
		frappe.throw(_("You don't have permission to update estimated costs"), frappe.PermissionError)
	
	# Get the BOQ Item
	doc = frappe.get_doc("BOQ Item", boq_item)
	
	# Track changes for audit
	changes = []
	cost_fields = [
		"estimated_material_cost_per_unit",
		"estimated_labour_cost_per_unit",
		"estimated_subcontract_cost_per_unit",
		"estimated_asset_cost_per_unit",
		"estimated_other_cost_per_unit",
		"estimated_material_cost",
		"estimated_labour_cost",
		"estimated_subcontract_cost",
		"estimated_asset_cost",
		"estimated_other_cost",
		"total_estimated_cost"
	]
	
	for field in cost_fields:
		old_val = flt(old_values.get(field, 0))
		new_val = flt(new_values.get(field, 0))
		
		if old_val != new_val:
			changes.append({
				"field": field,
				"old_value": old_val,
				"new_value": new_val
			})
			# Update the field
			doc.set(field, new_val)
	
	if not changes:
		return {"success": True, "message": _("No changes detected")}
	
	# Save the document
	doc.flags.ignore_permissions = True
	doc.save()
	
	# Create audit log entry using Version doctype
	create_cost_audit_log(boq_item, changes)
	
	return {
		"success": True,
		"message": _("Estimated costs updated successfully"),
		"changes": changes
	}


def create_cost_audit_log(boq_item: str, changes: list):
	"""
	Create an audit log entry for estimated cost changes.
	
	Uses the Version doctype to track changes.
	
	Args:
		boq_item: BOQ Item name
		changes: List of change dicts with field, old_value, new_value
	"""
	import json
	
	# Format changes for Version doctype
	data = {
		"changed": [],
		"comment_type": "Edit",
		"comment": "Estimated costs updated"
	}
	
	for change in changes:
		data["changed"].append([
			change["field"],
			change["old_value"],
			change["new_value"]
		])
	
	# Create Version entry
	version = frappe.new_doc("Version")
	version.ref_doctype = "BOQ Item"
	version.docname = boq_item
	version.data = json.dumps(data)
	version.flags.ignore_permissions = True
	version.insert()
	
	# Also add a comment for visibility
	frappe.get_doc({
		"doctype": "Comment",
		"comment_type": "Info",
		"reference_doctype": "BOQ Item",
		"reference_name": boq_item,
		"content": _("Estimated costs updated by {0}").format(frappe.session.user)
	}).insert(ignore_permissions=True)


@frappe.whitelist()
def get_cost_audit_log(boq_item: str) -> list:
	"""
	Get audit log entries for estimated cost changes.
	
	Args:
		boq_item: BOQ Item name
	
	Returns:
		List of audit log entries
	"""
	import json
	
	versions = frappe.get_all(
		"Version",
		filters={
			"ref_doctype": "BOQ Item",
			"docname": boq_item
		},
		fields=["name", "data", "owner", "creation"],
		order_by="creation desc",
		limit=50
	)
	
	audit_entries = []
	
	for version in versions:
		try:
			data = json.loads(version.data)
			if data.get("changed"):
				for change in data["changed"]:
					if change[0].startswith("estimated_"):
						audit_entries.append({
							"field": change[0],
							"old_value": change[1],
							"new_value": change[2],
							"changed_by": version.owner,
							"changed_at": version.creation
						})
		except (json.JSONDecodeError, KeyError, IndexError):
			continue
	

	return audit_entries


def validate_dpr_costs(boq_item_name, dpr_costs, dpr_name=None):
	"""
	Validate DPR costs against BOQ Item estimated costs.
	
	Args:
		boq_item_name: BOQ Item Name
		dpr_costs: Dictionary of DPR costs
		dpr_name: Optional DPR Name (to exclude from calculation if editing)
		
	Returns:
		Object with has_warnings property and warnings list
	"""
	from collections import namedtuple
	Result = namedtuple('Result', ['has_warnings', 'warnings', 'has_errors', 'errors'])
	warnings = []
	errors = []
	
	if not boq_item_name:
		return Result(False, [], False, [])
		
	# Skip if not a valid BOQ Item
	if not frappe.db.exists("BOQ Item", boq_item_name):
		return Result(False, [], False, [])

	boq_item = frappe.get_doc("BOQ Item", boq_item_name)
	
	# Skip if estimates are not set (zero)
	if flt(boq_item.total_estimated_cost) <= 0:
		return Result(False, [], False, [])
		
	# Get current costs to date (excluding this DPR)
	from construction_management.api.boq_ledger import get_cost_to_date
	current_cost = get_cost_to_date(boq_item.name)
	
	# If editing existing DPR, subtract its previous contribution? 
	# get_cost_to_date usually sums from GL/Ledger. 
	# If DPR is draft, it's not in ledger yet, so current_cost is fine.
	# If DPR is submitted and being re-validated? Usually runs on submit.
	
	# Add this DPR cost
	dpr_total_cost = flt(dpr_costs.get('total_cost'))
	new_total_cost = current_cost + dpr_total_cost
	
	# Check against limit
	if new_total_cost > flt(boq_item.total_estimated_cost):
		# Resolve currency
		currency = None
		project_company = None

		# Older schemas may not have Project.currency; guard the lookup
		if frappe.db.has_column("Project", "currency"):
			currency = frappe.db.get_value("Project", boq_item.project, "currency")

		# Company lookup is safe across versions
		project_company = frappe.db.get_value("Project", boq_item.project, "company")

		if not currency and project_company:
			currency = frappe.get_cached_value('Company', project_company, 'default_currency')
		
		# Fallback
		if not currency:
			currency = frappe.get_system_settings('currency')

		msg = _("Total cost ({0}) exceeds estimated cost ({1}) for BOQ Item {2}").format(
			frappe.format(new_total_cost, currency=currency),
			frappe.format(boq_item.total_estimated_cost, currency=currency),
			boq_item.name
		)
		warnings.append(msg)
		errors.append(msg)
		
	return Result(len(warnings) > 0, warnings, len(errors) > 0, errors)


def validate_total_cost(estimated: float, incurred: float, new_cost: float) -> Optional[str]:
	"""
	Validate total cost against estimate.
	"""
	if estimated <= 0:
		return None
		
	if (flt(incurred) + flt(new_cost)) > flt(estimated):
		return _("Total cost exceeds estimated cost")
	return None


def validate_component_costs(boq_doc: Any, incurred: dict, new_costs: dict) -> List[str]:
	"""
	Validate component costs and return warnings.
	"""
	warnings = []
	components = {
		"material": ("estimated_material_cost", "material_cost", "Material"),
		"labour": ("estimated_labour_cost", "labour_cost", "Labour"),
		"subcontract": ("estimated_subcontract_cost", "subcontract_cost", "Subcontract"),
		"asset": ("estimated_asset_cost", "asset_cost", "Asset"),
		"other": ("estimated_other_cost", "expense_cost", "Other")
	}
	
	for key, (est_field, new_field, label) in components.items():
		est_val = flt(boq_doc.get(est_field))
		if est_val > 0:
			curr_incurred = flt(incurred.get(key, 0))
			new_val = flt(new_costs.get(new_field, 0))
			if (curr_incurred + new_val) > est_val:
				warnings.append(_("{0} cost exceeds estimate").format(label))
				
	return warnings


def get_incurred_costs(boq_item: str) -> dict:
	"""
	Get accumulated costs per component.
	"""
	# Placeholder implementation
	return {
		"material": 0,
		"labour": 0,
		"subcontract": 0,
		"asset": 0,
		"other": 0
	}
