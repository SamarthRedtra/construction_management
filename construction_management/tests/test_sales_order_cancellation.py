# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today
from construction_management.api.boq_invoice import create_sales_order_from_selected_items


class TestSalesOrderCancellation(FrappeTestCase):
	def setUp(self):
		self.project = self.create_test_project("CANCEL-TEST-PROJECT")
		self.boq_item = self.create_test_boq_item()
		self.item_code = self.create_test_item()

	def create_test_project(self, name):
		existing = frappe.db.get_value("Project", {"project_name": name})
		if existing:
			return existing
		
		if not frappe.db.exists("Customer", "Test Customer"):
			customer = frappe.new_doc("Customer")
			customer.customer_name = "Test Customer"
			customer.insert(ignore_permissions=True)
		
		project = frappe.new_doc("Project")
		project.project_name = name
		project.customer = "Test Customer"
		project.company = frappe.defaults.get_user_default("Company") or "Test Company"
		project.insert(ignore_permissions=True)
		return project.name

	def create_test_item(self):
		item_code = "Test Item for Cancellation"
		if not frappe.db.exists("Item", item_code):
			item = frappe.new_doc("Item")
			item.item_code = item_code
			item.item_name = item_code
			item.item_group = frappe.db.get_value("Item Group", {"is_group": 0}) or "All Item Groups"
			item.stock_uom = "Nos"
			item.insert(ignore_permissions=True)
		return item_code

	def create_test_boq_item(self):
		boq_name = frappe.db.get_value("Project BOQ", {"project": self.project})
		if not boq_name:
			boq = frappe.new_doc("Project BOQ")
			boq.project = self.project
			boq.boq_name = f"BOQ-{self.project}"
			boq.insert(ignore_permissions=True)
			boq_name = boq.name
		
		bill_name = frappe.db.get_value("BOQ Bill", {"project": self.project, "bill_no": "BILL-001"})
		if not bill_name:
			bill = frappe.new_doc("BOQ Bill")
			bill.project = self.project
			bill.project_boq = boq_name
			bill.bill_no = "BILL-001"
			bill.insert(ignore_permissions=True)
			bill_name = bill.name
		
		item_name = frappe.db.get_value("BOQ Item", {"parent_bill": bill_name, "description": "Cancel Test Item"})
		if not item_name:
			item = frappe.new_doc("BOQ Item")
			item.parent_bill = bill_name
			item.project = self.project
			item.description = "Cancel Test Item"
			item.unit = "Nos"
			item.rate = 1000
			item.total_qty = 10
			item.insert(ignore_permissions=True)
			item_name = item.name
		return item_name

	def test_so_cancel_no_invoice(self):
		"""Test that ledger entries are DELETED when SO is cancelled without an invoice."""
		items = [{"boq_item": self.boq_item, "qty": 1, "percentage": 10}]
		result = create_sales_order_from_selected_items(
			project=self.project,
			items=items,
			auto_submit=1
		)
		so_name = result.get("name")
		
		# Verify ledger entry exists
		ledger_entries = frappe.get_all("BOQ Progress Ledger", filters={
			"reference_doctype": "Sales Order",
			"reference_name": so_name
		})
		self.assertEqual(len(ledger_entries), 1)
		
		# Cancel SO
		so = frappe.get_doc("Sales Order", so_name)
		so.cancel()
		
		# Verify ledger entry is deleted
		ledger_entries = frappe.get_all("BOQ Progress Ledger", filters={
			"reference_doctype": "Sales Order",
			"reference_name": so_name
		})
		self.assertEqual(len(ledger_entries), 0)

	def test_so_trash_cleanup(self):
		"""Test that ledger entries are DELETED when SO is trashed."""
		items = [{"boq_item": self.boq_item, "qty": 2, "percentage": 20}]
		result = create_sales_order_from_selected_items(
			project=self.project,
			items=items,
			auto_submit=1
		)
		so_name = result.get("name")
		
		# Verify ledger entry exists
		ledger_exists = frappe.db.exists("BOQ Progress Ledger", {
			"reference_doctype": "Sales Order",
			"reference_name": so_name
		})
		self.assertTrue(ledger_exists)
		
		# Delete SO (trash)
		# Needs to be cancelled first to be trashed usually, but hooks should catch it.
		so = frappe.get_doc("Sales Order", so_name)
		so.cancel()
		frappe.delete_doc("Sales Order", so_name)
		
		# Verify ledger entry is gone
		ledger_exists = frappe.db.exists("BOQ Progress Ledger", {
			"reference_doctype": "Sales Order",
			"reference_name": so_name
		})
		self.assertFalse(ledger_exists)

	def test_so_cancel_with_invoice(self):
		"""Test that ledger entries are REVERSED (not deleted) when SO has a linked invoice."""
		items = [{"boq_item": self.boq_item, "qty": 3, "percentage": 30}]
		result = create_sales_order_from_selected_items(
			project=self.project,
			items=items,
			auto_submit=1
		)
		so_name = result.get("name")
		
		# Create a dummy Sales Invoice Item linked to this SO via raw SQL to bypass validations
		dummy_name = frappe.generate_hash()
		frappe.db.sql("""
			INSERT INTO `tabSales Invoice Item` (name, parent, parenttype, sales_order, item_code, docstatus, qty, amount)
			VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
		""", (dummy_name, "DUMMY-INV", "Sales Invoice", so_name, self.item_code, 0, 3, 3000))
		frappe.db.commit()
		
		# Cancel SO
		so = frappe.get_doc("Sales Order", so_name)
		so.cancel()
		
		# Verify ledger entry still exists but is reversed (amount = 0)
		ledger_entry = frappe.db.get_value("BOQ Progress Ledger", {
			"reference_doctype": "Sales Order",
			"reference_name": so_name
		}, ["name", "amount"], as_dict=True)
		
		self.assertIsNotNone(ledger_entry)
		self.assertEqual(flt(ledger_entry.amount), 0)
		
		# Cleanup si_item
		frappe.db.delete("Sales Invoice Item", {"sales_order": so_name})


def run_manual_tests():
	"""
	Helper to run tests via bench execute when the test runner is broken.
	"""
	test = TestSalesOrderCancellation()
	test.setUp()
	
	print("Running test_so_cancel_no_invoice...")
	test.test_so_cancel_no_invoice()
	print("✓ test_so_cancel_no_invoice passed")
	
	print("Running test_so_trash_cleanup...")
	test.test_so_trash_cleanup()
	print("✓ test_so_trash_cleanup passed")
	
	print("Running test_so_cancel_with_invoice...")
	test.test_so_cancel_with_invoice()
	print("✓ test_so_cancel_with_invoice passed")
	
	print("All tests passed successfully!")
