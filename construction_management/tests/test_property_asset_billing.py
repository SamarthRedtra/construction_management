# Copyright (c) 2024, Construction Management
# License: MIT
# Property Tests for Asset Billing

"""
Property Tests for Asset Billing Frequency

These tests validate the following properties:
- Property 7: Asset Billing Frequency Rate Selection
- Property 8: Monthly Asset Cost Proration
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, getdate, today
from hypothesis import given, strategies as st, settings
import calendar

from construction_management.api.asset_billing import (
	get_billing_rate,
	calculate_cost,
	get_prorated_monthly_cost,
	calculate_asset_cost_for_dpr,
	AssetBillingRate
)


class TestAssetBillingFrequencyRateSelection(FrappeTestCase):
	"""
	**Feature: boq-costing-estimation, Property 7: Asset Billing Frequency Rate Selection**
	**Validates: Requirements 4.2, 4.3, 4.4**
	
	Property: For any asset in DPR, the rate used SHALL match the billing_frequency 
	configured in Project Asset Billing:
	- Hourly uses value_per_hour
	- Daily uses value_per_day
	- Monthly uses value_per_month
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-ASSET-BILLING-PROJECT")
		cls.test_asset = create_test_asset("TEST-ASSET-001")
	
	def test_hourly_frequency_uses_hourly_rate(self):
		"""Property: Hourly frequency returns value_per_hour"""
		# Create billing with hourly frequency
		billing = create_asset_billing(
			self.test_project, self.test_asset,
			frequency="Hourly",
			hourly_rate=100,
			daily_rate=700,
			monthly_rate=15000
		)
		
		rate_info = get_billing_rate(self.test_project, self.test_asset)
		
		self.assertEqual(rate_info.frequency, "Hourly")
		self.assertEqual(rate_info.rate, 100)
		
		# Cleanup
		frappe.delete_doc("Project Asset Billing", billing, force=True)
	
	def test_daily_frequency_uses_daily_rate(self):
		"""Property: Daily frequency returns value_per_day"""
		billing = create_asset_billing(
			self.test_project, self.test_asset,
			frequency="Daily",
			hourly_rate=100,
			daily_rate=700,
			monthly_rate=15000
		)
		
		rate_info = get_billing_rate(self.test_project, self.test_asset)
		
		self.assertEqual(rate_info.frequency, "Daily")
		self.assertEqual(rate_info.rate, 700)
		
		# Cleanup
		frappe.delete_doc("Project Asset Billing", billing, force=True)
	
	def test_monthly_frequency_uses_monthly_rate(self):
		"""Property: Monthly frequency returns value_per_month"""
		billing = create_asset_billing(
			self.test_project, self.test_asset,
			frequency="Monthly",
			hourly_rate=100,
			daily_rate=700,
			monthly_rate=15000
		)
		
		rate_info = get_billing_rate(self.test_project, self.test_asset)
		
		self.assertEqual(rate_info.frequency, "Monthly")
		self.assertEqual(rate_info.rate, 15000)
		
		# Cleanup
		frappe.delete_doc("Project Asset Billing", billing, force=True)
	
	@given(
		hourly_rate=st.floats(min_value=10, max_value=1000, allow_nan=False, allow_infinity=False),
		daily_rate=st.floats(min_value=50, max_value=5000, allow_nan=False, allow_infinity=False),
		monthly_rate=st.floats(min_value=1000, max_value=50000, allow_nan=False, allow_infinity=False),
		frequency=st.sampled_from(["Hourly", "Daily", "Monthly"])
	)
	@settings(max_examples=100, deadline=None)
	def test_rate_selection_matches_frequency(self, hourly_rate, daily_rate, monthly_rate, frequency):
		"""Property: Selected rate always matches configured frequency"""
		billing = create_asset_billing(
			self.test_project, self.test_asset,
			frequency=frequency,
			hourly_rate=hourly_rate,
			daily_rate=daily_rate,
			monthly_rate=monthly_rate
		)
		
		rate_info = get_billing_rate(self.test_project, self.test_asset)
		
		expected_rate = {
			"Hourly": hourly_rate,
			"Daily": daily_rate,
			"Monthly": monthly_rate
		}[frequency]
		
		self.assertEqual(rate_info.frequency, frequency)
		self.assertAlmostEqual(rate_info.rate, expected_rate, places=2)
		
		# Cleanup
		frappe.delete_doc("Project Asset Billing", billing, force=True)
	
	def test_no_billing_returns_zero_rate(self):
		"""Property: No billing configuration returns zero rate"""
		# Use a different asset with no billing
		test_asset_2 = create_test_asset("TEST-ASSET-NO-BILLING")
		
		rate_info = get_billing_rate(self.test_project, test_asset_2)
		
		self.assertEqual(rate_info.frequency, "Hourly")  # Default
		self.assertEqual(rate_info.rate, 0)
		
		# Cleanup
		frappe.delete_doc("Asset", test_asset_2, force=True)


