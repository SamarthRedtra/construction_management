# Copyright (c) 2024, Construction Management
# License: MIT

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt
from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice
from erpnext.accounts.utils import update_voucher_outstanding
from redtra_customisation.override.purchase_invoice import CustomPurchaseInvoice

LEGACY_FIXED_ASSET_PO = "SKD-LPO-00371-1"

_PO_PROGRESS_DEDUCTION_ITEMS = frozenset(
	{"RETENTION-DEDUCTION", "ADVANCE-DEDUCTION", "PURCHASE-ADVANCE"}
)

_PO_PROGRESS_FIELDS = (
	"custom_prev_qty",
	"custom_prev_amount",
	"custom_current_qty",
	"custom_current_amount",
	"custom_accumulated_qty",
	"custom_accumulated_amount",
)


class PurchaseInvoiceOverride(CustomPurchaseInvoice):
	def set_expense_account(self, for_validate=False):
		super().set_expense_account(for_validate)
		_set_legacy_fixed_asset_stock_clearing_account(self)

	def validate_with_previous_doc(self):
		"""Allow PI project/warehouse to differ from PO (e.g. receive into another site warehouse)."""
		super(PurchaseInvoice, self).validate_with_previous_doc(
			{
				"Purchase Order": {
					"ref_dn_field": "purchase_order",
					"compare_fields": [["supplier", "="], ["company", "="], ["currency", "="]],
				},
				"Purchase Order Item": {
					"ref_dn_field": "po_detail",
					"compare_fields": [["item_code", "="], ["uom", "="]],
					"is_child_table": True,
					"allow_duplicate_prev_row_id": True,
				},
				"Purchase Receipt": {
					"ref_dn_field": "purchase_receipt",
					"compare_fields": [["supplier", "="], ["company", "="], ["currency", "="]],
				},
				"Purchase Receipt Item": {
					"ref_dn_field": "pr_detail",
					"compare_fields": [["item_code", "="], ["uom", "="]],
					"is_child_table": True,
				},
			}
		)

		if (
			cint(frappe.db.get_single_value("Buying Settings", "maintain_same_rate"))
			and not self.is_return
			and not self.is_internal_supplier
		):
			self.validate_rate_with_reference_doc(
				[
					["Purchase Order", "purchase_order", "po_detail"],
					["Purchase Receipt", "purchase_receipt", "pr_detail"],
				]
			)

	def get_gl_entries(self, warehouse_account=None):
		gl_entries = super().get_gl_entries(warehouse_account)

		# If project is not set, keep default ERPNext posting
		if not self.get("project"):
			return _ensure_supplier_party_on_gl_entries(self, gl_entries)

		# If BOQ Settings is missing for company, keep default posting
		if not frappe.db.exists("BOQ Settings", self.company):
			return _ensure_supplier_party_on_gl_entries(self, gl_entries)

		boq_settings = frappe.db.get_value(
			"BOQ Settings",
			self.company,
			["purchase_retention_account", "purchase_advance_account"],
			as_dict=True,
		) or {}
		retention_account = boq_settings.get("purchase_retention_account")
		advance_account = boq_settings.get("purchase_advance_account")

		if not (retention_account or advance_account):
			return _ensure_supplier_party_on_gl_entries(self, gl_entries)

		deductions = []
		expense_accounts = set()
		for item in self.items:
			if item.expense_account:
				expense_accounts.add(item.expense_account)

			target_account = None
			if item.item_code == "RETENTION-DEDUCTION": target_account = retention_account
			elif item.item_code == "ADVANCE-DEDUCTION" and not self.get("custom_is_advance"): target_account = advance_account

			if target_account:
				deductions.append(
					{
						"expense_account": item.expense_account,
						"target_account": target_account,
						"amount": abs(flt(item.base_amount)),
						"transaction_amount": abs(flt(item.amount)),
						"project": item.project or self.project,
						"cost_center": item.cost_center or self.cost_center,
						"boq_item": item.boq_item,
						"bill_no": item.bill_no,
						"item_code": item.item_code,
					}
				)

		if not deductions:
			return _ensure_supplier_party_on_gl_entries(self, gl_entries)

		# If subcontractor purchase, redirect deduction entries directly to target accounts and do not gross up (Case A),
		# or if they are merged into Accrued, gross up and add custom entries (Case B).
		if _is_subcontractor_purchase(self):
			def add_party_if_needed(gl_dict, account):
				acc_type = frappe.db.get_value("Account", account, "account_type")
				if acc_type in ["Receivable", "Payable"]:
					gl_dict.update(
						{
							"party_type": "Supplier",
							"party": self.supplier,
							"against": self.supplier,
						}
					)
				return gl_dict

			new_entries, processed_deductions = _redirect_subcontractor_deduction_credits(
				self, gl_entries, deductions, add_party_if_needed
			)

			# Second Pass: Handle remaining unmatched merged entries (Case B)
			final_entries = []
			for entry in new_entries:
				# Match expense entries (Debits to an account used in items)
				if entry.get("account") in expense_accounts and flt(entry.get("debit")) > 0:
					total_gross_up = 0
					total_gross_up_transaction = 0
					for idx, d in enumerate(deductions):
						if idx in processed_deductions:
							continue

						# Match by project, boq_item, and cost_center
						match = (
							d["project"] == entry.get("project")
							and d["boq_item"] == entry.get("boq_item")
						)
						if not match and not entry.get("boq_item") and not d["boq_item"]:
							match = (
								d["project"] == entry.get("project")
								and d["cost_center"] == entry.get("cost_center")
							)

						if match:
							total_gross_up += d["amount"]
							total_gross_up_transaction += d["transaction_amount"]
							processed_deductions.append(idx)

							target_currency = frappe.get_cached_value("Account", d["target_account"], "account_currency") or self.company_currency
							deduction_entry = self.get_gl_dict(
								add_party_if_needed({
									"account": d["target_account"],
									"credit": d["amount"],
									"credit_in_account_currency": (
										d["amount"]
										if target_currency == self.company_currency
										else d["transaction_amount"]
									),
									"project": d["project"],
									"boq_item": d["boq_item"],
									"bill_no": d["bill_no"],
									"cost_center": d["cost_center"],
									"against": self.supplier,
									"remarks": f"{d['item_code']} for {self.name}",
								}, d["target_account"]),
								account_currency=target_currency
							)
							deduction_entry.update(
								{
									"transaction_currency": self.currency,
									"transaction_exchange_rate": self.get("conversion_rate") or 1,
									"credit_in_transaction_currency": d["transaction_amount"],
								}
							)
							final_entries.append(deduction_entry)

					if total_gross_up > 0:
						entry["debit"] = flt(entry.get("debit", 0)) + total_gross_up
						if "debit_in_account_currency" in entry:
							if entry.get("account_currency") == self.currency:
								entry["debit_in_account_currency"] = (
									flt(entry.get("debit_in_account_currency", 0)) + total_gross_up_transaction
								)
							else:
								entry["debit_in_account_currency"] = flt(entry.get("debit_in_account_currency", 0)) + total_gross_up
						if "debit_in_transaction_currency" in entry:
							entry["debit_in_transaction_currency"] = (
								flt(entry.get("debit_in_transaction_currency", 0)) + total_gross_up_transaction
							)
						if "debit_in_reporting_currency" in entry:
							entry["debit_in_reporting_currency"] = (
								flt(entry.get("debit_in_reporting_currency", 0)) + total_gross_up
							)

				final_entries.append(entry)

			# Add unmatched deductions as orphans (should theoretically never happen if standard entries exist)
			for idx, d in enumerate(deductions):
				if idx not in processed_deductions:
					for entry in final_entries:
						if entry.get("account") in expense_accounts and flt(entry.get("debit")) > 0:
							entry["debit"] = flt(entry.get("debit", 0)) + d["amount"]
							if "debit_in_transaction_currency" in entry:
								entry["debit_in_transaction_currency"] = (
									flt(entry.get("debit_in_transaction_currency", 0)) + d["transaction_amount"]
								)
							if "debit_in_account_currency" in entry:
								if entry.get("account_currency") == self.currency:
									entry["debit_in_account_currency"] = (
										flt(entry.get("debit_in_account_currency", 0)) + d["transaction_amount"]
									)
								else:
									entry["debit_in_account_currency"] = flt(entry.get("debit_in_account_currency", 0)) + d["amount"]
							break

					unmatched_gl = {
						"account": d["target_account"],
						"credit": d["amount"],
						"project": d["project"],
						"boq_item": d["boq_item"],
						"bill_no": d["bill_no"],
						"cost_center": d["cost_center"],
						"against": self.supplier,
						"remarks": f"{d['item_code']} for {self.name}",
					}
					target_currency = frappe.get_cached_value("Account", d["target_account"], "account_currency") or self.company_currency
					deduction_entry = self.get_gl_dict(
						add_party_if_needed(unmatched_gl, d["target_account"]),
						account_currency=target_currency
					)
					deduction_entry.update(
						{
							"transaction_currency": self.currency,
							"transaction_exchange_rate": self.get("conversion_rate") or 1,
							"credit_in_transaction_currency": d["transaction_amount"],
						}
					)
					final_entries.append(deduction_entry)

			return _ensure_supplier_party_on_gl_entries(self, final_entries)

		# Keep original gross-up logic for non-subcontractor purchases if they ever have deductions
		new_entries = []
		processed_deductions = []

		def add_party_if_needed(gl_dict, account):
			acc_type = frappe.db.get_value("Account", account, "account_type")
			if acc_type in ["Receivable", "Payable"]:
				gl_dict.update(
					{
						"party_type": "Supplier",
						"party": self.supplier,
					}
				)
			return gl_dict

		for entry in gl_entries:
			# Match expense entries (Debits to an account used in items)
			if entry.get("account") in expense_accounts and flt(entry.get("debit")) > 0:
				total_gross_up = 0
				total_gross_up_transaction = 0
				for idx, d in enumerate(deductions):
					if idx in processed_deductions:
						continue

					match = (
						d["project"] == entry.get("project")
						and d["boq_item"] == entry.get("boq_item")
					)
					if not match and not entry.get("boq_item") and not d["boq_item"]:
						match = (
							d["project"] == entry.get("project")
							and d["cost_center"] == entry.get("cost_center")
						)

					if match:
						total_gross_up += d["amount"]
						total_gross_up_transaction += d["transaction_amount"]
						processed_deductions.append(idx)

						acc_currency = frappe.get_cached_value("Account", d["target_account"], "account_currency") or self.company_currency
						deduction_entry = self.get_gl_dict(
							add_party_if_needed({
								"account": d["target_account"],
								"credit": d["amount"],
								"credit_in_account_currency": (
									d["amount"]
									if entry.get("account_currency") == self.company_currency
									else d["transaction_amount"]
								),
								"project": d["project"],
								"boq_item": d["boq_item"],
								"bill_no": d["bill_no"],
								"cost_center": d["cost_center"],
								"against": self.supplier,
								"remarks": f"{d['item_code']} for {self.name}",
							}, d["target_account"]),
							account_currency=acc_currency
						)
						deduction_entry.update(
							{
								"transaction_currency": self.currency,
								"transaction_exchange_rate": self.get("conversion_rate") or 1,
								"credit_in_transaction_currency": d["transaction_amount"],
							}
						)
						new_entries.append(deduction_entry)

				if total_gross_up > 0:
					entry["debit"] = flt(entry.get("debit", 0)) + total_gross_up
					if "debit_in_account_currency" in entry:
						if entry.get("account_currency") == self.currency:
							entry["debit_in_account_currency"] = (
								flt(entry.get("debit_in_account_currency", 0)) + total_gross_up_transaction
							)
						else:
							entry["debit_in_account_currency"] = flt(entry.get("debit_in_account_currency", 0)) + total_gross_up
					if "debit_in_transaction_currency" in entry:
						entry["debit_in_transaction_currency"] = (
							flt(entry.get("debit_in_transaction_currency", 0)) + total_gross_up_transaction
						)
					if "debit_in_reporting_currency" in entry:
						entry["debit_in_reporting_currency"] = (
							flt(entry.get("debit_in_reporting_currency", 0)) + total_gross_up
						)

			new_entries.append(entry)

		# Add unmatched deductions as orphans
		for idx, d in enumerate(deductions):
			if idx not in processed_deductions:
				for entry in new_entries:
					if entry.get("account") in expense_accounts and flt(entry.get("debit")) > 0:
						entry["debit"] = flt(entry.get("debit", 0)) + d["amount"]
						if "debit_in_transaction_currency" in entry:
							entry["debit_in_transaction_currency"] = (
								flt(entry.get("debit_in_transaction_currency", 0)) + d["transaction_amount"]
							)
						if "debit_in_account_currency" in entry:
							if entry.get("account_currency") == self.currency:
								entry["debit_in_account_currency"] = (
									flt(entry.get("debit_in_account_currency", 0)) + d["transaction_amount"]
								)
							else:
								entry["debit_in_account_currency"] = flt(entry.get("debit_in_account_currency", 0)) + d["amount"]
						break

				unmatched_gl = {
					"account": d["target_account"],
					"credit": d["amount"],
					"project": d["project"],
					"boq_item": d["boq_item"],
					"bill_no": d["bill_no"],
					"cost_center": d["cost_center"],
					"against": self.supplier,
					"remarks": f"{d['item_code']} for {self.name}",
				}
				acc_currency = frappe.get_cached_value("Account", d["target_account"], "account_currency") or self.company_currency
				deduction_entry = self.get_gl_dict(
					add_party_if_needed(unmatched_gl, d["target_account"]),
					account_currency=acc_currency
				)
				deduction_entry.update(
					{
						"transaction_currency": self.currency,
						"transaction_exchange_rate": self.get("conversion_rate") or 1,
						"credit_in_transaction_currency": d["transaction_amount"],
					}
				)
				new_entries.append(deduction_entry)

		return _ensure_supplier_party_on_gl_entries(self, new_entries)

	def get_pc_payable_print_context(self):
		"""Build dict for Payment Certificate (Payable) Jinja print format."""
		from construction_management.pc_payable_print_context import build_pc_payable_print_context

		return build_pc_payable_print_context(self)


