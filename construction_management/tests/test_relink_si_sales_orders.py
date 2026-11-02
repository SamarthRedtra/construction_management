from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.api import boq_invoice, relink_si_sales_orders as relink
from construction_management.overrides.sales_invoice import link_deduction_rows


def _row(item_code, boq_item=None, sales_order=None, **extra):
	return frappe._dict(item_code=item_code, boq_item=boq_item, sales_order=sales_order, so_detail=None, **extra)


class TestOpenSalesOrderLine(UnitTestCase):
	def test_prefers_the_invoice_header_order_then_the_oldest(self):
		rows = [frappe._dict(sales_order="SO-OLD", so_detail="L1", item_code="IT", uom="M2"),
			frappe._dict(sales_order="SO-HEADER", so_detail="L2", item_code="IT", uom="M2")]
		with patch.object(boq_invoice, "_open_sales_order_lines", return_value=rows):
			self.assertEqual(boq_invoice._open_sales_order_line("BOQ-1", "IT", "M2", "SO-HEADER").so_detail, "L2")
			self.assertEqual(boq_invoice._open_sales_order_line("BOQ-1", "IT", "M2", "SO-OTHER").so_detail, "L1")
		with patch.object(boq_invoice, "_open_sales_order_lines", return_value=[]):
			self.assertIsNone(boq_invoice._open_sales_order_line("BOQ-1", "IT", "M2"))

	def test_skips_order_lines_with_another_item_or_uom(self):
		rows = [frappe._dict(sales_order="SO-1", so_detail="L1", item_code="OTHER", uom="M2"),
			frappe._dict(sales_order="SO-2", so_detail="L2", item_code="IT", uom="LM")]
		with patch.object(boq_invoice, "_open_sales_order_lines", return_value=rows):
			self.assertIsNone(boq_invoice._open_sales_order_line("BOQ-1", "IT", "M2"))


class TestLinkDeductionRows(UnitTestCase):
	so_lines = [
		frappe._dict(name="SOD-R1", parent="SO-1", item_code="RETENTION-DEDUCTION", boq_item="BOQ-1"),
		frappe._dict(name="SOD-R0", parent="SO-1", item_code="RETENTION-DEDUCTION", boq_item=None),
	]

	@patch("construction_management.overrides.sales_invoice.frappe.get_all")
	def test_per_boq_and_global_rows_follow_their_order(self, get_all):
		get_all.return_value = self.so_lines
		items = [
			_row("WORK", "BOQ-1", "SO-1"),
			_row("RETENTION-DEDUCTION", "BOQ-1"),
			_row("RETENTION-DEDUCTION"),
			_row("ADVANCE-DEDUCTION", "BOQ-1"),
			_row("RETENTION-DEDUCTION", custom_service_deduction=1),
		]

		linked = link_deduction_rows(items)

		self.assertEqual([(row.sales_order, row.so_detail) for row in linked], [("SO-1", "SOD-R1"), ("SO-1", "SOD-R0")])
		self.assertIsNone(items[3].sales_order)
		self.assertIsNone(items[4].sales_order)

	@patch("construction_management.overrides.sales_invoice.frappe.get_all")
	def test_global_row_stays_unlinked_with_several_orders(self, get_all):
		items = [_row("WORK", "BOQ-1", "SO-1"), _row("WORK", "BOQ-2", "SO-2"), _row("RETENTION-DEDUCTION")]

		self.assertEqual(link_deduction_rows(items), [])
		get_all.assert_not_called()


class TestRelinkInvoice(UnitTestCase):
	def _invoice(self):
		si = MagicMock(project="PRJ", items=[
			_row("WORK-A", "BOQ-A", idx=1, name="R1", uom="M2"),
			_row("WORK-B", "BOQ-B", idx=2, name="R2", uom="M2"),
			_row("WORK-C", "BOQ-C", idx=3, name="R3", uom="M2"),
		])
		si.name = "SI-1"
		return si

	def _run(self, si, dry_run):
		module = "construction_management.api.relink_si_sales_orders"
		with patch(f"{module}.frappe.get_doc", return_value=si), \
			patch(f"{module}._named_orders", return_value=["SO-H"]), \
			patch(f"{module}._header_order_lines", return_value={("BOQ-A", "WORK-A", "M2"): ("SO-H", "H-A")}), \
			patch(f"{module}._single_open_order_line",
				side_effect=lambda project, row: (("SO-X", "X-B"), "only open project order") if row.boq_item == "BOQ-B" else (None, "no open Sales Order line")), \
			patch(f"{module}.link_deduction_rows", return_value=[]), \
			patch(f"{module}._gl_change_preview", return_value="Sales - T +1.00"), \
			patch(f"{module}.frappe.db.set_value") as set_value, \
			patch(f"{module}._merge_boq_ledger_row") as merge:
			report, linked = relink._relink_invoice("SI-1", dry_run=dry_run)
		return report, linked, set_value, merge

	def test_dry_run_matches_header_first_then_single_open_order_and_writes_nothing(self):
		si = self._invoice()
		report, linked, set_value, merge = self._run(si, dry_run=True)

		self.assertEqual([(row.get("boq_item"), row.get("sales_order"), row["result"]) for row in report], [
			("BOQ-A", "SO-H", "header order"),
			("BOQ-B", "SO-X", "only open project order"),
			("BOQ-C", None, "skipped: no open Sales Order line"),
			(None, None, "GL change after repost: Sales - T +1.00"),
		])
		self.assertEqual(len(linked), 2)
		set_value.assert_not_called()
		merge.assert_not_called()
		si.update_prevdoc_status.assert_not_called()

	def test_apply_writes_links_updates_billing_and_merges_ledger(self):
		si = self._invoice()
		_report, _linked, set_value, merge = self._run(si, dry_run=False)

		self.assertEqual([call.args[1] for call in set_value.call_args_list], ["R1", "R2"])
		si.update_prevdoc_status.assert_called_once()
		self.assertEqual(merge.call_count, 2)

	def test_invoice_naming_no_order_is_left_alone(self):
		si = self._invoice()
		module = "construction_management.api.relink_si_sales_orders"
		with patch(f"{module}.frappe.get_doc", return_value=si), \
			patch(f"{module}._named_orders", return_value=[]), \
			patch(f"{module}._single_open_order_line") as single, \
			patch(f"{module}.link_deduction_rows", return_value=[]):
			report, linked = relink._relink_invoice("SI-1", dry_run=True)

		self.assertEqual((report, linked), ([], []))
		single.assert_not_called()

	def test_header_lines_keep_the_first_named_order(self):
		rows = [frappe._dict(parent="SO-2", name="L2", boq_item="BOQ-1", item_code="IT", uom="M2"),
			frappe._dict(parent="SO-1", name="L1", boq_item="BOQ-1", item_code="IT", uom="M2"),
			frappe._dict(parent="SO-1", name="L3", boq_item="BOQ-1", item_code="OTHER", uom="LM")]
		with patch("construction_management.api.relink_si_sales_orders.frappe.db.sql", return_value=rows):
			self.assertEqual(relink._header_order_lines(["SO-1", "SO-2"]),
				{("BOQ-1", "IT", "M2"): ("SO-1", "L1"), ("BOQ-1", "OTHER", "LM"): ("SO-1", "L3")})

	def test_named_orders_merges_header_and_source_orders(self):
		si = SimpleNamespace(get=lambda field: {"custom_sales_order": "SO-1", "custom_source_sales_orders": "SO-2, SO-1 ,"}.get(field))
		self.assertEqual(relink._named_orders(si), ["SO-1", "SO-2"])
