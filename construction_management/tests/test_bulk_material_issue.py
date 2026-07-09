# Copyright (c) 2026, Construction Management
# License: MIT

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, get_last_day, getdate, today

from construction_management.api.bulk_material_issue import (
	POSTING_DATE_END_OF_MONTH,
	POSTING_DATE_SAME,
	SOURCE_PURCHASE_RECEIPT,
	create_material_issues,
	get_bulk_material_issue_posting_date,
	get_eligible_sources,
	get_issued_qty,
)


class TestBulkMaterialIssuePostingDate(FrappeTestCase):
	def setUp(self):
		self.company = self._get_company()
		self._ensure_boq_settings()

	def test_same_date_rule(self):
		source_date = "2026-03-15"
		frappe.db.set_value(
			"BOQ Settings",
			self.company,
			"bulk_material_issue_posting_date_rule",
			POSTING_DATE_SAME,
		)

		posting_date = get_bulk_material_issue_posting_date(self.company, source_date)
		self.assertEqual(getdate(posting_date), getdate(source_date))

	def test_end_of_month_rule(self):
		source_date = "2026-03-15"
		frappe.db.set_value(
			"BOQ Settings",
			self.company,
			"bulk_material_issue_posting_date_rule",
			POSTING_DATE_END_OF_MONTH,
		)

		posting_date = get_bulk_material_issue_posting_date(self.company, source_date)
		self.assertEqual(getdate(posting_date), getdate(get_last_day(source_date)))

	def test_posting_date_override(self):
		override = "2026-05-01"
		posting_date = get_bulk_material_issue_posting_date(
			self.company,
			"2026-03-15",
			posting_date_override=override,
		)
		self.assertEqual(getdate(posting_date), getdate(override))

	def _get_company(self):
		company = frappe.db.get_value("Company", {}, "name")
		if not company:
			self.skipTest("No company available for tests")
		return company

	def _ensure_boq_settings(self):
		if not frappe.db.exists("BOQ Settings", self.company):
			settings = frappe.new_doc("BOQ Settings")
			settings.company = self.company
			settings.insert(ignore_permissions=True)