def _set_legacy_fixed_asset_stock_clearing_account(doc) -> None:
	"""Clear the stock accrual used before this PO was converted to fixed assets."""
	stock_received_but_not_billed = doc.get_company_default("stock_received_but_not_billed")
	if not stock_received_but_not_billed:
		return

	receipt_names = {
		row.purchase_receipt
		for row in doc.get("items") or []
		if row.purchase_order == LEGACY_FIXED_ASSET_PO and row.purchase_receipt
	}
	if not receipt_names:
		return

	receipts_using_stock_accrual = set(
		frappe.get_all(
			"GL Entry",
			filters={
				"voucher_type": "Purchase Receipt",
				"voucher_no": ["in", list(receipt_names)],
				"account": stock_received_but_not_billed,
				"is_cancelled": 0,
			},
			pluck="voucher_no",
			distinct=True,
		)
	)
	for row in doc.get("items") or []:
		if row.purchase_order == LEGACY_FIXED_ASSET_PO and row.purchase_receipt in receipts_using_stock_accrual:
			row.expense_account = stock_received_but_not_billed


def _signed_gl_amount(entry) -> float:
	debit_val = flt(entry.get("debit"))
	credit_val = flt(entry.get("credit"))
	return debit_val if debit_val != 0 else -credit_val


