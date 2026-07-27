# Copyright (c) 2026, Construction Management
# License: MIT

"""Backfill sales commission accrual Journal Entries for already-recorded invoices."""

import frappe

from construction_management.api.sales_commission_gl import backfill_commission_accrual_jvs
from construction_management.patches.add_sales_commission_gl_fields import (
	execute as ensure_commission_gl_fields,
)


def execute():
	# Ensure SI/PE custom fields exist before linking JVs.
	ensure_commission_gl_fields()

	stats = backfill_commission_accrual_jvs()
	frappe.db.commit()

	msg = (
		f"Commission accrual backfill: created={stats.get('created', 0)}, "
		f"skipped={stats.get('skipped', 0)}, errors={stats.get('errors', 0)}"
	)
	skipped_companies = stats.get("companies_skipped") or []
	if skipped_companies:
		msg += f"; companies missing BOQ accounts={', '.join(skipped_companies)}"

	print(msg)
	frappe.logger("sales_commission_gl").info(msg)
