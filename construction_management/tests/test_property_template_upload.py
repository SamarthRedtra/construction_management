# Copyright (c) 2024, Construction Management
# License: MIT
# Property Tests for BOQ Template Upload

"""
Property Tests for BOQ Template Upload

These tests validate the following properties:
- Property 21: Template Upload Validation and Creation

Requirements: 11.2, 11.3, 11.4
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt
from hypothesis import given, strategies as st, settings
from construction_management.api.template_upload import (
	parse_template,
	validate_template_data,
	create_boq_records,
	REQUIRED_COLUMNS,
	OPTIONAL_COLUMNS
)


class TestTemplateUploadValidationAndCreation(FrappeTestCase):
	"""
	**Feature: boq-costing-estimation, Property 21: Template Upload Validation and Creation**
	**Validates: Requirements 11.3, 11.4**
	
	Property: For any valid BOQ template upload, the number of BOQ Items created 
	SHALL equal the number of valid data rows in the template, and each item's 
	fields SHALL match the template values
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-TEMPLATE-UPLOAD-PROJECT")
	
	def test_valid_template_creates_correct_number_of_items(self):
		"""Property: Number of items created equals number of valid rows"""
		# Create test data
		data = [
			{
				"bill_no": "Bill 1",
				"description": "Excavation work",
				"unit": "CuM",
				"quantity": 100,
				"rate": 500,
				"_row_number": 2
			},
			{
				"bill_no": "Bill 1",
				"description": "Concrete work",
				"unit": "CuM",
				"quantity": 50,
				"rate": 8000,
				"_row_number": 3
			},
			{
				"bill_no": "Bill 2",
				"description": "Steel reinforcement",
				"unit": "Kg",
				"quantity": 1000,
				"rate": 80,
				"_row_number": 4
			}
		]
		
		# Create records
		result = create_boq_records(self.test_project, data)
		
		# Assert correct number of items created
		self.assertTrue(result.success)
		self.assertEqual(result.items_created, 3)
		self.assertEqual(result.bills_created, 2)  # Bill 1 and Bill 2
		
		# Cleanup
		cleanup_test_boq_data(self.test_project)
	
	def test_item_fields_match_template_values(self):
		"""Property: Each item's fields match the template values"""
		data = [
			{
				"bill_no": "Bill Test",
				"item_code": "ITEM-001",
				"description": "Test Item Description",
				"unit": "Nos",
				"quantity": 150.5,
				"rate": 1234.56,
				"estimated_material_cost": 5000,
				"estimated_labour_cost": 3000,
				"estimated_subcontract_cost": 1000,
				"estimated_asset_cost": 500,
				"estimated_other_cost": 200,
				"_row_number": 2
			}
		]
		
		result = create_boq_records(self.test_project, data)
		
		self.assertTrue(result.success)
		self.assertEqual(result.items_created, 1)
		
		# Verify item fields match template
		item = frappe.get_doc("BOQ Item", result.created_items[0])
		
		self.assertEqual(item.description, "Test Item Description")
		self.assertEqual(item.unit, "Nos")
		self.assertAlmostEqual(flt(item.total_qty), 150.5, places=2)
		self.assertAlmostEqual(flt(item.rate), 1234.56, places=2)
		self.assertAlmostEqual(flt(item.estimated_material_cost), 5000, places=2)
		self.assertAlmostEqual(flt(item.estimated_labour_cost), 3000, places=2)
		self.assertAlmostEqual(flt(item.estimated_subcontract_cost), 1000, places=2)
		self.assertAlmostEqual(flt(item.estimated_asset_cost), 500, places=2)
		self.assertAlmostEqual(flt(item.estimated_other_cost), 200, places=2)
		
		# Cleanup
		cleanup_test_boq_data(self.test_project)
	
	def test_validation_rejects_missing_required_columns(self):
		"""Property: Validation fails when required columns are missing"""
		# Data without required columns
		data = [{"bill_no": "Bill 1", "description": "Test", "_row_number": 2}]
		headers = ["bill_no", "description"]  # Missing unit, quantity, rate
		
		result = validate_template_data(data, headers)
		
		self.assertFalse(result.is_valid)
		self.assertTrue(len(result.errors) > 0)
		# Check that missing columns are reported
		error_messages = [e.message for e in result.errors]
		self.assertTrue(any("Missing required columns" in msg for msg in error_messages))
	
	def test_validation_rejects_missing_required_values(self):
		"""Property: Validation fails when required values are missing"""
		headers = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
		data = [
			{
				"bill_no": "",  # Missing bill_no
				"description": "Test",
				"unit": "Nos",
				"quantity": 100,
				"rate": 10,
				"_row_number": 2
			}
		]
		
		result = validate_template_data(data, headers)
		
		self.assertFalse(result.is_valid)
		self.assertTrue(any(e.column == "bill_no" for e in result.errors))
	
	def test_validation_rejects_invalid_quantity(self):
		"""Property: Validation fails for invalid quantity values"""
		headers = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
		data = [
			{
				"bill_no": "Bill 1",
				"description": "Test",
				"unit": "Nos",
				"quantity": -100,  # Negative quantity
				"rate": 10,
				"_row_number": 2
			}
		]
		
		result = validate_template_data(data, headers)
		
		self.assertFalse(result.is_valid)
		self.assertTrue(any(e.column == "quantity" for e in result.errors))
	
	def test_validation_rejects_invalid_rate(self):
		"""Property: Validation fails for invalid rate values"""
		headers = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
		data = [
			{
				"bill_no": "Bill 1",
				"description": "Test",
				"unit": "Nos",
				"quantity": 100,
				"rate": -50,  # Negative rate
				"_row_number": 2
			}
		]
		
		result = validate_template_data(data, headers)
		
		self.assertFalse(result.is_valid)
		self.assertTrue(any(e.column == "rate" for e in result.errors))
	
	def test_validation_rejects_duplicate_item_codes(self):
		"""Property: Validation fails for duplicate item codes"""
		headers = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
		data = [
			{
				"bill_no": "Bill 1",
				"item_code": "ITEM-DUP",
				"description": "Test 1",
				"unit": "Nos",
				"quantity": 100,
				"rate": 10,
				"_row_number": 2
			},
			{
				"bill_no": "Bill 1",
				"item_code": "ITEM-DUP",  # Duplicate
				"description": "Test 2",
				"unit": "Nos",
				"quantity": 50,
				"rate": 20,
				"_row_number": 3
			}
		]
		
		result = validate_template_data(data, headers)
		
		self.assertFalse(result.is_valid)
		self.assertTrue(any("Duplicate item code" in e.message for e in result.errors))
	
	def test_valid_template_passes_validation(self):
		"""Property: Valid template passes all validation checks"""
		headers = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
		data = [
			{
				"bill_no": "Bill 1",
				"item_code": "ITEM-001",
				"description": "Valid Item 1",
				"unit": "Nos",
				"quantity": 100,
				"rate": 500,
				"estimated_material_cost": 10000,
				"_row_number": 2
			},
			{
				"bill_no": "Bill 1",
				"item_code": "ITEM-002",
				"description": "Valid Item 2",
				"unit": "CuM",
				"quantity": 50,
				"rate": 1000,
				"_row_number": 3
			}
		]
		
		result = validate_template_data(data, headers)
		
		self.assertTrue(result.is_valid)
		self.assertEqual(len(result.errors), 0)
		self.assertEqual(result.row_count, 2)
		self.assertEqual(result.valid_row_count, 2)
	
	@given(
		num_items=st.integers(min_value=1, max_value=10),
		quantity=st.floats(min_value=0.1, max_value=10000, allow_nan=False, allow_infinity=False),
		rate=st.floats(min_value=0.1, max_value=10000, allow_nan=False, allow_infinity=False)
	)
	@settings(max_examples=50, deadline=None)
	def test_items_created_equals_valid_rows_property(self, num_items, quantity, rate):
		"""Property: For any valid template, items_created == valid_row_count"""
		# Generate test data
		data = []
		for i in range(num_items):
			data.append({
				"bill_no": f"Bill {(i // 3) + 1}",  # Group into bills
				"description": f"Item {i + 1} - {frappe.generate_hash()[:6]}",
				"unit": "Nos",
				"quantity": quantity,
				"rate": rate,
				"_row_number": i + 2
			})
		
		# Validate
		headers = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
		validation = validate_template_data(data, headers)
		
		if validation.is_valid:
			# Create records
			result = create_boq_records(self.test_project, data)
			
			# Assert items created equals valid rows
			self.assertEqual(result.items_created, validation.valid_row_count)
			
			# Cleanup
			cleanup_test_boq_data(self.test_project)
	
	def test_hierarchical_structure_preserved(self):
		"""Property: Bill No grouping creates correct parent-child relationships"""
		data = [
			{"bill_no": "Bill A", "description": "Item A1", "unit": "Nos", "quantity": 10, "rate": 100, "_row_number": 2},
			{"bill_no": "Bill A", "description": "Item A2", "unit": "Nos", "quantity": 20, "rate": 200, "_row_number": 3},
			{"bill_no": "Bill B", "description": "Item B1", "unit": "Nos", "quantity": 30, "rate": 300, "_row_number": 4},
			{"bill_no": "Bill A", "description": "Item A3", "unit": "Nos", "quantity": 40, "rate": 400, "_row_number": 5},
		]
		
		result = create_boq_records(self.test_project, data)
		
		self.assertTrue(result.success)
		self.assertEqual(result.bills_created, 2)  # Bill A and Bill B
		self.assertEqual(result.items_created, 4)
		
		# Verify items are linked to correct bills
		bill_a = frappe.db.get_value("BOQ Bill", {"project": self.test_project, "bill_no": "Bill A"})
		bill_b = frappe.db.get_value("BOQ Bill", {"project": self.test_project, "bill_no": "Bill B"})
		
		items_in_bill_a = frappe.get_all("BOQ Item", filters={"parent_bill": bill_a})
		items_in_bill_b = frappe.get_all("BOQ Item", filters={"parent_bill": bill_b})
		
		self.assertEqual(len(items_in_bill_a), 3)  # A1, A2, A3
		self.assertEqual(len(items_in_bill_b), 1)  # B1
		
		# Cleanup
		cleanup_test_boq_data(self.test_project)
	
	def test_existing_bill_reused(self):
		"""Property: Existing bills are reused, not duplicated"""
		# First upload
		data1 = [
			{"bill_no": "Existing Bill", "description": "Item 1", "unit": "Nos", "quantity": 10, "rate": 100, "_row_number": 2}
		]
		result1 = create_boq_records(self.test_project, data1)
		
		self.assertEqual(result1.bills_created, 1)
		
		# Second upload with same bill_no
		data2 = [
			{"bill_no": "Existing Bill", "description": "Item 2", "unit": "Nos", "quantity": 20, "rate": 200, "_row_number": 2}
		]
		result2 = create_boq_records(self.test_project, data2)
		
		# Bill should be reused, not created again
		self.assertEqual(result2.bills_created, 0)
		self.assertEqual(result2.items_created, 1)
		
		# Verify only one bill exists
		bills = frappe.get_all("BOQ Bill", filters={"project": self.test_project, "bill_no": "Existing Bill"})
		self.assertEqual(len(bills), 1)
		
		# Cleanup
		cleanup_test_boq_data(self.test_project)
	
	def test_estimated_costs_preserved(self):
		"""Property: Estimated costs from template are preserved in created items"""
		data = [
			{
				"bill_no": "Cost Bill",
				"description": "Cost Item",
				"unit": "Nos",
				"quantity": 100,
				"rate": 1000,
				"estimated_material_cost": 25000,
				"estimated_labour_cost": 15000,
				"estimated_subcontract_cost": 8000,
				"estimated_asset_cost": 3000,
				"estimated_other_cost": 2000,
				"_row_number": 2
			}
		]
		
		result = create_boq_records(self.test_project, data)
		
		self.assertTrue(result.success)
		
		# Verify estimated costs
		item = frappe.get_doc("BOQ Item", result.created_items[0])
		
		self.assertEqual(flt(item.estimated_material_cost), 25000)
		self.assertEqual(flt(item.estimated_labour_cost), 15000)
		self.assertEqual(flt(item.estimated_subcontract_cost), 8000)
		self.assertEqual(flt(item.estimated_asset_cost), 3000)
		self.assertEqual(flt(item.estimated_other_cost), 2000)
		
		# Total should be calculated
		expected_total = 25000 + 15000 + 8000 + 3000 + 2000
		self.assertEqual(flt(item.total_estimated_cost), expected_total)
		
		# Cleanup
		cleanup_test_boq_data(self.test_project)


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


def cleanup_test_boq_data(project):
	"""Clean up all BOQ data for a test project"""
	# Delete BOQ Items
	items = frappe.get_all("BOQ Item", filters={"project": project})
	for item in items:
		frappe.delete_doc("BOQ Item", item.name, force=True)
	
	# Delete BOQ Bills
	bills = frappe.get_all("BOQ Bill", filters={"project": project})
	for bill in bills:
		frappe.delete_doc("BOQ Bill", bill.name, force=True)
	
	# Delete Project BOQ
	boqs = frappe.get_all("Project BOQ", filters={"project": project})
	for boq in boqs:
		frappe.delete_doc("Project BOQ", boq.name, force=True)
	
	frappe.db.commit()