class TestMonthlyAssetCostProration(FrappeTestCase):
	"""
	**Feature: boq-costing-estimation, Property 8: Monthly Asset Cost Proration**
	**Validates: Requirements 4.4**
	
	Property: For any asset with Monthly billing frequency,
	the cost SHALL equal (value_per_month / days_in_month) × days_used
	"""
	
	def test_monthly_proration_formula(self):
		"""Property: Monthly cost = (monthly_rate / days_in_month) × days_used"""
		monthly_rate = 30000
		days_used = 15
		
		# Use a specific date to know days in month
		test_date = "2024-01-15"  # January has 31 days
		
		cost = get_prorated_monthly_cost(monthly_rate, days_used, test_date)
		
		expected_daily_rate = monthly_rate / 31
		expected_cost = expected_daily_rate * days_used
		
		self.assertAlmostEqual(cost, expected_cost, places=2)
	
	def test_monthly_proration_february_leap_year(self):
		"""Property: Proration accounts for leap year February (29 days)"""
		monthly_rate = 29000
		days_used = 29
		
		test_date = "2024-02-15"  # 2024 is leap year, Feb has 29 days
		
		cost = get_prorated_monthly_cost(monthly_rate, days_used, test_date)
		
		# Full month should equal monthly rate
		expected_cost = monthly_rate  # 29000 / 29 * 29 = 29000
		
		self.assertAlmostEqual(cost, expected_cost, places=2)
	
	def test_monthly_proration_february_non_leap_year(self):
		"""Property: Proration accounts for non-leap year February (28 days)"""
		monthly_rate = 28000
		days_used = 28
		
		test_date = "2023-02-15"  # 2023 is not leap year, Feb has 28 days
		
		cost = get_prorated_monthly_cost(monthly_rate, days_used, test_date)
		
		# Full month should equal monthly rate
		expected_cost = monthly_rate
		
		self.assertAlmostEqual(cost, expected_cost, places=2)
	
	@given(
		monthly_rate=st.floats(min_value=1000, max_value=100000, allow_nan=False, allow_infinity=False),
		days_used=st.integers(min_value=1, max_value=31),
		month=st.integers(min_value=1, max_value=12),
		year=st.integers(min_value=2020, max_value=2030)
	)
	@settings(max_examples=100, deadline=None)
	def test_monthly_proration_property(self, monthly_rate, days_used, month, year):
		"""Property: Prorated cost follows formula for any month/year"""
		# Ensure days_used doesn't exceed days in month
		days_in_month = calendar.monthrange(year, month)[1]
		days_used = min(days_used, days_in_month)
		
		test_date = f"{year}-{month:02d}-15"
		
		cost = get_prorated_monthly_cost(monthly_rate, days_used, test_date)
		
		expected_daily_rate = monthly_rate / days_in_month
		expected_cost = expected_daily_rate * days_used
		
		self.assertAlmostEqual(cost, expected_cost, places=2,
			msg=f"Failed for {year}-{month}: rate={monthly_rate}, days={days_used}/{days_in_month}")
	
	def test_monthly_proration_zero_days(self):
		"""Property: Zero days used returns zero cost"""
		cost = get_prorated_monthly_cost(30000, 0, "2024-01-15")
		self.assertEqual(cost, 0)
	
	def test_monthly_proration_zero_rate(self):
		"""Property: Zero rate returns zero cost"""
		cost = get_prorated_monthly_cost(0, 15, "2024-01-15")
		self.assertEqual(cost, 0)
	
	def test_monthly_proration_full_month(self):
		"""Property: Full month usage equals monthly rate"""
		monthly_rate = 30000
		
		# Test for different months
		test_cases = [
			("2024-01-15", 31),  # January
			("2024-04-15", 30),  # April
			("2024-02-15", 29),  # February leap year
		]
		
		for test_date, days_in_month in test_cases:
			cost = get_prorated_monthly_cost(monthly_rate, days_in_month, test_date)
			self.assertAlmostEqual(cost, monthly_rate, places=2,
				msg=f"Full month cost should equal monthly rate for {test_date}")


