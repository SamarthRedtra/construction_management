# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today


class ProjectAssetBilling(Document):
	def validate(self):
		self.validate_dates()
		self.validate_duplicate()
	
	def validate_dates(self):
		"""Validate effective dates"""
		if self.effective_from and self.effective_to:
			if getdate(self.effective_from) > getdate(self.effective_to):
				frappe.throw(_("Effective From date cannot be after Effective To date"))
	
	def validate_duplicate(self):
		"""Check for duplicate active entries"""
		if self.effective_to:
			return  # Has end date, allow
		
		# Check for existing active entry without end date
		existing = frappe.db.exists(
			"Project Asset Billing",
			{
				"project": self.project,
				"asset": self.asset,
				"effective_to": ["is", "not set"],
				"name": ["!=", self.name]
			}
		)
		if existing:
			frappe.throw(
				_("An active billing rate already exists for Asset {0} in Project {1}. Please set an end date on the existing entry first.").format(
					self.asset, self.project
				)
			)


@frappe.whitelist()
def get_asset_hourly_rate(project: str, asset: str, date: str = None) -> float:
	"""
	Get the hourly rate for an asset in a project.
	
	Args:
		project: Project name
		asset: Asset name
		date: Date to check (defaults to today)
		
	Returns:
		Hourly rate value
	"""
	check_date = getdate(date) if date else getdate(today())
	
	# Find applicable rate
	rate = frappe.db.sql("""
		SELECT value_per_hour
		FROM `tabProject Asset Billing`
		WHERE project = %s AND asset = %s
		AND (effective_from IS NULL OR effective_from <= %s)
		AND (effective_to IS NULL OR effective_to >= %s)
		ORDER BY effective_from DESC
		LIMIT 1
	""", (project, asset, check_date, check_date))
	
	return flt(rate[0][0]) if rate else 0


@frappe.whitelist()
def get_asset_daily_rate(project: str, asset: str, date: str = None) -> float:
	"""
	Get the daily rate for an asset in a project (backward compatibility).
	Calculates as hourly_rate × 8 hours.
	
	Args:
		project: Project name
		asset: Asset name
		date: Date to check (defaults to today)
		
	Returns:
		Daily rate value (hourly × 8)
	"""
	return frappe.db.get_value(
		"Project Asset Billing",
		{
			"project": project,
			"asset": asset,
			"(effective_from IS NULL OR effective_from <= %s)": date or today(),
			"(effective_to IS NULL OR effective_to >= %s)": date or today(),
		},
		"value_per_day",
		order_by="effective_from DESC",
  	)