def _apply_deduction_credit_fields(entry, deduction, company_currency):
	"""Rewrite a negative expense GLE into a credit on the BOQ deduction account."""
	target_currency = (
		frappe.get_cached_value("Account", deduction["target_account"], "account_currency") or company_currency
	)
	entry["account"] = deduction["target_account"]
	entry["credit"] = deduction["amount"]
	entry["debit"] = 0
	entry["account_currency"] = target_currency
	if "credit_in_account_currency" in entry:
		entry["credit_in_account_currency"] = (
			deduction["amount"] if target_currency == company_currency else deduction["transaction_amount"]
		)
	if "debit_in_account_currency" in entry:
		entry["debit_in_account_currency"] = 0
	if "credit_in_transaction_currency" in entry:
		entry["credit_in_transaction_currency"] = deduction["transaction_amount"]
	if "debit_in_transaction_currency" in entry:
		entry["debit_in_transaction_currency"] = 0
	if "credit_in_reporting_currency" in entry:
		entry["credit_in_reporting_currency"] = deduction["amount"]
	if "debit_in_reporting_currency" in entry:
		entry["debit_in_reporting_currency"] = 0


def _make_deduction_credit_gl(doc, deduction, add_party_if_needed):
	target_currency = (
		frappe.get_cached_value("Account", deduction["target_account"], "account_currency") or doc.company_currency
	)
	entry = doc.get_gl_dict(
		add_party_if_needed(
			{
				"account": deduction["target_account"],
				"credit": deduction["amount"],
				"credit_in_account_currency": (
					deduction["amount"]
					if target_currency == doc.company_currency
					else deduction["transaction_amount"]
				),
				"project": deduction["project"],
				"boq_item": deduction["boq_item"],
				"bill_no": deduction["bill_no"],
				"cost_center": deduction["cost_center"],
				"against": doc.supplier,
				"remarks": f"{deduction['item_code']} for {doc.name}",
			},
			deduction["target_account"],
		),
		account_currency=target_currency,
	)
	entry.update(
		{
			"transaction_currency": doc.currency,
			"transaction_exchange_rate": doc.get("conversion_rate") or 1,
			"credit_in_transaction_currency": deduction["transaction_amount"],
		}
	)
	return entry


