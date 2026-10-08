"""Explicit, small-balance Sales Invoice write-off by Journal Entry."""

import frappe
from frappe import _
from frappe.utils import flt, nowdate


MAX_WRITE_OFF = 0.30


@frappe.whitelist(methods=["POST"])
def create_small_balance_write_off(invoice: str) -> dict:
	frappe.has_permission("Sales Invoice", "read", doc=invoice, throw=True)
	frappe.has_permission("Journal Entry", "create", throw=True)
	frappe.has_permission("Journal Entry", "submit", throw=True)
	frappe.db.sql("select name from `tabSales Invoice` where name = %s for update", invoice)
	doc = frappe.get_doc("Sales Invoice", invoice)
	if doc.docstatus != 1 or doc.is_return:
		frappe.throw(_("Only submitted, non-return Sales Invoices can be written off."))
	company = frappe.db.get_value("Company", doc.company,
		["default_currency", "write_off_account", "cost_center"], as_dict=True)
	if doc.currency != company.default_currency:
		frappe.throw(_("Small-balance write-off currently requires the invoice currency to match the company currency."))
	amount = flt(doc.outstanding_amount)
	if amount <= 0 or amount > MAX_WRITE_OFF:
		frappe.throw(_("Only a positive outstanding balance up to {0} {1} can be written off.").format(
			MAX_WRITE_OFF, doc.currency))
	if not company.write_off_account:
		frappe.throw(_("Configure a Write Off Account for company {0}.").format(doc.company))
	account = frappe.db.get_value("Account", company.write_off_account,
		["company", "root_type", "is_group", "account_currency"], as_dict=True)
	if not account or account.company != doc.company or account.root_type != "Expense" or account.is_group or account.account_currency != doc.currency:
		frappe.throw(_("Configure a non-group expense Write Off Account in the invoice currency for {0}.").format(doc.company))
	if not doc.debit_to:
		frappe.throw(_("Sales Invoice {0} has no receivable account.").format(invoice))
	receivable = frappe.db.get_value("Account", doc.debit_to,
		["company", "account_type", "account_currency"], as_dict=True)
	if not receivable or receivable.company != doc.company or receivable.account_type != "Receivable" or receivable.account_currency != doc.currency:
		frappe.throw(_("The invoice receivable account must belong to its company and currency."))
	remark = _("Small balance write-off for Sales Invoice {0}").format(invoice)
	if frappe.db.exists("Journal Entry", {"company": doc.company, "user_remark": remark, "docstatus": 1}):
		frappe.throw(_("A submitted write-off Journal Entry already exists for Sales Invoice {0}.").format(invoice))
	entry = frappe.new_doc("Journal Entry")
	entry.voucher_type = "Journal Entry"
	entry.company = doc.company
	entry.posting_date = nowdate()
	entry.user_remark = remark
	entry.append("accounts", {"account": company.write_off_account,
		"debit_in_account_currency": amount, "cost_center": doc.cost_center or company.cost_center,
		"project": doc.project})
	entry.append("accounts", {"account": doc.debit_to,
		"credit_in_account_currency": amount, "party_type": "Customer", "party": doc.customer,
		"reference_type": "Sales Invoice", "reference_name": invoice, "project": doc.project})
	entry.insert()
	entry.submit()
	doc.add_comment("Info", _("Outstanding balance {0} {1} written off through Journal Entry {2} by {3}.").format(
		amount, doc.currency, entry.name, frappe.session.user))
	return {"journal_entry": entry.name, "amount": amount, "currency": doc.currency}
