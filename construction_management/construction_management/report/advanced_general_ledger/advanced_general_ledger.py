# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _, _dict
from frappe.utils import cint, getdate, flt

import erpnext.accounts.report.general_ledger.general_ledger as gl_report
from erpnext.accounts.report.general_ledger.general_ledger import (
	validate_filters,
	validate_party,
	set_account_currency,
	get_columns as gl_get_columns,
	get_data_with_opening_closing,
	get_result_as_list,
	get_balance,
	get_translated_labels_for_totals,
	DEBIT_CREDIT_DICT,
)
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
	get_accounting_dimensions,
)


def execute(filters=None):
	if not filters:
		return [], []

	account_details = {}

	if filters and filters.get("print_in_account_currency") and not filters.get("account"):
		frappe.throw(_("Select an account to print in account currency"))

	for acc in frappe.db.sql("""select name, is_group from tabAccount""", as_dict=1):
		account_details.setdefault(acc.name, acc)

	if filters.get("party"):
		filters.party = frappe.parse_json(filters.get("party"))

	validate_filters(filters, account_details)
	validate_party(filters)
	filters = set_account_currency(filters)

	columns = get_columns(filters)
	res = get_result(filters, account_details)

	return columns, res


def get_result(filters, account_details):
	accounting_dimensions = []
	if filters.get("include_dimensions"):
		accounting_dimensions = get_accounting_dimensions()

	gl_entries = gl_report.get_gl_entries(filters, accounting_dimensions)

	if filters.get("party_type") or filters.get("party"):
		gl_entries = _sort_gl_entries_for_party(
			gl_entries,
			group_by_against_voucher=_get_group_by_against_voucher_setting(filters),
		)

	data = get_data_with_opening_closing(filters, account_details, accounting_dimensions, gl_entries)
	result = get_result_as_list(data, filters)

	# Inject Proforma (Sales Order) rows only when explicitly enabled.
	if cint(filters.get("include_proforma")):
		result = inject_proforma_rows(result, filters)

	return result


def _get_group_by_against_voucher_setting(filters):
	if "group_by_against_voucher" in filters and filters.get("group_by_against_voucher") is not None:
		return cint(filters.get("group_by_against_voucher"))

	try:
		from redtra_customisation.override.general_ledger_report import _get_gl_setting

		return bool(
			_get_gl_setting(
				"group_by_against_voucher_in_gl",
				filters,
				"group_by_against_voucher",
			)
		)
	except ImportError:
		return False


def _sort_gl_entries_for_party(gl_entries, group_by_against_voucher=False):
	def sort_key(gle):
		key = [gle.get("posting_date") or ""]
		if group_by_against_voucher:
			key.append(_group_key_for_party_sort(gle))
		key.extend(
			[
				gle.get("voucher_no") or "",
				gle.get("account") or "",
				gle.get("creation") or "",
			]
		)
		return tuple(key)

	return sorted(gl_entries, key=sort_key)


def _group_key_for_party_sort(gle):
	against_voucher = (gle.get("against_voucher") or "").strip()
	if against_voucher:
		return against_voucher
	return gle.get("voucher_no") or ""