def _redirect_subcontractor_deduction_credits(doc, gl_entries, deductions, add_party_if_needed):
	"""Case A: move expense credits for retention/advance onto BOQ accounts without grossing Accrued.

	ERPNext merge_similar_entries often collapses both deduction credits into one COGS line.
	Match 1:1 first; if the credit equals the remaining sum on that expense account, split it.
	"""
	new_entries = []
	processed = []

	for entry in gl_entries:
		val = _signed_gl_amount(entry)
		if val >= 0:
			new_entries.append(entry)
			continue

		credit_amt = abs(val)
		one_to_one = None
		for idx, deduction in enumerate(deductions):
			if idx in processed:
				continue
			if entry.get("account") == deduction["expense_account"] and abs(credit_amt - deduction["amount"]) < 0.01:
				one_to_one = (idx, deduction)
				break

		if one_to_one:
			idx, deduction = one_to_one
			_apply_deduction_credit_fields(entry, deduction, doc.company_currency)
			add_party_if_needed(entry, deduction["target_account"])
			processed.append(idx)
			new_entries.append(entry)
			continue

		remaining = [
			(idx, deduction)
			for idx, deduction in enumerate(deductions)
			if idx not in processed and deduction["expense_account"] == entry.get("account")
		]
		merged_total = sum(deduction["amount"] for _idx, deduction in remaining)
		if remaining and abs(merged_total - credit_amt) < 0.05:
			for idx, deduction in remaining:
				new_entries.append(_make_deduction_credit_gl(doc, deduction, add_party_if_needed))
				processed.append(idx)
			continue

		new_entries.append(entry)

	return new_entries, processed


def _ensure_supplier_party_on_gl_entries(doc, gl_entries):
	"""ERPNext requires Supplier on Payable account GL rows; retention/advance paths may omit it."""
	supplier = doc.get("supplier")
	if not supplier:
		return gl_entries

	for entry in gl_entries:
		if entry.get("party_type") and entry.get("party"):
			continue

		account = entry.get("account")
		if not account:
			continue

		account_type = frappe.get_cached_value("Account", account, "account_type")
		if account_type == "Payable":
			entry["party_type"] = "Supplier"
			entry["party"] = supplier

	return gl_entries


def _po_progress_row_applicable(item) -> bool:
	if not item.get("po_detail"):
		return False
	if item.get("item_code") in _PO_PROGRESS_DEDUCTION_ITEMS:
		return False
	return True


def _get_prev_billed_by_po_detail(po_details: list, exclude_pi_name: str) -> dict:
	"""Submitted non-advance PI items summed by po_detail, excluding exclude_pi_name."""
	if not po_details:
		return {}
	ex_name = exclude_pi_name or ""
	placeholders = ", ".join(["%s"] * len(po_details))
	rows = frappe.db.sql(
		f"""
		SELECT pii.po_detail AS po_detail,
			COALESCE(SUM(pii.qty), 0) AS qty,
			COALESCE(SUM(pii.amount), 0) AS amount
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
		WHERE pii.po_detail IN ({placeholders})
			AND pi.docstatus = 1
			AND IFNULL(pi.custom_is_advance, 0) = 0
			AND pi.name != %s
		GROUP BY pii.po_detail
		""",
		tuple(po_details) + (ex_name,),
		as_dict=True,
	)
	return {r.po_detail: r for r in rows}


def set_po_line_progress(doc, persist="memory"):
	"""
	Compute previous / current / accumulated qty & amount per PO line (po_detail).

	persist:
	- memory: set on row objects (saved with draft/submit via standard child update)
	- db: frappe.db.set_value per child row (after submit — final snapshot)
	"""
	if doc.get("custom_is_advance"):
		z = {f: 0 for f in _PO_PROGRESS_FIELDS}
		for row in doc.get("items") or []:
			_set_po_progress_on_row(row, z, persist)
		return

	values_by_row = _compute_po_line_progress_values(doc)
	_apply_progress_map(doc, persist, values_by_row)


