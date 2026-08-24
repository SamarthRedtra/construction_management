import frappe
from frappe.utils import flt


SO_UNEARNED_REMARK_PREFIX = "SO_UNEARNED_REVENUE"
SI_UNEARNED_REMARK_PREFIX = "SI_UNEARNED_REVENUE_REVERSAL"
_DEDUCTION_CODES = {"RETENTION-DEDUCTION", "ADVANCE-DEDUCTION"}
# SO / SI rows that are not part of revenue for unearned proration (same as _DEDUCTION_CODES; variance added per BOQ Settings on SI)
SO_UNEARNED_EXCLUDED_ITEM_CODES = frozenset(_DEDUCTION_CODES)


def create_so_unearned_revenue_jv(sales_order):
	settings = get_boq_unearned_settings(sales_order.company)
	if not settings.get("enable_so_unearned_revenue_jv"):
		return

	debit_account = settings.get("so_unearned_revenue_debit_account")
	credit_account = settings.get("so_unearned_revenue_credit_account")
	if not debit_account or not credit_account:
		frappe.throw(
			f"BOQ Settings is missing SO unearned revenue accounts for company {sales_order.company}"
		)

	amount = _get_so_unearned_amount(sales_order)
	if amount <= 0:
		return

	remark = _so_remark(sales_order.name)
	if _find_journal_entry_by_remark(remark):
		return

	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Journal Entry"
	je.posting_date = sales_order.transaction_date
	je.company = sales_order.company
	je.user_remark = remark
	je.custom_sales_order = sales_order.name

	cost_center = sales_order.cost_center or frappe.db.get_value("Company", sales_order.company, "cost_center")
	common_dims = {
		"project": sales_order.project,
		"cost_center": cost_center,
	}

	for acc, field in [(debit_account, "debit_in_account_currency"), (credit_account, "credit_in_account_currency")]:
		account_row = {
			"account": acc,
			field: amount,
			**common_dims,
		}

		acc_type = frappe.get_cached_value("Account", acc, "account_type")
		is_rec_pay = acc_type in ["Receivable", "Payable"]

		# Only link Sales Order reference to the Credit row if it's a Receivable/Payable account
		# Linking non-receivable accounts to SO in JVs triggers advance logic that fails for Liability accounts
		if field == "credit_in_account_currency" and is_rec_pay:
			account_row.update({
				"reference_type": "Sales Order",
				"reference_name": sales_order.name,
				"is_advance": "Yes",
			})

		if is_rec_pay or account_row.get("reference_type"):
			ptype = "Supplier" if acc_type == "Payable" else "Customer"
			party = (sales_order.customer or "").strip()

			if ptype == "Supplier" and not frappe.db.exists("Supplier", party):
				# Try to find by supplier_name if ID doesn't match
				found = frappe.db.get_value("Supplier", {"supplier_name": (sales_order.customer_name or "").strip()}, "name")
				if found:
					party = found

			account_row.update({
				"party_type": ptype,
				"party": party
			})

		je.append("accounts", account_row)

	je.insert()
	je.submit()


def reverse_so_unearned_revenue_for_invoice(sales_invoice):
	# This logic has been moved to integrated GL entries within Sales Invoice
	return


def get_boq_unearned_settings(company):
	return frappe.db.get_value(
		"BOQ Settings",
		company,
		[
			"enable_so_unearned_revenue_jv",
			"so_unearned_revenue_debit_account",
			"so_unearned_revenue_credit_account",
		],
		as_dict=True,
	) or {}


def _get_so_unearned_amount(sales_order):
	# The Sales Order net total is the contractual value before the custom
	# retention field is displayed. Adding that field again overstates revenue.
	# Only negative deduction rows actually included in the item total need to be
	# added back for the unearned-revenue calculation.
	amount = flt(sales_order.get("base_net_total") or sales_order.get("base_grand_total"))
	
	deductions = 0
	for item in sales_order.get("items", []):
		if item.get("item_code") in ["RETENTION-DEDUCTION", "ADVANCE-DEDUCTION"]:
			deductions += abs(flt(item.base_amount))

	gross_amount = amount + deductions
	percentage = flt(sales_order.get("custom_unbilled_revenue_percentage") or 100)
	
	return flt(gross_amount * (percentage / 100.0))


def correct_so_unearned_revenue_jv(sales_order_name):
	"""Replace an incorrect SO unearned-revenue JV when nothing has reversed it yet."""
	sales_order = frappe.get_doc("Sales Order", sales_order_name)
	journal_entry_name = find_journal_entry_by_so(sales_order_name)
	if not journal_entry_name:
		return None

	if frappe.db.exists(
		"Journal Entry",
		{
			"docstatus": 1,
			"user_remark": ("like", f"{SI_UNEARNED_REMARK_PREFIX}::%::{sales_order_name}"),
		},
	):
		frappe.throw(
			f"Cannot correct {journal_entry_name}: an invoice has already reversed this unearned revenue entry."
		)

	existing_amount = get_source_accounts_and_amount(journal_entry_name)["amount"]
	expected_amount = _get_so_unearned_amount(sales_order)
	if flt(existing_amount) == flt(expected_amount):
		return journal_entry_name

	journal_entry = frappe.get_doc("Journal Entry", journal_entry_name)
	journal_entry.cancel()
	create_so_unearned_revenue_jv(sales_order)
	return find_journal_entry_by_so(sales_order_name)


