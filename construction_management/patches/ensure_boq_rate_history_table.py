import frappe

from construction_management.construction_management.doctype.boq_item.boq_item import (
	check_rate_history_table,
)


def execute():
	"""Ensure BOQ Rate History table exists on sites that missed earlier patches."""
	check_rate_history_table()
