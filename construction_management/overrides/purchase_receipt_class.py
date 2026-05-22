import frappe
import erpnext
from frappe.utils import cint, flt
from erpnext.accounts.general_ledger import make_gl_entries, make_reverse_gl_entries
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import PurchaseReceipt


PURCHASE_DEDUCTION_ITEM_CODES = {"RETENTION-DEDUCTION", "ADVANCE-DEDUCTION"}


class PurchaseReceiptOverride(PurchaseReceipt):
	def before_cancel(self):
		self._ignore_accounting_ledger_links_on_cancel()
		super().before_cancel()

	def on_cancel(self):
		super().on_cancel()
		self._ignore_accounting_ledger_links_on_cancel()

	def make_gl_entries(self, gl_entries=None, from_repost=False, via_landed_cost_voucher=False):
		if self.docstatus == 2:
			make_reverse_gl_entries(voucher_type=self.doctype, voucher_no=self.name)
			return

		if self.docstatus != 1:
			return

		provisional_accounting_for_non_stock_items = cint(
			frappe.get_cached_value(
				"Company", self.company, "enable_provisional_accounting_for_non_stock_items"
			)
		)
		is_asset_pr = any(d.get("is_fixed_asset") for d in self.get("items"))
		need_inventory_map = (self.get_stock_items() or self.get("packed_items")) and (
			cint(erpnext.is_perpetual_inventory_enabled(self.company))
		)

		inventory_account_map = frappe._dict()
		if need_inventory_map:
			inventory_account_map = self.get_inventory_account_map()

		standard_gl_applies = (
			need_inventory_map or provisional_accounting_for_non_stock_items or is_asset_pr
		)
		if not gl_entries:
			gl_entries = (
				self.get_gl_entries(inventory_account_map, via_landed_cost_voucher)
				if standard_gl_applies
				else self._append_extra_accounting_entries([])
			)

		if gl_entries:
			make_gl_entries(gl_entries, from_repost=from_repost)

	def get_gl_entries(self, inventory_account_map=None, via_landed_cost_voucher=False):
		gl_entries = super().get_gl_entries(
			inventory_account_map=inventory_account_map,
			via_landed_cost_voucher=via_landed_cost_voucher,
		)
		gl_entries = self._net_provisional_deduction_entries(gl_entries)
		return self._append_extra_accounting_entries(gl_entries)

	def _ignore_accounting_ledger_links_on_cancel(self):
		"""Ledger rows are non-submittable accounting records; they should not be cancelled as linked docs."""
		existing = tuple(self.get("ignore_linked_doctypes") or ())
		extra = (
			"Payment Ledger Entry",
			"Advance Payment Ledger Entry",
			"Repost Payment Ledger",
			"Repost Payment Ledger Items",
			"Repost Accounting Ledger",
			"Repost Accounting Ledger Items",
			"Unreconcile Payment",
			"Unreconcile Payment Entries",
		)
		self.ignore_linked_doctypes = tuple(dict.fromkeys(existing + extra))

	def _append_extra_accounting_entries(self, gl_entries):
		rows = self.get("custom_extra_accounting_entries") or []
		if not rows:
			return gl_entries

		for row in rows:
			account = row.get("account")
			debit = flt(row.get("debit"))
			credit = flt(row.get("credit"))
			if not account:
				continue
			if debit <= 0 and credit <= 0:
				continue

			account_currency = frappe.get_cached_value("Account", account, "account_currency") or self.company_currency
			account_type = frappe.get_cached_value("Account", account, "account_type")
			party_type = row.get("party_type") if account_type in ("Receivable", "Payable") else None
			party = row.get("party") if party_type else None
			extra_entry = self.get_gl_dict(
				{
					"account": account,
					"debit": debit,
					"credit": credit,
					"cost_center": self.get("cost_center") or self._get_default_extra_entry_cost_center(),
					"project": self.get("project") or self._get_default_extra_entry_project(),
					"party_type": party_type,
					"party": party,
					"remarks": f"Extra entry from {self.doctype} {self.name}",
				},
				account_currency=account_currency,
			)
			gl_entries.append(extra_entry)

		return gl_entries

	def _net_provisional_deduction_entries(self, gl_entries):
		if not gl_entries:
			return gl_entries

		if not cint(
			frappe.get_cached_value(
				"Company", self.company, "enable_provisional_accounting_for_non_stock_items"
			)
		):
			return gl_entries

		deduction_detail_names = {
			row.name
			for row in self.get("items") or []
			if row.item_code in PURCHASE_DEDUCTION_ITEM_CODES
		}
		if not deduction_detail_names:
			return gl_entries

		deduction_entries = [
			entry
			for entry in gl_entries
			if entry.get("voucher_detail_no") in deduction_detail_names
		]
		if not deduction_entries:
			return gl_entries

		normal_entries = [
			entry
			for entry in gl_entries
			if entry.get("voucher_detail_no") not in deduction_detail_names
		]
		netted_deductions = set()

		for deduction_entry in deduction_entries:
			target_field = "credit" if flt(deduction_entry.get("debit")) > 0 else "debit"
			deduction_amount = flt(deduction_entry.get("debit") or deduction_entry.get("credit"))
			if deduction_amount <= 0:
				continue

			candidates = [
				entry
				for entry in normal_entries
				if entry.get("account") == deduction_entry.get("account")
				and entry.get("cost_center") == deduction_entry.get("cost_center")
				and entry.get("project") == deduction_entry.get("project")
				and flt(entry.get(target_field)) > 0
			]
			total_target = sum(flt(entry.get(target_field)) for entry in candidates)
			if total_target <= 0:
				continue

			remaining = deduction_amount
			for idx, entry in enumerate(candidates):
				current = flt(entry.get(target_field))
				reduction = remaining if idx == len(candidates) - 1 else flt(
					deduction_amount * current / total_target
				)
				reduction = min(reduction, current)
				self._reduce_gl_entry_amount(entry, target_field, reduction)
				remaining -= reduction

			if remaining <= 0.0001:
				netted_deductions.add(id(deduction_entry))

		return [
			entry
			for entry in normal_entries + deduction_entries
			if id(entry) not in netted_deductions
			and (flt(entry.get("debit")) or flt(entry.get("credit")))
		]

	def _reduce_gl_entry_amount(self, entry, amount_field, reduction):
		entry[amount_field] = flt(entry.get(amount_field)) - reduction
		for fieldname in self._linked_amount_fields(amount_field):
			if fieldname in entry and flt(entry.get(fieldname)):
				entry[fieldname] = flt(entry.get(fieldname)) - reduction

	def _linked_amount_fields(self, amount_field):
		if amount_field == "debit":
			return (
				"debit_in_account_currency",
				"debit_in_transaction_currency",
				"debit_in_reporting_currency",
			)
		return (
			"credit_in_account_currency",
			"credit_in_transaction_currency",
			"credit_in_reporting_currency",
		)

	def _get_default_extra_entry_cost_center(self):
		for item in self.get("items") or []:
			if item.get("cost_center"):
				return item.cost_center
		return frappe.get_cached_value("Company", self.company, "cost_center")

	def _get_default_extra_entry_project(self):
		for item in self.get("items") or []:
			if item.get("project"):
				return item.project
		return None
