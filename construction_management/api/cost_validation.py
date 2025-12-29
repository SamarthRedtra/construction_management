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
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ValidationResult:
	"""Result of cost validation"""
	is_valid: bool
	errors: List[str]  # Blocking errors (total cost overrun)
	warnings: List[str]  # Non-blocking warnings (component overruns)
	
	@property
	def has_errors(self) -> bool:
		return len(self.errors) > 0
	
	@property
	def has_warnings(self) -> bool:
		return len(self.warnings) > 0


def validate_dpr_costs(boq_item: str, dpr_costs: dict, exclude_dpr: str = None) -> ValidationResult:
	"""
	Validate DPR costs against BOQ Item estimated costs.
	
	Args:
		boq_item: BOQ Item name
		dpr_costs: Dict with cost components (material_cost, labour_cost, etc.)
		exclude_dpr: DPR name to exclude from incurred calculation (for updates)
	
	Returns:
		ValidationResult with errors and warnings
	"""
	errors = []
	warnings = []
	
	# Get BOQ Item estimated costs
	boq_doc = frappe.get_doc("BOQ Item", boq_item)
	
	# Check if estimates exist
	total_estimated = flt(boq_doc.total_estimated_cost)
	if total_estimated <= 0:
		# No estimates defined, skip validation (Requirement 3.5)
		return ValidationResult(is_valid=True, errors=[], warnings=[])
	
	# Get current incurred costs (excluding the DPR being validated if updating)
	incurred = get_incurred_costs(boq_item, exclude_dpr)
	
	# Validate total cost (Property 5)
	total_error = validate_total_cost(
		estimated=total_estimated,
		current_incurred=flt(incurred["total"]),
		new_cost=flt(dpr_costs.get("total_cost", 0))
	)
	if total_error:
		errors.append(total_error)
	
	# Validate component costs (Property 6)
	component_warnings = validate_component_costs(
		boq_doc=boq_doc,
		incurred=incurred,
		new_costs=dpr_costs
	)
	warnings.extend(component_warnings)
	
	return ValidationResult(
		is_valid=len(errors) == 0,
		errors=errors,
		warnings=warnings
	)


def validate_total_cost(estimated: float, current_incurred: float, new_cost: float) -> Optional[str]:
	"""
	Validate that total cost doesn't exceed estimate.
	
	Property 5: For any DPR submission against a BOQ Item with estimated costs,
	if (current_incurred + new_dpr_cost) > total_estimated_cost, 
	the submission SHALL be rejected.
	
	Args:
		estimated: Total estimated cost
		current_incurred: Already incurred cost
		new_cost: New DPR cost being added
	
	Returns:
		Error message if validation fails, None otherwise
	"""
	if estimated <= 0:
		return None  # No estimate, skip validation
	
	projected_total = flt(current_incurred) + flt(new_cost)
	
	if projected_total > estimated:
		overrun = projected_total - estimated
		return _(
			"Total cost ({0}) exceeds estimate ({1}) by {2}. "
			"Current incurred: {3}, New DPR cost: {4}"
		).format(
			frappe.format_value(projected_total, {"fieldtype": "Currency"}),
			frappe.format_value(estimated, {"fieldtype": "Currency"}),
			frappe.format_value(overrun, {"fieldtype": "Currency"}),
			frappe.format_value(current_incurred, {"fieldtype": "Currency"}),
			frappe.format_value(new_cost, {"fieldtype": "Currency"})
		)
	
	return None


def validate_component_costs(boq_doc, incurred: dict, new_costs: dict) -> List[str]:
	"""
	Validate individual cost components against estimates.
	
	Property 6: For any DPR submission, for each cost component,
	if (current_incurred_component + new_component_cost) > estimated_component_cost,
	a warning SHALL be generated.
	
	Args:
		boq_doc: BOQ Item document
		incurred: Dict of current incurred costs by component
		new_costs: Dict of new DPR costs by component
	
	Returns:
		List of warning messages for component overruns
	"""
	warnings = []
	
	# Component mapping: DPR field -> BOQ estimated field
	components = [
		("material_cost", "estimated_material_cost", "Material"),
		("labour_cost", "estimated_labour_cost", "Labour"),
		("subcontract_cost", "estimated_subcontract_cost", "Subcontract"),
		("asset_cost", "estimated_asset_cost", "Asset"),
		("expense_cost", "estimated_other_cost", "Other/Expense"),
	]
	
	for dpr_field, boq_field, label in components:
		estimated = flt(getattr(boq_doc, boq_field, 0))
		
		if estimated <= 0:
			continue  # No estimate for this component
		
		current = flt(incurred.get(dpr_field.replace("_cost", ""), 0))
		new = flt(new_costs.get(dpr_field, 0))
		projected = current + new
		
		if projected > estimated:
			overrun = projected - estimated
			warnings.append(_(
				"Warning: {0} cost ({1}) exceeds estimate ({2}) by {3}"
			).format(
				label,
				frappe.format_value(projected, {"fieldtype": "Currency"}),
				frappe.format_value(estimated, {"fieldtype": "Currency"}),
				frappe.format_value(overrun, {"fieldtype": "Currency"})
			))
	
	return warnings


def get_incurred_costs(boq_item: str, exclude_dpr: str = None) -> dict:
	"""
	Get total incurred costs for a BOQ Item from submitted DPRs.
	
	Args:
		boq_item: BOQ Item name
		exclude_dpr: DPR name to exclude (for updates)
	
	Returns:
		Dict with incurred costs by component
	"""
	conditions = "boq_item = %s AND docstatus = 1"
	params = [boq_item]
	
	if exclude_dpr:
		conditions += " AND name != %s"
		params.append(exclude_dpr)
	
	result = frappe.db.sql(f"""
		SELECT 
			COALESCE(SUM(material_cost), 0) as material,
			COALESCE(SUM(labour_cost), 0) as labour,
			COALESCE(SUM(subcontract_cost), 0) as subcontract,
			COALESCE(SUM(asset_cost), 0) as asset,
			COALESCE(SUM(expense_cost), 0) as other,
			COALESCE(SUM(total_cost), 0) as total
		FROM `tabDaily Progress Record`
		WHERE {conditions}
	""", params, as_dict=True)
	
	if result:
		return result[0]
	
	return {
		"material": 0,
		"labour": 0,
		"subcontract": 0,
		"asset": 0,
		"other": 0,
		"total": 0
	}


@frappe.whitelist()
def check_dpr_cost_validation(boq_item: str, dpr_costs: dict, dpr_name: str = None) -> dict:
	"""
	API endpoint to check DPR cost validation before submission.
	
	Args:
		boq_item: BOQ Item name
		dpr_costs: Dict with cost components
		dpr_name: DPR name (for updates, to exclude from calculation)
	
	Returns:
		Dict with validation result
	"""
	if isinstance(dpr_costs, str):
		import json
		dpr_costs = json.loads(dpr_costs)
	
	result = validate_dpr_costs(boq_item, dpr_costs, dpr_name)
	
	return {
		"is_valid": result.is_valid,
		"errors": result.errors,
		"warnings": result.warnings,
		"has_errors": result.has_errors,
		"has_warnings": result.has_warnings
	}
