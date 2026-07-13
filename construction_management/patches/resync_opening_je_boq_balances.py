import frappe

from construction_management.api.boq_opening_balance import sync_opening_journal_entry


def execute():
	"""Re-sync opening Journal Entries to BOQ Advance Payment (handles debit-side opening lines)."""
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
			AND (IFNULL(jea.debit, 0) != 0 OR IFNULL(jea.credit, 0) != 0)
		""",
		pluck=True,
	)

	created = 0
	for name in je_names:
		before = frappe.db.count(
			"BOQ Advance Payment",
			{"reference": ["like", f"{name}::%"], "docstatus": 1},
		)
		sync_opening_journal_entry(frappe.get_doc("Journal Entry", name))
		after = frappe.db.count(
			"BOQ Advance Payment",
			{"reference": ["like", f"{name}::%"], "docstatus": 1},
		)
		if after > before:
			created += after - before

	frappe.db.commit()
	frappe.logger().info(f"resync_opening_je_boq_balances: synced {len(je_names)} JEs, created {created} advance rows")