def _compute_po_line_progress_values(doc) -> dict:
	"""Return mapping child row name -> dict of six field values."""
	applicable = [r for r in doc.get("items") or [] if _po_progress_row_applicable(r)]
	po_details = list({r.po_detail for r in applicable})
	prev_map = _get_prev_billed_by_po_detail(po_details, doc.name)
	same_doc_prior = defaultdict(lambda: {"qty": 0.0, "amount": 0.0})
	out = {}

	for row in doc.get("items") or []:
		if not row.name:
			continue
		if not _po_progress_row_applicable(row):
			out[row.name] = None
			continue

		pd = row.po_detail
		db_prev = prev_map.get(pd) or {}
		db_qty = flt(db_prev.get("qty"))
		db_amt = flt(db_prev.get("amount"))
		s_prior = same_doc_prior[pd]
		prev_qty = db_qty + flt(s_prior["qty"])
		prev_amt = db_amt + flt(s_prior["amount"])

		cur_qty = flt(row.qty)
		cur_amt = flt(row.amount)

		out[row.name] = {
			"custom_prev_qty": prev_qty,
			"custom_prev_amount": prev_amt,
			"custom_current_qty": cur_qty,
			"custom_current_amount": cur_amt,
			"custom_accumulated_qty": prev_qty + cur_qty,
			"custom_accumulated_amount": prev_amt + cur_amt,
		}

		s_prior["qty"] += cur_qty
		s_prior["amount"] += cur_amt

	return out


def _apply_progress_map(doc, persist: str, values_by_row: dict):
	for row in doc.get("items") or []:
		vals = values_by_row.get(row.name) if row.name else None
		if vals is None:
			z = {f: 0 for f in _PO_PROGRESS_FIELDS}
			_set_po_progress_on_row(row, z, persist)
		else:
			_set_po_progress_on_row(row, vals, persist)


def _set_po_progress_on_row(row, vals: dict, persist: str):
	if persist == "db":
		if not row.name:
			return
		frappe.db.set_value(
			"Purchase Invoice Item",
			row.name,
			vals,
			update_modified=False,
		)
		for k, v in vals.items():
			row.set(k, v)
	else:
		for k, v in vals.items():
			row.set(k, v)


def clear_po_line_progress(doc):
	"""Zero stored PO line progress on all item rows (cancelled voucher)."""
	z = {f: 0 for f in _PO_PROGRESS_FIELDS}
	for row in doc.get("items") or []:
		if not row.name:
			continue
		frappe.db.set_value("Purchase Invoice Item", row.name, z, update_modified=False)


def before_validate(doc, method):
	"""Run before standard validate"""
	scale_fixed_discount(doc)


def validate(doc, method):
	"""Auto-add retention and advance deduction items based on linked Purchase Order percentages"""
	# Always ensure deduction items exist and are purchase-enabled
	_ensure_purchase_deduction_items()

	# If custom liability account is set on a row, use it for posting instead
	# of the regular expense account (no additional GL rows are created).
	_apply_custom_liability_account_override(doc)

	# Auto-fill blank warehouse/expense-account fields before ERPNext validates them
	_set_default_target_warehouse(doc)

	if doc.docstatus != 0:
		return

	if doc.get("custom_is_advance"):
		set_po_line_progress(doc, persist="memory")
		# Assign correct advance account to the PURCHASE-ADVANCE item
		boq_settings = frappe.db.get_value(
			"BOQ Settings",
			doc.company,
			["purchase_advance_account"],
			as_dict=True,
		) or {}
		advance_account = boq_settings.get("purchase_advance_account")
		if advance_account:
			for item in doc.items:
				if item.item_code == "PURCHASE-ADVANCE":
					item.expense_account = advance_account
		return

	if _is_subcontractor_purchase(doc):
		apply_purchase_deductions(doc)

	# Always sweep and enforce correct BOQ Setting accounts for deduction rows (fixes old drafts)
	# Always sweep to ensure deduction rows use the default expense account so the override can neatly pick them up
	default_expense_account = frappe.db.get_value("Company", doc.company, "default_expense_account")

	for item in doc.items:
		if item.item_code in ("RETENTION-DEDUCTION", "ADVANCE-DEDUCTION") and not doc.get("custom_is_advance"):
			# Deduction GL redirect expects these rows on the company default expense account.
			item.custom_liability_account = None
			item.expense_account = default_expense_account
			_populate_pi_deduction_row_fields(doc, item)

	# After deductions (if any) so new rows exist; ERPNext validate already ran (amounts final)
	set_po_line_progress(doc, persist="memory")


def _apply_custom_liability_account_override(doc):
	"""Use item-level custom liability account as posting account when provided."""
	default_liability_account = doc.get("custom_liability_account")

	for item in doc.items:
		if item.item_code in _PO_PROGRESS_DEDUCTION_ITEMS:
			continue

		liability_account = item.get("custom_liability_account")

		# If row-level field is blank, inherit from Purchase Invoice header.
		if not liability_account:
			liability_account = default_liability_account
			if liability_account:
				item.custom_liability_account = liability_account

		if not liability_account:
			continue

		account_company = frappe.db.get_value("Account", liability_account, "company")
		if account_company and account_company != doc.company:
			frappe.throw(
				_("Row {0}: Liability Account {1} must belong to company {2}.").format(
					item.idx or item.name, frappe.bold(liability_account), frappe.bold(doc.company)
				)
			)

		item.expense_account = liability_account


