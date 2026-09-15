# Copyright (c) 2026, Construction Management
# License: MIT

"""Align repaired DPR stock rows with the DPR package quantity and amount."""

from construction_management.scripts.workbook_material_uom_repair import run


def execute():
	run(dry_run=False, repost=True)
