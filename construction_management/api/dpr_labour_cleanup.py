"""Review and cancel Journal Entries posted solely for DPR labour.

Dry run: bench --site SITE execute construction_management.api.dpr_labour_cleanup.run
Apply: bench --site SITE execute construction_management.api.dpr_labour_cleanup.run --kwargs '{"apply": true, "confirm_count": N, "confirm_digest": "DIGEST"}'
"""

import hashlib
import re

import frappe
from frappe import _
from frappe.utils import cint


LABOUR_REMARK = re.compile(r"^Labour costs for DPR (.+)$")


def run(apply: bool = False, confirm_count: int = 0, confirm_digest: str = "", details: bool = False) -> dict:
	"""Cancel only verified, linked DPR labour JEs; never cancel the DPR itself."""
	if apply and frappe.session.user != "Administrator":
		frappe.throw(_("Run the labour cleanup as Administrator."), frappe.PermissionError)
	rows = frappe.get_all("Journal Entry", filters={"docstatus": 1,
		"user_remark": ["like", "Labour costs for DPR %"]},
		fields=["name", "company", "user_remark", "total_debit"], limit_page_length=0)
	eligible, skipped = [], []
	for row in rows:
		match = LABOUR_REMARK.fullmatch(row.user_remark or "")
		dpr_name = match.group(1) if match else ""
		dpr = frappe.db.get_value("Daily Progress Record", dpr_name,
			["name", "project", "journal_entries"], as_dict=True) if dpr_name else None
		company = frappe.db.get_value("Project", dpr.project, "company") if dpr else None
		linked = dpr and row.name in {part.strip() for part in (dpr.journal_entries or "").split(",")}
		if not dpr or not linked or company != row.company:
			skipped.append({"journal_entry": row.name, "dpr": dpr_name,
				"reason": "Missing DPR, journal link, or matching company"})
			continue
		eligible.append({"journal_entry": row.name, "dpr": dpr_name,
			"company": row.company, "amount": row.total_debit})
	digest = hashlib.sha256("\n".join(sorted(row["journal_entry"] for row in eligible)).encode()).hexdigest()
	summary = {"eligible_count": len(eligible), "total_amount": round(sum(row["amount"] for row in eligible), 3),
		"digest": digest, "skipped_count": len(skipped), "skipped": skipped}
	if not apply:
		return {"dry_run": True, **summary,
			"eligible": eligible if details else eligible[:20], "eligible_truncated": not details and len(eligible) > 20}
	if cint(confirm_count) != len(eligible) or confirm_digest != digest:
		frappe.throw(_("The eligible set changed; review a new dry run and confirm its count and digest."))
	for row in eligible:
		je = frappe.get_doc("Journal Entry", row["journal_entry"])
		if je.docstatus != 1 or je.user_remark != f"Labour costs for DPR {row['dpr']}":
			frappe.throw(_("Journal Entry {0} changed during cleanup; no entries were committed.").format(je.name))
		je.cancel()
		je.add_comment("Info", _("Cancelled by DPR labour cost cleanup; DPR {0} remains submitted.").format(row["dpr"]))
	return {"dry_run": False, "cancelled_count": len(eligible), **summary}
