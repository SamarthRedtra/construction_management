# Copyright (c) 2024, Construction Management
# License: MIT
# Property Tests for Stock Validation and Advance Aggregation

"""
Property Tests for Construction Management Enhancements v2

These tests validate the following properties:
- Task 8.2: Stock Availability Validation
- Task 8.4: Stock Entry Creation
- Task 9.2: Advance Aggregation
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today


class TestStockAvailabilityValidation(FrappeTestCase):
	"""
	Property 3: Stock Availability Validation
	
	Validates: Requirements 2.6
	Property: DPR cannot be saved if material quantity exceeds available stock.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-STOCK-VAL-PROJECT")
		cls.test_boq = create_test_project_boq(cls.test_project)
		cls.test_bill = create_test_bill(cls.test_project, "Bill No. 1 - Stock Test")
		cls.test_boq_item = create_test_boq_item(cls.test_bill, "Stock Test Item")
		cls.test_item = create_test_item("TEST-STOCK-VAL-ITEM")
		cls.test_warehouse = create_test_warehouse("Stock Val WH", cls.test_project)
		# Add 50 units of stock
		create_test_stock_entry(cls.test_item, cls.test_warehouse, 50, 100.0)
	
	def test_validate_material_stock_api_returns_valid_for_sufficient_stock(self):
		"""Property: Stock validation returns valid when qty <= available"""
		from construction_management.api.dpr_utils import validate_material_stock
		
		result = validate_material_stock(self.test_warehouse, self.test_item, 30)
		
		self.assertTrue(result["is_valid"])
		self.assertEqual(result["message"], "")
	
	def test_validate_material_stock_api_returns_invalid_for_insufficient_stock(self):
		"""Property: Stock validation returns invalid when qty > available"""
		from construction_management.api.dpr_utils import validate_material_stock
		
		result = validate_material_stock(self.test_warehouse, self.test_item, 100)
		
		self.assertFalse(result["is_valid"])
		self.assertIn("Insufficient stock", result["message"])
	
	def test_dpr_validation_throws_on_insufficient_stock(self):
		"""Property: DPR validate throws error when material qty exceeds stock"""
		dpr = frappe.new_doc("Daily Progress Record")
		dpr.project = self.test_project
		dpr.boq_item = self.test_boq_item
		dpr.date = today()
		dpr.append("materials", {
			"item_code": self.test_item,
			"warehouse": self.test_warehouse,
			"qty": 1000,  # Way more than available
			"rate": 100
		})
		
		with self.assertRaises(frappe.ValidationError):
			dpr.validate()
	
	def test_dpr_validation_passes_with_sufficient_stock(self):
		"""Property: DPR validate passes when material qty <= stock"""
		dpr = frappe.new_doc("Daily Progress Record")
		dpr.project = self.test_project
		dpr.boq_item = self.test_boq_item
		dpr.date = today()
		dpr.append("materials", {
			"item_code": self.test_item,
			"warehouse": self.test_warehouse,
			"qty": 10,  # Less than available
			"rate": 100
		})
		
		# Should not raise
		try:
			dpr.validate()
		except frappe.ValidationError as e:
			if "Insufficient stock" in str(e):
				self.fail("Should not throw insufficient stock error for valid qty")