class TestCalculateCostByFrequency(FrappeTestCase):
	"""
	**Feature: boq-costing-estimation, Property 7 & 8: Cost Calculation by Frequency**
	**Validates: Requirements 4.2, 4.3, 4.4**
	
	Integration tests for cost calculation based on frequency.
	"""
	
	def test_hourly_cost_calculation(self):
		"""Property: Hourly cost = rate × hours"""
		rate = 100
		hours = 8
		
		cost = calculate_cost(rate, "Hourly", hours)
		
		self.assertEqual(cost, 800)
	
	def test_daily_cost_calculation(self):
		"""Property: Daily cost = rate × days"""
		rate = 700
		days = 2
		
		cost = calculate_cost(rate, "Daily", days)
		
		self.assertEqual(cost, 1400)
	
	def test_monthly_cost_calculation(self):
		"""Property: Monthly cost uses proration"""
		rate = 31000
		days = 10
		
		cost = calculate_cost(rate, "Monthly", days, "2024-01-15")
		
		# 31000 / 31 days × 10 days = 10000
		expected = (31000 / 31) * 10
		self.assertAlmostEqual(cost, expected, places=2)
	
	@given(
		rate=st.floats(min_value=10, max_value=10000, allow_nan=False, allow_infinity=False),
		usage=st.floats(min_value=1, max_value=24, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=100, deadline=None)
	def test_hourly_cost_formula(self, rate, usage):
		"""Property: Hourly cost = rate × usage for any values"""
		cost = calculate_cost(rate, "Hourly", usage)
		expected = rate * usage
		self.assertAlmostEqual(cost, expected, places=2)
	
	@given(
		rate=st.floats(min_value=100, max_value=10000, allow_nan=False, allow_infinity=False),
		usage=st.floats(min_value=0.5, max_value=7, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=100, deadline=None)
	def test_daily_cost_formula(self, rate, usage):
		"""Property: Daily cost = rate × usage for any values"""
		cost = calculate_cost(rate, "Daily", usage)
		expected = rate * usage
		self.assertAlmostEqual(cost, expected, places=2)


# ============================================
# Test Fixtures
# ============================================

def create_test_project(name):
	"""Create a test project if it doesn't exist"""
	if frappe.db.exists("Project", name):
		return name
	
	project = frappe.new_doc("Project")
	project.project_name = name
	project.insert(ignore_permissions=True)
	return project.name


def create_test_asset(name):
	"""Create a test asset if it doesn't exist"""
	if frappe.db.exists("Asset", name):
		return name
	
	# Get or create required dependencies
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		company = frappe.db.get_value("Company", {}, "name")
	
	# Get or create asset category
	asset_category = frappe.db.get_value("Asset Category", {}, "name")
	if not asset_category:
		# Create a simple asset category
		cat = frappe.new_doc("Asset Category")
		cat.asset_category_name = "Test Category"
		cat.insert(ignore_permissions=True)
		asset_category = cat.name
	
	# Get fixed asset account
	fixed_asset_account = frappe.db.get_value(
		"Account",
		{"company": company, "account_type": "Fixed Asset", "is_group": 0},
		"name"
	)
	
	asset = frappe.new_doc("Asset")
	asset.asset_name = name
	asset.item_code = name
	asset.company = company
	asset.asset_category = asset_category
	asset.location = "Test Location"
	asset.purchase_date = today()
	asset.gross_purchase_amount = 100000
	asset.available_for_use_date = today()
	
	# Set status to allow creation
	asset.flags.ignore_validate = True
	asset.flags.ignore_mandatory = True
	asset.insert(ignore_permissions=True)
	
	return asset.name


def create_asset_billing(project, asset, frequency="Hourly", 
						 hourly_rate=0, daily_rate=0, monthly_rate=0):
	"""Create a Project Asset Billing entry"""
	# Delete existing if any
	existing = frappe.db.get_value(
		"Project Asset Billing",
		{"project": project, "asset": asset, "effective_to": ["is", "not set"]}
	)
	if existing:
		frappe.delete_doc("Project Asset Billing", existing, force=True)
	
	billing = frappe.new_doc("Project Asset Billing")
	billing.project = project
	billing.asset = asset
	billing.billing_frequency = frequency
	billing.value_per_hour = hourly_rate
	billing.value_per_day = daily_rate
	billing.value_per_month = monthly_rate
	billing.effective_from = today()
	billing.insert(ignore_permissions=True)
	
	return billing.name
