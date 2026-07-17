# Copyright (c) 2026, Construction Management
# License: MIT

"""Company-based Project Number generation.

MRG  → plain integer series (1145, 1146, ...)
SKADA → SKD-{n} series (SKD-50, SKD-51, ...)
"""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import cint


SKADA_PREFIX = "SKD-"
NUMERIC_RE = re.compile(r"^[0-9]+$")
SKADA_RE = re.compile(r"^SKD-([0-9]+)$", re.IGNORECASE)


def is_skada_company(company: str | None) -> bool:
	if not company:
		return False

	name = (company or "").upper()
	if "SKADA" in name:
		return True

	abbr = frappe.db.get_value("Company", company, "abbr") or ""
	return abbr.upper() in {"SC", "SKD", "SKADA"}


@frappe.whitelist()
def get_next_project_number(company: str | None = None) -> str:
	"""Return the next Project Number for the given company."""
	company = company or frappe.defaults.get_user_default("Company")
	if not company:
		frappe.throw(_("Select Company to generate the next Project Number"))

	if is_skada_company(company):
		return _next_skada_number(company)
	return _next_numeric_number(company)


def assign_project_number_if_missing(doc, method=None):
	"""before_insert / validate: auto-fill custom_project_no for new projects."""
	if not doc.is_new():
		return

	if (doc.custom_project_no or "").strip():
		return

	company = doc.company or frappe.defaults.get_user_default("Company")
	if not company:
		frappe.throw(_("Company is required to generate Project Number"))

	doc.company = company
	doc.custom_project_no = get_next_project_number(company)


def _next_numeric_number(company: str) -> str:
	last = frappe.db.sql(
		"""
		SELECT MAX(CAST(custom_project_no AS UNSIGNED))
		FROM `tabProject`
		WHERE company = %s
		  AND custom_project_no REGEXP '^[0-9]+$'
		""",
		company,
	)[0][0]
	candidate = cint(last) + 1 or 1

	while _project_number_taken(str(candidate)):
		candidate += 1
	return str(candidate)


def _next_skada_number(company: str) -> str:
	last = frappe.db.sql(
		"""
		SELECT MAX(CAST(SUBSTRING_INDEX(custom_project_no, '-', -1) AS UNSIGNED))
		FROM `tabProject`
		WHERE company = %s
		  AND custom_project_no REGEXP '^[Ss][Kk][Dd]-[0-9]+$'
		""",
		company,
	)[0][0]
	candidate = cint(last) + 1 or 1

	while _project_number_taken(f"{SKADA_PREFIX}{candidate}"):
		candidate += 1
	return f"{SKADA_PREFIX}{candidate}"


def _project_number_taken(project_no: str) -> bool:
	if frappe.db.exists("Project", project_no):
		return True
	return bool(
		frappe.db.exists("Project", {"custom_project_no": project_no})
	)