def _set_default_target_warehouse(doc):
	"""
	Auto-fill blank 'expense_account' (or warehouse) on each PI item row.

	For Purchase Invoice, ERPNext does not require a warehouse (it's an accounting doc),
	but some custom setups flag missing expense_account as problematic. This helper
	also mirrors the same warehouse logic as the PR override so the two are in sync.

	Priority:
	  1. Project.site_location  (row-level project → doc-level project)
	  2. BOQ Settings.default_warehouse for the company
	"""
	NO_STOCK_ITEMS = _PO_PROGRESS_DEDUCTION_ITEMS

	boq_default_wh = frappe.db.get_value("BOQ Settings", doc.company, "default_warehouse")
	project_wh_cache = {}

	for row in doc.get("items", []):
		if row.item_code in ("RETENTION-DEDUCTION", "ADVANCE-DEDUCTION"):
			_populate_pi_deduction_row_fields(doc, row)
			continue

		if row.item_code in NO_STOCK_ITEMS:
			continue
		# For PI there is no 'warehouse' field on items (it's a service/accounting doc),
		# but some ERPNext versions track it. Only fill if the attr exists and is empty.
		if not hasattr(row, "warehouse") or row.get("warehouse"):
			continue

		project = row.get("project") or doc.get("project")
		if project:
			if project not in project_wh_cache:
				project_wh_cache[project] = frappe.db.get_value("Project", project, "site_location")
			warehouse = project_wh_cache[project]
		else:
			warehouse = None

		if not warehouse:
			warehouse = boq_default_wh

		if warehouse:
			row.warehouse = warehouse

		# Auto-fill blank custom site fields to resolve mandatory dimension errors
		if not row.get("site") and frappe.get_meta(row.doctype).has_field("site"):
			row.site = "Transit"
		if not row.get("rejected_site") and frappe.get_meta(row.doctype).has_field("rejected_site"):
			row.rejected_site = "Transit"


def _populate_pi_deduction_row_fields(doc, row):
	"""Fill mandatory PI item fields on auto-added retention/advance deduction rows."""
	if row.item_code not in ("RETENTION-DEDUCTION", "ADVANCE-DEDUCTION"):
		return

	conversion_rate = flt(doc.get("conversion_rate") or 1.0)
	qty = flt(row.qty) or 1.0
	rate = flt(row.rate)
	amount = flt(row.amount) if row.get("amount") is not None else rate * qty

	row.qty = qty
	row.rate = rate
	row.amount = amount
	row.uom = row.uom or "Nos"
	row.stock_uom = row.stock_uom or row.uom
	row.conversion_factor = flt(row.conversion_factor) or 1.0
	row.stock_qty = flt(row.stock_qty) or qty * row.conversion_factor
	row.received_qty = flt(row.received_qty) or row.stock_qty
	row.base_rate = rate * conversion_rate
	row.base_amount = amount * conversion_rate

	if not row.get("project"):
		row.project = doc.get("project")

	item_meta = frappe.get_meta(row.doctype)
	if item_meta.has_field("site") and not row.get("site"):
		row.site = "Transit"
	if item_meta.has_field("rejected_site") and not row.get("rejected_site"):
		row.rejected_site = "Transit"


def scale_fixed_discount(doc):
	"""
	Proportionally scale the fixed discount amount if it was auto-mapped 
	from a Purchase Order and this is a partial invoice.
	"""
	if flt(doc.discount_amount) > 0 and not doc.additional_discount_percentage:
		po_name = _get_linked_purchase_order(doc)
		if not po_name:
			return

		po_doc = frappe.get_cached_doc("Purchase Order", po_name)
		
		# If the discount amounts match exactly, it was auto-copied.
		if flt(po_doc.discount_amount) > 0 and flt(doc.discount_amount) == flt(po_doc.discount_amount):
			pi_normal_items_total = sum(
				flt(item.amount) for item in doc.items
				if item.item_code not in _PO_PROGRESS_DEDUCTION_ITEMS
			)

			po_normal_items_total = sum(
				flt(item.amount) for item in po_doc.items
				if item.item_code not in _PO_PROGRESS_DEDUCTION_ITEMS
			)

			if po_normal_items_total > 0:
				ratio = pi_normal_items_total / po_normal_items_total
				doc.discount_amount = flt(po_doc.discount_amount * ratio, doc.precision("discount_amount"))


def on_submit(doc, method):
	"""Persist PO line progress snapshot; update cost tracking for BOQ items from Purchase Invoice"""
	set_po_line_progress(doc, persist="db")
	for item in doc.items:
		if item.get("boq_item"):
			update_boq_item_cost(item)

	# Fix outstanding_amount field:
	# Custom GL entries create multiple Payment Ledger Entries for the same voucher (Net + Retention).
	# ERPNext's standard processing calls update_voucher_outstanding for each PLE.
	# Since only one account should define the PI's outstanding_amount field (the main credit_to),
	# we explicitly re-trigger it here for the main account to ensure it 'wins' over the retention account.
	update_voucher_outstanding(
		doc.doctype, doc.name, doc.credit_to, "Supplier", doc.supplier
	)


def before_cancel(doc, method):
	"""Cancel linked Purchase Advance Payment before Frappe's link check"""
	_cancel_linked_advance_payment(doc)


def on_cancel(doc, method):
	"""Clear PO line progress on cancelled voucher; reverse cost tracking for BOQ items"""
	clear_po_line_progress(doc)
	for item in doc.items:
		if item.get("boq_item"):
			update_boq_item_cost(item)


def update_boq_item_cost(item):
	"""
	Update BOQ Item cost tracking from Purchase Invoice.

	Note: Primary cost tracking is done via Daily Progress Record (DPR).
	This function can be used for additional cost allocation if needed.

	Args:
		item: Purchase Invoice Item with boq_item set
	"""
	# Get BOQ Item
	boq_item = frappe.get_doc("BOQ Item", item.boq_item)

	# Recalculate cost fields
	boq_item.calculate_amounts()
	boq_item.db_update()
	
	# Also update parent Project BOQ / BOQ Bill so totals reflect the new cost
	boq_item.update_parent_totals()

	frappe.logger().info(f"Updated cost tracking for BOQ Item {item.boq_item}")


