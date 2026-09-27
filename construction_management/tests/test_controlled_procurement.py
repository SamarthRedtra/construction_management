from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.api import controlled_procurement


class TestControlledProcurement(UnitTestCase):
	def test_allocation_requires_project_bill_and_boq_item(self):
		with self.assertRaises(frappe.ValidationError):
			controlled_procurement._validate_allocation({"project": "PROJECT-1", "bill_no": "", "boq_item": "BOQ-1"})

	@patch("construction_management.api.controlled_procurement.frappe.has_permission", return_value=True)
	@patch("construction_management.api.controlled_procurement.frappe.get_doc")
	@patch("construction_management.api.controlled_procurement.frappe.db.get_value")
	def test_allocation_rejects_item_from_another_bill(self, get_value, get_doc, has_permission):
		get_doc.return_value = frappe._dict(name="PROJECT-1")
		get_value.side_effect = [frappe._dict(project="PROJECT-1"), frappe._dict(project="PROJECT-1", parent_bill="BILL-2")]
		with self.assertRaises(frappe.ValidationError):
			controlled_procurement._validate_allocation({"project": "PROJECT-1", "bill_no": "BILL-1", "boq_item": "BOQ-1"})

	@patch("construction_management.api.controlled_procurement.frappe.has_permission", return_value=True)
	@patch("construction_management.api.controlled_procurement.frappe.get_doc")
	@patch("construction_management.api.controlled_procurement.frappe.db.get_value")
	def test_allocation_accepts_matching_project_bill_and_boq_item(self, get_value, get_doc, has_permission):
		get_doc.return_value = frappe._dict(name="PROJECT-1")
		get_value.side_effect = [frappe._dict(project="PROJECT-1"), frappe._dict(project="PROJECT-1", parent_bill="BILL-1")]
		controlled_procurement._validate_allocation({"project": "PROJECT-1", "bill_no": "BILL-1", "boq_item": "BOQ-1"})
