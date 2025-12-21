# Copyright (c) 2024, Construction Management
# License: MIT
"""
Employee Rate Cache - Optimized daily rate lookup for DPR entries.

This module provides a cached lookup for employee daily rates to minimize
database queries during DPR creation. The cache is refreshed daily via
a scheduled job.

Rate calculation priority:
1. Salary Structure Assignment (base + variable)
2. Salary Structure (sum of fixed earnings)
3. Manual entry required (returns 0)
"""

import frappe
from frappe import _
from frappe.utils import flt, today, cint
import json


# Cache key for storing employee rates in frappe.cache
EMPLOYEE_RATE_CACHE_KEY = "employee_daily_rates"


def get_employee_rate_from_cache(employee: str) -> float:
	"""
	Get employee daily rate from cache. Fast lookup with no DB queries.
	
	Args:
		employee: Employee ID
		
	Returns:
		Daily rate or 0 if not found
	"""
	cache = frappe.cache()
	rates = cache.get_value(EMPLOYEE_RATE_CACHE_KEY)
	
	if rates and employee in rates:
		return flt(rates[employee].get("rate_per_day", 0))
	
	return 0


def get_all_employee_rates_from_cache() -> dict:
	"""
	Get all employee rates from cache.
	
	Returns:
		Dict of employee rates {employee_id: {rate_per_day, employee_name, ...}}
	"""
	cache = frappe.cache()
	rates = cache.get_value(EMPLOYEE_RATE_CACHE_KEY)
	return rates or {}


@frappe.whitelist()
def get_employee_rate_optimized(employee: str) -> dict:
	"""
	Get employee daily rate with optimized lookup.
	
	Priority:
	1. Cache lookup (fastest)
	2. Salary Structure Assignment (base + variable)
	3. Salary Structure (sum of fixed earnings)
	4. Returns 0 (manual entry required)
	
	Args:
		employee: Employee ID
		
	Returns:
		dict with employee details and rate
	"""
	# Try cache first
	cached_rate = get_employee_rate_from_cache(employee)
	
	# Get employee details
	emp = frappe.db.get_value(
		"Employee", 
		employee, 
		["name", "employee_name", "designation"],
		as_dict=True
	)
	
	if not emp:
		frappe.throw(_("Employee {0} not found").format(employee))
	
	# If cache has rate, return it
	if cached_rate > 0:
		return {
			"name": emp.name,
			"employee_name": emp.employee_name,
			"designation": emp.designation,
			"rate_per_day": cached_rate,
			"source": "cache"
		}
	
	# Cache miss or zero rate - calculate fresh
	rate, source = calculate_employee_daily_rate(employee)
	
	return {
		"name": emp.name,
		"employee_name": emp.employee_name,
		"designation": emp.designation,
		"rate_per_day": rate,
		"source": source
	}


def calculate_employee_daily_rate(employee: str) -> tuple:
	"""
	Calculate employee daily rate from Salary Structure Assignment or Salary Structure.
	
	Args:
		employee: Employee ID
		
	Returns:
		tuple: (rate_per_day, source)
	"""
	# Step 1: Try Salary Structure Assignment (base + variable)
	ssa = frappe.db.get_value(
		"Salary Structure Assignment",
		{
			"employee": employee,
			"docstatus": 1
		},
		["base", "variable", "salary_structure"],
		as_dict=True,
		order_by="from_date desc"
	)
	
	if ssa:
		monthly_salary = flt(ssa.base) + flt(ssa.variable)
		if monthly_salary > 0:
			return (monthly_salary / 30, "salary_structure_assignment")
		
		# Step 2: SSA exists but base/variable is 0 - check Salary Structure
		if ssa.salary_structure:
			ss_total = get_salary_structure_total(ssa.salary_structure)
			if ss_total > 0:
				return (ss_total / 30, "salary_structure")
	
	# Step 3: No SSA - try to find Salary Structure directly
	# Get the latest salary structure for this employee
	salary_structure = frappe.db.get_value(
		"Salary Structure Assignment",
		{"employee": employee},
		"salary_structure",
		order_by="from_date desc"
	)
	
	if salary_structure:
		ss_total = get_salary_structure_total(salary_structure)
		if ss_total > 0:
			return (ss_total / 30, "salary_structure")
	
	# No rate found - manual entry required
	return (0, "manual_required")


def get_salary_structure_total(salary_structure: str) -> float:
	"""
	Get total of fixed earnings from a Salary Structure.
	
	Args:
		salary_structure: Salary Structure name
		
	Returns:
		Total monthly amount from fixed earnings
	"""
	# Get all earning components with fixed amounts
	earnings = frappe.db.sql("""
		SELECT 
			COALESCE(SUM(
				CASE 
					WHEN amount_based_on_formula = 0 THEN COALESCE(amount, 0)
					ELSE 0
				END
			), 0) as total
		FROM `tabSalary Detail`
		WHERE parent = %s
		AND parentfield = 'earnings'
	""", salary_structure)
	
	return flt(earnings[0][0]) if earnings else 0


def refresh_employee_rate_cache():
	"""
	Refresh the employee rate cache. Called by daily scheduled job.
	
	This function:
	1. Gets all active employees
	2. Calculates their daily rates
	3. Stores in Redis cache
	"""
	frappe.logger().info("Starting employee rate cache refresh...")
	
	# Get all active employees
	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "employee_name", "designation"]
	)
	
	rates = {}
	
	for emp in employees:
		rate, source = calculate_employee_daily_rate(emp.name)
		rates[emp.name] = {
			"employee_name": emp.employee_name,
			"designation": emp.designation,
			"rate_per_day": rate,
			"source": source,
			"updated_on": str(today())
		}
	
	# Store in cache (expires in 25 hours to ensure daily refresh covers it)
	cache = frappe.cache()
	cache.set_value(EMPLOYEE_RATE_CACHE_KEY, rates, expires_in_sec=90000)
	
	frappe.logger().info(f"Employee rate cache refreshed. {len(rates)} employees cached.")
	
	return rates


@frappe.whitelist()
def force_refresh_cache():
	"""
	Force refresh the employee rate cache. Can be called manually.
	"""
	frappe.only_for(["System Manager", "HR Manager"])
	rates = refresh_employee_rate_cache()
	frappe.msgprint(_("Employee rate cache refreshed. {0} employees updated.").format(len(rates)))
	return rates


@frappe.whitelist()
def get_cache_status() -> dict:
	"""
	Get the current status of the employee rate cache.
	
	Returns:
		dict with cache status info
	"""
	cache = frappe.cache()
	rates = cache.get_value(EMPLOYEE_RATE_CACHE_KEY)
	
	if not rates:
		return {
			"status": "empty",
			"count": 0,
			"message": "Cache is empty. Run refresh to populate."
		}
	
	# Get sample of rates
	sample = list(rates.items())[:5]
	
	return {
		"status": "populated",
		"count": len(rates),
		"sample": sample,
		"message": f"Cache has {len(rates)} employees"
	}


# Scheduled job function
def daily_refresh_employee_rates():
	"""
	Daily scheduled job to refresh employee rate cache.
	Called from hooks.py scheduler_events.
	"""
	try:
		refresh_employee_rate_cache()
	except Exception as e:
		frappe.log_error(f"Error refreshing employee rate cache: {str(e)}")
