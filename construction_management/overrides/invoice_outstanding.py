# Copyright (c) 2026, Construction Management
# License: MIT

"""Outstanding calculation for invoices with secondary retention accounts."""

import frappe
from frappe.utils import flt


INVOICE_PARTY_FIELDS = {
	"Sales Invoice": ("debit_to", "customer", "Customer"),
	"Purchase Invoice": ("credit_to", "supplier", "Supplier"),
}


def update_primary_account_outstanding(voucher_type: str, voucher_no: str) -> float:
	"""Store outstanding from the invoice's primary party account Payment Ledger."""
	fields = INVOICE_PARTY_FIELDS.get(voucher_type)
	if not fields:
		return 0.0

	account_field, party_field, party_type = fields
	invoice = frappe.db.get_value(
		voucher_type,
		voucher_no,
		[account_field, party_field],
		as_dict=True,
	)
	if not invoice:
		return 0.0

	outstanding = frappe.db.sql(
		"""
		SELECT SUM(amount_in_account_currency)
		FROM `tabPayment Ledger Entry`
		WHERE against_voucher_type = %(voucher_type)s
			AND against_voucher_no = %(voucher_no)s
			AND account = %(account)s
			AND party_type = %(party_type)s
			AND party = %(party)s
			AND delinked = 0
		""",
		{
			"voucher_type": voucher_type,
			"voucher_no": voucher_no,
			"account": invoice.get(account_field),
			"party_type": party_type,
			"party": invoice.get(party_field),
		},
	)[0][0]
	if outstanding is None:
		return 0.0

	ref_doc = frappe.get_lazy_doc(voucher_type, voucher_no)
	previous_outstanding = ref_doc.outstanding_amount
	outstanding = flt(
		outstanding,
		ref_doc.precision("outstanding_amount"),
	)
	ref_doc.outstanding_amount = outstanding
	frappe.db.set_value(
		voucher_type,
		voucher_no,
		"outstanding_amount",
		outstanding,
		update_modified=False,
	)

	from erpnext.accounts.doctype.dunning.dunning import update_linked_dunnings

	update_linked_dunnings(ref_doc, previous_outstanding)
	ref_doc.set_status(update=True)
	ref_doc.notify_update()
	return outstanding