class TestStockEntryCreation(FrappeTestCase):
	"""
	Property 5: Stock Entry Creation
	
	Validates: Requirements 2.5
	Property: Submitting DPR creates Stock Entry for materials with correct quantities.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-SE-CREATE-PROJECT")
		cls.test_boq = create_test_project_boq(cls.test_project)
		cls.test_bill = create_test_bill(cls.test_project, "Bill No. 1 - SE Test")
		cls.test_boq_item = create_test_boq_item(cls.test_bill, "SE Test Item")
		cls.test_item = create_test_item("TEST-SE-CREATE-ITEM")
		cls.test_warehouse = create_test_warehouse("SE Create WH", cls.test_project)
		# Add sufficient stock
		create_test_stock_entry(cls.test_item, cls.test_warehouse, 500, 100.0)
	
	def test_dpr_submit_creates_stock_entry(self):
		"""Property: Submitting DPR creates a Stock Entry"""
		dpr = frappe.new_doc("Daily Progress Record")
		dpr.project = self.test_project
		dpr.boq_item = self.test_boq_item
		dpr.date = today()
		dpr.append("materials", {
			"item_code": self.test_item,
			"warehouse": self.test_warehouse,
			"qty": 5,
			"rate": 100
		})
		dpr.insert()
		dpr.submit()
		
		# Check stock entry was created
		self.assertTrue(dpr.stock_entries, "Stock entries field should be populated")
		
		# Verify stock entry exists and is submitted
		se_name = dpr.stock_entries.split(",")[0].strip()
		se = frappe.get_doc("Stock Entry", se_name)
		self.assertEqual(se.docstatus, 1, "Stock Entry should be submitted")
		self.assertEqual(se.stock_entry_type, "Material Issue")
		
		# Cleanup
		dpr.cancel()
	
	def test_stock_entry_has_correct_quantity(self):
		"""Property: Stock Entry quantity matches DPR material quantity"""
		test_qty = 7
		
		dpr = frappe.new_doc("Daily Progress Record")
		dpr.project = self.test_project
		dpr.boq_item = self.test_boq_item
		dpr.date = today()
		dpr.append("materials", {
			"item_code": self.test_item,
			"warehouse": self.test_warehouse,
			"qty": test_qty,
			"rate": 100
		})
		dpr.insert()
		dpr.submit()
		
		# Get stock entry
		se_name = dpr.stock_entries.split(",")[0].strip()
		se = frappe.get_doc("Stock Entry", se_name)
		
		# Verify quantity
		self.assertEqual(flt(se.items[0].qty), test_qty)
		
		# Cleanup
		dpr.cancel()
	
	def test_stock_entry_has_correct_warehouse(self):
		"""Property: Stock Entry source warehouse matches DPR material warehouse"""
		dpr = frappe.new_doc("Daily Progress Record")
		dpr.project = self.test_project
		dpr.boq_item = self.test_boq_item
		dpr.date = today()
		dpr.append("materials", {
			"item_code": self.test_item,
			"warehouse": self.test_warehouse,
			"qty": 3,
			"rate": 100
		})
		dpr.insert()
		dpr.submit()
		
		# Get stock entry
		se_name = dpr.stock_entries.split(",")[0].strip()
		se = frappe.get_doc("Stock Entry", se_name)
		
		# Verify warehouse
		self.assertEqual(se.items[0].s_warehouse, self.test_warehouse)
		
		# Cleanup
		dpr.cancel()


class TestBillItemAdvanceAggregation(FrappeTestCase):
	"""
	Property 6: Bill Item Advance Aggregation
	
	Validates: Requirements 4.3
	Property: Advances linked to a BOQ Item are correctly aggregated.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-ADV-AGG-PROJECT")
		cls.test_boq = create_test_project_boq(cls.test_project)
		cls.test_bill = create_test_bill(cls.test_project, "Bill No. 1 - Advance Test")
		cls.test_boq_item = create_test_boq_item(cls.test_bill, "Advance Test Item")
		
		# Create test advances
		cls.advance_1 = create_test_advance(cls.test_project, cls.test_bill, cls.test_boq_item, 1000)
		cls.advance_2 = create_test_advance(cls.test_project, cls.test_bill, cls.test_boq_item, 500)
	
	def test_get_bill_item_advances_returns_correct_total(self):
		"""Property: Total advances for BOQ Item equals sum of individual advances"""
		from construction_management.api.boq_invoice import get_bill_item_advances
		
		result = get_bill_item_advances(self.test_boq_item)
		
		self.assertEqual(flt(result["total_advances"]), 1500)
		self.assertEqual(result["count"], 2)
	
	def test_get_bill_item_advances_returns_correct_unallocated(self):
		"""Property: Unallocated amount equals total minus allocated"""
		from construction_management.api.boq_invoice import get_bill_item_advances
		
		result = get_bill_item_advances(self.test_boq_item)
		
		expected_unallocated = result["total_advances"] - result["allocated"]
		self.assertEqual(flt(result["unallocated"]), flt(expected_unallocated))


