"""Cancel the reviewed DPR-only labour Journal Entries once during migration.

This intentionally stops migration if the live target set differs from the
reviewed dry run. It does not cancel unrelated or unlinked Journal Entries.
"""

import frappe

from construction_management.api.dpr_labour_cleanup import run


EXPECTED_COUNT = 1595
EXPECTED_DIGEST = "0b35ce3958bb82868f42799934879ec3b99900cf3e5cd7831bf187861eee6a0e"
EXPECTED_AMOUNT = 205380.457
EXPECTED_COMPANY = "M R G INSULATION WORKS L.L.C"


def execute():
	preview = run(details=True)
	if preview["eligible_count"] == 0:
		return

	if (
		preview["eligible_count"] != EXPECTED_COUNT
		or preview["digest"] != EXPECTED_DIGEST
		or preview["total_amount"] != EXPECTED_AMOUNT
		or any(row["company"] != EXPECTED_COMPANY for row in preview["eligible"])
	):
		frappe.throw(
			"DPR labour cleanup targets differ from the reviewed dry run. "
			"No Journal Entries were cancelled. Re-run the cleanup preview and review the difference."
		)

	result = run(apply=True, confirm_count=EXPECTED_COUNT, confirm_digest=EXPECTED_DIGEST)
	frappe.logger(__name__).info(
		"Cancelled %s verified DPR labour Journal Entries for %s",
		result["cancelled_count"],
		EXPECTED_COMPANY,
	)
