# Copyright (c) 2024, Construction Management
# License: MIT

"""
Override module for Process Statement of Accounts.
Intercepts download_statements and send_emails to handle
'Advanced General Ledger' report type, which includes
Proforma (Sales Order) data alongside standard GL entries.
"""

import copy

import frappe
from frappe import _
from frappe.utils import add_days, add_months, format_date, getdate, today
from frappe.utils.pdf import get_pdf
from frappe.www.printview import get_print_style
from construction_management.report_pdf_utils import get_report_pdf_options, inline_file_images

from erpnext import get_company_currency
from erpnext.accounts.party import get_party_account_currency
from erpnext.accounts.report.accounts_receivable_summary.accounts_receivable_summary import (
	execute as get_ageing,
)

from erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts import (
	ProcessStatementOfAccounts,
	get_report_pdf as original_get_report_pdf,
	get_statement_dict as original_get_statement_dict,
	get_common_filters,
	get_gl_filters,
	set_ageing,
	get_recipients_and_cc,
	get_context,
)

from construction_management.construction_management.report.advanced_general_ledger.advanced_general_ledger import (
	execute as get_advanced_soa,
	get_soa_totals,
)


class ProcessStatementOfAccountsOverride(ProcessStatementOfAccounts):
	"""
	Override to make 'Advanced General Ledger' behave like 'General Ledger'
	during validation (default email body, mandatory fields, etc.).
	"""

	def validate(self):
		# Temporarily swap report to 'General Ledger' so the parent validate()
		# sets the correct default body ("from {{ doc.from_date }} to {{ doc.to_date }}")
		# and mandatory_depends_on checks pass for from_date / to_date.
		original_report = self.report
		if self.report == "Advanced General Ledger":
			self.report = "General Ledger"

		super().validate()

		# Restore the actual report value
		self.report = original_report


def enrich_reference_details(rows):
	"""
	Add payment reference details to report rows used for SOA rendering.
	This keeps template rendering stable even when some rows don't carry
	reference fields, and enriches Payment Entry rows in batch.
	"""
	if not rows:
		return

	payment_entry_names = list(
		{
			row.get("voucher_no")
			for row in rows
			if row.get("posting_date")
			and row.get("voucher_type") == "Payment Entry"
			and row.get("voucher_no")
		}
	)

	payment_entry_map = {}
	if payment_entry_names:
		payment_entries = frappe.get_all(
			"Payment Entry",
			filters={"name": ["in", payment_entry_names]},
			fields=["name", "reference_no", "reference_date", "mode_of_payment"],
		)
		payment_entry_map = {pe.name: pe for pe in payment_entries}

	for row in rows:
		row["reference_no"] = row.get("reference_no") or ""
		row["reference_date"] = row.get("reference_date")
		row["mode_of_payment"] = row.get("mode_of_payment") or ""

		if row.get("voucher_type") == "Payment Entry" and row.get("voucher_no"):
			payment_entry = payment_entry_map.get(row.get("voucher_no"))
			if payment_entry:
				row["reference_no"] = row.get("reference_no") or payment_entry.reference_no or ""
				row["reference_date"] = row.get("reference_date") or payment_entry.reference_date
				row["mode_of_payment"] = row.get("mode_of_payment") or payment_entry.mode_of_payment or ""


def get_advanced_statement_dict(doc, get_dict=False):
	"""
	Custom statement dict builder for Advanced General Ledger.
	Calls the advanced_general_ledger.execute() which includes Proforma rows.
	"""
	statement_dict = {}
	ageing = ""

	for entry in doc.customers:
		if doc.include_ageing:
			ageing = set_ageing(doc, entry)

		tax_id = frappe.get_doc("Customer", entry.customer).tax_id
		presentation_currency = (
			doc.currency
			or get_party_account_currency("Customer", entry.customer, doc.company)
			or get_company_currency(doc.company)
		)

		filters = get_common_filters(doc)
		if doc.ignore_exchange_rate_revaluation_journals:
			filters.update({"ignore_err": True})

		if doc.ignore_cr_dr_notes:
			filters.update({"ignore_cr_dr_notes": True})

		filters.update(get_gl_filters(doc, entry, tax_id, presentation_currency))

		# Enable proforma inclusion
		filters["include_proforma"] = 1

		col, res = get_advanced_soa(filters)
		enrich_reference_details(res)

		# Clean quote marks from opening/total/closing account labels
		for x in [0, -2, -1]:
			if x < len(res) and res[x].get("account"):
				res[x]["account"] = res[x]["account"].replace("'", "")

		# Skip if only opening + total + closing (no actual data)
		if len(res) <= 3:
			continue

		statement_dict[entry.customer] = (
			[res, ageing] if get_dict else get_advanced_html(doc, filters, entry, col, res, ageing)
		)

	return statement_dict


