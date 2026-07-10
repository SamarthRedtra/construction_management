# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe.tests.utils import FrappeTestCase

from construction_management.construction_management.page.project_soa.project_soa import (
	create_project_soa_follow_up,
	get_project_soa_follow_ups,
)
from construction_management.tests.test_utils import create_test_project


class TestProjectSOAFollowUp(FrappeTestCase):
	def setUp(self):
		self.project = create_test_project("TEST-SOA-FOLLOW-UP")
		frappe.db.set_value("Project", self.project, {"status": "Open", "is_active": "Yes"})

	def test_create_and_list_follow_up(self):
		result = create_project_soa_follow_up(
			project=self.project,
			reference_doctype="Sales Order",
			reference_name="SO-TEST-001",
			follow_up_date="2026-07-10",
			status="Open",
			remarks="Awaiting payment certificate",
		)
		self.assertTrue(result.get("name"))
		self.assertTrue(frappe.db.exists("Project SOA Follow Up", result["name"]))

		follow_ups = get_project_soa_follow_ups(self.project)
		self.assertEqual(len(follow_ups), 1)
		self.assertEqual(follow_ups[0]["reference_doctype"], "Sales Order")
		self.assertEqual(follow_ups[0]["reference_name"], "SO-TEST-001")
		self.assertEqual(follow_ups[0]["status"], "Open")
		self.assertEqual(follow_ups[0]["remarks"], "Awaiting payment certificate")

	def test_follow_up_with_payment_certificate_link(self):
		result = create_project_soa_follow_up(
			project=self.project,
			reference_doctype="Payment Certificate",
			reference_name="PC-TEST-001",
			payment_certificate="PC-TEST-001",
			status="Waiting Payment",
			remarks="PC attached",
		)
		doc = frappe.get_doc("Project SOA Follow Up", result["name"])
		self.assertEqual(doc.payment_certificate, "PC-TEST-001")
