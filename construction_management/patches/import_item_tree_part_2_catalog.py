"""Stage the approved Item Tree Part 2 workbook through the catalog workflow."""

from construction_management.api.item_tree_part_2_import import submit


def execute():
	submit()
