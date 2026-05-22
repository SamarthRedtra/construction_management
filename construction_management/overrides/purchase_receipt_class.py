import frappe
from frappe.utils import flt
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import PurchaseReceipt


class PurchaseReceiptOverride(PurchaseReceipt):
	def before_cancel(self):
		self._ignore_accounting_ledger_links_on_cancel()
		super().before_cancel()

	def on_cancel(self):
		super().on_cancel()
		self._ignore_accounting_ledger_links_on_cancel()

	def get_gl_entries(self, inventory_account_map=None, via_landed_cost_voucher=False):
		gl_entries = super().get_gl_entries(
			inventory_account_map=inventory_account_map,
			via_landed_cost_voucher=via_landed_cost_voucher,
		)
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
			extra_entry = self.get_gl_dict(
				{
					"account": account,
					"debit": debit,
					"credit": credit,
					"cost_center": self.get("cost_center"),
					"project": self.get("project"),
					"party_type": row.get("party_type"),
					"party": row.get("party"),
					"remarks": f"Extra entry from {self.doctype} {self.name}",
				},
				account_currency=account_currency,
			)
			gl_entries.append(extra_entry)

		return gl_entries
