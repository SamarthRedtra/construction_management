import frappe
from frappe.query_builder.functions import Sum
from pypika.terms import ExistsCriterion
from frappe.desk.reportview import build_match_conditions
import erpnext.accounts.report.financial_statements as fs

def get_accounting_entries(
	doctype,
	from_date,
	to_date,
	filters,
	root_lft=None,
	root_rgt=None,
	root_type=None,
	ignore_closing_entries=None,
	period_closing_voucher=None,
	ignore_opening_entries=False,
	group_by_account=False,
	ignore_reporting_currency=True,
):
	gl_entry = frappe.qb.DocType(doctype)
	query = (
		frappe.qb.from_(gl_entry)
		.select(
			gl_entry.account,
			gl_entry.debit if not group_by_account else Sum(gl_entry.debit).as_("debit"),
			gl_entry.credit if not group_by_account else Sum(gl_entry.credit).as_("credit"),
			gl_entry.debit_in_account_currency
			if not group_by_account
			else Sum(gl_entry.debit_in_account_currency).as_("debit_in_account_currency"),
			gl_entry.credit_in_account_currency
			if not group_by_account
			else Sum(gl_entry.credit_in_account_currency).as_("credit_in_account_currency"),
			gl_entry.account_currency,
		)
		.where(gl_entry.company == filters.company)
	)

	if not ignore_reporting_currency:
		query = query.select(
			gl_entry.debit_in_reporting_currency
			if not group_by_account
			else Sum(gl_entry.debit_in_reporting_currency).as_("debit_in_reporting_currency"),
			gl_entry.credit_in_reporting_currency
			if not group_by_account
			else Sum(gl_entry.credit_in_reporting_currency).as_("credit_in_reporting_currency"),
		)

	ignore_is_opening = frappe.get_single_value("Accounts Settings", "ignore_is_opening_check_for_reporting")

	if doctype == "GL Entry":
		query = query.select(gl_entry.posting_date, gl_entry.is_opening, gl_entry.fiscal_year)
		query = query.where(gl_entry.is_cancelled == 0)
		query = query.where(gl_entry.posting_date <= to_date)
		query = query.force_index("posting_date_company_index")

		if ignore_opening_entries and not ignore_is_opening:
			query = query.where(gl_entry.is_opening == "No")
	else:
		query = query.select(gl_entry.closing_date.as_("posting_date"))
		query = query.where(gl_entry.period_closing_voucher == period_closing_voucher)

	query = fs.apply_additional_conditions(doctype, query, from_date, ignore_closing_entries, filters)

	if (root_lft and root_rgt) or root_type:
		account_filter_query = fs.get_account_filter_query(root_lft, root_rgt, root_type, gl_entry)
		query = query.where(ExistsCriterion(account_filter_query))

	query, params = query.walk()
	match_conditions = build_match_conditions(doctype)

	if match_conditions:
		query += " AND " + match_conditions

	if group_by_account:
		query += " GROUP BY `account`"

	return frappe.db.sql(query, params, as_dict=True)

# Apply the patch
fs.get_accounting_entries = get_accounting_entries