def get_sales_orders(filters):
	"""Fetch submitted Sales Orders as pseudo-GL rows labeled 'Proforma'."""
	conditions = []
	so_filters = {}

	conditions.append("so.docstatus = 1")
	conditions.append("IFNULL(so.per_billed, 0) = 0")

	if filters.get("company"):
		conditions.append("so.company = %(company)s")
		so_filters["company"] = filters.get("company")

	if filters.get("party_type") == "Customer" and filters.get("party"):
		party_list = filters.get("party")
		if isinstance(party_list, str):
			party_list = [party_list]
		conditions.append("so.customer IN %(party)s")
		so_filters["party"] = party_list

	if filters.get("from_date"):
		conditions.append("so.transaction_date >= %(from_date)s")
		so_filters["from_date"] = filters.get("from_date")

	if filters.get("to_date"):
		conditions.append("so.transaction_date <= %(to_date)s")
		so_filters["to_date"] = filters.get("to_date")

	if filters.get("project"):
		project_list = filters.get("project")
		if isinstance(project_list, str):
			project_list = [project_list]
		conditions.append("so.project IN %(project)s")
		so_filters["project"] = project_list

	if filters.get("cost_center"):
		cost_center_list = filters.get("cost_center")
		if isinstance(cost_center_list, str):
			cost_center_list = [cost_center_list]
		conditions.append("so.cost_center IN %(cost_center)s")
		so_filters["cost_center"] = cost_center_list

	where_clause = " AND ".join(conditions)

	sales_orders = frappe.db.sql(
		f"""
		SELECT
			so.name as voucher_no,
			so.transaction_date as posting_date,
			so.customer as party,
			so.customer_name as party_name,
			'Customer' as party_type,
			'Proforma' as voucher_type,
			'' as voucher_subtype,
			so.base_grand_total as debit,
			0 as credit,
			so.base_grand_total as debit_in_account_currency,
			0 as credit_in_account_currency,
			so.project,
			so.cost_center,
			'' as account,
			'' as against,
			'' as against_voucher_type,
			'' as against_voucher,
			'' as gl_entry,
			'No' as is_opening,
			'' as bill_no,
			'' as remarks,
			so.currency as account_currency,
			so.grand_total as so_grand_total,
			so.base_grand_total as so_base_grand_total,
			so.status as so_status
		FROM `tabSales Order` so
		WHERE {where_clause}
		ORDER BY so.transaction_date, so.name
		""",
		so_filters,
		as_dict=1,
	)

	return sales_orders


def inject_proforma_rows(result, filters):
	"""
	Insert Proforma (Sales Order) rows into the GL result set.
	Proforma rows are inserted in date order among GL entries,
	then the running balance is recalculated.
	"""
	proforma_rows = get_sales_orders(filters)
	if not proforma_rows:
		return result

	# Separate totals rows (Opening, Total, Closing) from data rows
	# Totals rows have no posting_date but have an 'account' key with labels
	labels = get_translated_labels_for_totals()
	label_values = set(labels.values())

	opening_row = None
	closing_row = None
	total_row = None
	gl_data_rows = []
	separator_rows_before = []
	separator_rows_after = []
	found_first_data = False

	for row in result:
		account_val = row.get("account", "")
		if account_val in label_values:
			if account_val == labels["opening"]:
				opening_row = row
			elif account_val == labels["total"]:
				total_row = row
			elif account_val == labels["closing"]:
				closing_row = row
		elif row.get("posting_date"):
			found_first_data = True
			gl_data_rows.append(row)
		else:
			# Separator/spacer rows or sub-group rows
			if not found_first_data:
				separator_rows_before.append(row)
			else:
				separator_rows_after.append(row)

	# Enrich proforma rows with required fields
	for row in proforma_rows:
		row["is_proforma"] = 1
		row["account_currency"] = filters.get("account_currency", "")
		row["presentation_currency"] = filters.get("presentation_currency", "")
		row["balance"] = 0

	# Merge proforma rows into GL data rows sorted by posting_date
	merged = []
	gi, pi = 0, 0
	while gi < len(gl_data_rows) and pi < len(proforma_rows):
		gl_date = getdate(gl_data_rows[gi].get("posting_date"))
		so_date = getdate(proforma_rows[pi].get("posting_date"))
		if gl_date <= so_date:
			merged.append(gl_data_rows[gi])
			gi += 1
		else:
			merged.append(proforma_rows[pi])
			pi += 1
	merged.extend(gl_data_rows[gi:])
	merged.extend(proforma_rows[pi:])

	# Recalculate running balance across merged data
	balance = 0
	if opening_row:
		balance = flt(opening_row.get("debit", 0)) - flt(opening_row.get("credit", 0))

	for row in merged:
		balance = get_balance(row, balance, "debit", "credit")
		row["balance"] = balance

	# Update totals to include proforma amounts
	proforma_debit_total = sum(flt(r.get("debit", 0)) for r in proforma_rows)
	proforma_credit_total = sum(flt(r.get("credit", 0)) for r in proforma_rows)

	if total_row:
		total_row["debit"] = flt(total_row.get("debit", 0)) + proforma_debit_total
		total_row["credit"] = flt(total_row.get("credit", 0)) + proforma_credit_total

	if closing_row:
		closing_row["debit"] = flt(closing_row.get("debit", 0)) + proforma_debit_total
		closing_row["credit"] = flt(closing_row.get("credit", 0)) + proforma_credit_total
		closing_row["balance"] = flt(closing_row.get("debit", 0)) - flt(closing_row.get("credit", 0))

	# Reassemble the final result
	final = []
	if opening_row:
		final.append(opening_row)

	# Add separator rows that appeared before data
	final.extend(separator_rows_before)

	final.extend(merged)

	# Add separator rows that appeared after data
	final.extend(separator_rows_after)

	# Add a spacer before totals
	final.append({"debit_in_transaction_currency": None, "credit_in_transaction_currency": None})

	if total_row:
		final.append(total_row)
	if closing_row:
		final.append(closing_row)

	return final


