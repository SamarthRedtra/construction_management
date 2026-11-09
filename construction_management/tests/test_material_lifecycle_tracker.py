# Copyright (c) 2026, Construction Management
# License: MIT

from frappe.tests.utils import FrappeTestCase

from construction_management.api.material_lifecycle_tracker import derive_stage, is_overdue_grn


class TestMaterialLifecycleTracker(FrappeTestCase):
	def test_stage_mr_only(self):
		self.assertEqual(derive_stage(10, 0, 0, 0, 0, 0, 0), "mr_only")

	def test_stage_ordered(self):
		self.assertEqual(derive_stage(10, 10, 0, 0, 0, 0, 0), "ordered")

	def test_stage_partly_ordered(self):
		self.assertEqual(derive_stage(10, 4, 0, 0, 0, 0, 0), "partly_ordered")

	def test_stage_grn_pending_when_past_required_date(self):
		self.assertEqual(
			derive_stage(10, 10, 0, 0, 0, 0, 0, required_date="2026-01-01", as_of="2026-02-01"),
			"grn_pending",
		)

	def test_stage_partly_received(self):
		self.assertEqual(derive_stage(10, 10, 4, 0, 0, 0, 0), "partly_received")

	def test_stage_received(self):
		self.assertEqual(derive_stage(10, 10, 10, 0, 0, 0, 0), "received")

	def test_stage_transferred(self):
		self.assertEqual(derive_stage(10, 10, 10, 5, 0, 0, 0), "transferred")

	def test_stage_consumed(self):
		self.assertEqual(derive_stage(10, 10, 10, 5, 3, 0, 0), "consumed")

	def test_stage_invoiced(self):
		self.assertEqual(derive_stage(10, 10, 10, 5, 3, 10, 0), "invoiced")

	def test_stage_paid(self):
		self.assertEqual(derive_stage(10, 10, 10, 5, 3, 10, 10), "paid")

	def test_overdue_grn_flag(self):
		self.assertTrue(is_overdue_grn(10, 2, "2026-01-01", as_of="2026-02-01"))
		self.assertFalse(is_overdue_grn(10, 10, "2026-01-01", as_of="2026-02-01"))
		self.assertFalse(is_overdue_grn(10, 0, None, as_of="2026-02-01"))
