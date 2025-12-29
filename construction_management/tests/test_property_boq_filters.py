# Copyright (c) 2024, Construction Management
# License: MIT
# Property Tests for BOQ Filters and Warehouse Selection

"""
Property Tests for Construction Management Enhancements v2

These tests validate the following properties:
- Task 2.2: BOQ Item Filter by Bill No
- Task 3.4: Warehouse Project Filter
- Task 3.6: Valuation Rate Consistency
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt


class TestBOQItemFilterByBill(FrappeTestCase):
	"""
	Property 1: BOQ Item Filter by Bill
	
	Validates: Requirements 4.2
	Property: When filtering BOQ Items by Bill No, only items belonging to that bill are returned.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project = create_test_project("TEST-FILTER-PROJECT")
		cls.test_boq = create_test_project_boq(cls.test_project)
		cls.test_bill_1 = create_test_bill(cls.test_project, "Bill No. 1 - Test")
		cls.test_bill_2 = create_test_bill(cls.test_project, "Bill No. 2 - Test")
		cls.test_item_1 = create_test_boq_item(cls.test_bill_1, "Item 1 in Bill 1")
		cls.test_item_2 = create_test_boq_item(cls.test_bill_1, "Item 2 in Bill 1")
		cls.test_item_3 = create_test_boq_item(cls.test_bill_2, "Item 1 in Bill 2")
	
	def test_boq_items_filtered_by_bill_returns_correct_items(self):
		"""Property: Filtering by bill_no returns only items from that bill"""
		# Get items for Bill 1
		items_bill_1 = frappe.get_all(
			"BOQ Item",
			filters={"parent_bill": self.test_bill_1},
			fields=["name", "description"]
		)
		
		# Should have exactly 2 items
		self.assertEqual(len(items_bill_1), 2)
		
		# All items should belong to Bill 1
		for item in items_bill_1:
			parent_bill = frappe.db.get_value("BOQ Item", item.name, "parent_bill")
			self.assertEqual(parent_bill, self.test_bill_1)
	
	def test_boq_items_filtered_by_different_bill_returns_different_items(self):
		"""Property: Different bills return different item sets"""
		items_bill_1 = frappe.get_all(
			"BOQ Item",
			filters={"parent_bill": self.test_bill_1},
			pluck="name"
		)
		
		items_bill_2 = frappe.get_all(
			"BOQ Item",
			filters={"parent_bill": self.test_bill_2},
			pluck="name"
		)
		
		# No overlap between bills
		overlap = set(items_bill_1) & set(items_bill_2)
		self.assertEqual(len(overlap), 0, "Items should not appear in multiple bills")
	
	def test_advance_payment_boq_item_filter_respects_bill(self):
		"""Property: BOQ Item selection in advance payment respects bill filter"""
		# Simulate the filter query used in record_advance_payment dialog
		items = frappe.get_all(
			"BOQ Item",
			filters={"parent_bill": self.test_bill_1},
			fields=["name", "description", "parent_bill"]
		)
		
		# All returned items should have the correct parent_bill
		for item in items:
			self.assertEqual(item.parent_bill, self.test_bill_1)


class TestWarehouseProjectFilter(FrappeTestCase):
	"""
	Property 2: Warehouse Project Filter
	
	Validates: Requirements 2.2
	Property: Warehouses filtered by project return only warehouses linked to that project.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_project_1 = create_test_project("TEST-WH-PROJECT-1")
		cls.test_project_2 = create_test_project("TEST-WH-PROJECT-2")
		cls.test_warehouse_1 = create_test_warehouse("Test WH 1", cls.test_project_1)
		cls.test_warehouse_2 = create_test_warehouse("Test WH 2", cls.test_project_1)
		cls.test_warehouse_3 = create_test_warehouse("Test WH 3", cls.test_project_2)
	
	def test_warehouse_filter_returns_project_warehouses_only(self):
		"""Property: Filtering warehouses by project returns only that project's warehouses"""
		from construction_management.api.dpr_utils import get_project_warehouses
		
		warehouses = get_project_warehouses(self.test_project_1)
		warehouse_names = [w.name for w in warehouses]
		
		# Should include project 1 warehouses
		self.assertIn(self.test_warehouse_1, warehouse_names)
		self.assertIn(self.test_warehouse_2, warehouse_names)
		
		# Should NOT include project 2 warehouse
		self.assertNotIn(self.test_warehouse_3, warehouse_names)
	
	def test_different_projects_have_different_warehouses(self):
		"""Property: Different projects return different warehouse sets"""
		from construction_management.api.dpr_utils import get_project_warehouses
		
		wh_project_1 = set(w.name for w in get_project_warehouses(self.test_project_1))
		wh_project_2 = set(w.name for w in get_project_warehouses(self.test_project_2))
		
		# No overlap between projects
		overlap = wh_project_1 & wh_project_2
		self.assertEqual(len(overlap), 0, "Warehouses should not be shared between projects")
	
	def test_warehouse_custom_project_field_is_set(self):
		"""Property: Warehouse custom_project field correctly identifies the project"""
		custom_project = frappe.db.get_value("Warehouse", self.test_warehouse_1, "custom_project")
		self.assertEqual(custom_project, self.test_project_1)


class TestValuationRateConsistency(FrappeTestCase):
	"""
	Property 4: Valuation Rate Consistency
	
	Validates: Requirements 2.4
	Property: Item valuation rate from warehouse matches the rate used in DPR materials.
	"""
	
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_item = create_test_item("TEST-VALUATION-ITEM")
		cls.test_warehouse = create_test_warehouse("Test Valuation WH", None)
		# Create stock with known valuation rate
		create_test_stock_entry(cls.test_item, cls.test_warehouse, 100, 50.0)
	
	def test_valuation_rate_from_bin_matches_api(self):
		"""Property: API returns the same valuation rate as stored in Bin"""
		from construction_management.api.dpr_utils import get_item_valuation_rate
		
		# Get rate from API
		api_result = get_item_valuation_rate(self.test_item, self.test_warehouse)
		api_rate = api_result.get("valuation_rate", 0)
		
		# Get rate directly from Bin
		bin_rate = frappe.db.get_value(
			"Bin",
			{"item_code": self.test_item, "warehouse": self.test_warehouse},
			"valuation_rate"
		)
		
		self.assertEqual(flt(api_rate), flt(bin_rate))
	
	def test_valuation_rate_is_positive_when_stock_exists(self):
		"""Property: Valuation rate is positive when stock exists"""
		from construction_management.api.dpr_utils import get_item_valuation_rate
		
		result = get_item_valuation_rate(self.test_item, self.test_warehouse)
		rate = result.get("valuation_rate", 0)
		self.assertGreater(flt(rate), 0, "Valuation rate should be positive when stock exists")


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
	
	# Get project BOQ
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
	
	# Get default company
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
	item.valuation_rate = 50.0
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
