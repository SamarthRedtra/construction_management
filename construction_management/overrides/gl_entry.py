# Copyright (c) 2026, Construction Management
# License: MIT

from erpnext.accounts.doctype.gl_entry.gl_entry import GLEntry
from erpnext.accounts.party import (
	validate_party_frozen_disabled,
	validate_party_gle_currency,
)


class GLEntryOverride(GLEntry):
	def validate_party(self):
		if self._is_pr_extra_accounting_entry():
			validate_party_frozen_disabled(self.company, self.party_type, self.party)
			if self.party_type and self.party:
				validate_party_gle_currency(
					self.party_type, self.party, self.company, self.account_currency
				)
			return

		import frappe
		allow_party = False
		try:
			allow_party = frappe.db.get_single_value("Redtra Custom Setting", "allow_party_on_current_asset")
		except Exception:
			pass

		if allow_party and self.party_type and self.party:
			account_type = frappe.get_cached_value("Account", self.account, "account_type")
			if account_type == "Current Asset":
				validate_party_frozen_disabled(self.company, self.party_type, self.party)
				return

		super().validate_party()

	def _is_pr_extra_accounting_entry(self):
		return self.voucher_type == "Purchase Receipt" and (self.remarks or "").startswith(
			"Extra entry from Purchase Receipt"
		)
