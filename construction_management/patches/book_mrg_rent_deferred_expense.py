# Copyright (c) 2026, Construction Management
# License: MIT

"""Book missing deferred-expense journals for three MRG rent purchase invoices.

The Deferred Revenue and Expense report was showing a simulated schedule.
Only the original prepaid GL existed. Recognition is booked through yesterday,
using Accounts Settings (days, via journal entry), not through the service end.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, getdate, today

INVOICES = ("MRG-PI-01116", "MRG-PI-01117", "MRG-PI-01128")


def execute() -> None:
	from erpnext.accounts.deferred_revenue import book_deferred_income_or_expense

	cutoff = getdate(add_days(today(), -1))
	frappe.flags.deferred_accounting_error = False
	booked = []

	for name in INVOICES:
		doc = _load_invoice(name, cutoff)
		if not doc:
			continue

		book_deferred_income_or_expense(doc, None, cutoff)
		if frappe.flags.deferred_accounting_error:
			frappe.throw(f"Deferred expense booking failed for {name}")
		booked.append(name)

	if booked:
		frappe.logger("construction_management").info(
			f"Booked deferred expense through {cutoff} for {', '.join(booked)}"
		)


def _load_invoice(name: str, cutoff):
	if not frappe.db.exists("Purchase Invoice", name):
		return None

	doc = frappe.get_doc("Purchase Invoice", name)
	if doc.docstatus != 1:
		return None

	has_open_period = any(
		item.get("enable_deferred_expense")
		and item.service_start_date
		and getdate(item.service_start_date) <= cutoff
		and (not item.service_end_date or getdate(item.service_end_date) >= getdate(item.service_start_date))
		for item in doc.items
	)
	return doc if has_open_period else None