def get_soa_totals(data):
	"""Summary totals for SOA PDF including opening balance."""
	from erpnext.accounts.report.general_ledger.general_ledger import get_translated_labels_for_totals

	labels = get_translated_labels_for_totals()
	totals = {
		"opening_debit": 0,
		"opening_credit": 0,
		"period_debit": 0,
		"period_credit": 0,
		"closing_balance": 0,
	}

	for row in data:
		account = row.get("account")
		if account == labels["opening"]:
			totals["opening_debit"] = flt(row.get("debit"))
			totals["opening_credit"] = flt(row.get("credit"))
		elif account == labels["closing"]:
			totals["closing_balance"] = flt(row.get("balance"))
		elif row.get("posting_date"):
			totals["period_debit"] += flt(row.get("debit"))
			totals["period_credit"] += flt(row.get("credit"))

	totals["total_debit"] = totals["opening_debit"] + totals["period_debit"]
	totals["total_credit"] = totals["opening_credit"] + totals["period_credit"]
	totals["net_balance"] = totals["closing_balance"] or (
		totals["total_debit"] - totals["total_credit"]
	)
	return totals


@frappe.whitelist()
def get_soa_pdf(filters):
	"""
	Generate a Statement of Account PDF from the Advanced General Ledger report.
	Called from the report's 'Print SOA' button.
	"""
	import json
	from frappe.utils.pdf import get_pdf
	from frappe.www.printview import get_print_style
	from construction_management.report_pdf_utils import get_report_pdf_options, inline_file_images

	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))

	# Respect the report checkbox.  Previously this was forced to 1 here,
	# causing Proforma rows to appear in every printed SOA.
	filters["include_proforma"] = cint(filters.get("include_proforma"))

	columns, data = execute(filters)

	# Enrich Payment Entry rows with reference details (lazy import to avoid circular dependency)
	from construction_management.overrides.process_statement_of_accounts import enrich_reference_details
	enrich_reference_details(data)

	# Resolve letter head
	letter_head = None
	company = filters.get("company")
	if company:
		lh_name = frappe.get_cached_value("Company", company, "default_letter_head")
		if lh_name:
			letter_head = frappe.db.get_value(
				"Letter Head",
				lh_name,
				["content", "footer"],
				as_dict=True,
			)
		if not letter_head:
			letter_head = frappe.db.get_value(
				"Letter Head",
				{"is_default": 1},
				["content", "footer"],
				as_dict=True,
			)

	# Render SOA HTML
	template_path = (
		"construction_management/construction_management/report/"
		"advanced_general_ledger/advanced_general_ledger_soa.html"
	)

	# Normalize party / party_name to lists for the template
	party_label = ""
	if filters.get("party"):
		party_list = filters.get("party")
		if isinstance(party_list, str):
			party_list = [party_list]
		filters["party"] = party_list
		party_label = party_list[0] if party_list else ""

	if not filters.get("party_name"):
		# Resolve party_name from party
		if filters.get("party") and filters.get("party_type"):
			party_type = filters.get("party_type")
			party_names = []
			name_field = "customer_name" if party_type == "Customer" else (
				"supplier_name" if party_type == "Supplier" else "name"
			)
			for p in filters.get("party"):
				pname = frappe.db.get_value(party_type, p, name_field) or p
				party_names.append(pname)
			filters["party_name"] = party_names
		else:
			filters["party_name"] = filters.get("party", [])
	elif isinstance(filters.get("party_name"), str):
		filters["party_name"] = [filters.get("party_name")]

	# Fetch Pending PDCs for summary
	pdcs = get_pending_pdcs(filters)

	html = frappe.render_template(
		template_path,
		{
			"filters": filters,
			"data": data,
			"report": {"report_name": "Advanced General Ledger", "columns": columns},
			"ageing": None,
			"pdcs": pdcs,
			"letter_head": letter_head,
			"terms_and_conditions": None,
			"soa_totals": get_soa_totals(data),
		},
	)

	# Wrap in a complete HTML document with Bootstrap table styles
	full_html = """
	<!DOCTYPE html>
	<html>
	<head>
		<meta charset="utf-8">
		<title>Statement Of Account{title_suffix}</title>
		<style>
			{print_css}
			body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 11px; }}
			.table {{ width: 100%; border-collapse: collapse; margin-bottom: 10px; }}
			.table th, .table td {{ border: 1px solid #d1d8dd; padding: 6px 8px; }}
			.table thead th {{ background-color: #f7f7f7; font-weight: bold; }}
			.table-bordered {{ border: 1px solid #d1d8dd; }}
			.text-center {{ text-align: center; }}
			.text-right {{ text-align: right; }}
			h2 {{ margin-top: 0; }}
			.page-break {{ page-break-after: always; }}
			.letter-head {{ margin-bottom: 10px; }}
		</style>
	</head>
	<body>
		{body}
	</body>
	</html>
	""".format(
		title_suffix=f" - {party_label}" if party_label else "",
		print_css=get_print_style(),
		body=html,
	)

	pdf = get_pdf(
		inline_file_images(full_html),
		get_report_pdf_options(orientation="Landscape"),
	)

	frappe.local.response.filename = "Statement_of_Account{}.pdf".format(
		f"_{party_label}" if party_label else ""
	)
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "binary"