def _get_sales_order_amounts_from_invoice(sales_invoice):
	amount_map = {}
	for item in sales_invoice.items:
		so_name = item.get("sales_order")
		if not so_name:
			continue
		if item.get("item_code") in _DEDUCTION_CODES:
			continue

		base_amount = flt(item.get("base_amount"))
		if base_amount <= 0:
			continue

		amount_map[so_name] = amount_map.get(so_name, 0) + base_amount
	return amount_map


def _find_journal_entry_by_remark(remark):
	return frappe.db.get_value("Journal Entry", {"docstatus": 1, "user_remark": remark}, "name")


def find_journal_entry_by_so(sales_order_name):
	"""Find the original (non-reversal) submitted unearned revenue JV for a given Sales Order."""
	jvs = frappe.db.get_all(
		"Journal Entry",
		filters={"docstatus": 1, "custom_sales_order": sales_order_name},
		fields=["name", "custom_sales_invoice"],
	)
	# Return the first JV that has no linked Sales Invoice (i.e., the original entry)
	for jv in jvs:
		if not jv.get("custom_sales_invoice"):
			return jv["name"]
	return None


def get_so_unbilled_jv_amount(sales_order_name):
	"""Submitted SO unearned JV amount (Dr Unbilled / Cr Sales at order)."""
	journal_entry_name = find_journal_entry_by_so(sales_order_name)
	if not journal_entry_name:
		return 0

	source = get_source_accounts_and_amount(journal_entry_name)
	if not source:
		return 0

	return flt(source.get("amount"))


def get_unbilled_reversed_on_invoices(sales_order_name, unbilled_account, exclude_si=None):
	"""Unbilled balance already cleared via credits on submitted Sales Invoices for this SO."""
	si_names = frappe.db.sql(
		"""
		SELECT DISTINCT si.name
		FROM `tabSales Invoice` si
		INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		WHERE sii.sales_order = %s
			AND si.docstatus = 1
			AND (%s IS NULL OR si.name != %s)
		""",
		(sales_order_name, exclude_si, exclude_si),
		pluck="name",
	)
	if not si_names:
		return 0

	return flt(
		frappe.db.sql(
			"""
			SELECT COALESCE(SUM(credit), 0)
			FROM `tabGL Entry`
			WHERE voucher_type = 'Sales Invoice'
				AND voucher_no IN %(si_names)s
				AND account = %(account)s
				AND is_cancelled = 0
			""",
			{"si_names": tuple(si_names), "account": unbilled_account},
		)[0][0]
	)


def get_remaining_so_unbilled_balance(sales_order_name, unbilled_account, exclude_si=None):
	"""Remaining SO unbilled asset to reverse on the next invoice(s)."""
	jv_amount = get_so_unbilled_jv_amount(sales_order_name)
	if jv_amount <= 0:
		return 0

	reversed_amount = get_unbilled_reversed_on_invoices(
		sales_order_name, unbilled_account, exclude_si=exclude_si
	)
	return max(0, flt(jv_amount - reversed_amount, 2))


def get_source_accounts_and_amount(journal_entry):
	rows = frappe.db.get_all(
		"Journal Entry Account",
		filters={"parent": journal_entry},
		fields=["account", "debit_in_account_currency", "credit_in_account_currency"],
		order_by="idx asc",
	)
	debit_row = next((r for r in rows if flt(r.get("debit_in_account_currency")) > 0), None)
	credit_row = next((r for r in rows if flt(r.get("credit_in_account_currency")) > 0), None)
	if not debit_row or not credit_row:
		return None

	return {
		"debit_account": debit_row.get("account"),
		"credit_account": credit_row.get("account"),
		"amount": min(flt(debit_row.get("debit_in_account_currency")), flt(credit_row.get("credit_in_account_currency"))),
	}


def _get_already_reversed_amount(sales_order, credit_account):
	remarks = frappe.db.get_all(
		"Journal Entry",
		filters={
			"docstatus": 1,
			"user_remark": ("like", f"{SI_UNEARNED_REMARK_PREFIX}::%::{sales_order}"),
		},
		pluck="name",
	)
	if not remarks:
		return 0

	return flt(
		frappe.db.sql(
			"""
			SELECT COALESCE(SUM(debit_in_account_currency), 0)
			FROM `tabJournal Entry Account`
			WHERE parent IN %(journal_entries)s
				AND account = %(account)s
			""",
			{"journal_entries": tuple(remarks), "account": credit_account},
		)[0][0]
	)


def _so_remark(sales_order_name):
	return f"{SO_UNEARNED_REMARK_PREFIX}::{sales_order_name}"


def _si_remark(sales_invoice_name, sales_order_name):
	return f"{SI_UNEARNED_REMARK_PREFIX}::{sales_invoice_name}::{sales_order_name}"
