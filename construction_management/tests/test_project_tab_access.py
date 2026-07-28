# Copyright (c) 2026, Construction Management
# License: MIT

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from construction_management.construction_management.doctype.project_tab_access.project_tab_access import (
	TAB_FIELDNAMES,
	get_project_tab_access_config,
	get_user_project_scope,
	parse_tabs,
)
from construction_management.permissions.project import (
	get_project_permission_query_conditions,
	has_project_permission,
)

TEST_ROLE = "Test Tab Access Role"


class TestProjectTabAccess(FrappeTestCase):
	def setUp(self):
		doc = frappe.get_single("Project Tab Access")
		doc.enabled = 1
		doc.rules = []
		doc.save(ignore_permissions=True)

		if not frappe.db.exists("Role", TEST_ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": TEST_ROLE}).insert(ignore_permissions=True)

	def test_disabled_returns_no_restrictions(self):
		doc = frappe.get_single("Project Tab Access")
		doc.enabled = 0
		doc.save(ignore_permissions=True)

		config = get_project_tab_access_config()
		self.assertFalse(config["enabled"])

	def test_multiselect_tabs_expand_to_multiple_fieldnames(self):
		doc = frappe.get_single("Project Tab Access")
		doc.enabled = 1
		doc.append(
			"rules",
			{"tabs": "Project SOA, Accounting", "role": "Accounts Manager", "access_mode": "Y"},
		)
		doc.save(ignore_permissions=True)

		config = get_project_tab_access_config()
		self.assertTrue(config["enabled"])
		self.assertIn(TAB_FIELDNAMES["Project SOA"], config["restricted_tabs"])
		self.assertIn(TAB_FIELDNAMES["Accounting"], config["restricted_tabs"])
		self.assertEqual(len(config["restricted_tabs"][TAB_FIELDNAMES["Project SOA"]]), 1)
		self.assertEqual(len(config["restricted_tabs"][TAB_FIELDNAMES["Accounting"]]), 1)
		self.assertIn("costing_tab", config["always_hidden_tabs"])

	def test_commission_specific_requires_sales_manager(self):
		doc = frappe.get_single("Project Tab Access")
		doc.enabled = 1
		doc.append(
			"rules",
			{
				"tabs": "Commission",
				"user": "taqreeb@mrggroup.ae",
				"access_mode": "S",
				"required_role": "Sales Manager",
			},
		)
		doc.save(ignore_permissions=True)

		config = get_project_tab_access_config()
		rules = config["restricted_tabs"][TAB_FIELDNAMES["Commission"]]
		self.assertEqual(rules[0]["access_mode"], "S")
		self.assertEqual(rules[0]["required_role"], "Sales Manager")

	def test_parse_tabs_splits_comma_separated_values(self):
		self.assertEqual(parse_tabs("Details, Construction, Progress"), [
			"Details",
			"Construction",
			"Progress",
		])

	@patch(
		"construction_management.permissions.project.frappe.get_roles",
		return_value=[TEST_ROLE],
	)
	@patch(
		"construction_management.construction_management.doctype.project_tab_access.project_tab_access.frappe.get_roles",
		return_value=[TEST_ROLE],
	)
	def test_user_with_limited_projects_gets_scope_filter(
		self, mock_tab_access_roles, mock_permission_roles
	):
		project_a = self._ensure_project("TAB-ACCESS-PROJ-A")
		project_b = self._ensure_project("TAB-ACCESS-PROJ-B")

		doc = frappe.get_single("Project Tab Access")
		doc.enabled = 1
		doc.append(
			"rules",
			{
				"tabs": "Details",
				"role": TEST_ROLE,
				"allowed_projects": f"{project_a}, {project_b}",
			},
		)
		doc.save(ignore_permissions=True)

		scope = get_user_project_scope("limited_user@example.com")
		self.assertEqual(set(scope), {project_a, project_b})

		condition = get_project_permission_query_conditions("limited_user@example.com")
		self.assertIn(project_a, condition)
		self.assertIn(project_b, condition)

		project_doc = frappe.get_doc("Project", project_a)
		self.assertTrue(has_project_permission(project_doc, user="limited_user@example.com"))

	@patch(
		"construction_management.construction_management.doctype.project_tab_access.project_tab_access.frappe.get_roles"
	)
	def test_user_with_empty_projects_sees_all(self, mock_get_roles):
		mock_get_roles.return_value = [TEST_ROLE]
		doc = frappe.get_single("Project Tab Access")
		doc.enabled = 1
		doc.append(
			"rules",
			{"tabs": "Details", "role": TEST_ROLE},
		)
		doc.save(ignore_permissions=True)

		self.assertIsNone(get_user_project_scope("limited_user@example.com"))
		self.assertIsNone(get_project_permission_query_conditions("limited_user@example.com"))

	@patch(
		"construction_management.construction_management.doctype.project_tab_access.project_tab_access.frappe.get_roles",
		return_value=[TEST_ROLE],
	)
	def test_user_project_selection_overrides_empty_role_rule(self, mock_get_roles):
		project = self._ensure_project("TAB-ACCESS-USER-ONLY-PROJ")
		doc = frappe.get_single("Project Tab Access")
		doc.enabled = 1
		doc.append("rules", {"tabs": "Details", "role": TEST_ROLE})
		doc.append(
			"rules",
			{
				"tabs": "Details",
				"user": "limited_user@example.com",
				"allowed_projects": project,
			},
		)
		doc.save(ignore_permissions=True)

		self.assertEqual(get_user_project_scope("limited_user@example.com"), [project])

	def _ensure_project(self, name: str) -> str:
		if frappe.db.exists("Project", name):
			return name

		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": name,
				"status": "Open",
			}
		)
		project.insert(ignore_permissions=True)
		return project.name
