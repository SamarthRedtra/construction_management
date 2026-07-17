# Copyright (c) 2026, Construction Management
# License: MIT

from frappe.tests.utils import FrappeTestCase

from construction_management.api.project_numbering import (
	get_next_project_number,
	is_skada_company,
)


class TestProjectNumbering(FrappeTestCase):
	def test_is_skada_company_detects_skada_name(self):
		self.assertTrue(is_skada_company("SKADA CONSTRUCTION L.L.C"))
		self.assertFalse(is_skada_company("M R G INSULATION WORKS L.L.C"))

	def test_next_number_formats(self):
		mrg = "M R G INSULATION WORKS L.L.C"
		skada = "SKADA CONSTRUCTION L.L.C"

		mrg_next = get_next_project_number(mrg)
		skada_next = get_next_project_number(skada)

		self.assertTrue(mrg_next.isdigit(), mrg_next)
		self.assertTrue(skada_next.upper().startswith("SKD-"), skada_next)
		self.assertTrue(skada_next.split("-")[-1].isdigit(), skada_next)