def get_advanced_html(doc, filters, entry, col, res, ageing):
	"""Render the Advanced General Ledger SOA HTML template."""
	base_template_path = "frappe/www/printview.html"
	template_path = (
		"construction_management/construction_management/report/"
		"advanced_general_ledger/advanced_general_ledger_soa.html"
	)

	# Check for hook override
	process_soa_html = frappe.get_hooks("process_soa_html")
	if process_soa_html and process_soa_html.get(doc.report):
		template_path = process_soa_html[doc.report][-1]

	# Check for custom print format
	if doc.print_format:
		pf = frappe.db.get_value("Print Format", doc.print_format, ["html", "css"], as_dict=True)
		if pf:
			template_path = f"<style>{pf.css or ''}</style> {pf.html or ''}"

	letter_head = None
	if doc.letter_head:
		from frappe.www.printview import get_letter_head
		letter_head = get_letter_head(doc, 0)

	html = frappe.render_template(
		template_path,
		{
			"filters": filters,
			"data": res,
			"report": {"report_name": doc.report, "columns": col},
			"ageing": ageing[0] if (doc.include_ageing and ageing) else None,
			"letter_head": letter_head if doc.letter_head else None,
			"terms_and_conditions": frappe.db.get_value(
				"Terms and Conditions", doc.terms_and_conditions, "terms"
			)
			if doc.terms_and_conditions
			else None,
			"soa_totals": get_soa_totals(res),
		},
	)
	html = frappe.render_template(
		base_template_path,
		{"body": html, "css": get_print_style(), "title": "Statement For " + entry.customer},
	)
	return html


def get_advanced_report_pdf(doc, consolidated=True):
	"""Generate PDF for Advanced General Ledger SOA."""
	statement_dict = get_advanced_statement_dict(doc)
	if not bool(statement_dict):
		return False
	elif consolidated:
		delimiter = '<div style="page-break-before: always;"></div>' if doc.include_break else ""
		result = delimiter.join(list(statement_dict.values()))
		return get_pdf(
			inline_file_images(result),
			get_report_pdf_options(orientation=doc.orientation),
		)
	else:
		for customer, statement_html in statement_dict.items():
			statement_dict[customer] = get_pdf(
				inline_file_images(statement_html),
				get_report_pdf_options(orientation=doc.orientation),
			)
		return statement_dict


@frappe.whitelist()
def download_statements(document_name):
	"""Override: download SOA statements with Advanced General Ledger support."""
	doc = frappe.get_doc("Process Statement Of Accounts", document_name)

	if doc.report == "Advanced General Ledger":
		report = get_advanced_report_pdf(doc)
	else:
		report = original_get_report_pdf(doc)

	if report:
		frappe.local.response.filename = doc.name + ".pdf"
		frappe.local.response.filecontent = report
		frappe.local.response.type = "download"


@frappe.whitelist()
def send_emails(document_name, from_scheduler=False, posting_date=None):
	"""Override: send SOA emails with Advanced General Ledger support."""
	doc = frappe.get_doc("Process Statement Of Accounts", document_name)

	if doc.report == "Advanced General Ledger":
		report = get_advanced_report_pdf(doc, consolidated=False)
	else:
		report = original_get_report_pdf(doc, consolidated=False)

	if report:
		for customer, report_pdf in report.items():
			context = get_context(customer, doc)
			filename = frappe.render_template(doc.pdf_name, context)
			attachments = [{"fname": filename + ".pdf", "fcontent": report_pdf}]

			recipients, cc = get_recipients_and_cc(customer, doc)
			if not recipients:
				continue

			subject = frappe.render_template(doc.subject, context)
			message = frappe.render_template(doc.body, context)

			if doc.sender:
				sender_email = frappe.db.get_value("Email Account", doc.sender, "email_id")
			else:
				sender_email = frappe.session.user

			frappe.enqueue(
				queue="short",
				method=frappe.sendmail,
				recipients=recipients,
				sender=sender_email,
				cc=cc,
				subject=subject,
				message=message,
				now=True,
				reference_doctype="Process Statement Of Accounts",
				reference_name=document_name,
				attachments=attachments,
				expose_recipients="header",
			)

		if doc.enable_auto_email and from_scheduler:
			new_to_date = getdate(posting_date or today())
			if doc.frequency in ("Daily", "Weekly", "Biweekly"):
				frequency = {"Daily": 1, "Weekly": 7, "Biweekly": 14}
				new_to_date = add_days(new_to_date, frequency[doc.frequency])
			else:
				new_to_date = add_months(new_to_date, 1 if doc.frequency == "Monthly" else 3)
			new_from_date = add_months(new_to_date, -1 * doc.filter_duration)
			doc.add_comment("Comment", "Emails sent on: " + frappe.utils.format_datetime(frappe.utils.now()))
			doc.db_set("to_date", new_to_date, commit=True)
			doc.db_set("from_date", new_from_date, commit=True)
		return True
	else:
		return False
