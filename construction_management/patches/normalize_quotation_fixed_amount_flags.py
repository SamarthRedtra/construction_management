# Copyright (c) 2026, Construction Management
# License: MIT

"""Correct rows created while the Fixed Amount checkbox incorrectly defaulted to selected."""

import frappe
from frappe.utils import flt


def execute():
	if not frappe.db.has_column("Quotation BOQ Line", "is_fixed_rate"):
		return

	rows = frappe.get_all(
		"Quotation BOQ Line",
		filters={"line_type": "Sub", "is_fixed_rate": 1},
		fields=["name", "qty", "rate", "amount"],
	)
	for row in rows:
		# A row that already equals Qty × Rate has no manual amount to preserve.
		if abs(flt(row.amount) - (flt(row.qty) * flt(row.rate))) < 0.0001:
			frappe.db.set_value("Quotation BOQ Line", row.name, "is_fixed_rate", 0, update_modified=False)
