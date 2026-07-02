import frappe

from construction_management.api.boq_opening_balance import sync_opening_journal_entry


def execute():
	"""Backfill BOQ Advance Payment rows for existing opening Journal Entries."""
	je_names = frappe.db.sql(
		"""
		SELECT DISTINCT je.name
		FROM `tabJournal Entry` je
		INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
		INNER JOIN `tabBOQ Settings` bs ON bs.company = je.company
		WHERE je.docstatus = 1
			AND (je.is_opening = 'Yes' OR je.voucher_type = 'Opening Entry')
			AND IFNULL(jea.project, '') != ''
			AND jea.account = bs.advance_account
			AND IFNULL(bs.advance_account, '') != ''
		""",
		pluck=True,
	)

	for name in je_names:
		sync_opening_journal_entry(frappe.get_doc("Journal Entry", name))