def apply_purchase_deductions(doc):
	"""
	Auto-add RETENTION-DEDUCTION and ADVANCE-DEDUCTION items based on
	linked Purchase Order's retention/advance percentages.
	"""
	from construction_management.api.purchase_receipt_utils import get_purchase_billable_amounts

	if not doc.project:
		return

	# Find linked Purchase Order from items
	purchase_order = _get_linked_purchase_order(doc)
	if not purchase_order:
		return

	# Read PO percentages
	po_doc = frappe.get_cached_doc("Purchase Order", purchase_order)
	retention_pct = flt(po_doc.get("custom_retention_"))
	advance_pct = flt(po_doc.get("custom_advance_"))

	if retention_pct <= 0 and advance_pct <= 0:
		return

	# Check if deductions already exist on linked Purchase Receipts
	# to avoid double-deducting when PI is created from a PR
	pr_has_retention, pr_has_advance = _check_pr_deductions(doc)

	# Calculate total billable amount (exclude deduction items)
	total_billable, advance_billable = get_purchase_billable_amounts(doc)

	if total_billable <= 0:
		return

	# Ensure deduction items exist and are purchasable
	_ensure_purchase_deduction_items()

	default_expense_account = frappe.db.get_value("Company", doc.company, "default_expense_account")
	default_cost_center = doc.cost_center or frappe.db.get_value("Company", doc.company, "cost_center")

	boq_settings = frappe.db.get_value(
		"BOQ Settings",
		doc.company,
		["purchase_retention_account", "purchase_advance_account", "default_warehouse"],
		as_dict=True
	) or {}
	retention_account = boq_settings.get("purchase_retention_account") or default_expense_account
	advance_account = boq_settings.get("purchase_advance_account") or default_expense_account

	# 1. Add/Update Retention Deduction
	retention_item = "RETENTION-DEDUCTION"
	if retention_pct > 0 and not pr_has_retention:
		retention_amount = flt(total_billable * retention_pct / 100, 2)
		if retention_amount > 0:
			found = False
			for item in doc.items:
				if item.item_code == retention_item:
					item.rate = -retention_amount
					item.amount = -retention_amount
					item.description = f"Retention deduction ({retention_pct}%)"
					_populate_pi_deduction_row_fields(doc, item)
					found = True
					break
			if not found:
				doc.append("items", {
					"item_code": retention_item,
					"item_name": "Retention Deduction",
					"qty": 1,
					"rate": -retention_amount,
					"amount": -retention_amount,
					"description": f"Retention deduction ({retention_pct}%)",
					"project": doc.project,
					"expense_account": default_expense_account,
					"cost_center": default_cost_center,
					"uom": "Nos",
					"conversion_factor": 1.0,
				})
		else:
			# Remove existing if any
			doc.set("items", [item for item in doc.items if item.item_code != retention_item])

	# 2. Add/Update Advance Deduction — capped to remaining un-deducted advance for this PO
	advance_item = "ADVANCE-DEDUCTION"
	if advance_pct > 0 and not pr_has_advance and advance_billable > 0:
		# Total advance given (from advance PIs) for this PO
		total_advance_given = _get_total_advance_given(purchase_order)
		# Total advance already deducted on previous submitted PIs for this PO
		already_deducted = _get_advance_already_deducted(purchase_order, exclude_pi=doc.name)
		remaining_advance = flt(total_advance_given - already_deducted, 2)

		if remaining_advance > 0:
			# Advance deduction for this invoice — proportional to billable amount, capped at remaining
			advance_amount = min(
				flt(advance_billable * advance_pct / 100, 2),
				remaining_advance
			)
			if advance_amount > 0:
				found = False
				for item in doc.items:
					if item.item_code == advance_item:
						item.rate = -advance_amount
						item.amount = -advance_amount
						item.description = f"Advance deduction ({advance_pct}%) — remaining: {remaining_advance}"
						_populate_pi_deduction_row_fields(doc, item)
						found = True
						break
				if not found:
					doc.append("items", {
						"item_code": advance_item,
						"item_name": "Advance Deduction",
						"qty": 1,
						"rate": -advance_amount,
						"amount": -advance_amount,
						"description": f"Advance deduction ({advance_pct}%) — remaining: {remaining_advance}",
						"project": doc.project,
						"expense_account": default_expense_account,
						"cost_center": default_cost_center,
						"uom": "Nos",
						"conversion_factor": 1.0,
					})
			else:
				# Remove existing if any
				doc.set("items", [item for item in doc.items if item.item_code != advance_item])
		else:
			doc.set("items", [item for item in doc.items if item.item_code != advance_item])
	elif advance_pct > 0 and not pr_has_advance:
		doc.set("items", [item for item in doc.items if item.item_code != advance_item])


def _get_linked_purchase_order(doc):
	"""Find the linked Purchase Order from Purchase Invoice items"""
	for item in doc.items:
		if item.get("purchase_order"):
			return item.purchase_order
	return None


def _get_total_advance_given(purchase_order):
	"""
	Return the total advance amount paid to supplier for this PO.
	Sums the grand_total of all submitted advance Purchase Invoices linked to the PO.
	"""
	if not purchase_order:
		return 0.0
	result = frappe.db.sql("""
		SELECT COALESCE(SUM(pi.grand_total), 0)
		FROM `tabPurchase Invoice` pi
		INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
		WHERE pii.purchase_order = %s
		  AND pi.docstatus = 1
		  AND pi.custom_is_advance = 1
	""", purchase_order)
	return flt(result[0][0] if result else 0)


