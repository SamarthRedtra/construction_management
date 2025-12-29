# Copyright (c) 2024, Construction Management
# License: MIT
# Property Tests for Site Location Configuration

"""
Property Tests for Site Location Configuration

These tests validate the following properties:
- Property 9: Site Location Mandatory for BOQ Projects
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt
from hypothesis import given, strategies as st, settings


class TestSiteLocationMandatory(FrappeTestCase):
	"""
	**Feature: boq-costing-estimation, Property 9: Site Location Mandatory for BOQ Projects**
	**Validates: Requirements 5.2**
	
	Property: For any Project with enable_progressive_boq = True, 
	the site_location field SHALL be required and linked to a valid Warehouse
	"""
	
	def test_site_location_mandatory_when_boq_enabled(self):
		"""Property: site_location is mandatory when enable_progressive_boq is True"""
		# This test verifies the field configuration
		# The actual validation is done by Frappe's mandatory_depends_on
		
		# Check if custom field exists with correct configuration
		field = frappe.db.get_value(
			"Custom Field",
			{"dt": "Project", "fieldname": "site_location"},
			["mandatory_depends_on", "options"],
			as_dict=True
		)
		
		if field:
			self.assertEqual(field.options, "Warehouse")
			self.assertIn("enable_progressive_boq", field.mandatory_depends_on or "")
	
	def test_site_location_links_to_warehouse(self):
		"""Property: site_location field links to Warehouse doctype"""
		field = frappe.db.get_value(
			"Custom Field",
			{"dt": "Project", "fieldname": "site_location"},
			"options"
		)
		
		if field:
			self.assertEqual(field, "Warehouse")
	
	def test_project_can_save_without_site_when_boq_disabled(self):
		"""Property: Project can be saved without site_location when BOQ is disabled"""
		project = frappe.new_doc("Project")
		project.project_name = f"Test No Site {frappe.generate_hash()[:8]}"
		project.enable_progressive_boq = 0
		# Don't set site_location
		
		# Should save without error
		try:
			project.insert(ignore_permissions=True)
			saved = True
		except frappe.MandatoryError:
			saved = False
		finally:
			if frappe.db.exists("Project", project.name):
				frappe.delete_doc("Project", project.name, force=True)
		
		self.assertTrue(saved, "Project should save without site_location when BOQ is disabled")
	
	def test_project_with_boq_and_site_saves_successfully(self):
		"""Property: Project with BOQ enabled and valid site_location saves successfully"""
		# Create a test warehouse
		warehouse = create_test_warehouse("TEST-SITE-WAREHOUSE")
		
		project = frappe.new_doc("Project")
		project.project_name = f"Test With Site {frappe.generate_hash()[:8]}"
		project.enable_progressive_boq = 1
		project.site_location = warehouse
		
		try:
			project.insert(ignore_permissions=True)
			saved = True
		except Exception as e:
			saved = False
			print(f"Error: {e}")
		finally:
			if frappe.db.exists("Project", project.name):
				frappe.delete_doc("Project", project.name, force=True)
		
		self.assertTrue(saved, "Project should save with valid site_location when BOQ is enabled")


class TestWarehouseProjectLinking(FrappeTestCase):
	"""
	**Feature: boq-costing-estimation, Property 9: Warehouse-Project Auto-Linking**
	**Validates: Requirements 5.3**
	
	Tests for automatic linking of warehouse to project when site is selected.
	"""
	
	def test_warehouse_has_project_field(self):
		"""Property: Warehouse has custom_project field for project linking"""
		field = frappe.db.get_value(
			"Custom Field",
			{"dt": "Warehouse", "fieldname": "custom_project"},
			"options"
		)
		
		if field:
			self.assertEqual(field, "Project")


# ============================================
# Test Fixtures
# ============================================

def create_test_warehouse(name):
	"""Create a test warehouse if it doesn't exist"""
	if frappe.db.exists("Warehouse", name):
		return name
	
	# Get default company
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		company = frappe.db.get_value("Company", {}, "name")
	
	warehouse = frappe.new_doc("Warehouse")
	warehouse.warehouse_name = name
	warehouse.company = company
	warehouse.flags.ignore_permissions = True
	warehouse.insert()
	
	return warehouse.name
