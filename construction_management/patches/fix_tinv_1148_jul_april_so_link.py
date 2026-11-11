# Copyright (c) 2026, Construction Management
# License: MIT

"""Link TINV/1148/2026-JUL/1-1 to July Sales Order SAL-ORD-2026-00334 (Connections)."""

import frappe


def execute():
	if not frappe.db.exists("Sales Invoice", "TINV/1148/2026-JUL/1-1"):
		return

	from construction_management.api.fix_tinv_1148_jul_april_so_link import run

	run(dry_run=0)