class TestProjectAdvanceAggregation(FrappeTestCase):
	"""
	Property 8: Project Advance Aggregation
	
	Validates: Requirements 4.6
	Property: Project-level advance aggregation correctly sums all advances.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-PROJ-ADV-PROJECT")
		cls.test_boq = create_test_project_boq(cls.test_project)
		cls.test_bill_1 = create_test_bill(cls.test_project, "Bill No. 1 - Project Adv")
		cls.test_bill_2 = create_test_bill(cls.test_project, "Bill No. 2 - Project Adv")
		cls.test_item_1 = create_test_boq_item(cls.test_bill_1, "Project Adv Item 1")
		cls.test_item_2 = create_test_boq_item(cls.test_bill_2, "Project Adv Item 2")
		
		# Create advances across different bills
		cls.advance_1 = create_test_advance(cls.test_project, cls.test_bill_1, cls.test_item_1, 2000)
		cls.advance_2 = create_test_advance(cls.test_project, cls.test_bill_2, cls.test_item_2, 3000)
	
	def test_get_project_advances_returns_correct_total(self):
		"""Property: Project total advances equals sum of all bill advances"""
		from construction_management.api.boq_invoice import get_project_advances
		
		result = get_project_advances(self.test_project)
		
		self.assertEqual(flt(result["summary"]["total_advances"]), 5000)
		self.assertEqual(result["summary"]["count"], 2)
	
	def test_get_project_advances_groups_by_bill(self):
		"""Property: Project advances are correctly grouped by bill"""
		from construction_management.api.boq_invoice import get_project_advances
		
		result = get_project_advances(self.test_project)
		
		# Should have 2 bills
		self.assertEqual(len(result["by_bill"]), 2)
		
		# Each bill should have correct total
		bill_totals = {b["bill_no"]: b["total"] for b in result["by_bill"]}
		self.assertEqual(flt(bill_totals.get(self.test_bill_1)), 2000)
		self.assertEqual(flt(bill_totals.get(self.test_bill_2)), 3000)


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


def create_test_project_boq(project):
	"""Create a test Project BOQ"""
	existing = frappe.db.get_value("Project BOQ", {"project": project})
	if existing:
		return existing
	
	boq = frappe.new_doc("Project BOQ")
	boq.project = project
	boq.boq_name = f"BOQ - {project}"
	boq.insert(ignore_permissions=True)
	return boq.name


def create_test_bill(project, bill_no):
	"""Create a test BOQ Bill"""
	existing = frappe.db.get_value("BOQ Bill", {"project": project, "bill_no": bill_no})
	if existing:
		return existing
	
	project_boq = frappe.db.get_value("Project BOQ", {"project": project})
	
	bill = frappe.new_doc("BOQ Bill")
	bill.project = project
	bill.project_boq = project_boq
	bill.bill_no = bill_no
	bill.insert(ignore_permissions=True)
	return bill.name


def create_test_boq_item(parent_bill, description):
	"""Create a test BOQ Item"""
	bill_doc = frappe.get_doc("BOQ Bill", parent_bill)
	
	item = frappe.new_doc("BOQ Item")
	item.parent_bill = parent_bill
	item.project = bill_doc.project
	item.description = description
	item.unit = "Nos"
	item.total_qty = 100
	item.rate = 10
	item.insert(ignore_permissions=True)
	return item.name


def create_test_warehouse(name, project):
	"""Create a test warehouse"""
	full_name = f"{name} - _TC"
	if frappe.db.exists("Warehouse", full_name):
		if project:
			frappe.db.set_value("Warehouse", full_name, "custom_project", project)
		return full_name
	
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		company = frappe.db.get_value("Company", {}, "name")
	
	warehouse = frappe.new_doc("Warehouse")
	warehouse.warehouse_name = name
	warehouse.company = company
	warehouse.custom_project = project
	warehouse.insert(ignore_permissions=True)
	return warehouse.name


def create_test_item(item_code):
	"""Create a test item"""
	if frappe.db.exists("Item", item_code):
		return item_code
	
	item = frappe.new_doc("Item")
	item.item_code = item_code
	item.item_name = item_code
	item.item_group = "Products"
	item.stock_uom = "Nos"
	item.is_stock_item = 1
	item.valuation_rate = 100.0
	item.insert(ignore_permissions=True)
	return item.name


def create_test_stock_entry(item_code, warehouse, qty, rate):
	"""Create a stock entry to add stock"""
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		company = frappe.db.get_value("Company", {}, "name")
	
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Receipt"
	se.company = company
	se.append("items", {
		"item_code": item_code,
		"t_warehouse": warehouse,
		"qty": qty,
		"basic_rate": rate
	})
	se.insert(ignore_permissions=True)
	se.submit()
	return se.name


def create_test_advance(project, bill_no, boq_item, amount):
	"""Create a test advance payment"""
	advance = frappe.new_doc("BOQ Advance Payment")
	advance.project = project
	advance.bill_no = bill_no
	advance.boq_item = boq_item
	advance.amount = amount
	advance.unallocated_amount = amount
	advance.date = today()
	advance.insert(ignore_permissions=True)
	advance.submit()
	return advance.name