def _get_advance_already_deducted(purchase_order, exclude_pi=None):
	"""
	Return the total ADVANCE-DEDUCTION already applied on submitted, non-advance PIs
	for this PO (excluding the current PI being validated).
	"""
	if not purchase_order:
		return 0.0
	ex_name = exclude_pi or ""
	result = frappe.db.sql("""
		SELECT COALESCE(SUM(ABS(pii.amount)), 0)
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
		WHERE pii.item_code = 'ADVANCE-DEDUCTION'
		  AND pi.docstatus = 1
		  AND IFNULL(pi.custom_is_advance, 0) = 0
		  AND pi.name != %s
		  AND pi.name IN (
		    SELECT DISTINCT parent FROM `tabPurchase Invoice Item`
		    WHERE purchase_order = %s
		  )
	""", (ex_name, purchase_order))
	return flt(result[0][0] if result else 0)


def _is_subcontractor_purchase(doc):
	"""Check if the linked Purchase Order is for a Subcontractor"""
	if doc.get("custom_suppliersubcontractor") == "Subcontractor":
		return True
	po = _get_linked_purchase_order(doc)
	if not po:
		return False
	po_type = frappe.db.get_value("Purchase Order", po, "custom_suppliersubcontractor")
	return po_type == "Subcontractor"


def _check_pr_deductions(doc):
	"""
	Check if linked Purchase Receipts already have retention/advance deduction items.
	Returns (has_retention, has_advance) tuple.
	"""
	has_retention = False
	has_advance = False

	# Collect linked Purchase Receipts from PI items
	purchase_receipts = set()
	for item in doc.items:
		if item.get("purchase_receipt"):
			purchase_receipts.add(item.purchase_receipt)

	if not purchase_receipts:
		return has_retention, has_advance

	# Check if any linked PR has deduction items
	for pr_name in purchase_receipts:
		pr_items = frappe.db.get_all(
			"Purchase Receipt Item",
			filters={"parent": pr_name, "item_code": ["in", ["RETENTION-DEDUCTION", "ADVANCE-DEDUCTION"]]},
			fields=["item_code"]
		)
		for pr_item in pr_items:
			if pr_item.item_code == "RETENTION-DEDUCTION":
				has_retention = True
			if pr_item.item_code == "ADVANCE-DEDUCTION":
				has_advance = True

	return has_retention, has_advance


def _ensure_purchase_deduction_items():
	"""Ensure deduction and advance items exist and are purchase-enabled"""
	for item_code, item_name, description in [
		("RETENTION-DEDUCTION", "Retention Deduction", "Retention amount deducted from purchase invoices"),
		("ADVANCE-DEDUCTION", "Advance Deduction", "Advance payment deducted from purchase invoices"),
		("PURCHASE-ADVANCE", "Purchase Advance", "Advance payment to supplier/subcontractor"),
	]:
		if not frappe.db.exists("Item", item_code):
			item = frappe.new_doc("Item")
			item.item_code = item_code
			item.item_name = item_name
			item.item_group = "Services"
			item.stock_uom = "Nos"
			item.is_stock_item = 0
			item.is_sales_item = 1
			item.is_purchase_item = 1
			item.description = description
			item.insert(ignore_permissions=True)
		else:
			# Ensure existing item is also purchase-enabled
			existing = frappe.get_doc("Item", item_code)
			if not existing.is_purchase_item:
				existing.is_purchase_item = 1
				existing.save(ignore_permissions=True)


def create_purchase_advance_payment(doc):
	"""Automatically create Purchase Advance Payment record from a Paid Advance Purchase Invoice"""
	# Check if already exists to avoid duplication
	if frappe.db.exists(
		"Purchase Advance Payment",
		{"linked_purchase_invoice": doc.name, "docstatus": ["!=", 2]}
	):
		return

	adv = frappe.new_doc("Purchase Advance Payment")
	adv.project = doc.project
	adv.supplier = doc.supplier
	adv.purchase_order = _get_linked_purchase_order(doc)
	# Use grand_total (includes taxes) — this is what was actually paid to the supplier
	adv.amount = doc.grand_total
	adv.linked_purchase_invoice = doc.name
	adv.date = doc.posting_date
	adv.remarks = f"Automatically created from Advance Purchase Invoice {doc.name}"

	adv.flags.ignore_permissions = True
	adv.insert()
	adv.submit()
	frappe.msgprint(_("Purchase Advance Payment {0} created automatically.").format(adv.name))
	frappe.db.commit()


def _cancel_linked_advance_payment(doc):
	"""Cancel and delete linked Purchase Advance Payment if not utilized"""
	advance_payments = frappe.get_all(
		"Purchase Advance Payment",
		filters={"linked_purchase_invoice": doc.name, "docstatus": 1},
		fields=["name", "allocated_amount"]
	)

	for adv in advance_payments:
		if flt(adv.allocated_amount) > 0:
			frappe.throw(
				_("Cannot cancel Purchase Invoice {0} because the linked Purchase Advance Payment {1} "
				  "has been partially or fully utilized (Allocated: {2}). "
				  "Please reverse the advance allocation first.").format(
					doc.name, adv.name, adv.allocated_amount
				)
			)

		# Cancel and delete the advance payment
		adv_doc = frappe.get_doc("Purchase Advance Payment", adv.name)
		adv_doc.flags.ignore_permissions = True
		adv_doc.flags.ignore_links = True
		adv_doc.cancel()
		adv_doc.delete()
