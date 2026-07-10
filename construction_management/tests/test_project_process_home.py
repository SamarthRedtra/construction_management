# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from construction_management.construction_management.page.project_process_home.project_process_home import (
	get_member_home_companies,
	get_project_process_home_data,
	get_project_process_rows,
)
from construction_management.tests.test_utils import create_test_boq_structure, create_test_project


class TestProjectProcessHome(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ongoing_project = create_test_project("TEST-PPH-ONGOING")
		cls.completed_project = create_test_project("TEST-PPH-COMPLETED")
		frappe.db.set_value("Project", cls.ongoing_project, {
			"status": "Open",
			"custom_project_no": "9901",
			"custom_location": "Dubai Marina",
			"is_active": "Yes",
		})
		frappe.db.set_value("Project", cls.completed_project, {
			"status": "Completed",
			"custom_project_no": "9902",
			"custom_location": "Fujairah Site",
			"is_active": "Yes",
		})

		cls.bill_name, cls.boq_item = cls._create_boq_items(cls.ongoing_project)

	def test_ongoing_status_filter(self):
		result = get_project_process_home_data(status_filter="ongoing", search="9901")
		project_names = [row["name"] for row in result["projects"]]
		self.assertIn(self.ongoing_project, project_names)
		self.assertNotIn(self.completed_project, project_names)

	def test_completed_status_filter(self):
		result = get_project_process_home_data(status_filter="completed", search="9902")
		project_names = [row["name"] for row in result["projects"]]
		self.assertIn(self.completed_project, project_names)
		self.assertNotIn(self.ongoing_project, project_names)

	def test_search_by_project_name(self):
		result = get_project_process_home_data(status_filter="all", search="TEST-PPH-ONGOING")
		self.assertEqual(result["total_count"], 1)
		self.assertEqual(result["projects"][0]["name"], self.ongoing_project)

	def test_company_filter(self):
		company = frappe.db.get_value("Project", self.ongoing_project, "company")
		self.assertTrue(company)

		result = get_project_process_home_data(status_filter="all", company=company, search="9901")
		project_names = [row["name"] for row in result["projects"]]
		self.assertIn(self.ongoing_project, project_names)

		other_company = frappe.db.get_value("Company", {"name": ["!=", company]}, "name")
		if other_company:
			other_project = create_test_project("TEST-PPH-OTHER-CO")
			frappe.db.set_value("Project", other_project, {
				"status": "Open",
				"custom_project_no": "9901-OTHER",
				"is_active": "Yes",
				"company": other_company,
			})
			result_other = get_project_process_home_data(status_filter="all", company=other_company, search="9901-OTHER")
			self.assertEqual(result_other["total_count"], 1)
			self.assertEqual(result_other["projects"][0]["name"], other_project)

			result_filtered = get_project_process_home_data(status_filter="all", company=company, search="9901")
			self.assertNotIn(other_project, [row["name"] for row in result_filtered["projects"]])

	def test_assign_to_uses_project_engineer(self):
		employee_id = "TEST-PPH-ENGINEER"
		if not frappe.db.exists("Employee", employee_id):
			emp = frappe.new_doc("Employee")
			emp.employee = employee_id
			emp.first_name = "Test"
			emp.last_name = "Engineer"
			emp.employee_name = "Test Project Engineer"
			emp.status = "Active"
			emp.date_of_joining = today()
			emp.insert(ignore_permissions=True)

		frappe.db.set_value("Project", self.ongoing_project, "custom_project_engineer", employee_id)
		result = get_project_process_home_data(status_filter="all", search="9901")
		row = next(r for r in result["projects"] if r["name"] == self.ongoing_project)
		self.assertEqual(row["assign_to"], "Test Project Engineer")

	def test_search_by_project_engineer_name(self):
		employee_id = "TEST-PPH-SEARCH-ENG"
		if not frappe.db.exists("Employee", employee_id):
			emp = frappe.new_doc("Employee")
			emp.employee = employee_id
			emp.first_name = "Searchable"
			emp.last_name = "Engineer"
			emp.employee_name = "Searchable Engineer Name"
			emp.status = "Active"
			emp.date_of_joining = today()
			emp.insert(ignore_permissions=True)

		frappe.db.set_value("Project", self.ongoing_project, "custom_project_engineer", employee_id)
		result = get_project_process_home_data(status_filter="all", search="searchable engineer")
		project_names = [row["name"] for row in result["projects"]]
		self.assertIn(self.ongoing_project, project_names)

	def test_process_rows_from_boq_items(self):
		result = get_project_process_rows(self.ongoing_project)
		processes = result["processes"]
		self.assertTrue(processes)
		self.assertTrue(any(p["process_name"] == "GRP Ladder 2m height" for p in processes))
		process = next(p for p in processes if p["process_name"] == "GRP Ladder 2m height")
		self.assertEqual(process["area"], 120.0)
		self.assertEqual(process["doctype"], "BOQ Item")
		self.assertEqual(process["boq_bill"], self.bill_name)

	def test_process_rows_exclude_installments(self):
		project = create_test_project("TEST-PPH-INSTALLMENTS")
		frappe.db.set_value("Project", project, {"status": "Open", "is_active": "Yes"})
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

		result = get_project_process_rows(project)
		names = [row["process_name"] for row in result["processes"]]
		self.assertIn("Waterproofing Scope", names)
		self.assertNotIn("1st Installment", names)

	def test_side_project_falls_back_to_main_boq(self):
		main_project = create_test_project("TEST-PPH-MAIN")
		side_project = create_test_project("TEST-PPH-MAIN (SIDE)")
		frappe.db.set_value("Project", main_project, {"status": "Open", "is_active": "Yes"})
		frappe.db.set_value("Project", side_project, {"status": "Open", "is_active": "Yes"})
		_, _, scope_item = create_test_boq_structure(main_project, total_qty=80, rate=12)
		frappe.db.set_value("BOQ Item", scope_item, {"description": "Concrete Work"})

		_, side_bill, _ = create_test_boq_structure(side_project, total_qty=1, rate=1)
		frappe.db.set_value("BOQ Item", frappe.get_all("BOQ Item", filters={"parent_bill": side_bill}, pluck="name")[0], {
			"description": "2nd Installment",
			"item_code": "2nd Installment",
			"unit": "LM",
		})

		result = get_project_process_rows(side_project)
		self.assertEqual(result["boq_source_project"], main_project)
		self.assertEqual(result["processes"][0]["process_name"], "Concrete Work")

	def test_member_home_companies_api(self):
		companies = get_member_home_companies()
		self.assertTrue(companies)
		company_names = {row["name"] for row in companies}
		project_company = frappe.db.get_value("Project", self.ongoing_project, "company")
		if project_company:
			self.assertIn(project_company, company_names)

	@classmethod
	def _create_boq_items(cls, project: str) -> tuple[str, str]:
		_, bill_name, boq_item = create_test_boq_structure(project, total_qty=100, rate=20)
		frappe.db.set_value("BOQ Item", boq_item, {
			"description": "Insulation Scope",
			"total_qty": 100,
		})

		second_item = frappe.new_doc("BOQ Item")
		second_item.parent_bill = bill_name
		second_item.description = "GRP Ladder 2m height"
		second_item.total_qty = 120
		second_item.rate = 15
		second_item.unit = "m²"
		if hasattr(second_item, "start_date"):
			second_item.start_date = today()
			second_item.end_date = add_days(today(), 15)
		second_item.insert(ignore_permissions=True)

		return bill_name, boq_item
