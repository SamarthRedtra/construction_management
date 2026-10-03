# Copyright (c) 2026, Construction Management
# License: MIT

"""Project/month naming for project sales documents."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.naming import getseries
from frappe.utils import getdate, today


PREFIXES = {
	"Sales Order": "PINV",
	"Sales Invoice": "TINV",
}

MONTH_ABBREVIATIONS = (
	"JAN",
	"FEB",
	"MAR",
	"APR",
	"MAY",
	"JUN",
	"JUL",
	"AUG",
	"SEP",
	"OCT",
	"NOV",
	"DEC",
)


def assign_project_document_name(doc) -> bool:
	"""Assign the project/month series name, returning False for non-project documents."""
	name = allocate_project_document_name(doc)
	if not name:
		return False
	doc.name = name
	return True


def allocate_project_document_name(doc) -> str | None:
	"""Allocate and return a project/month name, or None for non-project documents."""
	if not doc.project:
		return None

	prefix = PREFIXES.get(doc.doctype)
	if not prefix:
		return None

	project_no = frappe.db.get_value("Project", doc.project, "custom_project_no")
	if not project_no:
		frappe.throw(_("Project {0} needs a Project No before creating {1}.").format(doc.project, doc.doctype))

	period = get_project_document_period(doc)
	series_prefix = f"{prefix}/{project_no}/{period}/"
	if doc.doctype == "Sales Invoice":
		_seed_invoice_series(series_prefix, f"SINV/{project_no}/{period}/")
	return f"{series_prefix}{getseries(series_prefix, 1)}"


def _seed_invoice_series(target: str, legacy: str) -> None:
	"""Carry forward the old SINV counter without resetting an existing TINV series."""
	frappe.db.sql("""insert into `tabSeries` (`name`, `current`)
		select %(target)s, `current` from `tabSeries` where `name` = %(legacy)s
		on duplicate key update `current` = greatest(`current`, values(`current`))""",
		{"target": target, "legacy": legacy})


def get_project_document_period(doc) -> str:
	"""Return the naming period for a project Sales Order or Sales Invoice."""
	if doc.doctype == "Sales Order":
		return format_period(doc.get("transaction_date") or today())

	if doc.doctype == "Sales Invoice":
		sales_orders = get_linked_sales_orders(doc)
		if sales_orders:
			return get_linked_sales_order_period(sales_orders)
		return format_period(doc.get("posting_date") or today())

	frappe.throw(_("Project naming is not configured for {0}.").format(doc.doctype))


def get_linked_sales_orders(doc) -> list[str]:
	"""Collect Sales Order references from invoice items and the combined-invoice field."""
	sales_orders = {
		item.get("sales_order")
		for item in doc.get("items", [])
		if item.get("sales_order")
	}

	for sales_order in (doc.get("custom_source_sales_orders") or "").split(","):
		if sales_order.strip():
			sales_orders.add(sales_order.strip())

	return sorted(sales_orders)


def get_linked_sales_order_period(sales_orders: list[str]) -> str:
	"""Return the common month of linked Sales Orders, rejecting mixed-month invoices."""
	orders = frappe.get_all(
		"Sales Order",
		filters={"name": ["in", sales_orders]},
		fields=["name", "transaction_date"],
	)
	if len(orders) != len(sales_orders):
		frappe.throw(_("A linked Sales Order could not be found."))

	periods = {format_period(order.transaction_date) for order in orders}
	if len(periods) != 1:
		frappe.throw(_("All linked Sales Orders must have the same transaction month."))

	return periods.pop()


def format_period(value) -> str:
	"""Format a date as the fixed English YYYY-MON naming period."""
	date_value = getdate(value)
	return f"{date_value.year}-{MONTH_ABBREVIATIONS[date_value.month - 1]}"
