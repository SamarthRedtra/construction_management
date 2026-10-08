from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.project_document_naming import _seed_invoice_series, assign_project_document_name
from construction_management.overrides.sales_order import rename_draft_project_order_for_date_change


class TestProjectDocumentNaming(UnitTestCase):
	@patch("construction_management.project_document_naming.getseries", return_value="1")
	@patch("construction_management.project_document_naming.frappe.db.get_value", return_value="1033")
	def test_sales_order_uses_pinv_project_month_series(self, get_value, getseries):
		doc = frappe._dict(doctype="Sales Order", project="PROJECT-1033", transaction_date="2025-10-12")
		assign_project_document_name(doc)
		self.assertEqual(doc.name, "PINV/1033/2025-OCT/1")
		getseries.assert_called_once_with("PINV/1033/2025-OCT/", 1)

	@patch("construction_management.project_document_naming.getseries", return_value="1")
	@patch("construction_management.project_document_naming._seed_invoice_series")
	@patch("construction_management.project_document_naming.frappe.db.get_value", return_value="1033")
	@patch(
		"construction_management.project_document_naming.frappe.get_all",
		return_value=[frappe._dict(name="PINV/1033/2025-OCT/1", transaction_date="2025-10-12")],
	)
	def test_sales_invoice_uses_linked_sales_order_month(self, get_all, get_value, seed, getseries):
		doc = frappe._dict(
			doctype="Sales Invoice",
			project="PROJECT-1033",
			posting_date="2025-11-12",
			items=[frappe._dict(sales_order="PINV/1033/2025-OCT/1")],
		)
		assign_project_document_name(doc)
		self.assertEqual(doc.name, "TINV/1033/2025-OCT/1")
		seed.assert_called_once_with("TINV/1033/2025-OCT/", "SINV/1033/2025-OCT/")
		getseries.assert_called_once_with("TINV/1033/2025-OCT/", 1)

	@patch("construction_management.project_document_naming.getseries", return_value="1")
	@patch("construction_management.project_document_naming._seed_invoice_series")
	@patch("construction_management.project_document_naming.frappe.db.get_value", return_value="1033")
	def test_direct_sales_invoice_uses_its_posting_month(self, get_value, seed, getseries):
		doc = frappe._dict(doctype="Sales Invoice", project="PROJECT-1033", posting_date="2025-11-12")
		assign_project_document_name(doc)
		self.assertEqual(doc.name, "TINV/1033/2025-NOV/1")
		seed.assert_called_once_with("TINV/1033/2025-NOV/", "SINV/1033/2025-NOV/")
		getseries.assert_called_once_with("TINV/1033/2025-NOV/", 1)

	@patch("construction_management.project_document_naming.frappe.db.sql")
	@patch("construction_management.project_document_naming.frappe.db.get_value", return_value=7)
	def test_invoice_series_carries_forward_legacy_count(self, get_value, sql):
		_seed_invoice_series("TINV/1033/2025-OCT/", "SINV/1033/2025-OCT/")
		query = sql.call_args.args[0].lower()
		self.assertIn("greatest", query)
		self.assertIn("values (%(target)s, %(legacy_current)s)", query)
		self.assertNotIn("select", query)
		get_value.assert_called_once_with("Series", "SINV/1033/2025-OCT/", "current", order_by="name")
		self.assertEqual(sql.call_args.args[1], {
			"target": "TINV/1033/2025-OCT/", "legacy_current": 7,
		})

	@patch("construction_management.project_document_naming.frappe.db.sql")
	@patch("construction_management.project_document_naming.frappe.db.get_value", return_value=None)
	def test_invoice_series_skips_missing_legacy_series(self, get_value, sql):
		_seed_invoice_series("TINV/1033/2025-OCT/", "SINV/1033/2025-OCT/")

		get_value.assert_called_once_with("Series", "SINV/1033/2025-OCT/", "current", order_by="name")
		sql.assert_not_called()

	@patch("construction_management.project_document_naming.getseries", return_value="5")
	@patch("construction_management.project_document_naming._seed_invoice_series")
	@patch("construction_management.project_document_naming.frappe.db.get_value", return_value="1033")
	def test_fifth_project_invoice_uses_tinv_five(self, get_value, seed, getseries):
		doc = frappe._dict(doctype="Sales Invoice", project="PROJECT-1033", posting_date="2025-10-12")
		assign_project_document_name(doc)
		self.assertEqual(doc.name, "TINV/1033/2025-OCT/5")

	@patch("construction_management.project_document_naming.getseries", return_value="1")
	@patch("construction_management.project_document_naming._seed_invoice_series")
	@patch("construction_management.project_document_naming.frappe.db.get_value", return_value="1033")
	@patch(
		"construction_management.project_document_naming.frappe.get_all",
		return_value=[
			frappe._dict(name="PINV/1033/2025-OCT/1", transaction_date="2025-10-12"),
			frappe._dict(name="PINV/1033/2025-OCT/2", transaction_date="2025-10-23"),
		],
	)
	def test_combined_sales_invoice_uses_the_common_sales_order_month(self, get_all, get_value, seed, getseries):
		doc = frappe._dict(
			doctype="Sales Invoice",
			project="PROJECT-1033",
			posting_date="2025-11-12",
			custom_source_sales_orders="PINV/1033/2025-OCT/1, PINV/1033/2025-OCT/2",
		)
		assign_project_document_name(doc)
		self.assertEqual(doc.name, "TINV/1033/2025-OCT/1")
		seed.assert_called_once_with("TINV/1033/2025-OCT/", "SINV/1033/2025-OCT/")
		getseries.assert_called_once_with("TINV/1033/2025-OCT/", 1)

	@patch(
		"construction_management.project_document_naming.frappe.get_all",
		return_value=[
			frappe._dict(name="PINV/1033/2025-OCT/1", transaction_date="2025-10-12"),
			frappe._dict(name="PINV/1033/2025-NOV/1", transaction_date="2025-11-12"),
		],
	)
	def test_invoice_rejects_linked_sales_orders_from_different_months(self, get_all):
		doc = frappe._dict(
			doctype="Sales Invoice",
			project="PROJECT-1033",
			items=[
				frappe._dict(sales_order="PINV/1033/2025-OCT/1"),
				frappe._dict(sales_order="PINV/1033/2025-NOV/1"),
			],
		)
		with self.assertRaises(frappe.ValidationError):
			assign_project_document_name(doc)

	def test_non_project_document_keeps_standard_naming(self):
		doc = frappe._dict(doctype="Sales Invoice", project="", posting_date="2025-10-12")
		self.assertFalse(assign_project_document_name(doc))
		self.assertFalse(doc.get("name"))

	@patch("frappe.model.rename_doc.rename_doc")
	@patch("construction_management.project_document_naming.frappe.db.get_value", return_value="1033")
	@patch("construction_management.project_document_naming.getseries", return_value="1")
	def test_draft_sales_order_is_renamed_when_its_transaction_month_changes(self, getseries, get_value, rename_doc):
		doc = frappe._dict(
			doctype="Sales Order",
			name="PINV/1033/2025-OCT/1",
			project="PROJECT-1033",
			transaction_date="2025-09-30",
			docstatus=0,
		)
		doc.is_new = lambda: False
		doc.get_doc_before_save = lambda: frappe._dict(transaction_date="2025-10-01")

		rename_draft_project_order_for_date_change(doc)

		rename_doc.assert_called_once_with(
			"Sales Order", "PINV/1033/2025-OCT/1", "PINV/1033/2025-SEP/1",
			force=True, ignore_permissions=True, show_alert=False,
		)
		self.assertEqual(doc.name, "PINV/1033/2025-SEP/1")

	@patch("construction_management.overrides.sales_order.frappe.rename_doc")
	def test_submitted_sales_order_is_not_renamed_for_a_date_change(self, rename_doc):
		doc = frappe._dict(project="PROJECT-1033", docstatus=1, _action="update_after_submit")
		doc.is_new = lambda: False

		rename_draft_project_order_for_date_change(doc)

		rename_doc.assert_not_called()
