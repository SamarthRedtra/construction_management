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
		super().validate_party()

	def _is_pr_extra_accounting_entry(self):
		return self.voucher_type == "Purchase Receipt" and (self.remarks or "").startswith(
			"Extra entry from Purchase Receipt"
		)
