# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
import unittest
from unittest.mock import patch
from frappe.utils import flt, today

from construction_management.api.boq_invoice import (
	append_per_item_revenue_and_deductions,
	get_billable_sales_orders_for_invoice,
	get_deduction_details,
	get_pending_so_revenue_lines,
	make_combined_sales_invoice_from_sales_orders,
)


class TestCombinedSalesInvoiceFromSO(unittest.TestCase):
	def test_combined_revenue_lines_preserve_sales_order_uom(self):
		so_item = frappe._dict(
			{
				"name": "SOI-UOM",
				"item_code": "COMBINED-SO-ITEM",
				"description": "Measured roofing work",
				"qty": 12,
				"rate": 50,
				"amount": 600,
				"billed_amt": 0,
				"returned_qty": 0,
				"uom": "M2",
				"stock_uom": "Nos",
				"conversion_factor": 1,
				"boq_item": "BOQ-UOM",
				"bill_no": "BILL-UOM",
			}
		)
		class SalesOrder:
			name = "SO-UOM"
			has_unit_price_items = 0
			items = [so_item]

			def get(self, fieldname, default=None):
				return getattr(self, fieldname, default)

		so_doc = SalesOrder()

		lines = get_pending_so_revenue_lines(so_doc)

		self.assertEqual(len(lines), 1)
		self.assertEqual(lines[0]["uom"], "M2")
		self.assertEqual(lines[0]["stock_uom"], "Nos")
		self.assertEqual(lines[0]["conversion_factor"], 1)

		class Invoice:
			cost_center = "Test Cost Center"

			def __init__(self):
				self.items = []

			def append(self, fieldname, value):
				if fieldname != "items":
					raise AssertionError(f"Unexpected child table: {fieldname}")
				self.items.append(value)

		invoice = Invoice()
		with patch(
			"construction_management.api.boq_invoice.frappe.get_cached_doc",
			return_value=frappe._dict({"varience_item": None}),
		), patch(
			"construction_management.api.boq_invoice.get_boq_items_skip_advance",
			return_value=set(),
		), patch(
			"construction_management.api.boq_invoice.get_or_create_retention_item"
		), patch("construction_management.api.boq_invoice.get_or_create_advance_item"):
			append_per_item_revenue_and_deductions(
				invoice,
				lines,
				{"suggested_retention": 0, "suggested_advance": 0},
				company="Test Company",
				project="Test Project",
				income_account="Test Income",
				cost_center="Test Cost Center",
			)

		self.assertEqual(invoice.items[0]["uom"], "M2")
		self.assertEqual(invoice.items[0]["stock_uom"], "Nos")
		self.assertEqual(invoice.items[0]["conversion_factor"], 1)

	@classmethod
	def setUpClass(cls):
		cls._rate_history_patcher = patch(
			"construction_management.construction_management.doctype.boq_item.boq_item.BOQItem.log_rate_change",
			return_value=None,
		)
		cls._rate_history_patcher.start()

	@classmethod
	def tearDownClass(cls):
		cls._rate_history_patcher.stop()

	def setUp(self):
		frappe.set_user("Administrator")
		self.company = self._get_test_company()
		self.customer = self._get_test_customer()
		if not self.customer:
			return
		self.item = self._get_test_item()
		self.project = self._create_test_project()
		self._ensure_boq_settings()

	def tearDown(self):
		frappe.db.rollback()

	def _get_test_company(self):
		company = frappe.db.get_value("Company", {}, "name")
		if not company:
			company = frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": "Combined SO Test Co",
					"default_currency": "USD",
					"country": "United States",
				}
			).insert(ignore_permissions=True).name

		if not frappe.db.get_value("Company", company, "cost_center"):
			cc = frappe.db.get_value("Cost Center", {"company": company}, "name")
			if cc:
				frappe.db.set_value("Company", company, "cost_center", cc)
		return company

	def _get_test_customer(self):
		customer = frappe.db.sql(
			"""
			SELECT c.name
			FROM `tabCustomer` c
			INNER JOIN `tabCustomer Group` cg ON cg.name = c.customer_group
			WHERE cg.is_group = 0
			LIMIT 1
			"""
		)
		return customer[0][0] if customer else None

	def _get_test_item(self):
		if not frappe.db.exists("Item", "COMBINED-SO-ITEM"):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": "COMBINED-SO-ITEM",
					"item_name": "Combined SO Item",
					"item_group": "All Item Groups",
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)
		return "COMBINED-SO-ITEM"

	def _create_test_project(self):
		project_name = f"Combined SO Test {frappe.generate_hash(length=6)}"
		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": project_name,
				"status": "Open",
				"company": self.company,
				"customer": self.customer,
				"retention_percentage": 10,
				"advance_deduction": 5,
				"enable_progressive_boq": 1,
			}
		).insert(ignore_permissions=True)

		project_boq = self._create_test_project_boq(project.name)
		bill = self._create_test_boq_bill(project.name, project_boq)
		self.boq_items = {}

		for label, amount in (("COMBINED-BOQ-1", 1000), ("COMBINED-BOQ-2", 2000)):
			item = frappe.get_doc(
				{
					"doctype": "BOQ Item",
					"item_code": self.item,
					"project": project.name,
					"project_boq": project_boq,
					"parent_bill": bill,
					"description": label,
					"unit": "Nos",
					"total_qty": 1,
					"rate": amount,
					"amount": amount,
				}
			).insert(ignore_permissions=True)
			self.boq_items[label] = item.name

		return project.name

	def _create_test_project_boq(self, project: str) -> str:
		boq = frappe.new_doc("Project BOQ")
		boq.project = project
		boq.boq_name = f"Combined BOQ {frappe.generate_hash(length=4)}"
		boq.status = "Draft"
		boq.insert(ignore_permissions=True)
		return boq.name

	def _create_test_boq_bill(self, project: str, project_boq: str) -> str:
		bill = frappe.new_doc("BOQ Bill")
		bill.project = project
		bill.project_boq = project_boq
		bill.label = "Combined Bill"
		bill.bill_no = f"CB-{frappe.generate_hash(length=6)}"
		bill.insert(ignore_permissions=True)
		return bill.name

	def _ensure_boq_settings(self):
		if not frappe.db.exists("BOQ Settings", self.company):
			parent_income = frappe.db.get_value(
				"Account", {"root_type": "Income", "company": self.company, "is_group": 1}, "name"
			)
			income_account = frappe.get_doc(
				{
					"doctype": "Account",
					"account_name": f"Combined SO Income {frappe.generate_hash(length=4)}",
					"parent_account": parent_income,
					"company": self.company,
					"account_type": "Income Account",
					"is_group": 0,
				}
			).insert(ignore_permissions=True).name
			frappe.db.set_value("Company", self.company, "default_income_account", income_account)
			frappe.get_doc(
				{
					"doctype": "BOQ Settings",
					"name": self.company,
					"company": self.company,
					"retention_account": income_account,
					"advance_account": income_account,
				}
			).insert(ignore_permissions=True)

	def _create_sales_order(self, boq_label: str, amount: float) -> str:
		boq_item_name = self.boq_items[boq_label]
		boq_item_doc = frappe.get_doc("BOQ Item", boq_item_name)
		so = frappe.new_doc("Sales Order")
		so.customer = self.customer
		so.company = self.company
		so.project = self.project
		so.transaction_date = today()
		so.delivery_date = today()
		so.append(
			"items",
			{
				"item_code": self.item,
				"qty": 1,
				"rate": amount,
				"amount": amount,
				"boq_item": boq_item_doc.name,
				"bill_no": boq_item_doc.parent_bill,
				"project": self.project,
			},
		)
		so.insert(ignore_permissions=True)
		so.submit()
		return so.name

	def test_combined_invoice_from_two_sales_orders(self):
		if not self.customer:
			self.skipTest("No customer available")

		boq_items = frappe.get_all("BOQ Item", filters={"project": self.project}, pluck="name")
		self.assertGreaterEqual(len(boq_items), 2)
		so1 = self._create_sales_order("COMBINED-BOQ-1", 1000)
		so2 = self._create_sales_order("COMBINED-BOQ-2", 2000)

		billable = get_billable_sales_orders_for_invoice(self.project)
		self.assertEqual(len(billable), 2)

		from construction_management.api.boq_invoice import (
			make_combined_sales_invoice_from_selected_sales_orders,
		)

		result = make_combined_sales_invoice_from_selected_sales_orders([so1, so2])
		si_name = result["sales_invoice"]
		si = frappe.get_doc("Sales Invoice", si_name)

		revenue_lines = [
			row
			for row in si.items
			if row.item_code not in ("RETENTION-DEDUCTION", "ADVANCE-DEDUCTION")
		]
		self.assertEqual(len(revenue_lines), 2)
		so_names = {row.sales_order for row in revenue_lines}
		self.assertEqual(so_names, {so1, so2})
		self.assertTrue(all(row.so_detail for row in revenue_lines))
		self.assertTrue(all(row.boq_item for row in revenue_lines))

		total_revenue = sum(flt(row.amount) for row in revenue_lines)
		self.assertEqual(total_revenue, 3000)

		details = get_deduction_details(self.project, revenue_lines, sales_order_names=[so1, so2])
		retention_rows = [row for row in si.items if row.item_code == "RETENTION-DEDUCTION"]
		self.assertEqual(sum(abs(flt(row.amount)) for row in retention_rows), details["suggested_retention"])

		if frappe.db.has_column("Sales Invoice", "custom_source_sales_orders"):
			self.assertIn(so1, si.custom_source_sales_orders)
			self.assertIn(so2, si.custom_source_sales_orders)

		si.submit()
		for so_name in (so1, so2):
			billed = frappe.db.sql(
				"""
				SELECT COALESCE(SUM(soi.billed_amt), 0)
				FROM `tabSales Order Item` soi
				WHERE soi.parent = %s
				""",
				so_name,
			)[0][0]
			self.assertGreater(flt(billed), 0)

	def test_draft_combined_invoice_must_keep_every_source_sales_order(self):
		from construction_management.api.boq_invoice import validate_combined_source_sales_orders

		doc = frappe._dict(
			docstatus=0,
			custom_source_sales_orders="SO-SEP, SO-JUN",
			items=[
				frappe._dict(item_code="WORK", sales_order="SO-SEP"),
				frappe._dict(item_code="RETENTION-DEDUCTION", sales_order="SO-JUN"),
			],
		)
		with self.assertRaises(frappe.ValidationError):
			validate_combined_source_sales_orders(doc)

		doc["items"].append(frappe._dict(item_code="WORK", sales_order="SO-JUN"))
		validate_combined_source_sales_orders(doc)

		doc["items"] = doc["items"][:1]
		doc["docstatus"] = 1
		validate_combined_source_sales_orders(doc)

	def test_direct_billing_blocked_when_boq_item_has_open_sales_order(self):
		from construction_management.api.boq_invoice import _block_direct_billing_with_open_sales_orders

		open_line = [frappe._dict(sales_order="SO-OPEN", boq_item="BOQI-1")]
		with patch(
			"construction_management.api.boq_invoice.frappe.db.sql", return_value=open_line
		), patch(
			"construction_management.api.boq_invoice._so_has_submitted_payment_certificate",
			return_value=False,
		):
			with self.assertRaises(frappe.ValidationError):
				_block_direct_billing_with_open_sales_orders(["BOQI-1"])

	def test_direct_billing_allowed_without_open_sales_order_or_with_pc(self):
		from construction_management.api.boq_invoice import _block_direct_billing_with_open_sales_orders

		with patch("construction_management.api.boq_invoice.frappe.db.sql", return_value=[]):
			_block_direct_billing_with_open_sales_orders(["BOQI-1"])

		open_line = [frappe._dict(sales_order="SO-PC", boq_item="BOQI-1")]
		with patch(
			"construction_management.api.boq_invoice.frappe.db.sql", return_value=open_line
		), patch(
			"construction_management.api.boq_invoice._so_has_submitted_payment_certificate",
			return_value=True,
		):
			_block_direct_billing_with_open_sales_orders(["BOQI-1"])

		with patch("construction_management.api.boq_invoice.frappe.db.sql") as sql:
			_block_direct_billing_with_open_sales_orders([None, ""])
			sql.assert_not_called()

	def test_saving_combined_invoice_without_a_source_order_line_fails(self):
		if not self.customer:
			self.skipTest("No customer available")
		if not frappe.db.has_column("Sales Invoice", "custom_source_sales_orders"):
			self.skipTest("custom_source_sales_orders not installed")
		so1 = self._create_sales_order("COMBINED-BOQ-1", 1000)
		so2 = self._create_sales_order("COMBINED-BOQ-2", 2000)
		result = make_combined_sales_invoice_from_sales_orders(self.project, [so1, so2])
		si = frappe.get_doc("Sales Invoice", result["sales_invoice"])

		si.set("items", [row for row in si.items if row.sales_order != so1])
		with self.assertRaises(frappe.ValidationError):
			si.save()

	def test_rejects_sales_order_without_pending_lines(self):
		if not self.customer:
			self.skipTest("No customer available")
		so1 = self._create_sales_order("COMBINED-BOQ-1", 1000)
		single = make_combined_sales_invoice_from_sales_orders(self.project, [so1])
		si = frappe.get_doc("Sales Invoice", single["sales_invoice"])
		si.submit()

		with self.assertRaises(frappe.ValidationError):
			make_combined_sales_invoice_from_sales_orders(self.project, [so1])

	def test_rejects_different_customers(self):
		if not self.customer:
			self.skipTest("No customer available")

		from construction_management.api.boq_invoice import _validate_combined_sales_orders
		from unittest.mock import MagicMock, patch

		so1 = MagicMock()
		so1.name = "SO-A"
		so1.docstatus = 1
		so1.project = self.project
		so1.customer = "Customer A"
		so1.company = self.company
		so1.taxes_and_charges = None

		so2 = MagicMock()
		so2.name = "SO-B"
		so2.docstatus = 1
		so2.project = self.project
		so2.customer = "Customer B"
		so2.company = self.company
		so2.taxes_and_charges = None

		with patch(
			"construction_management.api.boq_invoice.frappe.get_doc",
			side_effect=[so1, so2],
		), patch(
			"construction_management.api.boq_invoice._so_has_submitted_payment_certificate",
			return_value=False,
		), patch(
			"construction_management.api.boq_invoice.get_pending_so_revenue_lines",
			return_value=[{"amount": 100}],
		):
			with self.assertRaises(frappe.ValidationError):
				_validate_combined_sales_orders(self.project, ["SO-A", "SO-B"])
