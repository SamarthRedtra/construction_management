# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe.utils import today

from construction_management.api.quotation_boq import lines_to_boq_html
from construction_management.quotation_boq_print_context import build_boq_quotation_print_context


def run():
	frappe.set_user("Administrator")
	company = frappe.defaults.get_defaults().company

	lines = [
		frappe._dict(
			idx=1,
			line_type="Parent",
			parent_no="1",
			description="Waterproofing membrane",
		),
		frappe._dict(
			idx=2,
			line_type="Sub",
			parent_no="1",
			sub_no="A",
			description="Horizontal",
			uom="m2",
			qty=10,
			rate=50,
			amount=500,
			display_mode="Normal",
		),
		frappe._dict(
			idx=3,
			line_type="Parent",
			parent_no="2",
			section_title="ADDITIONAL ITEMS",
			description="Pool deck waterproofing",
		),
		frappe._dict(
			idx=4,
			line_type="Sub",
			parent_no="2",
			sub_no="A",
			description="Horizontal membrane",
			uom="m2",
			qty=20,
			rate=30,
			amount=600,
			display_mode="Normal",
		),
	]

	doc = frappe._dict(
		name="QTN-SMOKE",
		company=company,
		transaction_date=today(),
		currency="AED",
		custom_boq_lines=lines,
		terms="",
	)

	ctx = build_boq_quotation_print_context(doc)
	html = lines_to_boq_html(lines, company=company)

	assert ctx["hierarchy_mode"] == "2 Level (Parent + Sub)", ctx["hierarchy_mode"]
	assert len(ctx["sections"]) == 2, len(ctx["sections"])
	assert ctx["sections"][1]["title"] == "ADDITIONAL ITEMS"
	assert ctx["totals"]["total_excl_vat"] == 1100
	assert "Waterproofing membrane" in html
	assert "ADDITIONAL ITEMS" in html
	assert "1,100.00" in html

	print("2-level quotation BOQ smoke test passed")
