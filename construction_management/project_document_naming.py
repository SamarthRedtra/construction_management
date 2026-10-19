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

MONTH_NAMES = (
	"January",
	"February",
	"March",
	"April",
	"May",
	"June",
	"July",
	"August",
	"September",
	"October",
	"November",
	"December",
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

	period = get_project_document_period(doc)
	combined_invoice = is_combined_sales_invoice(doc)
	project_no = frappe.db.get_value("Project", doc.project, "custom_project_no")
	if not project_no:
		frappe.throw(
			_("Project {0} needs a Project No before creating {1}.").format(doc.project, doc.doctype)
		)
	# Combined and normal TINVs both include Project No; combined period is MonthYY[-…].
	series_prefix = f"{prefix}/{project_no}/{period}/"

	if doc.doctype == "Sales Invoice" and not combined_invoice:
		_seed_invoice_series(series_prefix, f"SINV/{project_no}/{period}/")
	return f"{series_prefix}{getseries(series_prefix, 1)}"


def _seed_invoice_series(target: str, legacy: str) -> None:
	"""Carry forward the old SINV counter without resetting an existing TINV series."""
	legacy_current = frappe.db.get_value("Series", legacy, "current", order_by="name")
	if legacy_current is None:
		return

	frappe.db.sql(
		"""insert into `tabSeries` (`name`, `current`)
		values (%(target)s, %(legacy_current)s)
		on duplicate key update `current` = greatest(`current`, values(`current`))""",
		{"target": target, "legacy_current": legacy_current},
	)


def get_project_document_period(doc) -> str:
	"""Return the naming period for a project Sales Order or Sales Invoice."""
	if doc.doctype == "Sales Order":
		return format_period(doc.get("transaction_date") or today())

	if doc.doctype == "Sales Invoice":
		combined_sales_orders = get_combined_source_sales_orders(doc)
		if combined_sales_orders:
			return get_combined_sales_order_period(combined_sales_orders)

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
	sales_orders.update(get_combined_source_sales_orders(doc))
	return sorted(sales_orders)


def get_combined_source_sales_orders(doc) -> list[str]:
	"""Return the Sales Orders explicitly selected for a combined Tax Invoice."""
	return sorted(
		{
			sales_order.strip()
			for sales_order in (doc.get("custom_source_sales_orders") or "").split(",")
			if sales_order.strip()
		}
	)


def is_combined_sales_invoice(doc) -> bool:
	"""Identify invoices created through the combined Tax Invoice flow."""
	return doc.doctype == "Sales Invoice" and bool(get_combined_source_sales_orders(doc))


def get_sales_order_dates(sales_orders: list[str]) -> list:
	"""Fetch and validate source Sales Order dates used in invoice naming."""
	orders = frappe.get_all(
		"Sales Order",
		filters={"name": ["in", sales_orders]},
		fields=["name", "transaction_date"],
	)
	if len(orders) != len(sales_orders):
		frappe.throw(_("A linked Sales Order could not be found."))
	return orders


def get_linked_sales_order_period(sales_orders: list[str]) -> str:
	"""Return the common month of linked Sales Orders, rejecting mixed-month invoices."""
	orders = get_sales_order_dates(sales_orders)
	periods = {format_period(order.transaction_date) for order in orders}
	if len(periods) != 1:
		frappe.throw(_("All linked Sales Orders must have the same transaction month."))

	return periods.pop()


def get_combined_sales_order_period(sales_orders: list[str]) -> str:
	"""Return ordered, distinct month labels for a combined Tax Invoice."""
	months = {
		(getdate(order.transaction_date).year, getdate(order.transaction_date).month)
		for order in get_sales_order_dates(sales_orders)
	}
	return "-".join(format_combined_period(year, month) for year, month in sorted(months))


def format_period(value) -> str:
	"""Format a date as the fixed English YYYY-MON naming period."""
	date_value = getdate(value)
	return f"{date_value.year}-{MONTH_ABBREVIATIONS[date_value.month - 1]}"


def format_combined_period(year: int, month: int) -> str:
	"""Format a combined-invoice month as fixed English MonthYY."""
	return f"{MONTH_NAMES[month - 1]}{year % 100:02d}"
