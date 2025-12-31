# Copyright (c) 2024, Construction Management
# License: MIT

"""
Property-Based Tests for Warehouse/Site Location Stock Dimension
Tests the warehouse dimension enforcement and BOQ Settings integration.
Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
"""

import frappe
import unittest
from hypothesis import given, strategies as st, settings, assume
from frappe.utils import flt, today, add_days
from construction_management.patches.v1_0.create_warehouse_inventory_dimension import (
	validate_warehouse_dimension_setup,
	get_mandatory_warehouse_for_company,
	enforce_warehouse_in_dpr
)


class TestPropertyWarehouseDimension(unittest.TestCase):
	"""
	Property-based tests for warehouse dimension functionality.
	**Feature: warehouse-dimension, Property 7: Stock Dimension Enforcement**
	**Validates: Requirements 9.2, 9.3, 9.4, 9.5**
	"""
	
	@classmethod
	def setUpClass(cls):
		"""Set up test data"""
		cls.test_company = "Test Company WD"
		cls.test_warehouse = "Test Warehouse - TWD"
		cls.test_project = "Test Project WD"
		
		# Create test company
		if not frappe.db.exists("Company", cls.test_company):
			company = frappe.new_doc("Company")
			company.company_name = cls.test_company
			company.abbr = "TWD"
			company.default_currency = "USD"
			company.country = "United States"
			company.flags.ignore_permissions = True
			company.insert()
		
		# Create test warehouse
		if not frappe.db.exists("Warehouse", cls.test_warehouse):
			warehouse = frappe.new_doc("Warehouse")
			warehouse.warehouse_name = "Test Warehouse"
			warehouse.company = cls.test_company
			warehouse.flags.ignore_permissions = True
			warehouse.insert()
		
		# Create test project
		if not frappe.db.exists("Project", cls.test_project):
			project = frappe.new_doc("Project")
			project.project_name = cls.test_project
			project.company = cls.test_company
			project.enable_progressive_boq = 1
			project.site_location = cls.test_warehouse
			project.flags.ignore_permissions = True
			project.insert()
	
	@given(
		mandatory_setting=st.booleans(),
		has_default_warehouse=st.booleans(),
		project_has_site_location=st.booleans()
	)
	@settings(max_examples=50, deadline=5000)
	def test_property_warehouse_enforcement_consistency(self, mandatory_setting, has_default_warehouse, project_has_site_location):
		"""
		Property: Warehouse enforcement should be consistent across all DPR entries
		For any combination of BOQ Settings and Project configuration,
		warehouse enforcement should behave predictably.
		**Validates: Requirements 9.2, 9.3, 9.5**
		"""
		
		# Create BOQ Settings
		boq_settings = self._create_boq_settings(
			mandatory_site_location=mandatory_setting,
			default_warehouse=self.test_warehouse if has_default_warehouse else None
		)
		
		# Create project with or without site location
		project_warehouse = self.test_warehouse if project_has_site_location else None
		test_project = self._create_test_project(site_location=project_warehouse)
		
		# Create DPR without warehouse
		dpr = self._create_test_dpr(test_project, warehouse=None)
		
		try:
			# Apply warehouse enforcement
			enforce_warehouse_in_dpr(dpr)
			
			# Validate behavior
			if mandatory_setting:
				# If mandatory is enabled, DPR should have a warehouse
				self.assertIsNotNone(dpr.warehouse, 
					"DPR should have warehouse when mandatory setting is enabled")
				
				if project_has_site_location:
					# Should use project's site location
					self.assertEqual(dpr.warehouse, project_warehouse,
						"DPR should use project's site location when available")
				elif has_default_warehouse:
					# Should use default warehouse from settings
					self.assertEqual(dpr.warehouse, self.test_warehouse,
						"DPR should use default warehouse from BOQ Settings")
			
			# Warehouse should always be valid if set
			if dpr.warehouse:
				self.assertTrue(frappe.db.exists("Warehouse", dpr.warehouse),
					"DPR warehouse should be a valid warehouse")
		
		except frappe.ValidationError:
			# Exception should only occur when mandatory is True but no warehouse available
			self.assertTrue(mandatory_setting and not project_has_site_location and not has_default_warehouse,
				"ValidationError should only occur when mandatory=True but no warehouse available")
	
	@given(
		warehouse_count=st.integers(min_value=1, max_value=5),
		project_count=st.integers(min_value=1, max_value=3)
	)
	@settings(max_examples=30, deadline=5000)
	def test_property_warehouse_dimension_setup_consistency(self, warehouse_count, project_count):
		"""
		Property: Warehouse dimension setup should be consistent regardless of data volume
		For any number of warehouses and projects, dimension validation should work uniformly.
		**Validates: Requirements 9.1, 9.4**
		"""
		
		# Create multiple warehouses
		warehouses = []
		for i in range(warehouse_count):
			warehouse_name = f"Test WH {i} - TWD"
			if not frappe.db.exists("Warehouse", warehouse_name):
				warehouse = frappe.new_doc("Warehouse")
				warehouse.warehouse_name = f"Test WH {i}"
				warehouse.company = self.test_company
				warehouse.flags.ignore_permissions = True
				warehouse.insert()
			warehouses.append(warehouse_name)
		
		# Create multiple projects
		projects = []
		for i in range(project_count):
			project_name = f"Test Project {i} WD"
			if not frappe.db.exists("Project", project_name):
				project = frappe.new_doc("Project")
				project.project_name = project_name
				project.company = self.test_company
				project.enable_progressive_boq = 1
				project.site_location = warehouses[i % len(warehouses)]  # Distribute warehouses
				project.flags.ignore_permissions = True
				project.insert()
			projects.append(project_name)
		
		# Validate warehouse dimension setup
		is_valid, message = validate_warehouse_dimension_setup()
		
		# Dimension should be properly configured regardless of data volume
		self.assertTrue(is_valid, f"Warehouse dimension setup should be valid: {message}")
		
		# Test DPR creation for each project
		for project in projects:
			dpr = self._create_test_dpr(project)
			
			# DPR should have warehouse from project
			project_warehouse = frappe.db.get_value("Project", project, "site_location")
			if project_warehouse:
				enforce_warehouse_in_dpr(dpr)
				self.assertEqual(dpr.warehouse, project_warehouse,
					f"DPR should inherit warehouse from project {project}")
	
	@given(
		auto_create=st.booleans(),
		naming_series=st.sampled_from(["PROJ-WH-.####", "SITE-.####", "WH-.YYYY.-.####"])
	)
	@settings(max_examples=20, deadline=5000)
	def test_property_auto_warehouse_creation_consistency(self, auto_create, naming_series):
		"""
		Property: Auto warehouse creation should be consistent with naming series
		For any naming series, auto-created warehouses should follow the pattern.
		**Validates: Requirements 9.5**
		"""
		
		# Create BOQ Settings with auto-create enabled
		boq_settings = self._create_boq_settings(
			auto_create_warehouse=auto_create,
			warehouse_naming_series=naming_series
		)
		
		# Create project without site location
		test_project_name = f"Auto Test Project {frappe.generate_hash(length=5)}"
		project = frappe.new_doc("Project")
		project.project_name = test_project_name
		project.company = self.test_company
		project.enable_progressive_boq = 1
		project.flags.ignore_permissions = True
		project.insert()
		
		if auto_create:
			# Trigger auto warehouse creation
			from construction_management.construction_management.doctype.boq_settings.boq_settings import auto_create_project_warehouse
			auto_create_project_warehouse(project)
			
			# Project should now have a site location
			project.reload()
			self.assertIsNotNone(project.site_location,
				"Project should have auto-created warehouse when auto_create is enabled")
			
			# Warehouse name should follow naming series pattern
			warehouse_name = project.site_location
			if naming_series == "PROJ-WH-.####":
				self.assertIn("PROJ-WH-", warehouse_name,
					"Auto-created warehouse should follow PROJ-WH naming pattern")
			elif naming_series == "SITE-.####":
				self.assertIn("SITE-", warehouse_name,
					"Auto-created warehouse should follow SITE naming pattern")
			
			# Warehouse should exist and belong to correct company
			warehouse_doc = frappe.get_doc("Warehouse", warehouse_name)
			self.assertEqual(warehouse_doc.company, self.test_company,
				"Auto-created warehouse should belong to correct company")
		else:
			# Project should not have auto-created warehouse
			self.assertIsNone(project.site_location,
				"Project should not have auto-created warehouse when auto_create is disabled")
	
	def _create_boq_settings(self, **kwargs):
		"""Helper to create BOQ Settings for testing"""
		
		# Delete existing settings
		if frappe.db.exists("BOQ Settings", self.test_company):
			frappe.delete_doc("BOQ Settings", self.test_company, force=True)
		
		settings = frappe.new_doc("BOQ Settings")
		settings.company = self.test_company
		settings.mandatory_site_location = kwargs.get("mandatory_site_location", 0)
		settings.default_warehouse = kwargs.get("default_warehouse")
		settings.auto_create_warehouse = kwargs.get("auto_create_warehouse", 0)
		settings.warehouse_naming_series = kwargs.get("warehouse_naming_series", "PROJ-WH-.####")
		settings.flags.ignore_permissions = True
		settings.insert()
		
		return settings
	
	def _create_test_project(self, site_location=None):
		"""Helper to create test project"""
		
		project_name = f"Test Project {frappe.generate_hash(length=5)}"
		project = frappe.new_doc("Project")
		project.project_name = project_name
		project.company = self.test_company
		project.enable_progressive_boq = 1
		project.site_location = site_location
		project.flags.ignore_permissions = True
		project.insert()
		
		return project.name
	
	def _create_test_dpr(self, project, warehouse=None):
		"""Helper to create test DPR"""
		
		dpr = frappe.new_doc("Daily Progress Record")
		dpr.project = project
		dpr.date = today()
		dpr.warehouse = warehouse
		dpr.flags.ignore_permissions = True
		
		return dpr
	
	@classmethod
	def tearDownClass(cls):
		"""Clean up test data"""
		
		# Clean up in reverse order of dependencies
		frappe.db.sql("DELETE FROM `tabDaily Progress Record` WHERE project LIKE 'Test Project%'")
		frappe.db.sql("DELETE FROM `tabBOQ Settings` WHERE company = %s", cls.test_company)
		frappe.db.sql("DELETE FROM `tabProject` WHERE company = %s", cls.test_company)
		frappe.db.sql("DELETE FROM `tabWarehouse` WHERE company = %s", cls.test_company)
		
		if frappe.db.exists("Company", cls.test_company):
			frappe.delete_doc("Company", cls.test_company, force=True)
		
		frappe.db.commit()


if __name__ == "__main__":
	unittest.main()