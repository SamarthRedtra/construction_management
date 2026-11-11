# Copyright (c) 2026, Construction Management
# License: MIT

"""Clear wrong April Sales Order line links on TINV/1148/2026-JUL/1-1."""

import frappe


def execute():
	if not frappe.db.exists("Sales Invoice", "TINV/1148/2026-JUL/1-1"):
		return

	from construction_management.api.fix_tinv_1148_jul_april_so_link import run

	run(dry_run=0)
