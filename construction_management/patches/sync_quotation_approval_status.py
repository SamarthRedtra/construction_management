# Copyright (c) 2026, Construction Management
# License: MIT

"""Show the current approval stage in the standard Quotation Status field."""

import frappe

from construction_management.overrides.quotation import _visible_quotation_status


def execute():
	if not frappe.db.has_column("Quotation", "custom_approval_status"):
		return

	for row in frappe.get_all(
		"Quotation",
		filters={"docstatus": 1},
		fields=["name", "custom_approval_status", "custom_agreement_status"],
	):
		status = _visible_quotation_status(row.custom_approval_status, row.custom_agreement_status)
		if status:
			frappe.db.set_value("Quotation", row.name, "status", status, update_modified=False)
