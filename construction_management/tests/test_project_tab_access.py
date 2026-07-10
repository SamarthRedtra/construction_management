# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe.tests.utils import FrappeTestCase

from construction_management.construction_management.doctype.project_tab_access.project_tab_access import (
	TAB_FIELDNAMES,
	get_project_tab_access_config,
)


class TestProjectTabAccess(FrappeTestCase):
	def setUp(self):
		doc = frappe.get_single("Project Tab Access")
		doc.enabled = 1
		doc.rules = []
		doc.save(ignore_permissions=True)

	def test_disabled_returns_no_restrictions(self):
		doc = frappe.get_single("Project Tab Access")
		doc.enabled = 0
		doc.save(ignore_permissions=True)

		config = get_project_tab_access_config()
		self.assertFalse(config["enabled"])

	def test_tab_rules_grouped_by_fieldname(self):
		doc = frappe.get_single("Project Tab Access")
		doc.enabled = 1
		doc.append("rules", {"tab": "Project SOA", "role": "Accounts Manager"})
		doc.append("rules", {"tab": "Costing", "role": "Projects Manager"})
		doc.save(ignore_permissions=True)

		config = get_project_tab_access_config()
		self.assertTrue(config["enabled"])
		self.assertIn(TAB_FIELDNAMES["Project SOA"], config["restricted_tabs"])
		self.assertEqual(len(config["restricted_tabs"][TAB_FIELDNAMES["Project SOA"]]), 1)
