# Copyright (c) 2024, Construction Management
# License: MIT

"""
Asset Billing Calculator

This module provides methods to calculate asset costs based on billing frequency.

Properties validated:
- Property 7: Asset Billing Frequency Rate Selection
- Property 8: Monthly Asset Cost Proration
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today, get_first_day, get_last_day
import calendar
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class AssetBillingRate:
	"""Asset billing rate information"""
	frequency: str
	rate: float
	value_per_hour: float
	value_per_day: float
	value_per_month: float


def get_billing_rate(project: str, asset: str, date: str = None) -> AssetBillingRate:
	"""
	Get the billing rate for an asset in a project based on configured frequency.
	
	Property 7: The rate used SHALL match the billing_frequency configured:
	- Hourly uses value_per_hour
	- Daily uses value_per_day
	- Monthly uses value_per_month
	
	Args:
		project: Project name
		asset: Asset name
		date: Date to check (defaults to today)
		
	Returns:
		AssetBillingRate with frequency and rate information
	"""
	check_date = getdate(date) if date else getdate(today())
	
	# Find applicable billing configuration
	billing = frappe.db.sql("""
		SELECT billing_frequency, value_per_hour, value_per_day, value_per_month
		FROM `tabProject Asset Billing`
		WHERE project = %s AND asset = %s
		AND (effective_from IS NULL OR effective_from <= %s)
		AND (effective_to IS NULL OR effective_to >= %s)
		ORDER BY effective_from DESC
		LIMIT 1
	""", (project, asset, check_date, check_date), as_dict=True)
	
	if not billing:
		# Return default hourly with zero rate
		return AssetBillingRate(
			frequency="Hourly",
			rate=0,
			value_per_hour=0,
			value_per_day=0,
			value_per_month=0
		)
	
	b = billing[0]
	frequency = b.billing_frequency or "Hourly"
	
	# Select rate based on frequency
	if frequency == "Hourly":
		rate = flt(b.value_per_hour)
	elif frequency == "Daily":
		rate = flt(b.value_per_day)
	elif frequency == "Monthly":
		rate = flt(b.value_per_month)
	else:
		rate = flt(b.value_per_hour)  # Default to hourly
	
	return AssetBillingRate(
		frequency=frequency,
		rate=rate,
		value_per_hour=flt(b.value_per_hour),
		value_per_day=flt(b.value_per_day),
		value_per_month=flt(b.value_per_month)
	)


def calculate_cost(rate: float, frequency: str, usage: float, date: str = None) -> float:
	"""
	Calculate asset cost based on frequency and usage.
	
	Args:
		rate: The rate value (per hour/day/month)
		frequency: Billing frequency (Hourly, Daily, Monthly)
		usage: Usage amount (hours for Hourly, days for Daily/Monthly)
		date: Date for monthly proration calculation
		
	Returns:
		Calculated cost
	"""
	if frequency == "Hourly":
		return flt(rate) * flt(usage)
	elif frequency == "Daily":
		return flt(rate) * flt(usage)
	elif frequency == "Monthly":
		# For monthly, usage represents days used
		return get_prorated_monthly_cost(rate, int(usage), date)
	else:
		return flt(rate) * flt(usage)


def get_prorated_monthly_cost(monthly_rate: float, days_used: int, date: str = None) -> float:
	"""
	Calculate prorated monthly cost based on days used.
	
	Property 8: For any asset with Monthly billing frequency,
	the cost SHALL equal (value_per_month / days_in_month) × days_used
	
	Args:
		monthly_rate: Monthly rate value
		days_used: Number of days the asset was used
		date: Date to determine the month (defaults to today)
		
	Returns:
		Prorated cost
	"""
	if not monthly_rate or days_used <= 0:
		return 0
	
	check_date = getdate(date) if date else getdate(today())
	
	# Get days in the month
	days_in_month = calendar.monthrange(check_date.year, check_date.month)[1]
	
	# Calculate prorated cost
	daily_rate = flt(monthly_rate) / days_in_month
	return flt(daily_rate) * days_used


def calculate_asset_cost_for_dpr(
	project: str, 
	asset: str, 
	hours: float = None, 
	date: str = None
) -> Tuple[float, str, float]:
	"""
	Calculate asset cost for DPR entry based on billing configuration.
	
	Args:
		project: Project name
		asset: Asset name
		hours: Hours used (for hourly billing)
		date: Date of usage
		
	Returns:
		Tuple of (cost, frequency, rate_used)
	"""
	billing = get_billing_rate(project, asset, date)
	
	if billing.frequency == "Hourly":
		# Use hours directly
		usage = flt(hours) or 8  # Default to 8 hours
		cost = calculate_cost(billing.rate, billing.frequency, usage)
		return (cost, billing.frequency, billing.rate)
	
	elif billing.frequency == "Daily":
		# Convert hours to days (8 hours = 1 day)
		days = (flt(hours) or 8) / 8
		cost = calculate_cost(billing.rate, billing.frequency, days)
		return (cost, billing.frequency, billing.rate)
	
	elif billing.frequency == "Monthly":
		# For monthly, calculate prorated cost for 1 day
		cost = get_prorated_monthly_cost(billing.rate, 1, date)
		return (cost, billing.frequency, billing.rate)
	
	return (0, billing.frequency, 0)


@frappe.whitelist()
def get_asset_rate_for_dpr(project: str, asset: str, date: str = None) -> dict:
	"""
	API endpoint to get asset rate information for DPR.
	
	Args:
		project: Project name
		asset: Asset name
		date: Date of usage
		
	Returns:
		Dict with rate information
	"""
	billing = get_billing_rate(project, asset, date)
	
	return {
		"frequency": billing.frequency,
		"rate": billing.rate,
		"value_per_hour": billing.value_per_hour,
		"value_per_day": billing.value_per_day,
		"value_per_month": billing.value_per_month
	}


@frappe.whitelist()
def calculate_dpr_asset_cost(
	project: str, 
	asset: str, 
	hours: float = None, 
	date: str = None
) -> dict:
	"""
	API endpoint to calculate asset cost for DPR.
	
	Args:
		project: Project name
		asset: Asset name
		hours: Hours used
		date: Date of usage
		
	Returns:
		Dict with cost calculation details
	"""
	cost, frequency, rate = calculate_asset_cost_for_dpr(project, asset, hours, date)
	
	return {
		"cost": cost,
		"frequency": frequency,
		"rate_used": rate,
		"hours": hours
	}


# Backward compatibility functions
@frappe.whitelist()
def get_asset_hourly_rate(project: str, asset: str, date: str = None) -> float:
	"""
	Get the hourly rate for an asset in a project.
	Backward compatible - returns hourly rate regardless of frequency setting.
	
	Args:
		project: Project name
		asset: Asset name
		date: Date to check (defaults to today)
		
	Returns:
		Hourly rate value
	"""
	billing = get_billing_rate(project, asset, date)
	return billing.value_per_hour


@frappe.whitelist()
def get_asset_daily_rate(project: str, asset: str, date: str = None) -> float:
	"""
	Get the daily rate for an asset in a project.
	Backward compatible - returns daily rate or hourly × 8.
	
	Args:
		project: Project name
		asset: Asset name
		date: Date to check (defaults to today)
		
	Returns:
		Daily rate value
	"""
	billing = get_billing_rate(project, asset, date)
	
	if billing.value_per_day:
		return billing.value_per_day
	
	# Fall back to hourly × 8
	return flt(billing.value_per_hour) * 8