class TestBulkMaterialIssueOperations(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_value("Company", {}, "name")
		if not cls.company:
			raise unittest.SkipTest("No company available for tests")

		cls.project = _create_test_project("TEST-BULK-ISSUE-PROJECT", cls.company)
		cls.item_code = _create_test_item("TEST-BULK-ISSUE-ITEM")
		cls.source_wh = _create_test_warehouse(f"Bulk Issue Source WH {frappe.generate_hash(length=6)}", cls.project)
		cls.site_wh = _create_test_warehouse(f"Bulk Issue Site WH {frappe.generate_hash(length=6)}", cls.project)
		_add_stock(cls.item_code, cls.source_wh, 100)
		_ensure_boq_settings(cls.company, default_warehouse=cls.site_wh)

	def setUp(self):
		from construction_management.api.bulk_material_issue import get_available_stock

		if get_available_stock(self.source_wh, self.item_code) < 500:
			_add_stock(self.item_code, self.source_wh, 500)

	def test_material_transfer_issue_from_target_warehouse(self):
		created_entries = []
		try:
			mt = _create_material_transfer(
				self.company,
				self.item_code,
				self.source_wh,
				self.site_wh,
				10,
			)
			mt_line = mt.items[0].name

			rows = get_eligible_sources(
				company=self.company,
				source_type="Material Transfer",
				selected_sources=[{"doctype": "Stock Entry", "name": mt.name}],
			)
			self.assertEqual(len(rows), 1)
			self.assertEqual(rows[0]["warehouse"], self.site_wh)
			self.assertEqual(flt(rows[0]["remaining_qty"]), 10)
			self.assertGreaterEqual(flt(rows[0]["available_qty"]), 10)
			self.assertEqual(
				flt(rows[0]["qty_to_issue"]),
				min(flt(rows[0]["remaining_qty"]), flt(rows[0]["available_qty"])),
			)
			self.assertLessEqual(flt(rows[0]["qty_to_issue"]), 10)

			results = create_material_issues([rows[0]], submit=1)
			self.assertEqual(results[0]["status"], "Success")
			self.assertTrue(results[0]["stock_entry"])
			created_entries.append(results[0]["stock_entry"])

			issue_se = frappe.get_doc("Stock Entry", results[0]["stock_entry"])
			self.assertEqual(issue_se.stock_entry_type, "Material Issue")
			self.assertEqual(issue_se.items[0].s_warehouse, self.site_wh)
			self.assertEqual(flt(get_issued_qty("Stock Entry Detail", mt_line)), 10)

			issue_se.cancel()
			created_entries.remove(issue_se.name)
			self.assertEqual(flt(get_issued_qty("Stock Entry Detail", mt_line)), 0)
		finally:
			_cancel_stock_entries(created_entries)

	def test_material_issue_posting_date_uses_source_document_not_today(self):
		from construction_management.api.bulk_material_issue import _create_material_issue_for_source

		frappe.db.set_value(
			"BOQ Settings",
			self.company,
			"bulk_material_issue_posting_date_rule",
			POSTING_DATE_SAME,
		)

		mt = _create_material_transfer(
			self.company,
			self.item_code,
			self.source_wh,
			self.site_wh,
			3,
		)
		frappe.db.set_value("Stock Entry", mt.name, "posting_date", "2026-06-15")
		mt.reload()

		row = {
			"source_doctype": "Stock Entry",
			"source_name": mt.name,
			"source_line_name": mt.items[0].name,
			"company": self.company,
			"item_code": self.item_code,
			"warehouse": self.site_wh,
			"qty_to_issue": 3,
			"project": self.project,
		}

		issue_se = _create_material_issue_for_source([row], submit=0)
		self.assertEqual(str(issue_se.posting_date), "2026-06-15")
		issue_se.delete()

	def test_material_issue_end_of_month_rule_from_source_date(self):
		from construction_management.api.bulk_material_issue import _create_material_issue_for_source

		frappe.db.set_value(
			"BOQ Settings",
			self.company,
			"bulk_material_issue_posting_date_rule",
			POSTING_DATE_END_OF_MONTH,
		)

		mt = _create_material_transfer(
			self.company,
			self.item_code,
			self.source_wh,
			self.site_wh,
			2,
		)
		frappe.db.set_value("Stock Entry", mt.name, "posting_date", "2026-06-15")
		mt.reload()

		row = {
			"source_doctype": "Stock Entry",
			"source_name": mt.name,
			"source_line_name": mt.items[0].name,
			"company": self.company,
			"item_code": self.item_code,
			"warehouse": self.site_wh,
			"qty_to_issue": 2,
			"project": self.project,
		}

		issue_se = _create_material_issue_for_source([row], submit=0)
		self.assertEqual(str(issue_se.posting_date), "2026-06-30")
		issue_se.delete()

	def test_create_recomputes_posting_date_from_boq_settings(self):
		frappe.db.set_value(
			"BOQ Settings",
			self.company,
			"bulk_material_issue_posting_date_rule",
			POSTING_DATE_END_OF_MONTH,
		)

		posting_date = get_bulk_material_issue_posting_date(self.company, "2026-03-15")
		self.assertEqual(str(posting_date), "2026-03-31")

	def test_finalize_hides_zero_stock_rows(self):
		from construction_management.api.bulk_material_issue import _finalize_eligible_rows

		rows = _finalize_eligible_rows(
			[
				{
					"warehouse": self.site_wh,
					"item_code": self.item_code,
					"remaining_qty": 10,
				},
				{
					"warehouse": self.site_wh,
					"item_code": "NON-EXISTENT-ITEM",
					"remaining_qty": 5,
				},
			],
			hide_zero_stock=True,
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["item_code"], self.item_code)

	def test_fetch_caps_qty_to_available_stock(self):
		from unittest.mock import patch

		from construction_management.api.bulk_material_issue import _apply_stock_cap

		with patch(
			"construction_management.api.bulk_material_issue.get_available_stock",
			return_value=20,
		):
			row = _apply_stock_cap(
				{
					"warehouse": self.site_wh,
					"item_code": self.item_code,
					"remaining_qty": 100,
				}
			)

		self.assertEqual(flt(row["remaining_qty"]), 100)
		self.assertEqual(flt(row["available_qty"]), 20)
		self.assertEqual(flt(row["qty_to_issue"]), 20)
		self.assertEqual(row["stock_limited"], 1)

	def test_purchase_receipt_partial_issue_blocks_over_issue(self):
		if not frappe.db.has_column("Purchase Receipt Item", "custom_material_issued_qty"):
			self.skipTest("Bulk material issue custom fields not installed")

		created_entries = []
		try:
			pr = _create_submitted_purchase_receipt(
				self.company,
				self.project,
				self.item_code,
				self.site_wh,
				10,
			)
			pr_line = pr.items[0].name

			rows = get_eligible_sources(
				company=self.company,
				source_type="Purchase Receipt",
				selected_sources=[{"doctype": "Purchase Receipt", "name": pr.name}],
			)
			self.assertEqual(len(rows), 1)
			self.assertEqual(flt(rows[0]["qty_to_issue"]), 10)

			first_row = rows[0].copy()
			first_row["qty_to_issue"] = 4
			results = create_material_issues([first_row], submit=1)
			self.assertEqual(results[0]["status"], "Success")
			created_entries.append(results[0]["stock_entry"])
			self.assertEqual(flt(get_issued_qty("Purchase Receipt Item", pr_line)), 4)

			remaining_rows = get_eligible_sources(
				company=self.company,
				source_type="Purchase Receipt",
				selected_sources=[{"doctype": "Purchase Receipt", "name": pr.name}],
			)
			self.assertEqual(len(remaining_rows), 1)
			self.assertEqual(flt(remaining_rows[0]["qty_to_issue"]), 6)

			over_row = remaining_rows[0].copy()
			over_row["qty_to_issue"] = 7
			over_results = create_material_issues([over_row], submit=1)
			self.assertEqual(over_results[0]["status"], "Failed")
			self.assertEqual(flt(get_issued_qty("Purchase Receipt Item", pr_line)), 4)

			second_row = remaining_rows[0].copy()
			second_row["qty_to_issue"] = 6
			second_results = create_material_issues([second_row], submit=1)
			self.assertEqual(second_results[0]["status"], "Success")
			created_entries.append(second_results[0]["stock_entry"])
			self.assertEqual(flt(get_issued_qty("Purchase Receipt Item", pr_line)), 10)

			issue_se = frappe.get_doc("Stock Entry", second_results[0]["stock_entry"])
			issue_se.cancel()
			created_entries.remove(issue_se.name)
			self.assertEqual(flt(get_issued_qty("Purchase Receipt Item", pr_line)), 4)
		finally:
			_cancel_stock_entries(created_entries)

	def test_bulk_tool_processes_multiple_sources(self):
		created_entries = []
		try:
			mt = _create_material_transfer(
				self.company,
				self.item_code,
				self.source_wh,
				self.site_wh,
				5,
			)
			pr = _create_submitted_purchase_receipt(
				self.company,
				self.project,
				self.item_code,
				self.site_wh,
				8,
			)

			rows = get_eligible_sources(
				company=self.company,
				source_type="Both",
				selected_sources=[
					{"doctype": "Stock Entry", "name": mt.name},
					{"doctype": "Purchase Receipt", "name": pr.name},
				],
			)
			self.assertEqual(len(rows), 2)

			results = create_material_issues(rows, submit=1)
			self.assertEqual(len(results), 2)
			self.assertTrue(all(result["status"] == "Success" for result in results))
			created_entries.extend(result["stock_entry"] for result in results)

			for result in results:
				frappe.get_doc("Stock Entry", result["stock_entry"]).cancel()
			created_entries.clear()
		finally:
			_cancel_stock_entries(created_entries)


def _ensure_boq_settings(company, default_warehouse=None):
	if not frappe.db.exists("BOQ Settings", company):
		settings = frappe.new_doc("BOQ Settings")
		settings.company = company
		settings.default_warehouse = default_warehouse
		settings.bulk_material_issue_posting_date_rule = POSTING_DATE_SAME
		settings.insert(ignore_permissions=True)
		return

	frappe.db.set_value(
		"BOQ Settings",
		company,
		{
			"default_warehouse": default_warehouse,
			"bulk_material_issue_posting_date_rule": POSTING_DATE_SAME,
		},
	)


def _create_test_item(item_code):
	if frappe.db.exists("Item", item_code):
		return item_code

	item = frappe.new_doc("Item")
	item.item_code = item_code
	item.item_name = item_code
	item.item_group = "Products"
	item.stock_uom = "Nos"
	item.is_stock_item = 1
	item.valuation_rate = 100
	item.insert(ignore_permissions=True)
	return item.name


def _create_test_project(name, company):
	existing = frappe.db.get_value("Project", {"project_name": name}, "name")
	if existing:
		frappe.db.set_value("Project", existing, "company", company)
		return existing

	project = frappe.new_doc("Project")
	project.project_name = name
	project.company = company
	project.insert(ignore_permissions=True)
	return project.name


def _create_test_warehouse(name, project=None):
	company = frappe.db.get_value("Company", {}, "name")
	full_name = frappe.db.get_value("Warehouse", {"warehouse_name": name, "company": company})
	if full_name:
		if project:
			frappe.db.set_value("Warehouse", full_name, "custom_project", project)
		return full_name

	warehouse = frappe.new_doc("Warehouse")
	warehouse.warehouse_name = name
	warehouse.company = company
	if project:
		warehouse.custom_project = project
	warehouse.insert(ignore_permissions=True)
	return warehouse.name


def _add_stock(item_code, warehouse, qty):
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Receipt"
	se.company = frappe.db.get_value("Warehouse", warehouse, "company")
	se.append(
		"items",
		{
			"item_code": item_code,
			"t_warehouse": warehouse,
			"qty": qty,
			"basic_rate": 100,
		},
	)
	se.insert(ignore_permissions=True)
	se.submit()


def _create_material_transfer(company, item_code, s_warehouse, t_warehouse, qty):
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Transfer"
	se.company = company
	se.append(
		"items",
		{
			"item_code": item_code,
			"s_warehouse": s_warehouse,
			"t_warehouse": t_warehouse,
			"qty": qty,
		},
	)
	se.insert(ignore_permissions=True)
	se.submit()
	return se


def _create_submitted_purchase_receipt(company, project, item_code, warehouse, qty):
	supplier = frappe.db.get_value("Supplier", {"disabled": 0}, "name")
	if not supplier:
		supplier = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": "Bulk Issue Test Supplier",
				"supplier_group": "All Supplier Groups",
			}
		).insert(ignore_permissions=True).name

	pr = frappe.new_doc("Purchase Receipt")
	pr.company = company
	pr.supplier = supplier
	pr.project = project
	pr.posting_date = today()
	pr.append(
		"items",
		{
			"item_code": item_code,
			"qty": qty,
			"received_qty": qty,
			"warehouse": warehouse,
			"project": project,
			"rate": 100,
			"uom": "Nos",
			"stock_uom": "Nos",
			"conversion_factor": 1,
		},
	)
	pr.insert(ignore_permissions=True)
	pr.submit()
	return pr


def _issue_stock_from_warehouse(company, item_code, warehouse, qty):
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Issue"
	se.company = company
	se.append(
		"items",
		{
			"item_code": item_code,
			"s_warehouse": warehouse,
			"qty": qty,
		},
	)
	se.insert(ignore_permissions=True)
	se.submit()
	return se


def _cancel_stock_entries(stock_entry_names):
	for stock_entry_name in stock_entry_names or []:
		if not stock_entry_name or not frappe.db.exists("Stock Entry", stock_entry_name):
			continue
		doc = frappe.get_doc("Stock Entry", stock_entry_name)
		if doc.docstatus == 1:
			doc.cancel()
		elif doc.docstatus == 0:
			doc.delete()
	frappe.db.commit()
