# Copyright (c) 2026, Construction Management
# License: MIT

"""Route PDF generation (including Email Queue print attachments) through Chrome.

wkhtmltopdf cannot be installed by a Frappe patch (it is a host OS binary). Email
Queue → attach_print → get_print reads Print Format.pdf_generator and falls back
to wkhtmltopdf when that field is empty, which fails when the binary is missing
from the process PATH. Chromium is already available via Frappe's chrome PDF
generator; align Print Settings and formats to use it.
"""

import frappe


def execute():
	if frappe.get_meta("Print Settings").has_field("pdf_generator"):
		current = frappe.db.get_single_value("Print Settings", "pdf_generator")
		if current != "chrome":
			frappe.db.set_single_value("Print Settings", "pdf_generator", "chrome")

	if not frappe.get_meta("Print Format").has_field("pdf_generator"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabPrint Format`
		SET pdf_generator = 'chrome'
		WHERE IFNULL(pdf_generator, '') IN ('', 'wkhtmltopdf')
		"""
	)
	frappe.clear_cache(doctype="Print Format")
	frappe.clear_cache(doctype="Print Settings")
