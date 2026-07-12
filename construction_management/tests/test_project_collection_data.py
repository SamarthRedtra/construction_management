# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, today

from construction_management.api.project_collection_data import (
	COLLECTION_ROW_KEYS,
	get_collection_portfolio,
	get_collection_project_rows,
)
from construction_management.construction_management.page.project_soa.project_soa import (
	create_project_soa_follow_up,
)
from construction_management.tests.test_utils import create_test_project


class TestProjectCollectionData(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.defaults.get_defaults().company
		cls.customer = cls._ensure_customer()
		cls.item = cls._ensure_item()
		cls.project = create_test_project("TEST-COLLECTION")
		frappe.db.set_value("Project", cls.project, {
			"status": "Open",
			"is_active": "Yes",
			"company": cls.company,
			"customer": cls.customer,
		})
		cls.boq_item_name = cls._create_boq_item(cls.project)

	def _prepare_project(self, project: str) -> None:
		frappe.db.set_value("Project", project, {
			"status": "Open",
			"is_active": "Yes",
			"company": self.company,
			"customer": self.customer,
		})

	def test_row_shape_has_all_keys(self):
		project = create_test_project("TEST-COL-ROW-SHAPE")
		self._prepare_project(project)
		self._create_boq_item(project)
		self._create_sales_order(project, 1000)

		data = get_collection_project_rows(project)
		self.assertTrue(data["rows"])
		row = data["rows"][0]
		for key in COLLECTION_ROW_KEYS:
			self.assertIn(key, row)

	def test_open_pc_row_has_pc_date_and_amt(self):
		project = create_test_project("TEST-COL-PC-ONLY")
		self._prepare_project(project)
		self._create_boq_item(project)
		so_name = self._create_sales_order(project, 3000)
		pc_name = self._create_payment_certificate(project, so_name, 3000)

		data = get_collection_project_rows(project)
		pc_rows = [r for r in data["rows"] if r["reference_name"] == pc_name]
		if not pc_rows:
			pc_rows = [
				r for r in data["rows"]
				if r.get("payment_certificate") == pc_name or flt(r.get("pc_amt")) == 3000
			]
		self.assertTrue(pc_rows, "Expected a row with PC amount populated")
		row = pc_rows[0]
		self.assertTrue(row["pc_date"])
		self.assertEqual(row["pc_amt"], 3000)

	def test_no_duplicate_so_when_pc_exists(self):
		project = create_test_project("TEST-COL-NO-DUP")
		self._prepare_project(project)
		self._create_boq_item(project)
		so_name = self._create_sales_order(project, 2500)
		self._create_payment_certificate(project, so_name, 2500)

		data = get_collection_project_rows(project)
		so_rows = [r for r in data["rows"] if r["reference_doctype"] == "Sales Order"]
		self.assertEqual(len(so_rows), 0)

	def test_open_so_row_has_pi_only(self):
		project = create_test_project("TEST-COL-SO-ONLY")
		self._prepare_project(project)
		self._create_boq_item(project)
		so_name = self._create_sales_order(project, 5000)

		data = get_collection_project_rows(project)
		so_rows = [r for r in data["rows"] if r["reference_name"] == so_name]
		self.assertEqual(len(so_rows), 1)
		row = so_rows[0]
		self.assertEqual(row["pi_amount"], 5000)
		self.assertFalse(row["pc_amt"])
		self.assertFalse(row["ti_amt"])

	def test_follow_up_overlay_merges_remarks(self):
		project = create_test_project("TEST-COL-FU")
		self._prepare_project(project)
		self._create_boq_item(project)
		so_name = self._create_sales_order(project, 1500)

		create_project_soa_follow_up(
			project=project,
			reference_doctype="Sales Order",
			reference_name=so_name,
			follow_up_date=today(),
			status="Open",
			remarks="Awaiting PC",
		)

		data = get_collection_project_rows(project)
		row = next(r for r in data["rows"] if r["reference_name"] == so_name)
		self.assertIn("Awaiting PC", row["remarks"])
		self.assertEqual(row["follow_up_status"], "Open")

	def test_portfolio_includes_project_summary(self):
		project = create_test_project("TEST-COL-PORTFOLIO")
		self._prepare_project(project)
		self._create_boq_item(project)
		self._create_sales_order(project, 2000)

		portfolio = get_collection_portfolio(self.company)
		match = next((p for p in portfolio if p["project"] == project), None)
		self.assertIsNotNone(match)
		self.assertGreater(match["pi_total"], 0)

	def test_tax_si_resolves_pc_from_custom_field(self):
		if not frappe.db.has_column("Sales Invoice", "custom_payment_certificate"):
			self.skipTest("custom_payment_certificate not on Sales Invoice")

		project = create_test_project("TEST-COL-TI-PC")
		self._prepare_project(project)
		self._create_boq_item(project)
		so_name = self._create_sales_order(project, 4000)
		pc_name = self._create_payment_certificate(project, so_name, 4000)
		si_name = self._create_tax_invoice(project, so_name, pc_name, 4000)

		data = get_collection_project_rows(project)
		si_rows = [r for r in data["rows"] if r["reference_name"] == si_name]
		self.assertEqual(len(si_rows), 1)
		row = si_rows[0]
		self.assertEqual(row["pc_amt"], 4000)
		self.assertEqual(row["ti_amt"], 4000)
		self.assertEqual(row["pi_amount"], 4000)

	@classmethod
	def _ensure_customer(cls) -> str:
		customer_name = "TEST-COL-CUSTOMER"
		if frappe.db.exists("Customer", customer_name):
			return customer_name
		doc = frappe.new_doc("Customer")
		doc.customer_name = customer_name
		doc.customer_type = "Company"
		doc.insert(ignore_permissions=True)
		return doc.name

	@classmethod
	def _ensure_item(cls) -> str:
		item_code = "TEST-COL-ITEM"
		if frappe.db.exists("Item", item_code):
			frappe.db.set_value("Item", item_code, "is_stock_item", 0)
			return item_code
		doc = frappe.new_doc("Item")
		doc.item_code = item_code
		doc.item_name = item_code
		doc.item_group = "All Item Groups"
		doc.stock_uom = "Nos"
		doc.is_stock_item = 0
		doc.insert(ignore_permissions=True)
		return doc.name

	@classmethod
	def _create_project_boq(cls, project: str) -> str:
		existing = frappe.db.get_value("Project BOQ", {"project": project}, "name")
		if existing:
			return existing

		boq = frappe.new_doc("Project BOQ")
		boq.project = project
		boq.boq_name = f"Collection BOQ {project}"
		boq.status = "Draft"
		boq.insert(ignore_permissions=True)
		return boq.name

	@classmethod
	def _create_boq_bill(cls, project: str, project_boq: str) -> str:
		existing = frappe.db.get_value("BOQ Bill", {"project": project, "project_boq": project_boq}, "name")
		if existing:
			return existing

		bill = frappe.new_doc("BOQ Bill")
		bill.project = project
		bill.project_boq = project_boq
		bill.label = "Collection Bill"
		bill.bill_no = f"COL-{frappe.generate_hash(length=6)}"
		bill.insert(ignore_permissions=True)
		return bill.name

	@classmethod
	def _create_boq_item(cls, project: str) -> str:
		existing = frappe.db.sql(
			"""
			SELECT name FROM `tabBOQ Item`
			WHERE project = %s
			ORDER BY creation ASC
			LIMIT 1
			""",
			project,
		)
		if existing:
			return existing[0][0]

		project_boq = cls._create_project_boq(project)
		bill = cls._create_boq_bill(project, project_boq)
		item = frappe.new_doc("BOQ Item")
		item.item_code = cls.item
		item.project = project
		item.project_boq = project_boq
		item.parent_bill = bill
		item.description = f"Collection item {project}"
		item.unit = "Nos"
		item.total_qty = 10
		item.rate = 100
		item.amount = 1000
		item.insert(ignore_permissions=True)
		return item.name

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

	def _create_tax_invoice(self, project: str, sales_order: str, payment_certificate: str, amount: float) -> str:
		boq_item = self._get_boq_item_for_project(project)
		si = frappe.new_doc("Sales Invoice")
		si.customer = self.customer
		si.company = self.company
		si.project = project
		si.posting_date = today()
		si.due_date = add_days(today(), 30)
		if frappe.db.has_column("Sales Invoice", "custom_sales_order"):
			si.custom_sales_order = sales_order
		if frappe.db.has_column("Sales Invoice", "custom_payment_certificate"):
			si.custom_payment_certificate = payment_certificate
		if frappe.db.has_column("Sales Invoice", "custom_is_proforma"):
			si.custom_is_proforma = 0
		si.append("items", {
			"item_code": self.item,
			"qty": 1,
			"rate": amount,
			"amount": amount,
			"sales_order": sales_order,
			"boq_item": boq_item.name,
			"bill_no": boq_item.parent_bill,
			"project": project,
		})
		si.insert(ignore_permissions=True)
		si.submit()
		return si.name
