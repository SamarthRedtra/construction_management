# Copyright (c) 2026, Construction Management
# License: MIT

"""Posting-date stock balances for Stock Entry item rows."""

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.stock.utils import get_stock_balance


@frappe.whitelist(methods=["POST"])
def get_item_balances(
	items: str | list[dict], posting_date: str, posting_time: str
) -> list[dict]:
	"""Return each row's warehouse balance at the selected posting timestamp."""
	if not (
		frappe.has_permission("Stock Entry", "write")
		or frappe.has_permission("Stock Entry", "create")
	):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	if isinstance(items, str):
		items = frappe.parse_json(items)

	balances = []
	for row in items or []:
		item_code = row.get("item_code")
		warehouse = row.get("s_warehouse") or row.get("t_warehouse")
		if not item_code or not warehouse:
			continue
		balances.append(
			{
				"name": row.get("name"),
				"actual_qty": flt(
					get_stock_balance(
						item_code,
						warehouse,
						posting_date=posting_date,
						posting_time=posting_time,
					)
				),
			}
		)
	return balances