def get_columns(filters):
	"""Return columns from standard GL report with voucher_type adjusted for Proforma."""
	columns = gl_get_columns(filters)

	# Add a column to flag proforma rows
	columns.append({
		"label": _("Is Proforma"),
		"fieldname": "is_proforma",
		"fieldtype": "Check",
		"width": 80,
		"hidden": 1,
	})

	# Modify voucher_no column: use Data type instead of Dynamic Link
	# so that "Proforma" voucher_type does not break the link resolution
	for col in columns:
		if col.get("fieldname") == "voucher_no":
			col["fieldtype"] = "Data"
			col.pop("options", None)
			break

	return columns

def get_pending_pdcs(filters):
	"""Fetch pending Post Dated Cheques for the SOA summary."""
	if not frappe.db.exists("DocType", "Post Dated Cheques"):
		return []

	conditions = ["status = 'Pending'", "docstatus = 1"]
	values = {}

	if filters.get("company"):
		conditions.append("company = %(company)s")
		values["company"] = filters.get("company")

	if filters.get("party_type") and filters.get("party"):
		conditions.append("party_type = %(party_type)s")
		values["party_type"] = filters.get("party_type")
		
		party_list = filters.get("party")
		if isinstance(party_list, str):
			party_list = [party_list]
		conditions.append("party IN %(party)s")
		values["party"] = party_list

	if filters.get("from_date"):
		conditions.append("reference_date >= %(from_date)s")
		values["from_date"] = filters.get("from_date")

	if filters.get("to_date"):
		conditions.append("reference_date <= %(to_date)s")
		values["to_date"] = filters.get("to_date")

	try:
		return frappe.db.sql(
			"""
			SELECT
				reference_date as chq_date,
				name as voucher_no,
				reference_no as chq_no,
				amount as cheque_amount,
				reference_date as date
			FROM `tabPost Dated Cheques`
			WHERE {0}
			ORDER BY reference_date ASC
			""".format(" AND ".join(conditions)),
			values,
			as_dict=1
		)
	except Exception:
		return []
