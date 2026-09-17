# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.api.project_collection_data import (
	_allocate_invoice_total,
	_collection_filter_date,
	_get_standard_sales_order_links,
	_set_conversion_status,
)
from construction_management.api.project_revenue import get_project_billed_revenue
from construction_management.api.stock_entry_balance import get_item_balances
from construction_management.construction_management.page.project_soa.project_soa import (
	_build_services,
	_payment_rows_for_reference,
)
from construction_management.overrides.sales_order import _as_incremental_values


class TestProjectReportingFixes(UnitTestCase):
	@patch(
		"construction_management.overrides.sales_order._get_previous_cumulative_values"
	)
	def test_cumulative_sales_order_stores_only_period_movement(self, get_previous):
		get_previous.return_value = {
			"qty": 606.61,
			"amount": 73375.5435,
			"retention": 7682.82,
			"advance": 0,
			"variance": 0,
		}
		current = {
			"qty": 1053.04,
			"amount": 127375.7205,
			"retention": 13478.91,
			"advance": 0,
			"variance": 0,
			"billing_percentage": 87.75,
		}

		movement = _as_incremental_values(
			frappe._dict(name="SO-AUG"), "BOQI-2026-00728", current
		)

		self.assertAlmostEqual(movement["qty"], 446.43)
		self.assertAlmostEqual(movement["amount"], 54000.177)
		self.assertAlmostEqual(movement["retention"], 5796.09)

	@patch(
		"construction_management.construction_management.page.project_soa.project_soa.fetch_scope_boq_items"
	)
	@patch(
		"construction_management.construction_management.page.project_soa.project_soa.resolve_boq_source_project",
		return_value="PROJECT-1",
	)
	def test_project_soa_services_use_contract_qty_and_rate(self, _resolve, fetch_items):
		fetch_items.return_value = [
			frappe._dict(
				description="Unit rate service",
				label="",
				item_code="SERVICE-1",
				total_qty=1200,
				rate=128,
				total_amount=141916.064,
				pricing_entry_mode="Unit Rate",
				lump_sum_total=0,
			),
			frappe._dict(
				description="Lump sum service",
				label="",
				item_code="SERVICE-2",
				total_qty=10,
				rate=1,
				total_amount=1,
				pricing_entry_mode="Lump Sum Total",
				lump_sum_total=5000,
			),
		]

		services, total, source = _build_services("PROJECT-1")

		self.assertEqual(services[0]["total_amount"], 153600)
		self.assertEqual(services[1]["unit_price"], 500)
		self.assertEqual(services[1]["total_amount"], 5000)
		self.assertEqual(total, 158600)
		self.assertEqual(source, "PROJECT-1")

	@patch(
		"construction_management.api.stock_entry_balance.get_stock_balance",
		return_value=600,
	)
	@patch(
		"construction_management.api.stock_entry_balance.frappe.has_permission",
		return_value=True,
	)
	def test_stock_entry_balance_uses_selected_posting_timestamp(
		self, _has_permission, get_stock_balance
	):
		balances = get_item_balances(
			items=[
				{
					"name": "ROW-1",
					"item_code": "ITEM-1",
					"s_warehouse": "Stores - MRG",
				}
			],
			posting_date="2026-08-14",
			posting_time="03:28:29",
		)

		self.assertEqual(balances, [{"name": "ROW-1", "actual_qty": 600.0}])
		get_stock_balance.assert_called_once_with(
			"ITEM-1",
			"Stores - MRG",
			posting_date="2026-08-14",
			posting_time="03:28:29",
		)

	def test_collection_filter_prefers_proforma_date(self):
		row = {"pi_date": "2026-01-10", "ti_date": "2026-02-15"}
		self.assertEqual(_collection_filter_date(row), "2026-01-10")

	def test_combined_tax_invoice_allocation_preserves_total(self):
		allocations = _allocate_invoice_total(
			215638.337,
			{"SO-1": 6510.277, "SO-2": 131722.907, "SO-3": 89955.532},
		)

		self.assertEqual(sum(allocations.values()), 215638.337)
		self.assertEqual(allocations["SO-1"], 6152.212)
		self.assertEqual(allocations["SO-2"], 124478.147)
		self.assertEqual(allocations["SO-3"], 85007.978)

	def test_proforma_conversion_status_uses_linked_net_value(self):
		row = {
			"proforma_net_amount": 1000,
			"invoiced_net_amount": 600,
			"tax_invoices": [{"name": "SINV-1"}],
		}
		_set_conversion_status(row)
		self.assertEqual(row["conversion_status"], "Partially Converted")

		row["invoiced_net_amount"] = 1000
		_set_conversion_status(row)
		self.assertEqual(row["conversion_status"], "Converted")

		row["tax_invoices"] = []
		_set_conversion_status(row)
		self.assertEqual(row["conversion_status"], "Not Converted")

	@patch("construction_management.api.project_collection_data.frappe.get_all")
	def test_standard_sales_order_link_is_used(self, get_all):
		get_all.return_value = [
			frappe._dict(parent="SINV-1", sales_order="SO-1"),
			frappe._dict(parent="SINV-1", sales_order="SO-2"),
		]

		links = _get_standard_sales_order_links(["SINV-1"])

		self.assertEqual(links, {"SINV-1": "SO-1"})

	@patch(
		"construction_management.construction_management.page.project_soa.project_soa.frappe.db.sql"
	)
	def test_multiple_payments_share_one_invoice_row(self, sql):
		sql.return_value = [
			frappe._dict(reference_no="CHQ-1", posting_date="2026-01-10", allocated_amount=400),
			frappe._dict(reference_no="CHQ-2", posting_date="2026-01-20", allocated_amount=600),
		]

		rows = _payment_rows_for_reference(
			project="PROJECT-1",
			reference_doctype="Sales Invoice",
			reference_name="SINV-1",
			proforma_date="2026-01-01",
			tax_invoice_date="2026-01-05",
			invoice_no="SINV-1",
			invoice_type="Tax Invoice",
			amount=1000,
		)

		self.assertEqual(len(rows), 1)
		self.assertEqual(len(rows[0]["payments"]), 2)
		self.assertEqual(rows[0]["cheque_amount"], 1000)
		self.assertEqual(rows[0]["cheque_no"], "CHQ-1, CHQ-2")

	@patch("construction_management.api.project_revenue.frappe.db.sql")
	@patch("construction_management.api.project_revenue.frappe.db.has_column")
	def test_revenue_excludes_advances_and_deductions(self, has_column, sql):
		has_column.return_value = True
		sql.return_value = [(66340.62,)]

		revenue = get_project_billed_revenue("PROJECT-1")

		self.assertEqual(revenue, 66340.62)
		query = sql.call_args.args[0]
		self.assertIn("custom_is_advanced", query)
		self.assertIn("RETENTION-DEDUCTION", query)
		self.assertIn("ADVANCE-DEDUCTION", query)
