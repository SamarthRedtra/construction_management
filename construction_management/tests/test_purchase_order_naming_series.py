from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.overrides.purchase_order import set_company_naming_series

SKADA = "SKADA CONSTRUCTION L.L.C"
MRG = "M R G INSULATION WORKS L.L.C"


def _series(company, naming_series="", amended_from=None):
	doc = frappe._dict(company=company, naming_series=naming_series, amended_from=amended_from)
	set_company_naming_series(doc)
	return doc.naming_series


def _abbr(doctype, name, field):
	return {SKADA: "SC", MRG: "MRG"}.get(name, "")


@patch("construction_management.api.controlled_procurement.frappe.db.get_value", side_effect=_abbr)
@patch("construction_management.api.project_numbering.frappe.db.get_value", side_effect=_abbr)
class TestPurchaseOrderNamingSeries(UnitTestCase):
	def test_skada_blank_series_uses_skd_lpo(self, *_):
		self.assertEqual(_series(SKADA), "SKD-LPO-")

	def test_mrg_generic_series_uses_mrg_lpo(self, *_):
		self.assertEqual(_series(MRG, "PUR-ORD-.YYYY.-"), "MRG-LPO-")

	def test_explicit_series_is_kept(self, *_):
		self.assertEqual(_series(SKADA, "MRG-LPO-"), "MRG-LPO-")

	def test_amendment_is_unchanged(self, *_):
		self.assertEqual(_series(MRG, "PUR-ORD-.YYYY.-", amended_from="PUR-ORD-2026-00116"), "PUR-ORD-.YYYY.-")
