"""Explicit, small-balance Sales Invoice write-off by Journal Entry."""

import frappe
from frappe import _
from frappe.utils import flt, nowdate


MAX_WRITE_OFF = 0.99


def _write_off_remark(invoice_doctype: str, invoice: str) -> str:
	if invoice_doctype == "Purchase Invoice":
		return _("Small balance write-off for Purchase Invoice {0}").format(invoice)
	return _("Small balance write-off for Sales Invoice {0}").format(invoice)


def _existing_write_off_je(company: str, remark: str) -> str | None:
	return frappe.db.get_value("Journal Entry", {"company": company, "user_remark": remark, "docstatus": 1}, "name")


def purchase_invoice_write_off_eligibility(doc) -> dict:
	"""Return whether a PI small-balance write-off can run, without throwing."""
	company_row = frappe.db.get_value(
		"Company",
		doc.company,
		["default_currency", "write_off_account", "cost_center"],
		as_dict=True,
	) or {}
	currency = doc.currency or company_row.get("default_currency") or ""
	amount = flt(doc.outstanding_amount)
	result = {
		"eligible": False,
		"amount": amount,
		"currency": currency,
		"max_amount": MAX_WRITE_OFF,
		"reason": None,
		"write_off_journal_entry": None,
	}
	remark = _write_off_remark("Purchase Invoice", doc.name)
	result["write_off_journal_entry"] = _existing_write_off_je(doc.company, remark)
	if doc.docstatus != 1 or doc.is_return:
		result["reason"] = "not_submitted"
		return result
	if doc.currency != company_row.get("default_currency"):
		result["reason"] = "currency_mismatch"
		return result
	if amount <= 0:
		result["reason"] = "no_outstanding"
		return result
	if amount > MAX_WRITE_OFF:
		result["reason"] = "above_limit"
		return result
	if result["write_off_journal_entry"]:
		result["reason"] = "already_written_off"
		return result
	if not company_row.get("write_off_account"):
		result["reason"] = "no_write_off_account"
		return result
	account = frappe.db.get_value(
		"Account",
		company_row.get("write_off_account"),
		["company", "report_type", "is_group", "account_currency"],
		as_dict=True,
	)
	if (
		not account
		or account.get("company") != doc.company
		or account.get("report_type") != "Profit and Loss"
		or account.get("is_group")
		or account.get("account_currency") != doc.currency
	):
		result["reason"] = "invalid_write_off_account"
		return result
	if not doc.credit_to:
		result["reason"] = "no_payable_account"
		return result
	payable = frappe.db.get_value(
		"Account",
		doc.credit_to,
		["company", "account_type", "account_currency"],
		as_dict=True,
	)
	if (
		not payable
		or payable.get("company") != doc.company
		or payable.get("account_type") != "Payable"
		or payable.get("account_currency") != doc.currency
	):
		result["reason"] = "invalid_payable_account"
		return result
	if not frappe.has_permission("Journal Entry", "create") or not frappe.has_permission("Journal Entry", "submit"):
		result["reason"] = "no_journal_entry_permission"
		return result
	result["eligible"] = True
	return result


@frappe.whitelist(methods=["GET"])
def get_purchase_invoice_write_off_eligibility(invoice: str) -> dict:
	frappe.has_permission("Purchase Invoice", "read", doc=invoice, throw=True)
	doc = frappe.get_doc("Purchase Invoice", invoice)
	return purchase_invoice_write_off_eligibility(doc)


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


@frappe.whitelist(methods=["POST"])
def create_small_balance_purchase_write_off(invoice: str) -> dict:
	frappe.has_permission("Purchase Invoice", "read", doc=invoice, throw=True)
	frappe.has_permission("Journal Entry", "create", throw=True)
	frappe.has_permission("Journal Entry", "submit", throw=True)
	frappe.db.sql("select name from `tabPurchase Invoice` where name = %s for update", invoice)
	doc = frappe.get_doc("Purchase Invoice", invoice)
	eligibility = purchase_invoice_write_off_eligibility(doc)
	if not eligibility["eligible"]:
		_messages = {
			"not_submitted": _("Only submitted, non-return Purchase Invoices can be written off."),
			"currency_mismatch": _("Small-balance write-off currently requires the invoice currency to match the company currency."),
			"no_outstanding": _("This invoice has no outstanding balance to write off."),
			"above_limit": _("Only a positive outstanding balance up to {0} {1} can be written off.").format(
				MAX_WRITE_OFF, doc.currency
			),
			"already_written_off": _("A submitted write-off Journal Entry already exists for Purchase Invoice {0}.").format(invoice),
			"no_write_off_account": _("Configure a Write Off Account for company {0}.").format(doc.company),
			"invalid_write_off_account": _("Configure a non-group Profit and Loss Write Off Account in the invoice currency for {0}.").format(
				doc.company
			),
			"no_payable_account": _("Purchase Invoice {0} has no payable account.").format(invoice),
			"invalid_payable_account": _("The invoice payable account must belong to its company and currency."),
			"no_journal_entry_permission": _("You need permission to create and submit Journal Entries."),
		}
		frappe.throw(_messages.get(eligibility["reason"]) or _("This invoice cannot be written off."))
	company = frappe.db.get_value(
		"Company",
		doc.company,
		["default_currency", "write_off_account", "cost_center"],
		as_dict=True,
	)
	amount = flt(doc.outstanding_amount)
	remark = _write_off_remark("Purchase Invoice", invoice)
	entry = frappe.new_doc("Journal Entry")
	entry.voucher_type = "Journal Entry"
	entry.company = doc.company
	entry.posting_date = nowdate()
	entry.user_remark = remark
	entry.append(
		"accounts",
		{
			"account": doc.credit_to,
			"debit_in_account_currency": amount,
			"party_type": "Supplier",
			"party": doc.supplier,
			"reference_type": "Purchase Invoice",
			"reference_name": invoice,
			"cost_center": doc.cost_center or company.cost_center,
			"project": doc.project,
		},
	)
	entry.append(
		"accounts",
		{
			"account": company.write_off_account,
			"credit_in_account_currency": amount,
			"cost_center": doc.cost_center or company.cost_center,
			"project": doc.project,
		},
	)
	entry.insert()
	entry.submit()
	doc.add_comment(
		"Info",
		_("Outstanding balance {0} {1} written off through Journal Entry {2} by {3}.").format(
			amount, doc.currency, entry.name, frappe.session.user
		),
	)
	return {"journal_entry": entry.name, "amount": amount, "currency": doc.currency}
