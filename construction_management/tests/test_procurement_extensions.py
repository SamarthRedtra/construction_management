from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from construction_management.api import consumable_receipt, dpr_labour_cleanup, sales_invoice_write_off
from construction_management.construction_management.doctype.daily_progress_record.daily_progress_record import DailyProgressRecord
from construction_management.patches import cancel_verified_dpr_labour_journal_entries as labour_patch


class TestProcurementExtensions(UnitTestCase):
	def test_dpr_labour_cost_no_longer_creates_journal_entry(self):
		dpr = SimpleNamespace(assets=[], asset_cost=0, employees=[object()], labour_cost=100,
			overheads=[], overhead_cost=0, expenses=[], expense_cost=0,
			_create_labour_journal_entry=MagicMock(), db_set=MagicMock())
		DailyProgressRecord.create_journal_entries(dpr)
		dpr._create_labour_journal_entry.assert_not_called()
		dpr.db_set.assert_not_called()
		self.assertFalse(dpr._je_created)

	@patch("construction_management.api.consumable_receipt.frappe.new_doc")
	@patch("construction_management.api.consumable_receipt.frappe.db.get_single_value", return_value=0)
	def test_consumable_receipt_setting_is_off_by_default(self, _setting, new_doc):
		consumable_receipt.on_submit(SimpleNamespace(is_return=0))
		new_doc.assert_not_called()

	@patch("construction_management.api.dpr_labour_cleanup.frappe.db.get_value")
	@patch("construction_management.api.dpr_labour_cleanup.frappe.get_all")
	def test_labour_cleanup_skips_unlinked_journal_entry(self, get_all, get_value):
		get_all.return_value = [SimpleNamespace(name="JE-1", company="MRG",
			user_remark="Labour costs for DPR DPR-1", total_debit=100)]
		get_value.return_value = SimpleNamespace(name="DPR-1", project="PROJ-1", journal_entries="JE-OTHER")
		result = dpr_labour_cleanup.run()
		self.assertEqual(result["eligible_count"], 0)
		self.assertEqual(result["skipped_count"], 1)

	@patch("construction_management.patches.cancel_verified_dpr_labour_journal_entries.run")
	def test_labour_patch_does_not_cancel_changed_target_set(self, run):
		run.return_value = {"eligible_count": 1, "digest": "changed", "total_amount": 10,
			"eligible": [{"company": "MRG"}]}
		with self.assertRaisesRegex(Exception, "targets differ"):
			labour_patch.execute()
		run.assert_called_once_with(details=True)

	@patch("construction_management.patches.cancel_verified_dpr_labour_journal_entries.run")
	def test_labour_patch_is_noop_on_fresh_site(self, run):
		run.return_value = {"eligible_count": 0}
		labour_patch.execute()
		run.assert_called_once_with(details=True)

	@patch("construction_management.api.sales_invoice_write_off.frappe.db.get_value",
		return_value=SimpleNamespace(default_currency="AED", write_off_account="Write Off - MRG", cost_center="Main - MRG"))
	@patch("construction_management.api.sales_invoice_write_off.frappe.get_doc",
		return_value=SimpleNamespace(docstatus=1, is_return=0, company="MRG", currency="AED", outstanding_amount=0.31))
	@patch("construction_management.api.sales_invoice_write_off.frappe.db.sql")
	@patch("construction_management.api.sales_invoice_write_off.frappe.has_permission")
	def test_small_balance_write_off_rejects_more_than_thirty_fils(self, _permission, _lock, _invoice, _company):
		with self.assertRaisesRegex(Exception, "up to 0.3"):
			sales_invoice_write_off.create_small_balance_write_off("SINV-1")
