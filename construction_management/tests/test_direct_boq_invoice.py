# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from construction_management.api.boq_invoice import create_invoice_from_selected_items
from construction_management.overrides.sales_invoice import SalesInvoiceOverride
from construction_management.tests.test_property_boq_ui import (
	create_test_boq_structure,
	create_test_customer,
	create_test_project,
)


def _add_boq_item_to_bill(project, project_boq, bill, total_qty=50, rate=20):
	"""Add another BOQ item under an existing bill (one Project BOQ per project)."""
	import random
	import string

	from frappe.utils import flt

	suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
	item = frappe.new_doc("BOQ Item")
	item.parent_bill = bill
	item.project_boq = project_boq
	item.project = project
	item.description = f"Test Item {suffix}"
	item.unit = "Nos"
	item.total_qty = flt(total_qty)
	item.rate = flt(rate)
	item.total_amount = flt(total_qty) * flt(rate)
	item.balance_qty = flt(total_qty)
	item.balance_amount = flt(total_qty) * flt(rate)
	item.billing_status = "Not Billed"
	item.insert(ignore_permissions=True)
	return item.name


class TestDirectBoqInvoice(IntegrationTestCase):
	"""Direct BOQ → Sales Invoice without Sales Order."""

	def setUp(self):
		self.test_project = create_test_project(f"TEST-DIRECT-BOQ-{frappe.generate_hash(length=8)}")
		self.test_customer = create_test_customer(f"Test Direct BOQ {frappe.generate_hash(length=6)}")
		frappe.db.set_value("Project", self.test_project, "customer", self.test_customer)

	@patch(
		"construction_management.construction_management.doctype.boq_item.boq_item.check_rate_history_table"
	)
	def test_multi_item_invoice_has_no_sales_order_and_direct_billing_mode(self, _mock_rate_table):
		boq, bill, item1 = create_test_boq_structure(self.test_project, total_qty=100, rate=10)
		item2 = _add_boq_item_to_bill(self.test_project, boq, bill, total_qty=50, rate=20)

		result = create_invoice_from_selected_items(
			project=self.test_project,
			items=[
				{"boq_item": item1, "qty": 10},
				{"boq_item": item2, "qty": 5},
			],
			apply_retention=0,
			is_proforma=0,
		)

		self.assertIn("invoice", result)
		si = frappe.get_doc("Sales Invoice", result["invoice"])
		self.assertEqual(si.docstatus, 0)

		revenue_lines = [
			row for row in si.items if row.item_code not in ("RETENTION-DEDUCTION", "ADVANCE-DEDUCTION")
		]
		self.assertGreaterEqual(len(revenue_lines), 2)
		for row in revenue_lines:
			self.assertFalse(row.sales_order)
			self.assertTrue(row.boq_item)

		if frappe.get_meta("Sales Invoice").has_field("custom_billing_mode"):
			self.assertEqual(si.custom_billing_mode, "Direct BOQ")

		si.submit()

		ledger_count = frappe.db.count(
			"BOQ Progress Ledger",
			{"reference_doctype": "Sales Invoice", "reference_name": si.name},
		)
		self.assertGreater(ledger_count, 0)

	@patch(
		"construction_management.construction_management.doctype.boq_item.boq_item.check_rate_history_table"
	)
	def test_direct_invoice_gl_has_no_unbilled_when_unearned_enabled(self, _mock_rate_table):
		company = frappe.db.get_value("Project", self.test_project, "company")
		if not company or not frappe.db.exists("BOQ Settings", company):
			self.skipTest("BOQ Settings not configured for test company")

		boq_settings = frappe.get_doc("BOQ Settings", company)
		if not boq_settings.get("enable_so_unearned_revenue_jv"):
			self.skipTest("Unearned revenue JV not enabled in BOQ Settings")

		unbilled_acc = boq_settings.so_unearned_revenue_debit_account
		if not unbilled_acc:
			self.skipTest("Unbilled account not configured")

		_, bill, item = create_test_boq_structure(self.test_project, total_qty=100, rate=100)

		result = create_invoice_from_selected_items(
			project=self.test_project,
			items=[{"boq_item": item, "qty": 5}],
			apply_retention=0,
			is_proforma=0,
		)
		si = frappe.get_doc("Sales Invoice", result["invoice"])

		gl = SalesInvoiceOverride.get_gl_entries(si)
		unbilled_lines = [e for e in gl if e.get("account") == unbilled_acc and flt(e.get("credit"))]
		self.assertEqual(len(unbilled_lines), 0)
