# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from construction_management.construction_management.page.project_soa.project_soa import (
	create_project_soa_follow_up,
	get_project_soa_data,
	get_project_soa_follow_ups,
)
from construction_management.tests.test_utils import create_test_boq_structure, create_test_project


class TestProjectSOABilling(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.defaults.get_defaults().company
		cls.customer = cls._ensure_customer()
		cls.item = cls._ensure_item()
		cls.project = create_test_project("TEST-SOA-BILLING")
		frappe.db.set_value("Project", cls.project, {
			"status": "Open",
			"is_active": "Yes",
			"company": cls.company,
		})
		cls.boq_item_name = cls._create_boq_item(cls.project)

	def test_sales_order_without_si_appears_as_proforma(self):
		project = create_test_project("TEST-SOA-SO-ONLY")
		frappe.db.set_value("Project", project, {"status": "Open", "is_active": "Yes", "company": self.company})
		self._create_boq_item(project)
		so_name = self._create_sales_order(project, 5000)
		data = get_project_soa_data(project)
		invoice_types = {row["invoice_no"]: row["invoice_type"] for row in data["invoices"]}
		self.assertEqual(invoice_types.get(so_name), "Sales Order (Proforma)")

	def test_payment_certificate_without_si_appears(self):
		project = create_test_project("TEST-SOA-PC-ONLY")
		frappe.db.set_value("Project", project, {"status": "Open", "is_active": "Yes", "company": self.company})
		self._create_boq_item(project)
		so_name = self._create_sales_order(project, 3000)
		pc_name = self._create_payment_certificate(project, so_name, 3000)
		data = get_project_soa_data(project)
		invoice_nos = [row["invoice_no"] for row in data["invoices"]]
		self.assertIn(pc_name, invoice_nos)
		self.assertNotIn(so_name, invoice_nos)

	def test_no_duplicate_so_when_pc_exists(self):
		project = create_test_project("TEST-SOA-NO-DUP")
		frappe.db.set_value("Project", project, {"status": "Open", "is_active": "Yes", "company": self.company})
		self._create_boq_item(project)
		so_name = self._create_sales_order(project, 2500)
		self._create_payment_certificate(project, so_name, 2500)
		data = get_project_soa_data(project)
		so_rows = [row for row in data["invoices"] if row["invoice_type"] == "Sales Order (Proforma)"]
		self.assertEqual(len(so_rows), 0)

	def test_services_exclude_installments(self):
		project = create_test_project("TEST-SOA-INSTALLMENTS")
		frappe.db.set_value("Project", project, {"status": "Open", "is_active": "Yes", "company": self.company})
		_, bill_name, scope_item = create_test_boq_structure(project, total_qty=50, rate=10)
		frappe.db.set_value("BOQ Item", scope_item, {"description": "Waterproofing Scope"})

		installment = frappe.new_doc("BOQ Item")
		installment.parent_bill = bill_name
		installment.description = "1st Installment"
		installment.item_code = "1st Installment"
		installment.total_qty = 1
		installment.rate = 100
		installment.unit = "LM"
		installment.insert(ignore_permissions=True)

		data = get_project_soa_data(project)
		service_names = [row["service"] for row in data["services"]]
		self.assertIn("Waterproofing Scope", service_names)
		self.assertFalse(any("installment" in (name or "").lower() for name in service_names))

	@classmethod
	def _ensure_customer(cls) -> str:
		customer_name = "TEST-SOA-CUSTOMER"
		if frappe.db.exists("Customer", customer_name):
			return customer_name
		doc = frappe.new_doc("Customer")
		doc.customer_name = customer_name
		doc.customer_type = "Company"
		doc.insert(ignore_permissions=True)
		return doc.name

	@classmethod
	def _ensure_item(cls) -> str:
		item_code = "TEST-SOA-ITEM"
		if frappe.db.exists("Item", item_code):
			return item_code
		doc = frappe.new_doc("Item")
		doc.item_code = item_code
		doc.item_name = item_code
		doc.is_stock_item = 0
		doc.insert(ignore_permissions=True)
		return doc.name

	@classmethod
	def _create_boq_item(cls, project: str) -> str:
		_, _, item_name = create_test_boq_structure(project, total_qty=10, rate=100)
		return item_name

	def _get_boq_item_for_project(self, project: str):
		if project == self.project:
			return frappe.get_doc("BOQ Item", self.boq_item_name)
		return frappe.get_doc("BOQ Item", self._create_boq_item(project))

	def _create_sales_order(self, project: str, amount: float) -> str:
		boq_item = self._get_boq_item_for_project(project)
		so = frappe.new_doc("Sales Order")
		so.customer = self.customer
		so.company = self.company
		so.project = project
		so.transaction_date = today()
		so.delivery_date = today()
		so.append("items", {
			"item_code": self.item,
			"qty": 1,
			"rate": amount,
			"amount": amount,
			"boq_item": boq_item.name,
			"bill_no": boq_item.parent_bill,
			"project": project,
		})
		so.insert(ignore_permissions=True)
		so.submit()
		return so.name

	def _create_payment_certificate(self, project: str, sales_order: str, amount: float) -> str:
		boq_item = self._get_boq_item_for_project(project)
		pc = frappe.new_doc("Payment Certificate")
		pc.type = "Sales"
		pc.project = project
		pc.customer = self.customer
		pc.company = self.company
		pc.posting_date = today()
		pc.sales_order = sales_order
		pc.proforma_amount = amount
		pc.accepted_amount = amount
		pc.append("items", {
			"boq_item": boq_item.name,
			"item_code": self.item,
			"item_name": self.item,
			"description": "Test Item",
			"qty": 1,
			"rate": amount,
			"proforma_amount": amount,
			"accepted_amount": amount,
			"bill_no": boq_item.parent_bill,
		})
		pc.insert(ignore_permissions=True)
		pc.submit()
		return pc.name
