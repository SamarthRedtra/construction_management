# Copyright (c) 2026, Construction Management
# License: MIT

import os

import frappe
from frappe.modules.import_file import import_file_by_path


CM_PRINT_FORMATS = (
	"BOQ Quotation",
	"Daily Roster",
	"Payment Certificate Payable",
	"Project Completion Report",
)


def execute():
	frappe.db.sql(
		"""
		UPDATE `tabPrint Format`
		SET print_format_for = 'DocType'
		WHERE name IN %(names)s
			AND (print_format_for IS NULL OR print_format_for = '')
		""",
		{"names": CM_PRINT_FORMATS},
	)

	for print_format_name in CM_PRINT_FORMATS:
		if frappe.db.exists("Print Format", print_format_name):
			continue

		module_path = frappe.get_module_path(
			"Construction Management", "Print Format", print_format_name
		)
		json_path = os.path.join(module_path, f"{frappe.scrub(print_format_name)}.json")
		if os.path.exists(json_path):
			import_file_by_path(json_path, force=True)

	frappe.db.commit()
